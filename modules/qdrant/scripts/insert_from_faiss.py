#!/usr/bin/env python3
"""
Insert data from FAISS indices to Qdrant

Sequential insertion from unmerged FAISS files to Qdrant collection.
Designed for HPC cluster environment with Singularity-based Qdrant server.

Usage:
    python insert_from_faiss.py --faiss-dir /path/to/processed \
                                 --collection collection_name \
                                 --qdrant-url http://nodeXXX:6333 \
                                 --batch-size 1000
"""

import os
import sys
import argparse
import pickle
import gc
import time
from glob import glob
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
import psutil
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

def log_with_timestamp(message: str) -> None:
    """Prints a message with timestamp and memory usage."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    log_line = f"[{timestamp}] [MEM: {memory_mb:.1f}MB] {message}"
    print(log_line, flush=True)

def upsert_with_retry(client: QdrantClient, collection_name: str, points: list,
                      max_retries: int = 5, initial_delay: float = 2.0) -> bool:
    """
    Upsert points with exponential backoff retry on WAL errors.

    Args:
        client: Qdrant client
        collection_name: Collection to insert into
        points: List of PointStruct to insert
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (doubles each retry)

    Returns:
        True if successful, False otherwise
    """
    delay = initial_delay

    for attempt in range(max_retries):
        try:
            client.upsert(collection_name=collection_name, points=points)
            return True

        except UnexpectedResponse as e:
            error_msg = str(e)

            # Extract detailed error from response if available
            if hasattr(e, 'content'):
                log_with_timestamp(f"  └─ Response content: {e.content}")

            # Check if it's a WAL-related error
            if "WAL" in error_msg or "segment creator" in error_msg:
                if attempt < max_retries - 1:
                    log_with_timestamp(f"  └─ WAL/segment error (attempt {attempt + 1}/{max_retries}): {error_msg}")
                    log_with_timestamp(f"  └─ Waiting {delay:.1f}s before retry...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                    continue
                else:
                    log_with_timestamp(f"  └─ FAILED after {max_retries} attempts")
                    log_with_timestamp(f"  └─ ERROR: {error_msg}")
                    log_with_timestamp(f"  └─ HINT: Qdrant server may need restart or storage cleanup")
                    return False
            else:
                # Non-WAL error, don't retry
                log_with_timestamp(f"  └─ Non-recoverable error: {error_msg}")
                return False

        except Exception as e:
            log_with_timestamp(f"  └─ ERROR: {type(e).__name__}: {e}")
            return False

    return False

def create_collection_if_needed(client: QdrantClient, collection_name: str,
                                 vector_size: int = 768) -> None:
    """Create Qdrant collection if it doesn't exist."""
    try:
        client.get_collection(collection_name)
        log_with_timestamp(f"Collection '{collection_name}' already exists")
    except Exception:
        log_with_timestamp(f"Creating collection '{collection_name}'...")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            ),
            # Optimize for large datasets with better WAL handling
            hnsw_config=models.HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10000
            ),
            optimizers_config=models.OptimizersConfigDiff(
                deleted_threshold=0.2,
                vacuum_min_vector_number=1000,
                default_segment_number=0,
                max_segment_size=2_000_000,  # 2M vectors per segment (reduced for better WAL stability)
                memmap_threshold=500_000,     # Lower threshold for memory mapping
                indexing_threshold=1_000_000, # Lower threshold for indexing
                flush_interval_sec=30         # Flush WAL more frequently (every 30 seconds)
            ),
            # Explicitly set WAL config for NFS environments
            wal_config=models.WalConfigDiff(
                wal_capacity_mb=256,          # Limit WAL size to 256MB
                wal_segments_ahead=2          # Keep fewer WAL segments ahead
            )
        )
        log_with_timestamp(f"Collection '{collection_name}' created")

def find_faiss_files(faiss_dir: str) -> list:
    """Find all FAISS index files in directory."""
    pattern = os.path.join(faiss_dir, "**", "*.index")
    files = sorted(glob(pattern, recursive=True))
    return files

def load_faiss_and_metadata(index_path: str) -> tuple:
    """Load FAISS index and corresponding metadata.

    Expects consistent naming: file.index + file.json (dict format with string keys)
    Falls back to file_metadata.pkl for legacy data.
    """
    index = faiss.read_index(index_path)

    # Try .json first (standard format for both PubMed and Clinical Trials)
    metadata_path_json = index_path.replace('.index', '.json')
    metadata_path_pkl = index_path.replace('.index', '_metadata.pkl')

    if os.path.exists(metadata_path_json):
        import json
        with open(metadata_path_json, 'r') as f:
            metadata = json.load(f)
    elif os.path.exists(metadata_path_pkl):
        with open(metadata_path_pkl, 'rb') as f:
            metadata = pickle.load(f)
    else:
        raise FileNotFoundError(f"Metadata not found: tried {metadata_path_json} and {metadata_path_pkl}")

    return index, metadata

def insert_from_faiss(faiss_dir: str, collection_name: str, qdrant_url: str,
                      batch_size: int = 1000, start_id: int = 0,
                      vector_size: int = 768) -> int:
    """
    Insert data from FAISS files to Qdrant

    Args:
        faiss_dir: Directory containing *.index and *.json metadata files (or legacy *_metadata.pkl)
        collection_name: Qdrant collection name
        qdrant_url: Qdrant server URL
        batch_size: Batch size for insertion
        start_id: Starting point ID (for resuming)
        vector_size: Vector dimension

    Returns:
        Total number of vectors inserted
    """
    log_with_timestamp("="*80)
    log_with_timestamp("FAISS to Qdrant Sequential Insertion")
    log_with_timestamp("="*80)
    log_with_timestamp(f"FAISS directory: {faiss_dir}")
    log_with_timestamp(f"Collection: {collection_name}")
    log_with_timestamp(f"Qdrant URL: {qdrant_url}")
    log_with_timestamp(f"Batch size: {batch_size}")
    log_with_timestamp(f"Starting point ID: {start_id}")
    log_with_timestamp("")

    # Initialize Qdrant client
    log_with_timestamp("Connecting to Qdrant...")
    try:
        # Increase timeout to 300s (5 minutes) for slow NFS writes
        client = QdrantClient(url=qdrant_url, timeout=300)
        # Test connection
        collections = client.get_collections()
        log_with_timestamp(f"Connected. Existing collections: {len(collections.collections)}")
        log_with_timestamp(f"Client timeout set to 300 seconds")
    except Exception as e:
        log_with_timestamp(f"ERROR: Failed to connect to Qdrant at {qdrant_url}")
        log_with_timestamp(f"Error: {e}")
        raise

    # Create collection if needed
    create_collection_if_needed(client, collection_name, vector_size)

    # Find all FAISS files
    index_files = find_faiss_files(faiss_dir)

    if not index_files:
        log_with_timestamp(f"WARNING: No FAISS index files found in {faiss_dir}")
        return 0

    log_with_timestamp(f"Found {len(index_files)} FAISS files to process")
    log_with_timestamp("")

    global_point_id = start_id
    total_inserted = 0
    batch = []

    # Process each FAISS file sequentially
    for file_idx, index_path in enumerate(index_files, 1):
        log_with_timestamp(f"[{file_idx}/{len(index_files)}] {os.path.basename(index_path)}")

        try:
            # Load FAISS index and metadata
            index, metadata = load_faiss_and_metadata(index_path)
            n_vectors = index.ntotal

            log_with_timestamp(f"  └─ Vectors: {n_vectors:,}")

            if n_vectors == 0:
                log_with_timestamp(f"  └─ Skipping (empty)")
                continue

            # Extract vectors
            vectors = np.zeros((n_vectors, vector_size), dtype=np.float32)
            for i in range(n_vectors):
                vectors[i] = index.reconstruct(i)

            # Create points
            for i in range(n_vectors):
                meta_key = str(i)
                if meta_key not in metadata:
                    log_with_timestamp(f"  └─ WARNING: Missing metadata for index {i}")
                    continue

                meta = metadata[meta_key]

                # Create point with flexible payload
                point = PointStruct(
                    id=global_point_id,
                    vector=vectors[i].tolist(),
                    payload={
                        **meta,  # Include all metadata fields
                        'source': meta.get('source', collection_name.split('_')[0]),
                        'date_processed': datetime.now().isoformat()
                    }
                )
                batch.append(point)
                global_point_id += 1
                total_inserted += 1

                # Batch insert
                if len(batch) >= batch_size:
                    success = upsert_with_retry(client, collection_name, batch)
                    if success:
                        log_with_timestamp(f"  └─ Inserted batch ({total_inserted:,} total)")
                        batch = []
                    else:
                        log_with_timestamp(f"  └─ Batch insert failed, stopping file processing")
                        break

            # Clear memory
            del index, vectors, metadata
            gc.collect()

        except Exception as e:
            log_with_timestamp(f"  └─ ERROR: {e}")
            log_with_timestamp(f"  └─ Continuing with next file...")
            continue

    # Insert final batch
    if batch:
        success = upsert_with_retry(client, collection_name, batch)
        if success:
            log_with_timestamp(f"Inserted final batch")
        else:
            log_with_timestamp(f"WARNING: Final batch insertion failed")

    log_with_timestamp("")
    log_with_timestamp("="*80)
    log_with_timestamp(f"Insertion complete!")
    log_with_timestamp(f"Total vectors inserted: {total_inserted:,}")
    log_with_timestamp(f"Final point ID: {global_point_id}")
    log_with_timestamp("="*80)

    # Verify collection
    try:
        info = client.get_collection(collection_name)
        log_with_timestamp(f"Collection verification:")
        log_with_timestamp(f"  Points count: {info.points_count:,}")
        log_with_timestamp(f"  Status: {info.status}")
    except Exception as e:
        log_with_timestamp(f"WARNING: Could not verify collection: {e}")

    return total_inserted

def main():
    parser = argparse.ArgumentParser(
        description="Insert FAISS indices to Qdrant sequentially"
    )
    parser.add_argument(
        '--faiss-dir',
        required=True,
        help='Directory containing FAISS index files'
    )
    parser.add_argument(
        '--collection',
        required=True,
        help='Qdrant collection name'
    )
    parser.add_argument(
        '--qdrant-url',
        required=True,
        help='Qdrant server URL (e.g., http://node042:6333)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=500,
        help='Batch size for insertion (default: 500, reduce to 100-250 for NFS/slow storage)'
    )
    parser.add_argument(
        '--start-id',
        type=int,
        default=0,
        help='Starting point ID for resuming (default: 0)'
    )
    parser.add_argument(
        '--vector-size',
        type=int,
        default=768,
        help='Vector dimension (default: 768)'
    )

    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.faiss_dir):
        log_with_timestamp(f"ERROR: FAISS directory not found: {args.faiss_dir}")
        sys.exit(1)

    # Run insertion
    try:
        insert_from_faiss(
            faiss_dir=args.faiss_dir,
            collection_name=args.collection,
            qdrant_url=args.qdrant_url,
            batch_size=args.batch_size,
            start_id=args.start_id,
            vector_size=args.vector_size
        )
    except KeyboardInterrupt:
        log_with_timestamp("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        log_with_timestamp(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

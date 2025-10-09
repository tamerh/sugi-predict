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
from glob import glob
from datetime import datetime
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
import psutil
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from qdrant_client.http import models

# Logging setup
# Default to current directory, but can be overridden
LOG_DIR = Path(os.environ.get("BIOYODA_LOG_DIR", "./logs/qdrant"))
_log_file: Optional[object] = None

def init_logging(log_dir: Path = LOG_DIR) -> None:
    """Initialize logging to file."""
    global _log_file
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"insert_{timestamp}.log"
    _log_file = open(log_path, 'w', buffering=1)  # Line buffered
    log_with_timestamp(f"Logging to: {log_path}")

def log_with_timestamp(message: str) -> None:
    """Prints a message with timestamp and memory usage."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    log_line = f"[{timestamp}] [MEM: {memory_mb:.1f}MB] {message}"

    print(log_line)

    if _log_file is not None:
        _log_file.write(log_line + '\n')
        _log_file.flush()

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
            # Optimize for large datasets
            hnsw_config=models.HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10000
            ),
            optimizers_config=models.OptimizersConfigDiff(
                deleted_threshold=0.2,
                vacuum_min_vector_number=1000,
                default_segment_number=0,
                max_segment_size=5_000_000,  # 5M vectors per segment
                memmap_threshold=1_000_000,
                indexing_threshold=2_000_000
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
                    client.upsert(collection_name=collection_name, points=batch)
                    log_with_timestamp(f"  └─ Inserted batch ({total_inserted:,} total)")
                    batch = []

            # Clear memory
            del index, vectors, metadata
            gc.collect()

        except Exception as e:
            log_with_timestamp(f"  └─ ERROR: {e}")
            log_with_timestamp(f"  └─ Continuing with next file...")
            continue

    # Insert final batch
    if batch:
        client.upsert(collection_name=collection_name, points=batch)
        log_with_timestamp(f"Inserted final batch")

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
        default=1000,
        help='Batch size for insertion (default: 1000)'
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

    # Initialize logging
    init_logging()

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
    finally:
        if _log_file:
            _log_file.close()

if __name__ == "__main__":
    main()

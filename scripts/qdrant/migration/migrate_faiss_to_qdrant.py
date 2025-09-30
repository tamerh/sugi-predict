#!/usr/bin/env python3
"""
FAISS to Qdrant Migration Script for BioYoda

Migrates vectors and metadata from FAISS index files to Qdrant database.
Designed for HPC cluster environment with memory optimization.
"""

import os
import json
import faiss
import numpy as np
import argparse
import psutil
from datetime import datetime
from typing import List, Dict, Any, Iterator
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from qdrant_client.http import models

# Configuration
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_BATCH_SIZE = 1000
DEFAULT_COLLECTION_NAME = "pubmed_abstracts"

def log_with_timestamp(message: str) -> None:
    """Prints a message with a prepended timestamp and memory usage."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    print(f"[{timestamp}] [MEM: {memory_mb:.1f}MB] {message}")

def get_memory_usage() -> tuple:
    """Returns current memory usage in MB (used, available, percentage)."""
    memory = psutil.virtual_memory()
    return (
        memory.used / 1024 / 1024,
        memory.available / 1024 / 1024,
        memory.percent
    )

class FaissToQdrantMigrator:
    """Migrates FAISS indices and metadata to Qdrant database."""

    def __init__(self, qdrant_url: str = DEFAULT_QDRANT_URL):
        """Initialize the migrator with Qdrant connection."""
        self.qdrant_url = qdrant_url
        self.client = None
        log_with_timestamp(f"Initializing migrator for Qdrant at {qdrant_url}")

    def connect_to_qdrant(self) -> None:
        """Establish connection to Qdrant database."""
        try:
            self.client = QdrantClient(url=self.qdrant_url)
            # Test connection
            collections = self.client.get_collections()
            log_with_timestamp(f"Connected to Qdrant. Existing collections: {len(collections.collections)}")
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to connect to Qdrant: {e}")
            raise

    def create_collection(self, collection_name: str, vector_size: int) -> None:
        """Create a new collection in Qdrant."""
        log_with_timestamp(f"Creating collection '{collection_name}' with vector size {vector_size}")

        try:
            self.client.create_collection(
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
                # Set optimizers for better performance
                optimizers_config=models.OptimizersConfigDiff(
                    deleted_threshold=0.2,
                    vacuum_min_vector_number=1000,
                    default_segment_number=0,
                    max_segment_size=5242880,  # 5GB
                    memmap_threshold=1048576,  # 1GB
                    indexing_threshold=2097152  # 2GB
                )
            )
            log_with_timestamp(f"Collection '{collection_name}' created successfully")
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to create collection: {e}")
            raise

    def load_faiss_data(self, index_path: str, metadata_path: str) -> tuple:
        """Load FAISS index and metadata."""
        log_with_timestamp(f"Loading FAISS index: {index_path}")
        faiss_index = faiss.read_index(index_path)
        log_with_timestamp(f"FAISS index loaded: {faiss_index.ntotal} vectors, {faiss_index.d} dimensions")

        log_with_timestamp(f"Loading metadata: {metadata_path}")
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        log_with_timestamp(f"Metadata loaded: {len(metadata)} entries")

        return faiss_index, metadata

    def extract_vectors_batch(self, faiss_index: faiss.Index, start_idx: int, batch_size: int) -> np.ndarray:
        """Extract a batch of vectors from FAISS index."""
        end_idx = min(start_idx + batch_size, faiss_index.ntotal)
        actual_batch_size = end_idx - start_idx

        vectors = np.zeros((actual_batch_size, faiss_index.d), dtype=np.float32)
        for i in range(actual_batch_size):
            vectors[i] = faiss_index.reconstruct(start_idx + i)

        return vectors

    def prepare_points_batch(self, vectors: np.ndarray, metadata: Dict[str, Any],
                           start_idx: int) -> List[PointStruct]:
        """Prepare a batch of points for Qdrant upload."""
        points = []

        for i, vector in enumerate(vectors):
            point_id = start_idx + i
            metadata_key = str(point_id)

            # Get metadata for this point
            if metadata_key in metadata:
                point_metadata = metadata[metadata_key]

                # Create payload with searchable fields
                payload = {
                    "pmid": point_metadata.get("pmid", ""),
                    "chunk_text": point_metadata.get("chunk_text", ""),
                    "source_file": point_metadata.get("source_file", ""),
                    "vector_id": point_id
                }

                # Parse title and abstract if available
                chunk_text = point_metadata.get("chunk_text", "")
                if chunk_text.startswith("Title: "):
                    parts = chunk_text.split("\nAbstract: ", 1)
                    payload["title"] = parts[0].replace("Title: ", "")
                    payload["abstract"] = parts[1] if len(parts) > 1 else ""

                point = PointStruct(
                    id=point_id,
                    vector=vector.tolist(),
                    payload=payload
                )
                points.append(point)
            else:
                log_with_timestamp(f"WARNING: No metadata found for vector {point_id}")

        return points

    def migrate_data(self, index_path: str, metadata_path: str,
                    collection_name: str, batch_size: int = DEFAULT_BATCH_SIZE,
                    resume: bool = False, start_batch: int = 0) -> None:
        """Main migration function."""
        log_with_timestamp("=== Starting FAISS to Qdrant Migration ===")

        # Load data
        faiss_index, metadata = self.load_faiss_data(index_path, metadata_path)

        # Handle resume logic
        if resume or start_batch > 0:
            try:
                collection_info = self.client.get_collection(collection_name)
                current_points = collection_info.points_count
                log_with_timestamp(f"Collection exists with {current_points} points")

                if resume:
                    # Auto-calculate start batch from current points
                    start_batch = current_points // batch_size
                    log_with_timestamp(f"Auto-resume: Starting from batch {start_batch} (point {current_points})")
                else:
                    log_with_timestamp(f"Manual resume: Starting from batch {start_batch}")
            except Exception as e:
                log_with_timestamp(f"Collection doesn't exist or error checking: {e}")
                # Create collection if it doesn't exist
                self.create_collection(collection_name, faiss_index.d)
                start_batch = 0
        else:
            # Create collection for fresh start
            self.create_collection(collection_name, faiss_index.d)

        # Migration loop
        total_vectors = faiss_index.ntotal
        num_batches = (total_vectors + batch_size - 1) // batch_size

        log_with_timestamp(f"Starting migration of {total_vectors} vectors in {num_batches} batches")
        log_with_timestamp(f"Starting from batch {start_batch} (skipping {start_batch * batch_size} vectors)")

        for batch_num in range(start_batch, num_batches):
            start_idx = batch_num * batch_size
            log_with_timestamp(f"Processing batch {batch_num + 1}/{num_batches} (vectors {start_idx} to {start_idx + batch_size})")

            # Extract vectors
            vectors = self.extract_vectors_batch(faiss_index, start_idx, batch_size)

            # Prepare points
            points = self.prepare_points_batch(vectors, metadata, start_idx)

            # Upload to Qdrant
            if points:
                try:
                    response = self.client.upsert(
                        collection_name=collection_name,
                        points=points
                    )

                    # Verify the response
                    if hasattr(response, 'status') and response.status != 'ok':
                        log_with_timestamp(f"WARNING: Batch {batch_num + 1} upload status: {response.status}")

                    log_with_timestamp(f"Uploaded batch {batch_num + 1}: {len(points)} points")

                    # Periodic verification - check actual point count every 50 batches
                    if (batch_num + 1) % 50 == 0:
                        try:
                            collection_info = self.client.get_collection(collection_name)
                            expected_points = (batch_num + 1) * batch_size
                            actual_points = collection_info.points_count
                            if actual_points != expected_points:
                                log_with_timestamp(f"WARNING: Point count mismatch - Expected: {expected_points}, Actual: {actual_points}")
                            else:
                                log_with_timestamp(f"✓ Point count verified: {actual_points} points")
                        except Exception as ve:
                            log_with_timestamp(f"Could not verify point count: {ve}")

                except Exception as e:
                    log_with_timestamp(f"ERROR uploading batch {batch_num + 1}: {e}")

                    # Try to get more details about the error
                    try:
                        collection_info = self.client.get_collection(collection_name)
                        log_with_timestamp(f"Current collection state: {collection_info.points_count} points")
                    except:
                        log_with_timestamp("Could not retrieve collection state")

                    raise

            # Memory cleanup and reporting
            del vectors, points
            if (batch_num + 1) % 10 == 0:
                used_mb, avail_mb, percent = get_memory_usage()
                log_with_timestamp(f"Progress: {batch_num + 1}/{num_batches} batches. Memory: {used_mb:.1f}MB used ({percent:.1f}%)")

        # Final verification
        collection_info = self.client.get_collection(collection_name)
        log_with_timestamp(f"Migration completed! Collection '{collection_name}' now has {collection_info.points_count} points")

        log_with_timestamp("=== Migration Complete ===")

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Migrate FAISS index and metadata to Qdrant database",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--index", "-i", required=True,
        help="Path to FAISS index file"
    )
    parser.add_argument(
        "--metadata", "-m", required=True,
        help="Path to metadata JSON file"
    )
    parser.add_argument(
        "--collection", "-c", default=DEFAULT_COLLECTION_NAME,
        help=f"Qdrant collection name (default: {DEFAULT_COLLECTION_NAME})"
    )
    parser.add_argument(
        "--qdrant-url", default=DEFAULT_QDRANT_URL,
        help=f"Qdrant server URL (default: {DEFAULT_QDRANT_URL})"
    )
    parser.add_argument(
        "--batch-size", "-b", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for upload (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--recreate", action="store_true",
        help="Recreate collection if it exists"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume migration from where it left off"
    )
    parser.add_argument(
        "--start-batch", type=int, default=0,
        help="Start migration from specific batch number (for manual resume)"
    )

    args = parser.parse_args()

    # Validate input files
    if not os.path.exists(args.index):
        log_with_timestamp(f"ERROR: Index file not found: {args.index}")
        return 1

    if not os.path.exists(args.metadata):
        log_with_timestamp(f"ERROR: Metadata file not found: {args.metadata}")
        return 1

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Initialize migrator
        migrator = FaissToQdrantMigrator(args.qdrant_url)
        migrator.connect_to_qdrant()

        # Handle existing collection
        if args.recreate:
            try:
                migrator.client.delete_collection(args.collection)
                log_with_timestamp(f"Deleted existing collection '{args.collection}'")
            except Exception:
                pass  # Collection might not exist

        # Start migration
        migrator.migrate_data(
            args.index,
            args.metadata,
            args.collection,
            args.batch_size,
            args.resume,
            args.start_batch
        )

        return 0

    except KeyboardInterrupt:
        log_with_timestamp("Migration interrupted by user")
        return 1
    except Exception as e:
        log_with_timestamp(f"ERROR during migration: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
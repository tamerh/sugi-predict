#!/usr/bin/env python3
"""
Clinical Trials Merge Script for BioYoda Pipeline

Merges multiple chunked FAISS indices into a single master index.
Similar to PubMed's merge0.py but adapted for clinical trials.
"""

import os
import json
import faiss
import numpy as np
import psutil
import argparse
from datetime import datetime
from pathlib import Path


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


def merge_trial_chunks(processed_dir: str, output_index: str, output_metadata: str, vector_dim: int) -> bool:
    """
    Merge all chunked FAISS indices into a single master index.

    Args:
        processed_dir: Directory containing chunk indices
        output_index: Path to output master index
        output_metadata: Path to output master metadata
        vector_dim: Vector dimension

    Returns:
        True if successful, False otherwise
    """
    log_with_timestamp("=== Starting Clinical Trials Merge Process ===")

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    # Create output directories
    os.makedirs(os.path.dirname(output_index), exist_ok=True)
    os.makedirs(os.path.dirname(output_metadata), exist_ok=True)

    # 1. Discover all chunk index files
    log_with_timestamp(f"Scanning for chunk files in: {processed_dir}")

    index_files = []
    metadata_files = []

    for root, _, files in os.walk(processed_dir):
        for file in files:
            if file.startswith('trials_chunk_') and file.endswith('.index'):
                index_path = os.path.join(root, file)
                # Corresponding metadata file (with _metadata.json suffix)
                metadata_path = index_path.replace('.index', '_metadata.json')

                if os.path.exists(metadata_path):
                    index_files.append(index_path)
                    metadata_files.append(metadata_path)
                else:
                    log_with_timestamp(f"WARNING: Missing metadata for {file}")

    # Sort by chunk number
    index_files.sort()
    metadata_files.sort()

    if not index_files:
        log_with_timestamp("ERROR: No chunk files found to merge")
        return False

    log_with_timestamp(f"Found {len(index_files)} chunk pairs to merge")

    # 2. Initialize master index and metadata
    master_index = faiss.IndexFlatL2(vector_dim)
    master_metadata = {}
    master_vector_count = 0

    log_with_timestamp(f"Initialized master index with dimension {vector_dim}")

    # 3. Iterate and merge chunks
    for i, (index_path, metadata_path) in enumerate(zip(index_files, metadata_files)):
        chunk_name = os.path.basename(index_path)
        log_with_timestamp(f"Merging chunk {i+1}/{len(index_files)}: {chunk_name}")

        try:
            # Load chunk index
            chunk_index = faiss.read_index(index_path)
            num_vectors = chunk_index.ntotal
            log_with_timestamp(f"  Loaded {num_vectors} vectors from {chunk_name}")

            # Add vectors to master index
            if num_vectors > 0:
                vectors = chunk_index.reconstruct_n(0, num_vectors)
                master_index.add(vectors)

            # Load and merge metadata
            with open(metadata_path, 'r') as f:
                chunk_metadata = json.load(f)

            # Re-key metadata with sequential IDs
            for local_id in sorted(chunk_metadata.keys(), key=int):
                master_metadata[str(master_vector_count)] = chunk_metadata[local_id]
                master_vector_count += 1

            log_with_timestamp(f"  Chunk merged. Total vectors: {master_index.ntotal}, metadata entries: {len(master_metadata)}")

            # Memory usage report every 5 chunks
            if (i + 1) % 5 == 0:
                used_mb, avail_mb, percent = get_memory_usage()
                log_with_timestamp(f"  Progress: {i+1}/{len(index_files)} chunks merged. Memory: {used_mb:.1f}MB used ({percent:.1f}%)")

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to merge chunk {chunk_name}: {e}")
            return False

    # Verify counts match
    if master_index.ntotal != len(master_metadata):
        log_with_timestamp(f"ERROR: Count mismatch! Index: {master_index.ntotal}, Metadata: {len(master_metadata)}")
        return False

    log_with_timestamp(f"All chunks merged successfully. Total vectors: {master_index.ntotal}")

    # 4. Save master index
    log_with_timestamp(f"Saving master index to {output_index}")
    try:
        faiss.write_index(master_index, output_index)
        index_size_mb = os.path.getsize(output_index) / 1024 / 1024
        log_with_timestamp(f"Master index saved: {index_size_mb:.1f}MB")
    except Exception as e:
        log_with_timestamp(f"ERROR: Failed to save master index: {e}")
        return False

    # 5. Save master metadata
    log_with_timestamp(f"Saving master metadata to {output_metadata}")
    try:
        with open(output_metadata, 'w') as f:
            json.dump(master_metadata, f, indent=2, default=str, ensure_ascii=False)

        metadata_size_mb = os.path.getsize(output_metadata) / 1024 / 1024
        log_with_timestamp(f"Master metadata saved: {metadata_size_mb:.1f}MB")
    except Exception as e:
        log_with_timestamp(f"ERROR: Failed to save master metadata: {e}")
        return False

    # Final summary
    log_with_timestamp("=== Merge Complete ===")
    log_with_timestamp(f"Total vectors: {master_index.ntotal}")
    log_with_timestamp(f"Total metadata entries: {len(master_metadata)}")
    log_with_timestamp(f"Master index: {output_index}")
    log_with_timestamp(f"Master metadata: {output_metadata}")

    return True


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Merge chunked clinical trials FAISS indices into a single master index"
    )
    parser.add_argument(
        "--processed-dir", required=True,
        help="Directory containing chunk index files"
    )
    parser.add_argument(
        "--output-index", required=True,
        help="Output path for master FAISS index"
    )
    parser.add_argument(
        "--output-metadata", required=True,
        help="Output path for master metadata JSON"
    )
    parser.add_argument(
        "--vector-dim", type=int, default=768,
        help="Vector dimension (default: 768)"
    )

    args = parser.parse_args()

    try:
        success = merge_trial_chunks(
            args.processed_dir,
            args.output_index,
            args.output_metadata,
            args.vector_dim
        )

        return 0 if success else 1

    except KeyboardInterrupt:
        log_with_timestamp("Merge interrupted by user")
        return 1
    except Exception as e:
        log_with_timestamp(f"ERROR: Unexpected error during merge: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

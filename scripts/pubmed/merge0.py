import os
import json
import faiss
import numpy as np
import psutil
from datetime import datetime

# --- Configuration ---
from config_loader import get_config

# --- Configuration from .env ---
config = get_config()
BASE_PROCESSED_DIR = str(config.get_path('PROCESSED_DIR'))

# Check if MODEL_FINAL_DIR is set (for model-specific directory structure)
FINAL_OUTPUT_DIR = os.environ.get('MODEL_FINAL_DIR', str(config.get_path('FINAL_DIR')))

MASTER_INDEX_PATH = os.path.join(FINAL_OUTPUT_DIR, 'master_pubmed.index')
MASTER_METADATA_PATH = os.path.join(FINAL_OUTPUT_DIR, 'master_metadata.json')
VECTOR_DIMENSION = config.get_int('VECTOR_DIMENSION', 384)

# --- Helper Functions ---
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

# --- Main Merging Logic ---
def merge_all_parts():
    log_with_timestamp("--- Starting Merge Process ---")
    os.makedirs(FINAL_OUTPUT_DIR, exist_ok=True)

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    # 1. Discover all the individual file parts
    index_files = []
    metadata_files = []
    for root, _, files in os.walk(BASE_PROCESSED_DIR):
        for file in files:
            if file.endswith('.index'):
                index_files.append(os.path.join(root, file))
            elif file.endswith('.json'):
                metadata_files.append(os.path.join(root, file))
    
    index_files.sort()
    metadata_files.sort()

    if not index_files or len(index_files) != len(metadata_files):
        log_with_timestamp("Error: Mismatch in index and metadata file counts, or no files found.")
        return

    log_with_timestamp(f"Found {len(index_files)} index/metadata pairs to merge.")

    # 2. Initialize master index and metadata
    master_index = faiss.IndexFlatL2(VECTOR_DIMENSION)
    master_metadata = {}
    master_vector_count = 0

    log_with_timestamp(f"Initialized master index with dimension {VECTOR_DIMENSION}")

    # 3. Iterate and merge
    for i in range(len(index_files)):
        index_path = index_files[i]
        metadata_path = metadata_files[i]
        
        log_with_timestamp(f"Merging part {i+1}/{len(index_files)}: {os.path.basename(index_path)}")

        # Merge FAISS index
        partial_index = faiss.read_index(index_path)
        log_with_timestamp(f"  Loaded {partial_index.ntotal} vectors from {os.path.basename(index_path)}")
        master_index.add(partial_index.reconstruct_n(0, partial_index.ntotal))

        # Merge metadata, re-keying the IDs to be sequential
        with open(metadata_path, 'r') as f:
            partial_metadata = json.load(f)

        for local_id in sorted(partial_metadata.keys(), key=int):
            master_metadata[master_vector_count] = partial_metadata[local_id]
            master_vector_count += 1

        log_with_timestamp(f"  Part {i+1} merged. Total vectors: {master_index.ntotal}")

        # Memory usage report every 100 files
        if (i + 1) % 100 == 0:
            used_mb, avail_mb, percent = get_memory_usage()
            log_with_timestamp(f"  Progress: {i+1}/{len(index_files)} files merged. Memory: {used_mb:.1f}MB used, {avail_mb:.1f}MB available ({percent:.1f}%)")

    log_with_timestamp(f"All files processed. Total vectors in master index: {master_index.ntotal}")

    # Final memory report before saving
    used_mb, avail_mb, percent = get_memory_usage()
    log_with_timestamp(f"Memory status before saving: {used_mb:.1f}MB used, {avail_mb:.1f}MB available ({percent:.1f}%)")

    # 4. Save the final master files
    log_with_timestamp(f"Saving master FAISS index to {MASTER_INDEX_PATH}...")
    faiss.write_index(master_index, MASTER_INDEX_PATH)

    log_with_timestamp(f"Saving master metadata to {MASTER_METADATA_PATH}...")
    with open(MASTER_METADATA_PATH, 'w') as f:
        json.dump(master_metadata, f)

    # Final statistics
    log_with_timestamp(f"Final index vectors: {master_index.ntotal}")
    log_with_timestamp(f"Final metadata entries: {len(master_metadata)}")

    if master_index.ntotal != len(master_metadata):
        log_with_timestamp("WARNING: Mismatch between index vectors and metadata entries!")
    else:
        log_with_timestamp("SUCCESS: Index and metadata counts match!")

    # Final memory report
    used_mb, avail_mb, percent = get_memory_usage()
    log_with_timestamp(f"Final memory usage: {used_mb:.1f}MB used ({percent:.1f}%)")

    log_with_timestamp("--- Merge Process Complete ---")

if __name__ == "__main__":
    merge_all_parts()
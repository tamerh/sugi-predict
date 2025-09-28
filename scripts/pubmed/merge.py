import os
import json
import faiss
import numpy as np
from datetime import datetime

# --- Configuration ---
BASE_PROCESSED_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'pubmed')
FINAL_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'final', 'pubmed')
MASTER_INDEX_PATH = os.path.join(FINAL_OUTPUT_DIR, 'master_pubmed.index')
MASTER_METADATA_PATH = os.path.join(FINAL_OUTPUT_DIR, 'master_metadata.json')
VECTOR_DIMENSION = 384 # Must match the model's dimension

# --- Helper Function for Timestamped Logging ---
def log_with_timestamp(message):
    """Prints a message with a prepended timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# --- Main Merging Logic ---
def merge_all_parts():
    log_with_timestamp("--- Starting Merge Process ---")
    os.makedirs(FINAL_OUTPUT_DIR, exist_ok=True)

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

    # 3. Iterate and merge
    for i in range(len(index_files)):
        index_path = index_files[i]
        metadata_path = metadata_files[i]
        
        log_with_timestamp(f"Merging part {i+1}/{len(index_files)}: {os.path.basename(index_path)}")
        
        # Merge FAISS index
        partial_index = faiss.read_index(index_path)
        master_index.add(partial_index.reconstruct_n(0, partial_index.ntotal))
        
        # Merge metadata, re-keying the IDs to be sequential
        with open(metadata_path, 'r') as f:
            partial_metadata = json.load(f)
        
        for local_id in sorted(partial_metadata.keys(), key=int):
            master_metadata[master_vector_count] = partial_metadata[local_id]
            master_vector_count += 1

    log_with_timestamp(f"Total vectors in master index: {master_index.ntotal}")

    # 4. Save the final master files
    log_with_timestamp(f"Saving master FAISS index to {MASTER_INDEX_PATH}...")
    faiss.write_index(master_index, MASTER_INDEX_PATH)
    
    log_with_timestamp(f"Saving master metadata to {MASTER_METADATA_PATH}...")
    with open(MASTER_METADATA_PATH, 'w') as f:
        json.dump(master_metadata, f)
        
    log_with_timestamp("--- Merge Process Complete ---")

if __name__ == "__main__":
    merge_all_parts()
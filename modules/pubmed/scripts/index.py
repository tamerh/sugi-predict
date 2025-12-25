import os
import gzip
import json
import faiss
import numpy as np
import argparse
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
import xml.etree.ElementTree as ET
from datetime import datetime

# Limit threads to avoid contention when running multiple processes
# Each process should use 1 thread since we parallelize at process level
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import torch
torch.set_num_threads(1)

# --- Configuration ---
# Will be set from command-line arguments in main()
MODEL_NAME = None
VECTOR_DIMENSION = None
DELETED_PMIDS_PATH = None

# --- Helper Functions ---
def log_with_timestamp(message):
    """Prints a message with a prepended timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def load_deleted_pmids(path):
    """Loads the gzipped list of deleted PMIDs into a set for fast lookups."""
    log_with_timestamp(f"Loading deleted PMIDs from {path}...")
    if not os.path.exists(path):
        log_with_timestamp(f"Warning: {os.path.basename(path)} not found. Proceeding without deletion check.")
        return set()
    
    deleted_set = set()
    with gzip.open(path, 'rt') as f:
        for line in f:
            deleted_set.add(line.strip())
    log_with_timestamp(f"Loaded {len(deleted_set)} deleted PMIDs into memory.")
    return deleted_set

# --- Main Processing Function ---
# Batch size for encoding (64 optimal for CPU, 128-256 for GPU)
ENCODE_BATCH_SIZE = 64

def process_file(input_path, output_dir, deleted_pmids_set, model_name, vector_dim, limit=None):
    """
    Processes a single gzipped PubMed XML file, creates a FAISS index and metadata file,
    skipping any PMIDs that are in the deleted_pmids_set.

    Args:
        input_path: Path to input .xml.gz file
        output_dir: Directory to save output files
        deleted_pmids_set: Set of deleted PMIDs to skip
        model_name: Name of the sentence transformer model
        vector_dim: Dimension of the vectors
        limit: Optional limit on number of abstracts to process (for testing)
    """
    log_with_timestamp(f"--- Processing {os.path.basename(input_path)} ---")
    if limit:
        log_with_timestamp(f"TEST MODE: Processing only first {limit} abstracts")
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.basename(input_path).replace('.xml.gz', '')
    faiss_output_path = os.path.join(output_dir, f"{base_name}.index")
    metadata_output_path = os.path.join(output_dir, f"{base_name}.json")

    if os.path.exists(faiss_output_path) and os.path.exists(metadata_output_path):
        log_with_timestamp(f"Output for {base_name} already exists. Skipping.")
        return

    log_with_timestamp(f"Loading sentence-transformer model: {model_name}...")
    model = SentenceTransformer(model_name)
    log_with_timestamp("Model loaded.")

    index = faiss.IndexFlatL2(vector_dim)
    metadata = {}
    vector_count = 0
    skipped_count = 0

    # Batching: accumulate texts before encoding
    batch_texts = []
    batch_pmids = []

    def flush_batch():
        """Encode and add accumulated batch to index."""
        nonlocal vector_count
        if not batch_texts:
            return

        # Encode entire batch at once (10-30x faster than one-by-one)
        vectors = model.encode(batch_texts, show_progress_bar=False)

        # Add all vectors to FAISS index
        index.add(np.array(vectors, dtype='float32'))

        # Store metadata for each vector
        for i, (pmid, chunk_text) in enumerate(zip(batch_pmids, batch_texts)):
            metadata[vector_count + i] = {'pmid': pmid, 'chunk_text': chunk_text}

        vector_count += len(batch_texts)
        batch_texts.clear()
        batch_pmids.clear()

    log_with_timestamp(f"Streaming and processing XML from {input_path}...")
    log_with_timestamp(f"Using batch size: {ENCODE_BATCH_SIZE} for encoding")

    hit_limit = False
    with gzip.open(input_path, 'rb') as f:
        context = ET.iterparse(f, events=('end',))
        for event, elem in tqdm(context, desc=f"Parsing {base_name}", mininterval=300.0):
            if elem.tag == 'PubmedArticle':
                try:
                    pmid_element = elem.find('.//PMID')
                    pmid = pmid_element.text if pmid_element is not None else None

                    # Skip deleted PMIDs
                    if pmid and pmid in deleted_pmids_set:
                        skipped_count += 1
                        elem.clear()
                        continue

                    title_element = elem.find('.//ArticleTitle')
                    title = "".join(title_element.itertext()) if title_element is not None else ""

                    abstract_element = elem.find('.//AbstractText')
                    abstract = "".join(abstract_element.itertext()) if abstract_element is not None else ""

                    if pmid and abstract:
                        chunk_text = f"Title: {title}\nAbstract: {abstract}"
                        batch_texts.append(chunk_text)
                        batch_pmids.append(pmid)

                        # Flush batch when full
                        if len(batch_texts) >= ENCODE_BATCH_SIZE:
                            flush_batch()

                        # Check limit for test mode
                        if limit and vector_count + len(batch_texts) >= limit:
                            log_with_timestamp(f"Reached test limit of {limit} abstracts. Stopping processing.")
                            hit_limit = True
                            elem.clear()
                            break
                except Exception:
                    pass
                elem.clear()

    # Flush any remaining items in the batch
    flush_batch()

    log_with_timestamp(f"Processed {index.ntotal} chunks. Skipped {skipped_count} deleted PMIDs. Saving assets...")
    faiss.write_index(index, faiss_output_path)
    with open(metadata_output_path, 'w') as f:
        json.dump(metadata, f)
    log_with_timestamp(f"--- Finished {os.path.basename(input_path)} ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a single PubMed XML file.")
    parser.add_argument("input_file", type=str, help="Path to the input .xml.gz file.")
    parser.add_argument("output_dir", type=str, help="Directory to save the output files.")
    parser.add_argument("--deleted-pmids", type=str, required=True, help="Path to deleted PMIDs file.")
    parser.add_argument("--model-name", type=str, required=True, help="Name of the sentence transformer model.")
    parser.add_argument("--vector-dim", type=int, required=True, help="Dimension of the vectors.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only first N abstracts (for testing). Default: process all.")
    parser.add_argument("--tracking-file", type=str, default=None,
                        help="Path to tracking JSON file (for update mode)")
    parser.add_argument("--relative-path", type=str, default=None,
                        help="Relative path of file (e.g., 'baseline/pubmed25n0001.xml.gz') for tracking")

    args = parser.parse_args()

    # Load the deleted PMIDs set once at the start of the script
    deleted_pmids = load_deleted_pmids(args.deleted_pmids)

    # Process the file
    process_file(args.input_file, args.output_dir, deleted_pmids, args.model_name, args.vector_dim, limit=args.limit)

    # Mark as processed in tracking system if tracking file provided
    if args.tracking_file and args.relative_path:
        try:
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            from tracking import PubMedTracker

            tracker = PubMedTracker(args.tracking_file)

            # Get vector count from generated files
            base_name = os.path.basename(args.input_file).replace('.xml.gz', '')
            faiss_output_path = os.path.join(args.output_dir, f"{base_name}.index")

            # Read the index to get vector count
            vector_count = None
            if os.path.exists(faiss_output_path):
                index = faiss.read_index(faiss_output_path)
                vector_count = index.ntotal

            # Mark as processed
            tracker.mark_processed(args.relative_path, vectors_count=vector_count)
            log_with_timestamp(f"Marked {args.relative_path} as processed in tracking system")

        except Exception as e:
            log_with_timestamp(f"Warning: Could not update tracking system: {e}")


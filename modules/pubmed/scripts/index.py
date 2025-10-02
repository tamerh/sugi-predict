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

# --- Load Configuration from pubmed.env ---
def load_env_config():
    """Load configuration from pubmed.env file."""
    config = {}
    env_file = os.path.join(os.path.dirname(__file__), 'pubmed.env')

    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip().strip('"').strip("'")

    return config

# Load configuration
env_config = load_env_config()

# --- Configuration ---
MODEL_NAME = env_config.get('MODEL_NAME', 'all-MiniLM-L6-v2')
VECTOR_DIMENSION = int(env_config.get('VECTOR_DIMENSION', '384'))
BASE_DATA_DIR = env_config.get('BASE_DATA_DIR', '/data/scc/ag-gruber/GROUP/tgur/x/bioyoda/data/raw/pubmed')
# Point to the new sorted file for efficiency
DELETED_PMIDS_PATH = os.path.join(BASE_DATA_DIR, 'deleted.pmids.sorted.gz')

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
def process_file(input_path, output_dir, deleted_pmids_set, limit=None):
    """
    Processes a single gzipped PubMed XML file, creates a FAISS index and metadata file,
    skipping any PMIDs that are in the deleted_pmids_set.

    Args:
        input_path: Path to input .xml.gz file
        output_dir: Directory to save output files
        deleted_pmids_set: Set of deleted PMIDs to skip
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

    log_with_timestamp(f"Loading sentence-transformer model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    log_with_timestamp("Model loaded.")

    index = faiss.IndexFlatL2(VECTOR_DIMENSION)
    metadata = {}
    vector_count = 0
    skipped_count = 0

    log_with_timestamp(f"Streaming and processing XML from {input_path}...")

    with gzip.open(input_path, 'rb') as f:
        context = ET.iterparse(f, events=('end',))
        for event, elem in tqdm(context, desc=f"Parsing {base_name}", mininterval=300.0):
            if elem.tag == 'PubmedArticle':
                try:
                    pmid_element = elem.find('.//PMID')
                    pmid = pmid_element.text if pmid_element is not None else None

                    # <<< --- THE CORE OPTIMIZATION IS HERE --- >>>
                    if pmid and pmid in deleted_pmids_set:
                        skipped_count += 1
                        elem.clear() # IMPORTANT: Still clear the element from memory
                        continue

                    title_element = elem.find('.//ArticleTitle')
                    title = "".join(title_element.itertext()) if title_element is not None else ""

                    abstract_element = elem.find('.//AbstractText')
                    abstract = "".join(abstract_element.itertext()) if abstract_element is not None else ""

                    if pmid and abstract:
                        chunk_text = f"Title: {title}\nAbstract: {abstract}"
                        vector = model.encode([chunk_text])[0]
                        index.add(np.array([vector], dtype='float32'))
                        metadata[vector_count] = {'pmid': pmid, 'chunk_text': chunk_text}
                        vector_count += 1

                        # Check limit for test mode
                        if limit and vector_count >= limit:
                            log_with_timestamp(f"Reached test limit of {limit} abstracts. Stopping processing.")
                            elem.clear()
                            break
                except Exception:
                    pass
                elem.clear()

    log_with_timestamp(f"Processed {index.ntotal} chunks. Skipped {skipped_count} deleted PMIDs. Saving assets...")
    faiss.write_index(index, faiss_output_path)
    with open(metadata_output_path, 'w') as f:
        json.dump(metadata, f)
    log_with_timestamp(f"--- Finished {os.path.basename(input_path)} ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a single PubMed XML file.")
    parser.add_argument("input_file", type=str, help="Path to the input .xml.gz file.")
    parser.add_argument("output_dir", type=str, help="Directory to save the output files.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only first N abstracts (for testing). Default: process all.")

    args = parser.parse_args()

    # Load the deleted PMIDs set once at the start of the script
    deleted_pmids = load_deleted_pmids(DELETED_PMIDS_PATH)

    process_file(args.input_file, args.output_dir, deleted_pmids, limit=args.limit)


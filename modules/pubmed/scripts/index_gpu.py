"""
PubMed Index Processing with GPU Acceleration
Optimized for Google Colab (T4/A100)

Usage in Colab:
    !python index_gpu.py input.xml.gz output_dir --deleted-pmids deleted.pmids.sorted.gz \
        --model-name pritamdeka/S-BioBERT-snli-multinli-stsb --vector-dim 768
"""
import os
import gzip
import json
import faiss
import numpy as np
import argparse
from tqdm import tqdm
import xml.etree.ElementTree as ET
from datetime import datetime

# Disable tokenizer parallelism warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# --- Configuration ---
# Batch sizes optimized for different GPUs
GPU_BATCH_SIZES = {
    "T4": 128,      # 16GB VRAM
    "A100": 512,    # 40-80GB VRAM
    "V100": 256,    # 16-32GB VRAM
    "default": 128
}

def log_with_timestamp(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def detect_gpu():
    """Detect GPU type and return optimal batch size."""
    try:
        import torch
        if not torch.cuda.is_available():
            log_with_timestamp("No GPU detected, using CPU")
            return "cpu", 64

        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9

        log_with_timestamp(f"GPU detected: {gpu_name} ({vram_gb:.1f} GB VRAM)")

        if "A100" in gpu_name:
            return "A100", GPU_BATCH_SIZES["A100"]
        elif "V100" in gpu_name:
            return "V100", GPU_BATCH_SIZES["V100"]
        elif "T4" in gpu_name:
            return "T4", GPU_BATCH_SIZES["T4"]
        else:
            # Unknown GPU, use conservative batch size based on VRAM
            batch_size = min(512, int(vram_gb * 16))
            return gpu_name, max(64, batch_size)
    except Exception as e:
        log_with_timestamp(f"GPU detection failed: {e}")
        return "cpu", 64

def load_deleted_pmids(path):
    """Load deleted PMIDs into a set."""
    log_with_timestamp(f"Loading deleted PMIDs from {path}...")
    if not os.path.exists(path):
        log_with_timestamp(f"Warning: {path} not found. Proceeding without deletion check.")
        return set()

    deleted_set = set()
    with gzip.open(path, 'rt') as f:
        for line in f:
            deleted_set.add(line.strip())
    log_with_timestamp(f"Loaded {len(deleted_set)} deleted PMIDs.")
    return deleted_set

def load_model_gpu(model_name):
    """Load model with GPU acceleration."""
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log_with_timestamp(f"Loading model on {device}: {model_name}...")

    model = SentenceTransformer(model_name, device=device)

    # Enable FP16 for faster inference on GPU (2x speedup)
    if device == "cuda":
        # Check if model supports FP16
        try:
            model.half()
            log_with_timestamp("FP16 (half precision) enabled for faster inference")
        except:
            log_with_timestamp("FP16 not supported, using FP32")

    log_with_timestamp("Model loaded successfully.")
    return model, device

def process_file(input_path, output_dir, deleted_pmids_set, model_name, vector_dim,
                 limit=None, batch_size=None, model=None, gpu_type=None):
    """Process PubMed XML file with GPU acceleration.

    Args:
        model: Pre-loaded SentenceTransformer model (optional). If None, loads model.
        gpu_type: GPU type string (optional). If None, detects GPU.
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

    # Detect GPU and set batch size (if not provided)
    if gpu_type is None:
        gpu_type, auto_batch_size = detect_gpu()
        if batch_size is None:
            batch_size = auto_batch_size
    else:
        if batch_size is None:
            batch_size = GPU_BATCH_SIZES.get(gpu_type, 128)

    log_with_timestamp(f"Using batch size: {batch_size} for {gpu_type}")

    # Load model if not provided
    if model is None:
        model, device = load_model_gpu(model_name)

    index = faiss.IndexFlatL2(vector_dim)
    metadata = {}
    vector_count = 0
    skipped_count = 0

    # Batching
    batch_texts = []
    batch_pmids = []

    def flush_batch():
        nonlocal vector_count
        if not batch_texts:
            return

        # Encode with GPU
        vectors = model.encode(
            batch_texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=False
        )

        # Ensure float32 for FAISS
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)

        index.add(vectors)

        for i, (pmid, chunk_text) in enumerate(zip(batch_pmids, batch_texts)):
            metadata[vector_count + i] = {'pmid': pmid, 'chunk_text': chunk_text}

        vector_count += len(batch_texts)
        batch_texts.clear()
        batch_pmids.clear()

    log_with_timestamp(f"Streaming XML from {input_path}...")

    # Progress tracking
    processed_articles = 0
    start_time = datetime.now()

    with gzip.open(input_path, 'rb') as f:
        context = ET.iterparse(f, events=('end',))
        for event, elem in tqdm(context, desc=f"Parsing {base_name}", mininterval=10.0):
            if elem.tag == 'PubmedArticle':
                processed_articles += 1
                try:
                    pmid_element = elem.find('.//PMID')
                    pmid = pmid_element.text if pmid_element is not None else None

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

                        if len(batch_texts) >= batch_size:
                            flush_batch()

                            # Log progress every 1000 vectors
                            if vector_count % 1000 == 0 and vector_count > 0:
                                elapsed = (datetime.now() - start_time).total_seconds()
                                rate = vector_count / elapsed
                                log_with_timestamp(f"Progress: {vector_count} vectors, {rate:.1f} texts/sec")

                        if limit and vector_count + len(batch_texts) >= limit:
                            log_with_timestamp(f"Reached limit of {limit} abstracts.")
                            elem.clear()
                            break
                except Exception:
                    pass
                elem.clear()

    flush_batch()

    # Final stats
    elapsed = (datetime.now() - start_time).total_seconds()
    rate = vector_count / elapsed if elapsed > 0 else 0

    log_with_timestamp(f"Processed {vector_count} vectors in {elapsed:.1f}s ({rate:.1f} texts/sec)")
    log_with_timestamp(f"Skipped {skipped_count} deleted PMIDs")
    log_with_timestamp("Saving FAISS index and metadata...")

    faiss.write_index(index, faiss_output_path)
    with open(metadata_output_path, 'w') as f:
        json.dump(metadata, f)

    log_with_timestamp(f"--- Finished {os.path.basename(input_path)} ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process PubMed XML with GPU acceleration")
    parser.add_argument("input_file", type=str, help="Input .xml.gz file")
    parser.add_argument("output_dir", type=str, help="Output directory")
    parser.add_argument("--deleted-pmids", type=str, required=True, help="Deleted PMIDs file")
    parser.add_argument("--model-name", type=str, required=True, help="Model name")
    parser.add_argument("--vector-dim", type=int, required=True, help="Vector dimension")
    parser.add_argument("--limit", type=int, default=None, help="Limit abstracts (testing)")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size")
    parser.add_argument("--tracking-file", type=str, default=None, help="Tracking file")
    parser.add_argument("--relative-path", type=str, default=None, help="Relative path for tracking")

    args = parser.parse_args()

    deleted_pmids = load_deleted_pmids(args.deleted_pmids)
    process_file(
        args.input_file, args.output_dir, deleted_pmids,
        args.model_name, args.vector_dim,
        limit=args.limit, batch_size=args.batch_size
    )

    # Tracking (if provided)
    if args.tracking_file and args.relative_path:
        try:
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            from tracking import PubMedTracker
            tracker = PubMedTracker(args.tracking_file)
            base_name = os.path.basename(args.input_file).replace('.xml.gz', '')
            faiss_output_path = os.path.join(args.output_dir, f"{base_name}.index")
            vector_count = None
            if os.path.exists(faiss_output_path):
                idx = faiss.read_index(faiss_output_path)
                vector_count = idx.ntotal
            tracker.mark_processed(args.relative_path, vectors_count=vector_count)
            log_with_timestamp(f"Marked {args.relative_path} as processed")
        except Exception as e:
            log_with_timestamp(f"Warning: Tracking failed: {e}")

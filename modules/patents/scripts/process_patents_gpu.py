"""
Patent Processing with GPU Acceleration
Optimized for Google Colab (T4/A100)

Processes patent Parquet chunks from SureChEMBL to create FAISS embeddings
using S-BioBERT model with GPU acceleration.

Usage in Colab:
    !python process_patents_gpu.py input_chunk.parquet output_dir \
        --model-name pritamdeka/S-BioBERT-snli-multinli-stsb --vector-dim 768 \
        --uspto-data uspto_historical.parquet
"""
import os
import json
import faiss
import numpy as np
import pandas as pd
import argparse
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

# Disable tokenizer parallelism warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# --- Configuration ---
GPU_BATCH_SIZES = {
    "T4": 128,      # 16GB VRAM
    "A100": 512,    # 40-80GB VRAM
    "V100": 256,    # 16-32GB VRAM
    "default": 128
}

def log_with_timestamp(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

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
            batch_size = min(512, int(vram_gb * 16))
            return gpu_name, max(64, batch_size)
    except Exception as e:
        log_with_timestamp(f"GPU detection failed: {e}")
        return "cpu", 64

def load_model_gpu(model_name, use_fp16=True):
    """Load model with GPU acceleration and optional FP16."""
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log_with_timestamp(f"Loading model on {device}: {model_name}...")

    log_with_timestamp("Initializing SentenceTransformer...")
    model = SentenceTransformer(model_name, device=device)
    log_with_timestamp("SentenceTransformer initialized.")

    # Enable FP16 for faster inference on GPU (2x speedup)
    # Note: FP16 can sometimes hang on certain GPU configurations
    if device == "cuda" and use_fp16:
        try:
            log_with_timestamp("Converting to FP16 (half precision)...")
            model.half()
            log_with_timestamp("FP16 enabled for faster inference")
        except Exception as e:
            log_with_timestamp(f"FP16 conversion failed: {e}, using FP32")
    else:
        log_with_timestamp("Using FP32 precision")

    log_with_timestamp("Model loaded successfully.")
    return model, device

def clean_text(text: str) -> str:
    """Clean and normalize patent text content."""
    if not text or pd.isna(text):
        return ""

    text = str(text)
    text = re.sub(r'\s+', ' ', text.strip())
    text = re.sub(r'\r\n|\r|\n', ' ', text)
    text = re.sub(r'\t+', ' ', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

    return text.strip()

def safe_to_list(value):
    """Safely convert various types to list."""
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass

    if isinstance(value, list):
        return [x for x in value if x is not None and (not isinstance(x, float) or not pd.isna(x))]

    if hasattr(value, '__iter__') and not isinstance(value, str):
        return [x for x in value if x is not None and (not isinstance(x, float) or not pd.isna(x))]

    return [value]

def load_uspto_lookup(uspto_parquet_file: str) -> Dict[str, Dict]:
    """Load USPTO data into memory for fast lookup."""
    log_with_timestamp(f"Loading USPTO data from {uspto_parquet_file}...")

    uspto_df = pd.read_parquet(uspto_parquet_file)
    log_with_timestamp(f"Loaded {len(uspto_df):,} USPTO patents")

    # Create fast dictionary lookup
    uspto_lookup = {}
    for _, row in uspto_df.iterrows():
        uspto_lookup[row['patent_number']] = {
            'title': row.get('title', ''),
            'abstract': row.get('abstract', ''),
            'publication_date': row.get('publication_date', '')
        }

    log_with_timestamp(f"Created USPTO lookup with {len(uspto_lookup):,} entries")
    return uspto_lookup

def process_patent(patent: Dict[str, Any], uspto_lookup: Optional[Dict] = None) -> Optional[Dict]:
    """Process single patent into text chunk with metadata."""
    patent_id = patent.get('patent_number', patent.get('patent_id', ''))
    if not patent_id:
        return None

    # Extract fields from SureChEMBL
    title = clean_text(patent.get('title', ''))
    has_full_text = False
    text_source = 'surechembl_only'
    abstract = ''

    # USPTO enrichment for US patents
    if uspto_lookup and patent.get('country') == 'US':
        if patent_id in uspto_lookup:
            uspto_data = uspto_lookup[patent_id]
            if uspto_data['title']:
                title = clean_text(uspto_data['title'])
            abstract = clean_text(uspto_data['abstract'])
            has_full_text = True
            text_source = 'surechembl+uspto'

    # Build searchable text
    text_parts = []
    if title:
        text_parts.append(title)
        text_parts.append(title)  # Weight title higher
    if abstract:
        text_parts.append(abstract)

    searchable_text = ' '.join(text_parts)

    if not searchable_text or len(searchable_text) < 50:
        return None

    # Extract metadata
    family_id = patent.get('family_id', '')
    pub_date = patent.get('publication_date', patent.get('pub_date', ''))
    ipc_codes = safe_to_list(patent.get('ipc', patent.get('ipc_codes', [])))
    cpc_codes = safe_to_list(patent.get('cpc', []))
    assignees = safe_to_list(patent.get('asignee', patent.get('assignees', [])))

    return {
        'patent_id': patent_id,
        'text': searchable_text,
        'title': title,
        'has_full_text': has_full_text,
        'text_source': text_source,
        'family_id': family_id,
        'pub_date': str(pub_date) if pub_date else '',
        'ipc_codes': ipc_codes,
        'cpc_codes': cpc_codes,
        'classification_codes': list(set(ipc_codes + cpc_codes)),
        'assignees': assignees
    }

def process_chunk(input_path, output_dir, model_name, vector_dim,
                  uspto_lookup=None, limit=None, batch_size=None,
                  model=None, gpu_type=None):
    """Process patent Parquet chunk with GPU acceleration.

    Args:
        input_path: Path to input parquet chunk
        output_dir: Output directory for index and metadata
        model_name: Sentence transformer model name
        vector_dim: Vector dimension
        uspto_lookup: Pre-loaded USPTO lookup dict (optional)
        limit: Limit patents for testing (optional)
        batch_size: Override batch size (optional)
        model: Pre-loaded model (optional)
        gpu_type: GPU type string (optional)

    Returns:
        int: Number of vectors created
    """
    base_name = os.path.basename(input_path).replace('.parquet', '')
    log_with_timestamp(f"--- Processing {base_name} ---")

    os.makedirs(output_dir, exist_ok=True)

    faiss_output_path = os.path.join(output_dir, f"{base_name}.index")
    metadata_output_path = os.path.join(output_dir, f"{base_name}.json")

    # Check if already processed
    if os.path.exists(faiss_output_path) and os.path.exists(metadata_output_path):
        log_with_timestamp(f"Output for {base_name} already exists. Skipping.")
        return 0

    # Detect GPU and set batch size
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

    # Load parquet chunk
    log_with_timestamp(f"Loading patents from {input_path}...")
    df = pd.read_parquet(input_path)

    if limit:
        df = df.head(limit)
        log_with_timestamp(f"TEST MODE: Limited to {limit} patents")

    log_with_timestamp(f"Loaded {len(df):,} patents")

    # Process patents into chunks
    start_time = datetime.now()
    all_chunks = []
    all_texts = []
    enriched_count = 0
    us_count = 0

    for idx, row in df.iterrows():
        patent = row.to_dict()

        if patent.get('country') == 'US':
            us_count += 1

        chunk = process_patent(patent, uspto_lookup)
        if chunk:
            all_chunks.append(chunk)
            all_texts.append(chunk['text'])
            if chunk['has_full_text']:
                enriched_count += 1

        # Progress every 10K
        if (len(all_chunks) + 1) % 10000 == 0:
            log_with_timestamp(f"  Processed {len(all_chunks):,} patents...")

    log_with_timestamp(f"Generated {len(all_chunks):,} text chunks from {len(df):,} patents")
    if us_count > 0:
        log_with_timestamp(f"USPTO enrichment: {enriched_count:,}/{us_count:,} US patents ({enriched_count/us_count*100:.1f}%)")

    if not all_texts:
        log_with_timestamp("No valid text chunks generated")
        return 0

    # Generate embeddings in batches
    log_with_timestamp(f"Generating embeddings (batch_size={batch_size})...")

    index = faiss.IndexFlatL2(vector_dim)
    metadata = {}
    vector_count = 0

    for i in range(0, len(all_texts), batch_size):
        batch_texts = all_texts[i:i+batch_size]
        batch_chunks = all_chunks[i:i+batch_size]

        # Encode batch
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

        # Store metadata (without text to save space)
        for j, chunk in enumerate(batch_chunks):
            metadata[vector_count + j] = {
                'patent_id': chunk['patent_id'],
                'title': chunk['title'],
                'has_full_text': chunk['has_full_text'],
                'text_source': chunk['text_source'],
                'family_id': chunk['family_id'],
                'pub_date': chunk['pub_date'],
                'ipc_codes': chunk['ipc_codes'],
                'assignees': chunk['assignees']
            }

        vector_count += len(batch_texts)

        # Progress every 50K vectors
        if vector_count % 50000 < batch_size:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = vector_count / elapsed if elapsed > 0 else 0
            log_with_timestamp(f"Progress: {vector_count:,} vectors, {rate:.1f} texts/sec")

    # Final stats
    elapsed = (datetime.now() - start_time).total_seconds()
    rate = vector_count / elapsed if elapsed > 0 else 0

    log_with_timestamp(f"Generated {vector_count:,} vectors in {elapsed:.1f}s ({rate:.1f} texts/sec)")

    # Save outputs
    log_with_timestamp("Saving FAISS index and metadata...")
    faiss.write_index(index, faiss_output_path)

    with open(metadata_output_path, 'w') as f:
        json.dump(metadata, f)

    # Report file sizes
    index_size_mb = os.path.getsize(faiss_output_path) / 1024 / 1024
    meta_size_mb = os.path.getsize(metadata_output_path) / 1024 / 1024
    log_with_timestamp(f"Saved: {base_name}.index ({index_size_mb:.1f}MB), {base_name}.json ({meta_size_mb:.1f}MB)")

    log_with_timestamp(f"--- Finished {base_name} ---")
    return vector_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process patent chunk with GPU acceleration")
    parser.add_argument("input_file", type=str, help="Input parquet chunk file")
    parser.add_argument("output_dir", type=str, help="Output directory")
    parser.add_argument("--model-name", type=str, default="pritamdeka/S-BioBERT-snli-multinli-stsb")
    parser.add_argument("--vector-dim", type=int, default=768)
    parser.add_argument("--uspto-data", type=str, default=None, help="USPTO parquet file for enrichment")
    parser.add_argument("--limit", type=int, default=None, help="Limit patents (testing)")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size")

    args = parser.parse_args()

    # Load USPTO data if provided
    uspto_lookup = None
    if args.uspto_data and os.path.exists(args.uspto_data):
        uspto_lookup = load_uspto_lookup(args.uspto_data)

    process_chunk(
        args.input_file,
        args.output_dir,
        args.model_name,
        args.vector_dim,
        uspto_lookup=uspto_lookup,
        limit=args.limit,
        batch_size=args.batch_size
    )

"""
Clinical Trials Processing with GPU Acceleration
Optimized for Google Colab (T4/A100)

Processes clinical trial JSON chunks to create FAISS embeddings
using S-BioBERT model with GPU acceleration.

Usage in Colab:
    !python process_trials_gpu.py input_chunk.json output_dir \
        --model-name pritamdeka/S-BioBERT-snli-multinli-stsb --vector-dim 768
"""
import os
import json
import faiss
import numpy as np
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


class TrialTextProcessor:
    """Processes clinical trial text into chunks for embedding generation."""

    def __init__(self, max_chunk_length: int = 500, min_text_length: int = 50):
        self.max_chunk_length = max_chunk_length
        self.min_text_length = min_text_length

    def clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text.strip())
        text = re.sub(r'\r\n|\r|\n', ' ', text)
        text = re.sub(r'\t+', ' ', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        return text.strip()

    def chunk_long_text(self, text: str, max_length: int) -> List[str]:
        """Split long text into chunks while preserving sentence boundaries."""
        if not text or len(text) <= max_length:
            return [text] if text else []

        chunks = []
        sentences = re.split(r'[.!?]+', text)
        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(current_chunk) + len(sentence) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += ". " + sentence
                else:
                    current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def process_trial_to_chunks(self, trial: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process a single trial into multiple text chunks for embedding."""
        chunks = []
        nct_id = trial.get('nct_id', '')

        if not nct_id:
            return chunks

        # Core summary chunk
        brief_title = self.clean_text(trial.get('brief_title', ''))
        brief_summary = self.clean_text(trial.get('brief_summary', ''))

        if brief_summary and len(brief_summary) >= self.min_text_length:
            core_text = f"Title: {brief_title}. Summary: {brief_summary}"
            chunks.append({
                'nct_id': nct_id,
                'chunk_type': 'summary',
                'chunk_id': 0,
                'text': core_text,
                'brief_title': brief_title,
                'overall_status': trial.get('overall_status', ''),
                'phase': trial.get('phase', ''),
                'study_type': trial.get('study_type', ''),
                'conditions': trial.get('conditions', []),
                'interventions': trial.get('interventions', []),
                'sponsors': trial.get('sponsors', []),
            })

        # Detailed description chunks
        detailed_description = self.clean_text(trial.get('detailed_description', ''))
        if detailed_description and len(detailed_description) >= self.min_text_length:
            desc_chunks = self.chunk_long_text(detailed_description, self.max_chunk_length)
            for i, chunk_text in enumerate(desc_chunks):
                if len(chunk_text) >= self.min_text_length:
                    chunks.append({
                        'nct_id': nct_id,
                        'chunk_type': 'description',
                        'chunk_id': i,
                        'text': f"Description: {chunk_text}",
                        'brief_title': brief_title,
                        'overall_status': trial.get('overall_status', ''),
                        'phase': trial.get('phase', ''),
                        'study_type': trial.get('study_type', ''),
                        'conditions': trial.get('conditions', []),
                        'interventions': trial.get('interventions', []),
                        'sponsors': trial.get('sponsors', []),
                    })

        # Eligibility criteria chunks
        eligibility_data = trial.get('eligibility', {})
        if isinstance(eligibility_data, dict):
            eligibility = self.clean_text(eligibility_data.get('criteria', ''))
        else:
            eligibility = self.clean_text(str(eligibility_data) if eligibility_data else '')
        if eligibility and len(eligibility) >= self.min_text_length:
            elig_chunks = self.chunk_long_text(eligibility, self.max_chunk_length)
            for i, chunk_text in enumerate(elig_chunks):
                if len(chunk_text) >= self.min_text_length:
                    chunks.append({
                        'nct_id': nct_id,
                        'chunk_type': 'eligibility',
                        'chunk_id': i,
                        'text': f"Eligibility: {chunk_text}",
                        'brief_title': brief_title,
                        'overall_status': trial.get('overall_status', ''),
                        'phase': trial.get('phase', ''),
                        'study_type': trial.get('study_type', ''),
                        'conditions': trial.get('conditions', []),
                        'interventions': trial.get('interventions', []),
                        'sponsors': trial.get('sponsors', []),
                    })

        # Outcomes chunks
        outcomes = trial.get('outcomes', [])
        if outcomes:
            outcome_text = ". ".join([
                f"{o.get('type', 'Outcome')}: {self.clean_text(o.get('measure', ''))}"
                for o in outcomes if o.get('measure')
            ])
            if outcome_text and len(outcome_text) >= self.min_text_length:
                chunks.append({
                    'nct_id': nct_id,
                    'chunk_type': 'outcomes',
                    'chunk_id': 0,
                    'text': f"Outcomes: {outcome_text}",
                    'brief_title': brief_title,
                    'overall_status': trial.get('overall_status', ''),
                    'phase': trial.get('phase', ''),
                    'study_type': trial.get('study_type', ''),
                    'conditions': trial.get('conditions', []),
                    'interventions': trial.get('interventions', []),
                    'sponsors': trial.get('sponsors', []),
                })

        return chunks


def process_chunk(input_path, output_dir, model_name, vector_dim,
                  limit=None, batch_size=None, model=None, gpu_type=None):
    """Process clinical trials JSON chunk with GPU acceleration."""
    base_name = os.path.basename(input_path).replace('.json', '')
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

    # Load JSON chunk
    log_with_timestamp(f"Loading trials from {input_path}...")
    with open(input_path, 'r') as f:
        trials = json.load(f)

    if limit:
        trials = trials[:limit]
        log_with_timestamp(f"TEST MODE: Limited to {limit} trials")

    log_with_timestamp(f"Loaded {len(trials):,} trials")

    # Process trials into chunks
    text_processor = TrialTextProcessor()
    start_time = datetime.now()
    all_chunks = []
    all_texts = []

    for idx, trial in enumerate(trials):
        chunks = text_processor.process_trial_to_chunks(trial)
        for chunk in chunks:
            all_chunks.append(chunk)
            all_texts.append(chunk['text'])

        # Progress every 1K trials
        if (idx + 1) % 1000 == 0:
            log_with_timestamp(f"  Processed {idx + 1:,} trials...")

    log_with_timestamp(f"Generated {len(all_chunks):,} text chunks from {len(trials):,} trials")

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
                'nct_id': chunk['nct_id'],
                'chunk_type': chunk['chunk_type'],
                'chunk_id': chunk['chunk_id'],
                'brief_title': chunk['brief_title'],
                'overall_status': chunk['overall_status'],
                'phase': chunk['phase'],
                'study_type': chunk['study_type'],
                'conditions': chunk['conditions'],
                'interventions': chunk['interventions'],
                'sponsors': chunk['sponsors'],
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
    parser = argparse.ArgumentParser(description="Process clinical trials chunk with GPU acceleration")
    parser.add_argument("input_file", type=str, help="Input JSON chunk file")
    parser.add_argument("output_dir", type=str, help="Output directory")
    parser.add_argument("--model-name", type=str, default="pritamdeka/S-BioBERT-snli-multinli-stsb")
    parser.add_argument("--vector-dim", type=int, default=768)
    parser.add_argument("--limit", type=int, default=None, help="Limit trials (testing)")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size")

    args = parser.parse_args()

    process_chunk(
        args.input_file,
        args.output_dir,
        args.model_name,
        args.vector_dim,
        limit=args.limit,
        batch_size=args.batch_size
    )

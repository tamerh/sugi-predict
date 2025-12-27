#!/usr/bin/env python3
"""
Batch ESM-2 GPU Processing for Google Colab

Processes all FASTA chunks to generate embeddings and FAISS indices.
Supports resume capability - skips already processed chunks.

Usage in Colab:
    !python batch_esm2_gpu.py \
        --input-dir /content/drive/MyDrive/bioyoda/raw_data/esm2/chunks \
        --output-dir /content/drive/MyDrive/bioyoda/processed/esm2 \
        --state-file /content/drive/MyDrive/bioyoda/state/esm2/gpu_progress.json \
        --model esm2_t33_650M_UR50D
"""

import os
import sys
import json
import argparse
import glob
import numpy as np
import faiss
import h5py
from datetime import datetime
from pathlib import Path

# Disable tokenizer warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"

def log_with_timestamp(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def detect_gpu():
    """Detect GPU type and return optimal batch size."""
    try:
        import torch
        if not torch.cuda.is_available():
            log_with_timestamp("No GPU detected, using CPU (will be slow!)")
            return "cpu", 4

        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9

        log_with_timestamp(f"GPU detected: {gpu_name} ({vram_gb:.1f} GB VRAM)")

        # ESM-2 650M needs more memory per sequence than sentence transformers
        if "A100" in gpu_name:
            return "A100", 16  # A100 can handle larger batches
        elif "V100" in gpu_name:
            return "V100", 8
        elif "T4" in gpu_name:
            return "T4", 4  # T4 is memory limited
        else:
            # Conservative default based on VRAM
            batch_size = max(2, int(vram_gb / 4))
            return gpu_name, min(16, batch_size)
    except Exception as e:
        log_with_timestamp(f"GPU detection failed: {e}")
        return "cpu", 4


def load_esm_model(model_name, device):
    """Load ESM-2 model."""
    import torch
    import esm

    log_with_timestamp(f"Loading ESM-2 model: {model_name}...")

    if model_name == "esm2_t30_150M_UR50D":
        model, alphabet = esm.pretrained.esm2_t30_150M_UR50D()
        repr_layer = 30
    elif model_name == "esm2_t33_650M_UR50D":
        model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
        repr_layer = 33
    elif model_name == "esm2_t36_3B_UR50D":
        model, alphabet = esm.pretrained.esm2_t36_3B_UR50D()
        repr_layer = 36
    else:
        raise ValueError(f"Unknown model: {model_name}")

    model = model.to(device)
    model.eval()

    log_with_timestamp(f"Model loaded on {device}")
    return model, alphabet, repr_layer


def truncate_sequence(seq, max_len=1024):
    """Truncate sequence if too long."""
    if len(seq) > max_len:
        return seq[:max_len]
    return seq


def process_chunk(fasta_path, output_dir, model, alphabet, repr_layer,
                  device, batch_size, max_seq_len=1024):
    """Process a single FASTA chunk: generate embeddings + create FAISS index."""
    import torch
    from Bio import SeqIO

    base_name = Path(fasta_path).stem  # chunk_001
    log_with_timestamp(f"--- Processing {base_name} ---")

    # Output paths
    h5_path = os.path.join(output_dir, f"{base_name}.h5")
    index_path = os.path.join(output_dir, f"{base_name}.index")
    metadata_path = os.path.join(output_dir, f"{base_name}.json")

    # Check if already processed
    if os.path.exists(index_path) and os.path.exists(metadata_path):
        log_with_timestamp(f"Output for {base_name} already exists. Skipping.")
        return 0

    os.makedirs(output_dir, exist_ok=True)

    # Read sequences
    log_with_timestamp(f"Reading sequences from {fasta_path}...")
    sequences = []
    for record in SeqIO.parse(fasta_path, "fasta"):
        seq_str = str(record.seq)
        seq_str = truncate_sequence(seq_str, max_seq_len)
        sequences.append((record.id, seq_str))

    log_with_timestamp(f"Loaded {len(sequences):,} protein sequences")

    if not sequences:
        log_with_timestamp("No sequences found, skipping")
        return 0

    # Process in batches
    batch_converter = alphabet.get_batch_converter()
    all_embeddings = []
    all_ids = []

    start_time = datetime.now()

    with torch.no_grad():
        for i in range(0, len(sequences), batch_size):
            batch = sequences[i:i + batch_size]
            batch_ids = [item[0] for item in batch]

            # Convert batch
            batch_labels, batch_strs, batch_tokens = batch_converter(batch)
            batch_tokens = batch_tokens.to(device)

            # Generate embeddings
            results = model(batch_tokens, repr_layers=[repr_layer])
            embeddings = results["representations"][repr_layer].cpu().numpy()

            # Mean pooling (skip BOS/EOS tokens)
            for j, embedding in enumerate(embeddings):
                seq_len = len(batch_strs[j])
                mean_embedding = embedding[1:seq_len+1].mean(axis=0)
                all_embeddings.append(mean_embedding)
                all_ids.append(batch_ids[j])

            # Progress every 1000 sequences
            processed = min(i + batch_size, len(sequences))
            if processed % 1000 < batch_size or processed == len(sequences):
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = processed / elapsed if elapsed > 0 else 0
                log_with_timestamp(f"  Progress: {processed:,}/{len(sequences):,} sequences ({rate:.1f} seq/sec)")

    all_embeddings = np.array(all_embeddings, dtype=np.float32)
    embed_dim = all_embeddings.shape[1]

    elapsed = (datetime.now() - start_time).total_seconds()
    rate = len(sequences) / elapsed if elapsed > 0 else 0
    log_with_timestamp(f"Generated {len(all_embeddings):,} embeddings ({embed_dim}D) in {elapsed:.1f}s ({rate:.1f} seq/sec)")

    # Create FAISS index
    log_with_timestamp("Creating FAISS index...")
    index = faiss.IndexFlatL2(embed_dim)
    index.add(all_embeddings)

    # Save FAISS index
    faiss.write_index(index, index_path)

    # Create metadata (extract UniProt accession)
    metadata = {}
    for i, protein_id in enumerate(all_ids):
        parts = protein_id.split('|')
        accession = parts[1] if len(parts) >= 2 else protein_id
        metadata[str(i)] = {'protein_id': accession}

    # Save metadata
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f)

    # Report sizes
    index_size_mb = os.path.getsize(index_path) / 1024 / 1024
    meta_size_mb = os.path.getsize(metadata_path) / 1024 / 1024
    log_with_timestamp(f"Saved: {base_name}.index ({index_size_mb:.1f}MB), {base_name}.json ({meta_size_mb:.2f}MB)")

    log_with_timestamp(f"--- Finished {base_name} ---")
    return len(all_embeddings)


def load_state(state_file):
    """Load processing state from file."""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            return json.load(f)
    return {"processed_chunks": [], "total_vectors": 0}


def save_state(state_file, state):
    """Save processing state to file."""
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    state["last_update"] = datetime.now().isoformat()
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Batch ESM-2 GPU Processing")
    parser.add_argument("--input-dir", required=True, help="Directory with FASTA chunks")
    parser.add_argument("--output-dir", required=True, help="Output directory for indices")
    parser.add_argument("--state-file", required=True, help="State file for resume")
    parser.add_argument("--model", default="esm2_t33_650M_UR50D",
                       choices=["esm2_t30_150M_UR50D", "esm2_t33_650M_UR50D", "esm2_t36_3B_UR50D"],
                       help="ESM-2 model to use")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size")
    parser.add_argument("--max-seq-len", type=int, default=1024, help="Max sequence length")
    parser.add_argument("--start", type=int, default=None, help="Start chunk number")
    parser.add_argument("--end", type=int, default=None, help="End chunk number")
    parser.add_argument("--limit", type=int, default=None, help="Limit chunks (for testing)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip existing outputs")

    args = parser.parse_args()

    log_with_timestamp("=" * 60)
    log_with_timestamp("ESM-2 Batch GPU Processing")
    log_with_timestamp("=" * 60)

    # Detect GPU
    import torch
    gpu_type, auto_batch_size = detect_gpu()
    batch_size = args.batch_size or auto_batch_size
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    log_with_timestamp(f"Device: {device}")
    log_with_timestamp(f"Batch size: {batch_size}")
    log_with_timestamp(f"Model: {args.model}")

    # Load model once
    model, alphabet, repr_layer = load_esm_model(args.model, device)

    # Find all chunks
    chunk_pattern = os.path.join(args.input_dir, "chunk_*.fasta")
    all_chunks = sorted(glob.glob(chunk_pattern))

    if not all_chunks:
        log_with_timestamp(f"No chunks found matching: {chunk_pattern}")
        return 1

    log_with_timestamp(f"Found {len(all_chunks)} chunks")

    # Apply range filters
    if args.start is not None:
        all_chunks = [c for c in all_chunks if int(Path(c).stem.split('_')[1]) >= args.start]
    if args.end is not None:
        all_chunks = [c for c in all_chunks if int(Path(c).stem.split('_')[1]) <= args.end]
    if args.limit:
        all_chunks = all_chunks[:args.limit]

    log_with_timestamp(f"Processing {len(all_chunks)} chunks")

    # Load state
    state = load_state(args.state_file)

    # Filter already processed
    if args.skip_existing:
        pending_chunks = []
        for chunk in all_chunks:
            base_name = Path(chunk).stem
            index_path = os.path.join(args.output_dir, f"{base_name}.index")
            if not os.path.exists(index_path):
                pending_chunks.append(chunk)
        log_with_timestamp(f"Skipping {len(all_chunks) - len(pending_chunks)} existing, {len(pending_chunks)} remaining")
        all_chunks = pending_chunks

    # Process chunks
    total_vectors = state.get("total_vectors", 0)
    start_time = datetime.now()

    for idx, chunk_path in enumerate(all_chunks):
        log_with_timestamp("")
        log_with_timestamp("=" * 60)
        log_with_timestamp(f"Processing chunk {idx + 1}/{len(all_chunks)}: {Path(chunk_path).name}")
        log_with_timestamp("=" * 60)

        try:
            vectors = process_chunk(
                chunk_path,
                args.output_dir,
                model, alphabet, repr_layer,
                device, batch_size,
                args.max_seq_len
            )

            total_vectors += vectors
            state["processed_chunks"].append(Path(chunk_path).name)
            state["total_vectors"] = total_vectors
            save_state(args.state_file, state)

            # Progress summary
            elapsed = (datetime.now() - start_time).total_seconds() / 3600
            chunks_done = idx + 1
            chunks_remaining = len(all_chunks) - chunks_done
            if elapsed > 0:
                rate = chunks_done / elapsed
                eta = chunks_remaining / rate if rate > 0 else 0
                log_with_timestamp(f"\nProgress: {chunks_done}/{len(all_chunks)} chunks, {total_vectors:,} vectors")
                log_with_timestamp(f"Rate: {rate:.1f} chunks/hour, ETA: {eta:.1f}h")

        except Exception as e:
            log_with_timestamp(f"ERROR processing {chunk_path}: {e}")
            import traceback
            traceback.print_exc()
            continue

    log_with_timestamp("")
    log_with_timestamp("=" * 60)
    log_with_timestamp("BATCH PROCESSING COMPLETE")
    log_with_timestamp(f"Total vectors: {total_vectors:,}")
    log_with_timestamp(f"Output: {args.output_dir}")
    log_with_timestamp("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

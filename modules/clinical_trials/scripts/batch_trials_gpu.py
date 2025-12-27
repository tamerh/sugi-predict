"""
Batch Clinical Trials Processing for Google Colab GPU
Processes multiple JSON chunks with resume capability and state tracking.

Usage in Colab:
    # Mount drive first
    from google.colab import drive
    drive.mount('/content/drive')

    # Run processing
    !python batch_trials_gpu.py \
        --input-dir /content/drive/MyDrive/bioyoda/raw_data/clinical_trials/chunked \
        --output-dir /content/drive/MyDrive/bioyoda/processed/clinical_trials/text \
        --state-file /content/drive/MyDrive/bioyoda/state/clinical_trials/processed_chunks.json
"""
import os
import sys
import glob
import json
import argparse
from datetime import datetime
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def load_state(state_file):
    """Load processing state from JSON file."""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            return json.load(f)
    return {"chunks": {}, "last_update": None}

def save_state(state_file, state):
    """Save processing state to JSON file."""
    state["last_update"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

def get_pending_chunks(input_dir, output_dir, state):
    """Find chunks that haven't been processed yet."""
    # Find all input JSON chunks
    pattern = os.path.join(input_dir, "trials_chunk_*.json")
    all_chunks = sorted(glob.glob(pattern))

    # Also check for update chunks
    update_pattern = os.path.join(input_dir, "trials_update_*.json")
    all_chunks.extend(sorted(glob.glob(update_pattern)))

    pending = []
    for input_path in all_chunks:
        base_name = os.path.basename(input_path).replace('.json', '')

        # Check state file
        chunk_state = state.get("chunks", {}).get(os.path.basename(input_path), {})
        if chunk_state.get("status") == "completed":
            continue

        # Also check output files
        faiss_path = os.path.join(output_dir, f"{base_name}.index")
        meta_path = os.path.join(output_dir, f"{base_name}.json")

        if not (os.path.exists(faiss_path) and os.path.exists(meta_path)):
            pending.append(input_path)

    return pending

def update_chunk_state(state, chunk_name, vectors_count):
    """Update state for a completed chunk."""
    if "chunks" not in state:
        state["chunks"] = {}

    state["chunks"][chunk_name] = {
        "status": "completed",
        "processed_date": datetime.now().isoformat(),
        "vectors_count": vectors_count,
        "qdrant_inserted": False
    }

def main():
    parser = argparse.ArgumentParser(description="Batch GPU processing for clinical trials")
    parser.add_argument("--input-dir", required=True, help="Directory with JSON chunks")
    parser.add_argument("--output-dir", required=True, help="Output directory for indices")
    parser.add_argument("--state-file", required=True, help="State tracking JSON file")
    parser.add_argument("--model-name", default="pritamdeka/S-BioBERT-snli-multinli-stsb")
    parser.add_argument("--vector-dim", type=int, default=768)
    parser.add_argument("--start", type=int, default=0, help="Start index (0-based)")
    parser.add_argument("--end", type=int, default=None, help="End index (exclusive)")
    parser.add_argument("--limit", type=int, default=None, help="Limit per chunk (testing)")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip chunks with existing output files")
    parser.add_argument("--no-fp16", action="store_true", default=False,
                        help="Disable FP16 (use if model loading hangs)")

    args = parser.parse_args()

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Load state
    log(f"Loading state from {args.state_file}...")
    state = load_state(args.state_file)
    log(f"State has {len(state.get('chunks', {}))} chunk entries")

    # Get pending chunks
    log(f"Scanning for pending chunks in {args.input_dir}...")
    pending = get_pending_chunks(args.input_dir, args.output_dir, state)

    # Apply range
    if args.end is not None:
        pending = pending[args.start:args.end]
    else:
        pending = pending[args.start:]

    log(f"Found {len(pending)} chunks to process")

    if not pending:
        log("Nothing to process. All chunks complete!")
        return

    # Import GPU processing module
    from process_trials_gpu import (
        process_chunk, load_model_gpu, detect_gpu
    )

    # Detect GPU and load model ONCE
    gpu_type, auto_batch_size = detect_gpu()
    batch_size = args.batch_size if args.batch_size else auto_batch_size
    use_fp16 = not args.no_fp16
    log(f"Loading model once for all chunks (batch_size={batch_size}, fp16={use_fp16})...")
    model, device = load_model_gpu(args.model_name, use_fp16=use_fp16)
    log("Model loaded. Starting batch processing...")

    # Process each chunk
    start_time = datetime.now()
    completed = 0
    failed = 0
    total_vectors = 0

    for i, input_path in enumerate(pending):
        chunk_name = os.path.basename(input_path)
        log(f"\n{'='*60}")
        log(f"Processing chunk {i+1}/{len(pending)}: {chunk_name}")
        log(f"{'='*60}")

        try:
            vectors = process_chunk(
                input_path,
                args.output_dir,
                args.model_name,
                args.vector_dim,
                limit=args.limit,
                batch_size=batch_size,
                model=model,
                gpu_type=gpu_type
            )

            total_vectors += vectors
            completed += 1

            # Update state
            update_chunk_state(state, chunk_name, vectors)
            save_state(args.state_file, state)
            log(f"State saved for {chunk_name}")

        except Exception as e:
            log(f"ERROR processing {chunk_name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
            continue

        # Progress update
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = completed / (elapsed / 3600) if elapsed > 0 else 0
        remaining = len(pending) - completed - failed
        eta_hours = remaining / rate if rate > 0 else 0

        log(f"\nProgress: {completed}/{len(pending)} chunks, {total_vectors:,} vectors")
        log(f"Rate: {rate:.1f} chunks/hour, ETA: {eta_hours:.1f}h")

    # Final summary
    elapsed = (datetime.now() - start_time).total_seconds() / 3600

    log("\n" + "="*60)
    log("BATCH COMPLETE")
    log("="*60)
    log(f"  Chunks processed: {completed}/{len(pending)}")
    log(f"  Chunks failed: {failed}")
    log(f"  Total vectors: {total_vectors:,}")
    log(f"  Total time: {elapsed:.2f} hours")
    log(f"  Average rate: {completed/elapsed:.1f} chunks/hour" if elapsed > 0 else "")
    log("="*60)

    # Final state save
    save_state(args.state_file, state)

if __name__ == "__main__":
    main()

"""
Batch PubMed Processing for Google Colab GPU
Processes multiple files with resume capability and tracking.

Usage in Colab:
    # Mount drive first
    from google.colab import drive
    drive.mount('/content/drive')

    # Run in background with tracking
    !nohup python batch_gpu.py \
        --input-dir /content/drive/MyDrive/bioyoda/raw_data/pubmed \
        --output-dir /content/drive/MyDrive/bioyoda/processed/pubmed \
        --deleted-pmids /content/drive/MyDrive/bioyoda/raw_data/pubmed/deleted.pmids.sorted.gz \
        --tracking-file /content/drive/MyDrive/bioyoda/state/pubmed/processed_files.json \
        > processing.log 2>&1 &
"""
import os
import sys
import glob
import argparse
from datetime import datetime

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def get_subdir(input_path):
    """Extract subdirectory (baseline or updatefiles) from input path."""
    if '/baseline/' in input_path or '\\baseline\\' in input_path:
        return 'baseline'
    elif '/updatefiles/' in input_path or '\\updatefiles\\' in input_path:
        return 'updatefiles'
    return ''

def get_pending_files(input_dir, output_dir):
    """Find files that haven't been processed yet."""
    # Find all input files
    baseline_files = sorted(glob.glob(os.path.join(input_dir, "baseline", "*.xml.gz")))
    update_files = sorted(glob.glob(os.path.join(input_dir, "updatefiles", "*.xml.gz")))
    all_files = baseline_files + update_files

    pending = []
    for input_path in all_files:
        base_name = os.path.basename(input_path).replace('.xml.gz', '')
        subdir = get_subdir(input_path)

        # Output preserves baseline/updatefiles subdirectory structure
        output_subdir = os.path.join(output_dir, subdir) if subdir else output_dir
        faiss_path = os.path.join(output_subdir, f"{base_name}.index")
        meta_path = os.path.join(output_subdir, f"{base_name}.json")

        if not (os.path.exists(faiss_path) and os.path.exists(meta_path)):
            pending.append(input_path)

    return pending

def get_relative_path(input_path, input_dir):
    """Convert absolute path to relative path for tracking (e.g., baseline/pubmed25n0001.xml.gz)."""
    rel_path = os.path.relpath(input_path, input_dir)
    return rel_path

def main():
    parser = argparse.ArgumentParser(description="Batch GPU processing for PubMed")
    parser.add_argument("--input-dir", required=True, help="Base input directory")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--deleted-pmids", required=True, help="Deleted PMIDs file")
    parser.add_argument("--model-name", default="pritamdeka/S-BioBERT-snli-multinli-stsb")
    parser.add_argument("--vector-dim", type=int, default=768)
    parser.add_argument("--start", type=int, default=0, help="Start index (0-based)")
    parser.add_argument("--end", type=int, default=None, help="End index (exclusive)")
    parser.add_argument("--limit", type=int, default=None, help="Limit per file (testing)")
    parser.add_argument("--batch-size", type=int, default=None, help="Override batch size")
    parser.add_argument("--tracking-file", type=str, default=None,
                        help="Path to tracking JSON file (updates after each file)")

    args = parser.parse_args()

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Initialize tracker if tracking file provided
    tracker = None
    if args.tracking_file:
        try:
            from tracking import PubMedTracker
            tracker = PubMedTracker(args.tracking_file)
            log(f"Tracking enabled: {args.tracking_file}")
        except Exception as e:
            log(f"Warning: Could not initialize tracker: {e}")

    # Get pending files
    log(f"Scanning for pending files in {args.input_dir}...")
    pending = get_pending_files(args.input_dir, args.output_dir)

    # Apply range
    if args.end is not None:
        pending = pending[args.start:args.end]
    else:
        pending = pending[args.start:]

    log(f"Found {len(pending)} files to process")

    if not pending:
        log("Nothing to process. All files complete!")
        return

    # Import GPU processing module
    from index_gpu import load_deleted_pmids, process_file, load_model_gpu, detect_gpu

    # Load deleted PMIDs once
    deleted_pmids = load_deleted_pmids(args.deleted_pmids)

    # Detect GPU and load model ONCE (major optimization)
    gpu_type, auto_batch_size = detect_gpu()
    batch_size = args.batch_size if args.batch_size else auto_batch_size
    log(f"Loading model once for all files (batch_size={batch_size})...")
    model, device = load_model_gpu(args.model_name)
    log("Model loaded. Starting batch processing...")

    # Process each file
    start_time = datetime.now()
    completed = 0
    total_vectors = 0

    for i, input_path in enumerate(pending):
        log(f"Processing file {i+1}/{len(pending)}: {os.path.basename(input_path)}")

        # Determine output subdirectory (baseline or updatefiles)
        subdir = get_subdir(input_path)
        output_subdir = os.path.join(args.output_dir, subdir) if subdir else args.output_dir
        os.makedirs(output_subdir, exist_ok=True)

        try:
            process_file(
                input_path,
                output_subdir,  # Pass subdirectory-aware output path
                deleted_pmids,
                args.model_name,
                args.vector_dim,
                limit=args.limit,
                batch_size=batch_size,
                model=model,
                gpu_type=gpu_type
            )

            # Count vectors from output
            base_name = os.path.basename(input_path).replace('.xml.gz', '')
            faiss_path = os.path.join(output_subdir, f"{base_name}.index")
            vectors_count = 0
            if os.path.exists(faiss_path):
                import faiss
                idx = faiss.read_index(faiss_path)
                vectors_count = idx.ntotal
                total_vectors += vectors_count

            # Update tracking file
            if tracker:
                try:
                    relative_path = get_relative_path(input_path, args.input_dir)
                    tracker.mark_processed(relative_path, vectors_count=vectors_count)
                    log(f"Tracked: {relative_path} ({vectors_count} vectors)")
                except Exception as e:
                    log(f"Warning: Could not update tracking: {e}")

            completed += 1

        except Exception as e:
            log(f"ERROR processing {input_path}: {e}")
            continue

        # Progress update
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = completed / (elapsed / 3600) if elapsed > 0 else 0
        remaining = len(pending) - completed
        eta_hours = remaining / rate if rate > 0 else 0

        log(f"Progress: {completed}/{len(pending)} files, {total_vectors} vectors, ETA: {eta_hours:.1f}h")

    # Final summary
    elapsed = (datetime.now() - start_time).total_seconds() / 3600
    log("="*60)
    log(f"BATCH COMPLETE")
    log(f"  Files processed: {completed}/{len(pending)}")
    log(f"  Total vectors: {total_vectors}")
    log(f"  Total time: {elapsed:.2f} hours")
    log("="*60)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Unified Patents Data Download and Preparation

Orchestrates the complete patent data pipeline:
1. Download SureChEMBL data
2. Chunk patents.parquet for parallel processing
3. Extract US patent IDs (optional)
4. Download USPTO data (if enabled)
5. Parse USPTO XML files (if enabled)

This single script manages the entire download/preparation phase.
"""

import os
import sys
import json
import argparse
import subprocess
import pandas as pd
import psutil
from pathlib import Path
from datetime import datetime


def log(message: str) -> None:
    """Print message with timestamp and memory usage."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    print(f"[{timestamp}] [MEM: {memory_mb:.1f}MB] {message}", flush=True)


def write_processed_chunks_json(output_path: str, chunk_files: list, no_changes: bool = False):
    """
    Write processed_chunks.json (single source of truth for tracking).

    IMPORTANT: Preserves existing chunk metadata (like qdrant_inserted, vectors_count)
    and only updates/adds new chunks.
    """
    # Read existing state to preserve metadata
    existing_chunks = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r') as f:
                existing_state = json.load(f)
            existing_chunks = existing_state.get('chunks', {})
            log(f"Preserving metadata for {len(existing_chunks)} existing chunks")
        except Exception as e:
            log(f"WARNING: Could not read existing state: {e}")

    # Start with ALL existing chunks to preserve everything
    chunks_dict = existing_chunks.copy()

    # Update/add chunks from chunk_files
    for chunk_info in chunk_files:
        chunk_filename = chunk_info['filename']

        if chunk_filename in chunks_dict:
            # Chunk exists - preserve all existing metadata
            # Only update the fields we know about
            chunks_dict[chunk_filename]['num_patents'] = chunk_info['num_patents']
            chunks_dict[chunk_filename]['size_mb'] = chunk_info['size_mb']
            if 'status' not in chunks_dict[chunk_filename]:
                chunks_dict[chunk_filename]['status'] = 'ready_to_process'
        else:
            # New chunk - create fresh entry
            chunks_dict[chunk_filename] = {
                'status': 'ready_to_process',
                'num_patents': chunk_info['num_patents'],
                'size_mb': chunk_info['size_mb']
            }

    processed_chunks = {
        'last_update': datetime.now().isoformat(),
        'no_changes': no_changes,
        'chunks': chunks_dict
    }

    with open(output_path, 'w') as f:
        json.dump(processed_chunks, f, indent=2)

    log(f"Written processed_chunks.json: {output_path}")


def run_script(script_path, args, description):
    """Run a Python script and check for errors."""
    log(f"Starting: {description}")

    cmd = [sys.executable, script_path] + args
    log(f"Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        log(f"ERROR: {description} failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    log(f"Completed: {description}")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description='Unified patent data download and preparation pipeline'
    )

    # Output directories
    parser.add_argument('--surechembl-raw-dir', required=True,
                       help='Output directory for SureChEMBL data')
    parser.add_argument('--uspto-raw-dir', required=True,
                       help='Output directory for USPTO data')
    parser.add_argument('--state-dir', required=True,
                       help='State directory for tracking and intermediate files')

    # SureChEMBL options
    parser.add_argument('--surechembl-update-mode', action='store_true',
                       help='Update mode for SureChEMBL (skip if already exists)')
    parser.add_argument('--surechembl-limit-files', type=int,
                       help='Limit number of SureChEMBL files (test mode)')

    # USPTO options
    parser.add_argument('--enable-uspto', action='store_true',
                       help='Enable USPTO data download and processing')
    parser.add_argument('--uspto-historical-json-dir', required=False,
                       help='Directory containing USPTO-Chem historical JSON files')
    parser.add_argument('--uspto-limit-files', type=int,
                       help='Limit number of USPTO files to process (test mode)')
    parser.add_argument('--uspto-test-mode', action='store_true',
                       help='Test mode for USPTO')

    # Chunking options
    parser.add_argument('--chunk-size', type=int, default=0,
                       help='Patents per chunk (0 = no chunking)')
    parser.add_argument('--compounds-chunk-size', type=int, default=1000000,
                       help='Compounds per chunk (default: 1M)')
    parser.add_argument('--processed-chunks-output', required=True,
                       help='Path to processed_chunks.json state file')
    parser.add_argument('--limit', type=int,
                       help='Limit total patents (test mode)')
    parser.add_argument('--compounds-limit', type=int,
                       help='Limit total compounds (test mode)')

    args = parser.parse_args()

    # Get script directory
    script_dir = Path(__file__).parent

    log("="*60)
    log("UNIFIED PATENTS DATA PIPELINE")
    log("="*60)

    # ========================================================================
    # STEP 1: Download SureChEMBL
    # ========================================================================
    log("\n" + "="*60)
    log("STEP 1: Download SureChEMBL Data")
    log("="*60)

    surechembl_args = [
        '--raw-dir', args.surechembl_raw_dir
    ]

    if args.surechembl_update_mode:
        surechembl_args.append('--update-mode')

    if args.surechembl_limit_files:
        surechembl_args.extend(['--limit-files', str(args.surechembl_limit_files)])

    run_script(
        str(script_dir / 'download_surechembl.py'),
        surechembl_args,
        'SureChEMBL download'
    )

    # Find the downloaded release directory
    surechembl_dir = Path(args.surechembl_raw_dir)
    releases = sorted([d for d in surechembl_dir.iterdir() if d.is_dir()], reverse=True)

    if not releases:
        log("ERROR: No SureChEMBL release found after download")
        sys.exit(1)

    latest_release = releases[0]
    release_name = latest_release.name
    log(f"Latest release: {release_name}")

    patents_file = latest_release / 'patents.parquet'
    if not patents_file.exists():
        log(f"ERROR: Patents file not found: {patents_file}")
        sys.exit(1)

    # ========================================================================
    # STEP 2a: Download USPTO-Chem Historical Data (if USPTO enabled)
    # ========================================================================
    if args.enable_uspto:
        log("\n" + "="*60)
        log("STEP 2a: Download USPTO-Chem Historical Data")
        log("="*60)

        # Validate USPTO historical JSON directory
        if not args.uspto_historical_json_dir:
            log("ERROR: --uspto-historical-json-dir is required when --enable-uspto is set")
            sys.exit(1)

        json_dir = Path(args.uspto_historical_json_dir)

        # Create directory if it doesn't exist
        json_dir.mkdir(parents=True, exist_ok=True)

        # Tracking file for USPTO-Chem downloads
        uspto_tracking_file = Path(args.state_dir) / 'uspto_historical_download.json'

        # Build arguments for download_uspto_chem.py
        download_args = [
            '--output-dir', str(json_dir),
            '--tracking-file', str(uspto_tracking_file)
        ]

        # Add limit for test mode
        if args.uspto_limit_files:
            download_args.extend(['--limit-files', str(args.uspto_limit_files)])

        # Add debug flag in test mode
        if args.uspto_test_mode:
            download_args.append('--debug')

        log(f"Downloading USPTO-Chem data from eloyfelix/uspto-chem...")
        log(f"Output directory: {json_dir}")
        log(f"Tracking file: {uspto_tracking_file}")

        run_script(
            str(script_dir / 'download_uspto_chem.py'),
            download_args,
            'USPTO-Chem download'
        )

        log(f"USPTO-Chem download complete")

    # ========================================================================
    # STEP 2b: Process USPTO Historical JSON Data (if USPTO enabled)
    # ========================================================================
    if args.enable_uspto:
        log("\n" + "="*60)
        log("STEP 2b: Process USPTO Historical JSON to Parquet")
        log("="*60)

        json_dir = Path(args.uspto_historical_json_dir)

        # Check if parquet file already exists
        uspto_parquet_file = json_dir / 'uspto_historical.parquet'

        if uspto_parquet_file.exists():
            log(f"USPTO historical parquet already exists: {uspto_parquet_file}")
            log(f"File size: {uspto_parquet_file.stat().st_size / 1024 / 1024:.1f} MB")
            log("Skipping JSON processing...")
        else:
            log(f"USPTO historical parquet not found, processing JSON files...")
            log(f"JSON directory: {json_dir}")

            # Build arguments for process_uspto_json.py
            process_args = [
                '--input-dir', str(json_dir),
                '--output', str(uspto_parquet_file)
            ]

            # No filter-ids - process ALL patents as discussed
            # Filter happens during enrichment, not here

            # Add limit for test mode
            if args.uspto_limit_files:
                process_args.extend(['--limit-files', str(args.uspto_limit_files)])

            # Add debug flag in test mode
            if args.uspto_test_mode:
                process_args.append('--debug')

            run_script(
                str(script_dir / 'process_uspto_json.py'),
                process_args,
                'USPTO JSON to parquet processing'
            )

            log(f"USPTO historical parquet created: {uspto_parquet_file}")

    else:
        log("\n" + "="*60)
        log("USPTO processing DISABLED (enable_uspto=false)")
        log("="*60)

    # ========================================================================
    # STEP 3: Chunk patents.parquet for parallel processing
    # ========================================================================
    log("\n" + "="*60)
    log("STEP 3: Chunk Patents for Parallel Processing")
    log("="*60)

    # Determine chunking strategy
    # state_dir is at: {base_dir}/state/patents
    # We want: {base_dir}/raw_data/patents/chunked
    base_dir = Path(args.state_dir).parent.parent
    raw_chunked_dir = base_dir / "raw_data" / "patents" / "chunked"
    raw_chunked_dir.mkdir(parents=True, exist_ok=True)

    if args.chunk_size > 0:
        # Chunked output - use STREAMING to avoid loading entire file into memory
        log(f"Chunking enabled: {args.chunk_size} patents per chunk")

        # Check if chunks already exist
        existing_chunks = list(raw_chunked_dir.glob("patents_chunk_*.parquet"))
        state_file_exists = Path(args.processed_chunks_output).exists()

        if existing_chunks and not state_file_exists:
            # Chunks exist but state file is missing - regenerate state file
            log(f"Found {len(existing_chunks)} existing chunks but no state file")
            log(f"Regenerating state file from existing chunks...")

            chunk_files = []
            for chunk_path in sorted(existing_chunks):
                chunk_size_mb = chunk_path.stat().st_size / 1024 / 1024

                # Get row count from parquet metadata
                import pyarrow.parquet as pq
                chunk_parquet = pq.ParquetFile(chunk_path)
                num_patents = chunk_parquet.metadata.num_rows

                chunk_files.append({
                    'filename': chunk_path.name,
                    'num_patents': num_patents,
                    'size_mb': round(chunk_size_mb, 2)
                })

            write_processed_chunks_json(args.processed_chunks_output, chunk_files, no_changes=False)
            log(f"✓ Regenerated state file with {len(chunk_files)} chunks")

        elif existing_chunks and state_file_exists:
            # Both exist - skip chunking
            log(f"Chunks and state file already exist ({len(existing_chunks)} chunks)")
            log(f"Skipping chunking step...")

        else:
            # Need to create chunks
            log(f"Reading patents from: {patents_file}")

            import pyarrow.parquet as pq

            # Open parquet file for streaming
            parquet_file = pq.ParquetFile(patents_file)
            total_patents = parquet_file.metadata.num_rows
            log(f"Total patents: {total_patents:,}")

            # Apply limit if specified (test mode)
            if args.limit and args.limit < total_patents:
                log(f"Applying limit: {args.limit:,} patents")
                total_patents = args.limit

            num_chunks = (total_patents + args.chunk_size - 1) // args.chunk_size
            log(f"Will create {num_chunks} chunks using streaming")

            chunk_files = []
            patents_processed = 0
            chunk_idx = 0

            # Stream through parquet file in batches
            for batch in parquet_file.iter_batches(batch_size=args.chunk_size):
                # Convert batch to pandas
                batch_df = batch.to_pandas()

                # Handle limit
                if args.limit and patents_processed + len(batch_df) > args.limit:
                    remaining = args.limit - patents_processed
                    batch_df = batch_df.head(remaining)

                if len(batch_df) == 0:
                    break

                # Save chunk
                chunk_filename = f"patents_chunk_{chunk_idx+1:04d}.parquet"
                chunk_path = raw_chunked_dir / chunk_filename

                batch_df.to_parquet(chunk_path, index=False)

                chunk_size_mb = chunk_path.stat().st_size / 1024 / 1024
                chunk_files.append({
                    'filename': chunk_filename,
                    'num_patents': len(batch_df),
                    'size_mb': round(chunk_size_mb, 2)
                })

                patents_processed += len(batch_df)
                chunk_idx += 1

                log(f"  Created chunk {chunk_idx}/{num_chunks}: {chunk_filename} ({len(batch_df):,} patents, {chunk_size_mb:.1f}MB)")

                # Stop if we've hit the limit
                if args.limit and patents_processed >= args.limit:
                    break

            # Write processed_chunks.json
            write_processed_chunks_json(args.processed_chunks_output, chunk_files, no_changes=False)
            log(f"✓ Created {len(chunk_files)} chunks in {raw_chunked_dir}")
            log(f"✓ Total patents chunked: {patents_processed:,}")

    else:
        # No chunking - create single-file entry in processed_chunks.json
        log("Chunking disabled (chunk_size=0)")

        # Get total count without loading into memory
        import pyarrow.parquet as pq
        parquet_file = pq.ParquetFile(patents_file)
        total_patents = parquet_file.metadata.num_rows
        log(f"Total patents: {total_patents:,}")

        # Still write state file for consistency
        patents_size_mb = patents_file.stat().st_size / 1024 / 1024
        single_file_info = [{
            'filename': 'patents.parquet',
            'num_patents': total_patents,
            'size_mb': round(patents_size_mb, 2)
        }]
        write_processed_chunks_json(args.processed_chunks_output, single_file_info, no_changes=False)

    # ========================================================================
    # STEP 4: Chunk compounds.parquet for parallel processing
    # ========================================================================
    log("\n" + "="*60)
    log("STEP 4: Chunk Compounds for Parallel Processing")
    log("="*60)

    compounds_file = latest_release / 'compounds.parquet'
    if not compounds_file.exists():
        log(f"WARNING: Compounds file not found: {compounds_file}")
        log("Skipping compound chunking...")
    else:
        # Output directory for compound chunks
        compounds_chunked_dir = base_dir / "raw_data" / "patents" / "chunked_compounds"
        compounds_chunked_dir.mkdir(parents=True, exist_ok=True)

        compounds_chunk_size = args.compounds_chunk_size
        compounds_state_file = Path(args.state_dir) / "processed_compounds_chunks.json"

        # Check if chunks already exist
        existing_chunks = list(compounds_chunked_dir.glob("compounds_chunk_*.parquet"))

        if existing_chunks and compounds_state_file.exists():
            log(f"Compound chunks already exist ({len(existing_chunks)} chunks)")
            log("Skipping compound chunking...")
        else:
            log(f"Chunking compounds: {compounds_chunk_size:,} compounds per chunk")

            import pyarrow.parquet as pq

            # Open parquet file for streaming
            compounds_parquet = pq.ParquetFile(compounds_file)
            total_compounds = compounds_parquet.metadata.num_rows
            log(f"Total compounds: {total_compounds:,}")

            # Apply limit if specified (test mode)
            if args.compounds_limit and args.compounds_limit < total_compounds:
                log(f"Applying limit: {args.compounds_limit:,} compounds")
                total_compounds = args.compounds_limit

            num_chunks = (total_compounds + compounds_chunk_size - 1) // compounds_chunk_size
            log(f"Will create {num_chunks} chunks using streaming")

            chunk_files = []
            compounds_processed = 0
            chunk_idx = 0

            # Stream through parquet file in batches
            for batch in compounds_parquet.iter_batches(batch_size=compounds_chunk_size):
                # Convert batch to pandas
                batch_df = batch.to_pandas()

                # Handle limit
                if args.compounds_limit and compounds_processed + len(batch_df) > args.compounds_limit:
                    remaining = args.compounds_limit - compounds_processed
                    batch_df = batch_df.head(remaining)

                if len(batch_df) == 0:
                    break

                # Save chunk
                chunk_filename = f"compounds_chunk_{chunk_idx+1:04d}.parquet"
                chunk_path = compounds_chunked_dir / chunk_filename

                batch_df.to_parquet(chunk_path, index=False)

                chunk_size_mb = chunk_path.stat().st_size / 1024 / 1024
                chunk_files.append({
                    'filename': chunk_filename,
                    'num_compounds': len(batch_df),
                    'size_mb': round(chunk_size_mb, 2)
                })

                compounds_processed += len(batch_df)
                chunk_idx += 1

                log(f"  Created chunk {chunk_idx}/{num_chunks}: {chunk_filename} "
                    f"({len(batch_df):,} compounds, {chunk_size_mb:.1f}MB)")

                # Stop if we've hit the limit
                if args.compounds_limit and compounds_processed >= args.compounds_limit:
                    break

            # Write processed_compounds_chunks.json (matching patents pattern)
            chunks_dict = {}
            for chunk_info in chunk_files:
                chunks_dict[chunk_info['filename']] = {
                    'status': 'ready_to_process',
                    'num_compounds': chunk_info['num_compounds'],
                    'size_mb': chunk_info['size_mb']
                }

            state = {
                'chunking_complete': True,
                'total_chunks': len(chunk_files),
                'chunks': chunks_dict
            }

            with open(compounds_state_file, 'w') as f:
                json.dump(state, f, indent=2)

            log(f"✓ Created {len(chunk_files)} compound chunks in {compounds_chunked_dir}")
            log(f"✓ Total compounds chunked: {compounds_processed:,}")
            log(f"✓ State file: {compounds_state_file}")

    # ========================================================================
    # COMPLETE
    # ========================================================================
    log("\n" + "="*60)
    log("PIPELINE COMPLETE")
    log("="*60)
    log(f"SureChEMBL release: {release_name}")
    log(f"SureChEMBL data: {latest_release}")

    if args.enable_uspto:
        log(f"USPTO historical data: {uspto_parquet_file}")

    if args.chunk_size > 0:
        log(f"Chunks directory: {raw_chunked_dir}")
        log(f"State file: {args.processed_chunks_output}")

    log("\nAll data ready for processing!")


if __name__ == '__main__':
    main()

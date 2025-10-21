#!/usr/bin/env python3
"""
Unified Patents Data Download and Preparation

Orchestrates the complete patent data pipeline:
1. Download SureChEMBL data
2. Extract US patent IDs
3. Download USPTO data (if enabled)
4. Parse USPTO XML files (if enabled)

This single script manages the entire download/preparation phase.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime


def log(message: str) -> None:
    """Print message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)


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
    parser.add_argument('--surechembl-tracking-file', required=True,
                       help='Tracking file for SureChEMBL downloads')
    parser.add_argument('--surechembl-update-mode', action='store_true',
                       help='Update mode for SureChEMBL')
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
        '--raw-dir', args.surechembl_raw_dir,
        '--tracking-file', args.surechembl_tracking_file
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
    # STEP 2: Process USPTO Historical JSON Data (if USPTO enabled)
    # ========================================================================
    if args.enable_uspto:
        log("\n" + "="*60)
        log("STEP 2: Process USPTO Historical JSON Data")
        log("="*60)

        # Validate USPTO historical JSON directory
        if not args.uspto_historical_json_dir:
            log("ERROR: --uspto-historical-json-dir is required when --enable-uspto is set")
            sys.exit(1)

        json_dir = Path(args.uspto_historical_json_dir)
        if not json_dir.exists():
            log(f"ERROR: USPTO historical JSON directory not found: {json_dir}")
            sys.exit(1)

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
    # COMPLETE
    # ========================================================================
    log("\n" + "="*60)
    log("PIPELINE COMPLETE")
    log("="*60)
    log(f"SureChEMBL release: {release_name}")
    log(f"SureChEMBL data: {latest_release}")

    if args.enable_uspto:
        log(f"USPTO historical data: {uspto_parquet_file}")

    log("\nAll data ready for processing!")


if __name__ == '__main__':
    main()

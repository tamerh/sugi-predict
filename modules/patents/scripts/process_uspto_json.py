#!/usr/bin/env python3
"""
Process USPTO-Chem Historical JSON Data

Reads downloaded USPTO-Chem JSON files and converts them to a single parquet file
with patent text data (title, abstract) for enriching SureChEMBL patents.

Strategy:
- Only process US patents that exist in SureChEMBL (filter using us_patent_ids.txt)
- Extract: patent_number, title, abstract, publication_date
- Output single parquet file for efficient loading during enrichment

Input:
    - USPTO-Chem JSON files (downloaded by download_uspto_chem.py)
    - US patent IDs from SureChEMBL (us_patent_ids.txt)

Output:
    - Single parquet file: uspto_historical.parquet
    - Columns: patent_number, title, abstract, publication_date

Usage:
    python process_uspto_json.py \
        --input-dir snapshots/raw_data/patents/historical_uspto \
        --filter-ids test_out/raw_data/patents/surechembl/2025-10-01/us_patent_ids.txt \
        --output snapshots/raw_data/patents/historical_uspto/uspto_historical.parquet
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Set, List, Dict, Optional
from datetime import datetime
import pandas as pd
from tqdm import tqdm
import psutil


def log(message: str) -> None:
    """Print message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)


def log_memory_usage() -> None:
    """Log current memory usage."""
    process = psutil.Process()
    mem_info = process.memory_info()
    mem_mb = mem_info.rss / 1024 / 1024
    log(f"Memory usage: {mem_mb:.1f} MB")


def load_filter_ids(filter_file: Optional[Path]) -> Optional[Set[str]]:
    """
    Load US patent IDs from SureChEMBL filter file.

    Returns:
        Set of patent IDs (e.g., "US-20040019981-A1") or None if no filter
    """
    if not filter_file:
        log("No filter file specified - processing ALL patents")
        return None

    log(f"Loading filter IDs from {filter_file}")

    if not filter_file.exists():
        log(f"ERROR: Filter file not found: {filter_file}")
        sys.exit(1)

    filter_ids = set()
    with open(filter_file) as f:
        for line in f:
            patent_id = line.strip()
            if patent_id:
                filter_ids.add(patent_id)

    log(f"Loaded {len(filter_ids):,} patent IDs from SureChEMBL")
    return filter_ids


def extract_patent_number(patent_json: Dict) -> Optional[str]:
    """
    Extract patent number in SureChEMBL format from USPTO-Chem JSON.

    Format: US-{doc_number}-{kind}
    Example: US-20040019981-A1
    """
    try:
        pub = patent_json.get('publication', {})
        doc_number = pub.get('doc_number', '')
        kind = pub.get('kind', '')

        if doc_number and kind:
            # Format to match SureChEMBL
            return f"US-{doc_number}-{kind}"

        return None
    except Exception:
        return None


def process_json_file(json_path: Path, filter_ids: Optional[Set[str]]) -> List[Dict]:
    """
    Process a single USPTO-Chem JSON file.

    Args:
        json_path: Path to JSON file
        filter_ids: Optional set of patent IDs to keep (None = keep all)

    Returns:
        List of patent dicts with extracted data
    """
    patents = []

    try:
        with open(json_path) as f:
            data = json.load(f)

        for patent_json in data:
            # Extract patent number
            patent_number = extract_patent_number(patent_json)
            if not patent_number:
                continue

            # Check if in SureChEMBL (if filtering enabled)
            if filter_ids is not None and patent_number not in filter_ids:
                continue

            # Extract fields
            title = patent_json.get('title', '')
            abstract = patent_json.get('abstract', '')
            pub_date = patent_json.get('publication', {}).get('date', '')

            # Only include if we have at least title or abstract
            if title or abstract:
                patents.append({
                    'patent_number': patent_number,
                    'title': title or None,
                    'abstract': abstract or None,
                    'publication_date': pub_date or None
                })

    except Exception as e:
        log(f"ERROR processing {json_path.name}: {e}")

    return patents


def find_all_json_files(input_dir: Path) -> List[Path]:
    """
    Find all JSON files in input directory.

    Args:
        input_dir: Root directory containing USPTO-Chem data

    Returns:
        List of JSON file paths
    """
    json_files = []

    # Find all .json files recursively
    for json_file in input_dir.rglob('*.json'):
        json_files.append(json_file)

    # Sort by path for consistent processing
    json_files.sort()

    return json_files


def process_all_files(
    input_dir: Path,
    filter_ids: Optional[Set[str]],
    output_file: Path,
    limit_files: Optional[int] = None,
    batch_size: int = 500
) -> int:
    """
    Process all USPTO-Chem JSON files in batches (memory efficient).

    Args:
        input_dir: Directory containing JSON files
        filter_ids: Optional set of patent IDs to keep (None = keep all)
        output_file: Output parquet file path
        limit_files: Optional limit on number of files to process
        batch_size: Number of files to process before writing to disk

    Returns:
        Total number of patents processed
    """
    log(f"Finding JSON files in {input_dir}")
    log_memory_usage()

    json_files = find_all_json_files(input_dir)

    if not json_files:
        log("ERROR: No JSON files found!")
        sys.exit(1)

    log(f"Found {len(json_files):,} JSON files")

    # Apply limit if specified
    if limit_files and len(json_files) > limit_files:
        log(f"Limiting to {limit_files} files (test mode)")
        json_files = json_files[:limit_files]

    # Process in batches
    batch_files = []
    all_batches = []
    total_processed = 0
    total_matched = 0
    batch_num = 0

    for json_file in tqdm(json_files, desc="Processing JSON files"):
        patents = process_json_file(json_file, filter_ids)

        total_processed += 1
        total_matched += len(patents)

        batch_files.extend(patents)

        # Write batch to disk when batch_size reached
        if len(batch_files) >= batch_size or total_processed == len(json_files):
            if batch_files:
                batch_num += 1
                batch_df = pd.DataFrame(batch_files)

                # Remove duplicates within batch
                batch_df = batch_df.drop_duplicates(subset='patent_number', keep='first')

                all_batches.append(batch_df)

                log(f"Batch {batch_num}: {len(batch_df):,} patents, Total so far: {total_matched:,}")
                log_memory_usage()

                # Clear batch
                batch_files = []

        # Progress reporting every 100 files
        if total_processed % 100 == 0:
            log(f"Processed {total_processed}/{len(json_files)} files, {total_matched:,} patents so far...")
            log_memory_usage()

    # Combine all batches
    log("\n" + "="*60)
    log("Combining batches...")
    log("="*60)

    if all_batches:
        log(f"Concatenating {len(all_batches)} batches...")
        df = pd.concat(all_batches, ignore_index=True)

        # Remove duplicates across batches
        original_len = len(df)
        df = df.drop_duplicates(subset='patent_number', keep='first')

        if len(df) < original_len:
            log(f"Removed {original_len - len(df):,} duplicate patents")

        log(f"Final dataset: {len(df):,} unique patents")
        log_memory_usage()

        # Save to parquet
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_file, index=False)

        log(f"\nSaved {len(df):,} patents to {output_file}")
        log(f"File size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")

        # Show sample
        log("\n" + "="*60)
        log("Sample Patents")
        log("="*60)
        for i, row in df.head(3).iterrows():
            log(f"\nPatent: {row['patent_number']}")
            log(f"  Title: {row['title'][:80] if row['title'] else 'N/A'}...")
            log(f"  Abstract: {row['abstract'][:80] if row['abstract'] else 'N/A'}...")
            log(f"  Date: {row['publication_date']}")

        return len(df)
    else:
        log("WARNING: No patents processed!")
        return 0


def main():
    parser = argparse.ArgumentParser(description='Process USPTO-Chem JSON files to parquet')
    parser.add_argument('--input-dir', type=str, required=True,
                       help='Directory containing USPTO-Chem JSON files')
    parser.add_argument('--filter-ids', type=str,
                       help='File with US patent IDs from SureChEMBL (optional - omit to process ALL)')
    parser.add_argument('--output', type=str, required=True,
                       help='Output parquet file')
    parser.add_argument('--limit-files', type=int,
                       help='Limit number of files to process (test mode)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')

    args = parser.parse_args()

    log("="*60)
    log("USPTO-Chem JSON Processing")
    log("="*60)
    log(f"Input directory: {args.input_dir}")
    log(f"Filter IDs: {args.filter_ids if args.filter_ids else 'None (processing ALL)'}")
    log(f"Output: {args.output}")

    # Load filter IDs (optional)
    filter_ids = load_filter_ids(Path(args.filter_ids) if args.filter_ids else None)

    # Process all files (now handles writing internally)
    total_patents = process_all_files(
        input_dir=Path(args.input_dir),
        filter_ids=filter_ids,
        output_file=Path(args.output),
        limit_files=args.limit_files
    )

    if total_patents == 0:
        log("ERROR: No patents processed")
        sys.exit(1)

    log("\n" + "="*60)
    log("Processing Statistics")
    log("="*60)
    log(f"Total patents: {total_patents:,}")
    if filter_ids:
        log(f"Match rate: {total_patents/len(filter_ids)*100:.1f}% of SureChEMBL US patents")

    log("\nProcessing complete!")
    log_memory_usage()


if __name__ == '__main__':
    main()

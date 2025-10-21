#!/usr/bin/env python3
"""
Extract US Patent IDs from SureChEMBL

Reads SureChEMBL patents.parquet and extracts all US patent IDs.
This creates a filter list for USPTO processing (only biomedical patents).

Input:
    - SureChEMBL patents.parquet file

Output:
    - Text file with US patent IDs (one per line)

Usage:
    python extract_us_patent_ids.py \
        --input raw_data/patents/surechembl/2025-10-29/patents.parquet \
        --output state/patents/2025-10-29/us_patent_ids.txt
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import pyarrow.parquet as pq


def log(message: str) -> None:
    """Print message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)


def extract_us_patent_ids(input_file: Path, output_file: Path) -> int:
    """
    Extract all US patent IDs from SureChEMBL patents file.

    Args:
        input_file: SureChEMBL patents.parquet file
        output_file: Output text file for patent IDs

    Returns:
        Number of US patent IDs found
    """
    log(f"Reading SureChEMBL patents from {input_file}")

    if not input_file.exists():
        log(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)

    # Open parquet file
    parquet_file = pq.ParquetFile(input_file)

    log(f"Total rows in file: {parquet_file.metadata.num_rows}")

    us_patent_ids = set()

    # Stream through file in batches to avoid loading all into memory
    for batch in parquet_file.iter_batches(batch_size=100000):
        df_batch = batch.to_pandas()

        # Filter for US patents only
        us_patents = df_batch[df_batch['country'] == 'US']

        # Extract patent numbers
        us_patent_ids.update(us_patents['patent_number'].tolist())

        if len(us_patent_ids) % 100000 == 0:
            log(f"  Found {len(us_patent_ids)} US patents so far...")

    log(f"Total US patents found: {len(us_patent_ids)}")

    # Save to text file
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        for patent_id in sorted(us_patent_ids):
            f.write(f"{patent_id}\n")

    log(f"Saved to {output_file}")
    log(f"File size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")

    return len(us_patent_ids)


def main():
    parser = argparse.ArgumentParser(description='Extract US patent IDs from SureChEMBL')
    parser.add_argument('--input', type=str, required=True,
                       help='SureChEMBL patents.parquet file')
    parser.add_argument('--output', type=str, required=True,
                       help='Output text file for patent IDs')

    args = parser.parse_args()

    output_file = Path(args.output)

    # Skip if output file already exists
    if output_file.exists():
        log(f"US patent IDs file already exists: {output_file}")
        log(f"File size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
        log("Skipping extraction (delete file to re-extract)")
        return

    # Extract IDs
    count = extract_us_patent_ids(
        input_file=Path(args.input),
        output_file=output_file
    )

    log(f"\nExtraction complete! Found {count} US patents")


if __name__ == '__main__':
    main()

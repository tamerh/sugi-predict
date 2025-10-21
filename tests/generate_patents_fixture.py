#!/usr/bin/env python3
"""
Create Test Fixture for USPTO Enrichment Testing

Generates a list of 100 SureChEMBL patent IDs that are guaranteed to match
USPTO-Chem historical data (2001-2025). This allows testing the enrichment
logic with known matches instead of the default test data (which has 0% match
due to temporal mismatch).

Usage:
    python modules/patents/tests/create_test_fixture.py

Output:
    modules/patents/tests/fixtures/test_patent_ids_with_uspto.txt
"""

import os
import sys
import pandas as pd
from pathlib import Path

# Configuration
SURECHEMBL_PARQUET = "test_out/raw_data/patents/surechembl/2025-10-01/patents.parquet"
USPTO_PARQUET = "snapshots/raw_data/patents/historical_uspto/uspto_historical.parquet"
OUTPUT_FILE = "tests/fixtures/patents/test_patent_ids_with_uspto.txt"
TARGET_MATCHES = 100

def main():
    print("=" * 70)
    print("USPTO ENRICHMENT TEST FIXTURE GENERATOR")
    print("=" * 70)
    print()

    # Validate input files exist
    print("Step 1: Validating input files...")
    if not os.path.exists(SURECHEMBL_PARQUET):
        print(f"ERROR: SureChEMBL file not found: {SURECHEMBL_PARQUET}")
        sys.exit(1)

    if not os.path.exists(USPTO_PARQUET):
        print(f"ERROR: USPTO file not found: {USPTO_PARQUET}")
        sys.exit(1)

    print(f"  ✓ SureChEMBL: {SURECHEMBL_PARQUET}")
    print(f"  ✓ USPTO: {USPTO_PARQUET}")
    print()

    # Load USPTO patent numbers (small file, fast)
    print("Step 2: Loading USPTO patent numbers...")
    uspto_df = pd.read_parquet(USPTO_PARQUET, columns=['patent_number'])
    uspto_nums = set(uspto_df['patent_number'])
    print(f"  ✓ Loaded {len(uspto_nums):,} USPTO patent numbers")
    print()

    # Search for matches in SureChEMBL (using chunked reading)
    print("Step 3: Finding matching patents in SureChEMBL...")
    print("  (Reading in chunks to avoid memory issues)")
    print()

    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(SURECHEMBL_PARQUET)
    total_rows = parquet_file.metadata.num_rows
    print(f"  Total patents in SureChEMBL: {total_rows:,}")
    print()

    matches = []
    rows_processed = 0
    batch_size = 50000

    print(f"  Searching (batch_size={batch_size:,}):")

    for batch in parquet_file.iter_batches(
        batch_size=batch_size,
        columns=['patent_number', 'country', 'publication_date']
    ):
        df = batch.to_pandas()
        rows_processed += len(df)

        # Filter to US patents only
        us_df = df[df['country'] == 'US']

        # Find matches with USPTO
        us_matches = us_df[us_df['patent_number'].isin(uspto_nums)]

        if len(us_matches) > 0:
            matches.append(us_matches)
            total_matches = sum(len(m) for m in matches)
            print(f"    Batch {rows_processed//batch_size}: {rows_processed:,} rows processed, {total_matches} matches found")

            if total_matches >= TARGET_MATCHES:
                print(f"  ✓ Reached target of {TARGET_MATCHES} matches!")
                break

    if not matches:
        print("  ERROR: No matches found!")
        sys.exit(1)

    print()

    # Combine all matches
    print("Step 4: Preparing output...")
    all_matches = pd.concat(matches, ignore_index=True)
    fixture_patents = all_matches.head(TARGET_MATCHES)

    print(f"  Total matches found: {len(all_matches):,}")
    print(f"  Selected for fixture: {len(fixture_patents)}")
    print()

    # Show date range of selected patents
    pub_dates = pd.to_datetime(fixture_patents['publication_date'])
    print(f"  Publication date range: {pub_dates.min().date()} to {pub_dates.max().date()}")
    print()

    # Create output directory
    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write fixture file
    print("Step 5: Writing fixture file...")
    with open(OUTPUT_FILE, 'w') as f:
        # Header
        f.write("# Test fixture: SureChEMBL patent IDs with known USPTO matches\n")
        f.write(f"# Generated: {pd.Timestamp.now()}\n")
        f.write(f"# Total patents: {len(fixture_patents)}\n")
        f.write("#\n")
        f.write("# These patents are guaranteed to have USPTO enrichment data (2001-2025).\n")
        f.write("# Use with: --limit {} in test_overrides.yaml\n".format(len(fixture_patents)))
        f.write("#\n")
        f.write("# Usage:\n")
        f.write("#   1. Copy these patent IDs\n")
        f.write("#   2. Filter SureChEMBL patents.parquet to only these IDs\n")
        f.write("#   3. Run processing with --limit {}\n".format(len(fixture_patents)))
        f.write("#   4. Expected enrichment: ~100%\n")
        f.write("#\n")

        # Patent IDs (one per line)
        for patent_id in fixture_patents['patent_number']:
            f.write(f"{patent_id}\n")

    print(f"  ✓ Fixture saved to: {OUTPUT_FILE}")
    print()

    # Show examples
    print("Step 6: Verification")
    print(f"  First 10 patent IDs in fixture:")
    for i, (_, row) in enumerate(fixture_patents.head(10).iterrows(), 1):
        print(f"    {i:2d}. {row['patent_number']} ({row['publication_date']})")
    print()

    # Summary
    print("=" * 70)
    print("FIXTURE GENERATION COMPLETE")
    print("=" * 70)
    print()
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Patent IDs: {len(fixture_patents)}")
    print(f"Expected enrichment rate: ~100%")
    print()
    print("Next steps:")
    print("  1. Use these patent IDs to create a filtered test dataset")
    print("  2. Run patents processing with this filtered dataset")
    print("  3. Verify enrichment shows ~100% (all patents should be enriched)")
    print()


if __name__ == '__main__':
    main()

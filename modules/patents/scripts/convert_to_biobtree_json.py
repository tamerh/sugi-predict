#!/usr/bin/env python3
"""
Convert SureChEMBL parquet files to JSON format for biobtree ingestion.

This script reads patents, compounds, and mapping parquet files and converts them
to JSON format with the wrapped structure that biobtree's jsparser expects:
- {"patents": [...]}
- {"compounds": [...]}
- {"mappings": [...]}
"""

import argparse
import json
import os
import sys
from pathlib import Path
import pandas as pd
from datetime import datetime


def convert_parquet_to_json(input_dir: Path, output_dir: Path, verbose: bool = False):
    """
    Convert parquet files to JSON format for biobtree.

    Args:
        input_dir: Directory containing parquet files
        output_dir: Directory where JSON files will be written
        verbose: Print detailed progress
    """

    if verbose:
        print(f"\n{'='*80}")
        print(f"Converting SureChEMBL Parquet to Biobtree JSON")
        print(f"{'='*80}")
        print(f"Input directory:  {input_dir}")
        print(f"Output directory: {output_dir}")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define file mappings
    conversions = [
        {
            'input': 'patents.parquet',
            'output': 'patents.json',
            'wrapper_key': 'patents',
            'description': 'Patents metadata'
        },
        {
            'input': 'compounds.parquet',
            'output': 'compounds.json',
            'wrapper_key': 'compounds',
            'description': 'Chemical compounds'
        },
        {
            'input': 'patent_compound_map.parquet',
            'output': 'mapping.json',
            'wrapper_key': 'mappings',
            'description': 'Patent-compound mappings'
        }
    ]

    stats = {}

    for conversion in conversions:
        input_file = input_dir / conversion['input']
        output_file = output_dir / conversion['output']

        if not input_file.exists():
            print(f"⚠️  WARNING: {conversion['input']} not found, skipping...")
            continue

        if verbose:
            print(f"\n{conversion['description']}:")
            print(f"  Reading: {input_file}")

        # Read parquet file
        df = pd.read_parquet(input_file)

        if verbose:
            print(f"  Records: {len(df):,}")
            print(f"  Columns: {', '.join(df.columns)}")

        # Convert to list of dictionaries
        records = df.to_dict(orient='records')

        # Wrap with the expected key for jsparser
        wrapped_data = {conversion['wrapper_key']: records}

        # Write JSON file
        if verbose:
            print(f"  Writing: {output_file}")

        with open(output_file, 'w') as f:
            json.dump(wrapped_data, f, indent=2, default=str)

        # Collect statistics
        stats[conversion['wrapper_key']] = {
            'records': len(records),
            'file_size_mb': output_file.stat().st_size / (1024 * 1024)
        }

        if verbose:
            print(f"  ✓ Completed ({stats[conversion['wrapper_key']]['file_size_mb']:.2f} MB)")

    # Write summary
    summary_file = output_dir / 'conversion_summary.json'
    summary = {
        'conversion_date': datetime.now().isoformat(),
        'input_directory': str(input_dir),
        'output_directory': str(output_dir),
        'statistics': stats
    }

    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    if verbose:
        print(f"\n{'='*80}")
        print(f"Conversion Summary:")
        print(f"{'='*80}")
        for key, stat in stats.items():
            print(f"  {key:15s}: {stat['records']:8,} records ({stat['file_size_mb']:8.2f} MB)")
        print(f"\n✓ Summary written to: {summary_file}")
        print(f"✓ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Convert SureChEMBL parquet files to JSON for biobtree',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert parquet files in a release directory
  python convert_to_biobtree_json.py \\
      --input raw_data/patents/surechembl/2025-10-01 \\
      --output raw_data/patents/surechembl/2025-10-01

  # Convert with verbose output
  python convert_to_biobtree_json.py \\
      --input raw_data/patents/surechembl/2025-10-01 \\
      --output raw_data/patents/surechembl/2025-10-01 \\
      --verbose
        """
    )

    parser.add_argument(
        '--input',
        '-i',
        type=Path,
        required=True,
        help='Input directory containing parquet files'
    )

    parser.add_argument(
        '--output',
        '-o',
        type=Path,
        required=True,
        help='Output directory for JSON files (can be same as input)'
    )

    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Print detailed progress information'
    )

    args = parser.parse_args()

    # Validate input directory
    if not args.input.exists():
        print(f"ERROR: Input directory does not exist: {args.input}", file=sys.stderr)
        sys.exit(1)

    if not args.input.is_dir():
        print(f"ERROR: Input path is not a directory: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        stats = convert_parquet_to_json(args.input, args.output, args.verbose)

        if not stats:
            print("WARNING: No files were converted", file=sys.stderr)
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        print(f"ERROR: Conversion failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

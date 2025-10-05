#!/usr/bin/env python3
"""
Optimized Text Extraction from AACT Flat Files for Clinical Trials Pipeline

Uses efficient pandas merge operations instead of row-by-row lookups for 100x+ speedup.
"""

import os
import sys
import json
import pandas as pd
import argparse
import psutil
from datetime import datetime
from typing import List, Dict, Any, Optional
import re

def log_with_timestamp(message: str) -> None:
    """Prints a message with a prepended timestamp and memory usage."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    print(f"[{timestamp}] [MEM: {memory_mb:.1f}MB] {message}", flush=True)

def get_memory_usage() -> tuple:
    """Returns current memory usage in MB (used, available, percentage)."""
    memory = psutil.virtual_memory()
    return (
        memory.used / 1024 / 1024,
        memory.available / 1024 / 1024,
        memory.percent
    )

class AACTTextExtractorOptimized:
    """Optimized extractor using pandas merge operations."""

    def __init__(self, extract_dir: str):
        """Initialize the text extractor with extracted files directory."""
        self.extract_dir = extract_dir
        self.extraction_info = None

    def load_extraction_info(self) -> bool:
        """Load extraction info JSON to find table files."""
        info_path = os.path.join(self.extract_dir, 'extraction_info.json')

        if not os.path.exists(info_path):
            log_with_timestamp(f"ERROR: extraction_info.json not found in {self.extract_dir}")
            return False

        try:
            with open(info_path, 'r') as f:
                self.extraction_info = json.load(f)
            log_with_timestamp(f"Loaded extraction info: {self.extraction_info['total_files']} tables available")
            return True
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to load extraction info: {e}")
            return False

    def load_table(self, table_name: str) -> Optional[pd.DataFrame]:
        """Load a table from the extracted flat files."""
        if not self.extraction_info:
            log_with_timestamp("ERROR: Extraction info not loaded. Call load_extraction_info() first.")
            return None

        if table_name not in self.extraction_info['tables']:
            log_with_timestamp(f"WARNING: Table '{table_name}' not found in extracted files")
            return None

        table_info = self.extraction_info['tables'][table_name]
        table_path = table_info['path']

        if not os.path.exists(table_path):
            log_with_timestamp(f"ERROR: Table file not found: {table_path}")
            return None

        try:
            log_with_timestamp(f"Loading table: {table_name} ({table_info['size_mb']:.1f}MB)")
            start = datetime.now()

            # AACT flat files are pipe-delimited
            df = pd.read_csv(table_path, sep='|', low_memory=False)

            elapsed = (datetime.now() - start).total_seconds()
            log_with_timestamp(f"  Loaded {len(df):,} rows in {elapsed:.1f}s")
            return df

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to load table {table_name}: {e}")
            return None

    def extract_studies_text_optimized(self, limit: Optional[int] = None,
                                      include_detailed_description: bool = True,
                                      include_outcomes: bool = True,
                                      include_eligibility: bool = True,
                                      include_interventions: bool = True,
                                      min_summary_length: int = 50,
                                      exclude_withdrawn: bool = True) -> List[Dict[str, Any]]:
        """Extract text using efficient pandas merge operations."""

        log_with_timestamp("Starting OPTIMIZED text extraction using pandas merges...")

        # Load main studies table
        studies = self.load_table('studies')
        if studies is None:
            log_with_timestamp("ERROR: Cannot load studies table")
            return []

        log_with_timestamp(f"Initial studies count: {len(studies):,}")

        # Filter withdrawn studies if requested
        if exclude_withdrawn and 'overall_status' in studies.columns:
            original_count = len(studies)
            studies = studies[studies['overall_status'] != 'Withdrawn'].copy()
            log_with_timestamp(f"Filtered out {original_count - len(studies):,} withdrawn studies")

        # Load brief summaries first (required for filtering)
        log_with_timestamp("Loading brief summaries...")
        brief_summaries = self.load_table('brief_summaries')

        if brief_summaries is None:
            log_with_timestamp("ERROR: Cannot load brief summaries")
            return []

        # Merge studies with brief summaries
        log_with_timestamp("Merging studies with brief summaries...")
        merged = studies.merge(
            brief_summaries[['nct_id', 'description']],
            on='nct_id',
            how='left'
        )
        merged.rename(columns={'description': 'brief_summary'}, inplace=True)

        # Filter by minimum summary length
        merged['summary_length'] = merged['brief_summary'].fillna('').str.len()
        original_count = len(merged)
        merged = merged[merged['summary_length'] >= min_summary_length].copy()
        log_with_timestamp(f"Filtered by summary length: {len(merged):,} remain ({original_count - len(merged):,} filtered)")

        # Apply limit if specified (after filtering for accurate test)
        if limit:
            merged = merged.head(limit)
            log_with_timestamp(f"Limited to {limit} studies")

        # Get the NCT IDs we're keeping
        kept_nct_ids = set(merged['nct_id'].values)
        log_with_timestamp(f"Processing {len(kept_nct_ids):,} studies")

        # Load and merge detailed descriptions
        if include_detailed_description:
            log_with_timestamp("Loading and merging detailed descriptions...")
            detailed_descriptions = self.load_table('detailed_descriptions')
            if detailed_descriptions is not None:
                merged = merged.merge(
                    detailed_descriptions[['nct_id', 'description']],
                    on='nct_id',
                    how='left',
                    suffixes=('', '_detailed')
                )
                merged.rename(columns={'description_detailed': 'detailed_description'}, inplace=True)
                log_with_timestamp(f"  Added detailed descriptions")

        # Load and merge eligibility
        if include_eligibility:
            log_with_timestamp("Loading and merging eligibility criteria...")
            eligibilities = self.load_table('eligibilities')
            if eligibilities is not None:
                elig_cols = ['nct_id', 'criteria', 'gender', 'minimum_age', 'maximum_age']
                available_cols = ['nct_id'] + [c for c in elig_cols[1:] if c in eligibilities.columns]
                merged = merged.merge(
                    eligibilities[available_cols],
                    on='nct_id',
                    how='left',
                    suffixes=('', '_elig')
                )
                log_with_timestamp(f"  Added eligibility criteria")

        # Process outcomes (one-to-many relationship - needs grouping)
        outcomes_dict = {}
        if include_outcomes:
            log_with_timestamp("Loading and processing outcomes...")
            design_outcomes = self.load_table('design_outcomes')
            if design_outcomes is not None:
                # Filter to only kept studies
                design_outcomes = design_outcomes[design_outcomes['nct_id'].isin(kept_nct_ids)]
                log_with_timestamp(f"  Filtered to {len(design_outcomes):,} outcomes for kept studies")

                # Group outcomes by NCT ID
                for nct_id, group in design_outcomes.groupby('nct_id'):
                    outcomes_dict[nct_id] = []
                    for _, row in group.iterrows():
                        outcomes_dict[nct_id].append({
                            'outcome_type': str(row.get('outcome_type', '')),
                            'measure': str(row.get('measure', '')),
                            'description': str(row.get('description', ''))
                        })
                log_with_timestamp(f"  Grouped outcomes for {len(outcomes_dict):,} studies")

        # Process interventions (one-to-many relationship - needs grouping)
        interventions_dict = {}
        if include_interventions:
            log_with_timestamp("Loading and processing interventions...")
            interventions = self.load_table('interventions')
            if interventions is not None:
                # Filter to only kept studies
                interventions = interventions[interventions['nct_id'].isin(kept_nct_ids)]
                log_with_timestamp(f"  Filtered to {len(interventions):,} interventions for kept studies")

                # Group interventions by NCT ID
                for nct_id, group in interventions.groupby('nct_id'):
                    interventions_dict[nct_id] = []
                    for _, row in group.iterrows():
                        interventions_dict[nct_id].append({
                            'intervention_type': str(row.get('intervention_type', '')),
                            'name': str(row.get('name', '')),
                            'description': str(row.get('description', ''))
                        })
                log_with_timestamp(f"  Grouped interventions for {len(interventions_dict):,} studies")

        # Convert merged DataFrame to list of dicts
        log_with_timestamp("Converting to final format...")
        extracted_studies = []

        for idx, row in merged.iterrows():
            nct_id = row['nct_id']

            study_data = {
                'nct_id': nct_id,
                'brief_title': str(row.get('brief_title', '')),
                'official_title': str(row.get('official_title', '')),
                'brief_summary': str(row.get('brief_summary', '')),
                'overall_status': str(row.get('overall_status', '')),
                'phase': str(row.get('phase', '')),
                'study_type': str(row.get('study_type', '')),
                'enrollment': int(row.get('enrollment', 0)) if pd.notna(row.get('enrollment')) else 0,
                'start_date': str(row.get('start_date', '')),
                'completion_date': str(row.get('completion_date', ''))
            }

            # Add detailed description if present
            if include_detailed_description and 'detailed_description' in row:
                study_data['detailed_description'] = str(row.get('detailed_description', ''))

            # Add eligibility if present
            if include_eligibility and 'criteria' in row:
                study_data['eligibility'] = {
                    'criteria': str(row.get('criteria', '')),
                    'gender': str(row.get('gender', '')),
                    'minimum_age': str(row.get('minimum_age', '')),
                    'maximum_age': str(row.get('maximum_age', ''))
                }

            # Add outcomes if present
            if nct_id in outcomes_dict:
                study_data['outcomes'] = outcomes_dict[nct_id]

            # Add interventions if present
            if nct_id in interventions_dict:
                study_data['interventions'] = interventions_dict[nct_id]

            extracted_studies.append(study_data)

            # Progress logging every 10K studies
            if len(extracted_studies) % 10000 == 0:
                mem_used, mem_avail, mem_pct = get_memory_usage()
                log_with_timestamp(f"  Converted {len(extracted_studies):,} studies, Memory: {mem_pct:.1f}%")

        log_with_timestamp(f"Text extraction complete: {len(extracted_studies):,} studies extracted")
        return extracted_studies

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Extract text from AACT flat files (OPTIMIZED version)"
    )
    parser.add_argument(
        "--extract-dir", required=True,
        help="Directory containing extracted AACT flat files"
    )
    parser.add_argument(
        "--output-json", required=True,
        help="Output JSON file for extracted trials data"
    )
    parser.add_argument(
        "--output-csv",
        help="Optional output CSV file for extracted trials data"
    )
    parser.add_argument(
        "--limit", type=int,
        help="Limit number of studies to process (for testing)"
    )
    parser.add_argument(
        "--min-summary-length", type=int, default=50,
        help="Minimum brief summary length (default: 50)"
    )
    parser.add_argument(
        "--include-detailed-description", action="store_true", default=True,
        help="Include detailed descriptions"
    )
    parser.add_argument(
        "--include-outcomes", action="store_true", default=True,
        help="Include study outcomes"
    )
    parser.add_argument(
        "--include-eligibility", action="store_true", default=True,
        help="Include eligibility criteria"
    )
    parser.add_argument(
        "--include-interventions", action="store_true", default=True,
        help="Include interventions"
    )
    parser.add_argument(
        "--exclude-withdrawn", action="store_true", default=True,
        help="Exclude withdrawn studies"
    )

    args = parser.parse_args()

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Initialize extractor
        extractor = AACTTextExtractorOptimized(args.extract_dir)

        # Load extraction info
        if not extractor.load_extraction_info():
            log_with_timestamp("ERROR: Failed to load extraction info")
            return 1

        # Extract text from studies
        log_with_timestamp("=== Starting OPTIMIZED Text Extraction ===")
        start_time = datetime.now()

        extracted_studies = extractor.extract_studies_text_optimized(
            limit=args.limit,
            include_detailed_description=args.include_detailed_description,
            include_outcomes=args.include_outcomes,
            include_eligibility=args.include_eligibility,
            include_interventions=args.include_interventions,
            min_summary_length=args.min_summary_length,
            exclude_withdrawn=args.exclude_withdrawn
        )

        extraction_time = (datetime.now() - start_time).total_seconds()
        log_with_timestamp(f"Extraction took {extraction_time:.1f}s ({len(extracted_studies)/extraction_time:.1f} studies/sec)")

        if not extracted_studies:
            log_with_timestamp("WARNING: No studies extracted")
            return 1

        # Save to JSON
        log_with_timestamp(f"Saving {len(extracted_studies):,} studies to JSON: {args.output_json}")
        os.makedirs(os.path.dirname(os.path.abspath(args.output_json)), exist_ok=True)

        with open(args.output_json, 'w') as f:
            json.dump(extracted_studies, f, indent=2)

        json_size = os.path.getsize(args.output_json) / 1024 / 1024
        log_with_timestamp(f"JSON saved: {json_size:.1f}MB")

        # Save to CSV if requested
        if args.output_csv:
            log_with_timestamp(f"Saving basic info to CSV: {args.output_csv}")

            # Create simplified version for CSV
            csv_data = []
            for study in extracted_studies:
                csv_data.append({
                    'nct_id': study['nct_id'],
                    'brief_title': study['brief_title'],
                    'overall_status': study['overall_status'],
                    'phase': study['phase'],
                    'study_type': study['study_type'],
                    'enrollment': study['enrollment'],
                    'summary_length': len(study['brief_summary'])
                })

            df = pd.DataFrame(csv_data)
            df.to_csv(args.output_csv, index=False)

            csv_size = os.path.getsize(args.output_csv) / 1024 / 1024
            log_with_timestamp(f"CSV saved: {csv_size:.1f}MB")

        total_time = (datetime.now() - start_time).total_seconds()
        log_with_timestamp(f"=== Text Extraction Complete in {total_time:.1f}s ===")
        return 0

    except Exception as e:
        log_with_timestamp(f"ERROR during extraction: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

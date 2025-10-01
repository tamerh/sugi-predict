#!/usr/bin/env python3
"""
Text Extraction from AACT Flat Files for Clinical Trials Pipeline

Extracts and processes text content from AACT pipe-delimited flat files
for embedding generation and FAISS indexing.
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
    print(f"[{timestamp}] [MEM: {memory_mb:.1f}MB] {message}")

def get_memory_usage() -> tuple:
    """Returns current memory usage in MB (used, available, percentage)."""
    memory = psutil.virtual_memory()
    return (
        memory.used / 1024 / 1024,
        memory.available / 1024 / 1024,
        memory.percent
    )

class AACTTextExtractor:
    """Extracts text content from AACT flat files for embedding generation."""

    def __init__(self, extract_dir: str):
        """Initialize the text extractor with extracted files directory."""
        self.extract_dir = extract_dir
        self.extraction_info = None
        self.tables = {}

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

    def load_table(self, table_name: str, chunksize: Optional[int] = None) -> Optional[pd.DataFrame]:
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

            # AACT flat files are pipe-delimited
            if chunksize:
                # Return iterator for large files
                return pd.read_csv(table_path, sep='|', low_memory=False, chunksize=chunksize)
            else:
                df = pd.read_csv(table_path, sep='|', low_memory=False)
                log_with_timestamp(f"Loaded {len(df):,} rows from {table_name}")
                return df

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to load table {table_name}: {e}")
            return None

    def get_dataset_stats(self) -> Dict[str, int]:
        """Get basic statistics about the AACT dataset."""
        log_with_timestamp("Getting dataset statistics...")

        stats = {}

        # Load studies table
        studies = self.load_table('studies')
        if studies is not None:
            stats['total_studies'] = len(studies)

            # Filter by status if needed
            if 'overall_status' in studies.columns:
                status_counts = studies['overall_status'].value_counts()
                log_with_timestamp(f"  Study statuses: {dict(status_counts)}")

        # Load brief summaries
        brief_summaries = self.load_table('brief_summaries')
        if brief_summaries is not None:
            stats['studies_with_summary'] = len(brief_summaries)

        # Load detailed descriptions
        detailed_descriptions = self.load_table('detailed_descriptions')
        if detailed_descriptions is not None:
            stats['studies_with_description'] = len(detailed_descriptions)

        # Load outcomes
        design_outcomes = self.load_table('design_outcomes')
        if design_outcomes is not None:
            stats['total_outcomes'] = len(design_outcomes)

        # Load eligibilities
        eligibilities = self.load_table('eligibilities')
        if eligibilities is not None:
            stats['total_eligibilities'] = len(eligibilities)

        # Load interventions
        interventions = self.load_table('interventions')
        if interventions is not None:
            stats['total_interventions'] = len(interventions)

        for stat_name, value in stats.items():
            log_with_timestamp(f"  {stat_name}: {value:,}")

        return stats

    def extract_studies_text(self, limit: Optional[int] = None,
                           include_detailed_description: bool = True,
                           include_outcomes: bool = True,
                           include_eligibility: bool = True,
                           include_interventions: bool = True,
                           min_summary_length: int = 50,
                           exclude_withdrawn: bool = True) -> List[Dict[str, Any]]:
        """Extract text content from studies with related information."""

        log_with_timestamp("Starting text extraction from flat files...")

        # Load main studies table
        studies = self.load_table('studies')
        if studies is None:
            log_with_timestamp("ERROR: Cannot load studies table")
            return []

        # Filter withdrawn studies if requested
        if exclude_withdrawn and 'overall_status' in studies.columns:
            original_count = len(studies)
            studies = studies[studies['overall_status'] != 'Withdrawn']
            log_with_timestamp(f"Filtered out {original_count - len(studies):,} withdrawn studies")

        # Apply limit if specified
        if limit:
            studies = studies.head(limit)
            log_with_timestamp(f"Limited to {limit} studies")

        # Load related tables
        brief_summaries = self.load_table('brief_summaries')
        detailed_descriptions = self.load_table('detailed_descriptions') if include_detailed_description else None
        design_outcomes = self.load_table('design_outcomes') if include_outcomes else None
        eligibilities = self.load_table('eligibilities') if include_eligibility else None
        interventions = self.load_table('interventions') if include_interventions else None

        # Extract text for each study
        extracted_studies = []
        processed_count = 0
        skipped_count = 0

        log_with_timestamp(f"Processing {len(studies):,} studies...")

        for idx, study_row in studies.iterrows():
            nct_id = study_row['nct_id']

            # Get brief summary
            summary_text = ""
            if brief_summaries is not None:
                summary_rows = brief_summaries[brief_summaries['nct_id'] == nct_id]
                if not summary_rows.empty:
                    summary_text = str(summary_rows.iloc[0]['description']) if 'description' in summary_rows.columns else ""

            # Filter by minimum summary length
            if len(summary_text) < min_summary_length:
                skipped_count += 1
                continue

            # Build study data
            study_data = {
                'nct_id': nct_id,
                'brief_title': str(study_row.get('brief_title', '')),
                'official_title': str(study_row.get('official_title', '')),
                'brief_summary': summary_text,
                'overall_status': str(study_row.get('overall_status', '')),
                'phase': str(study_row.get('phase', '')),
                'study_type': str(study_row.get('study_type', '')),
                'enrollment': int(study_row.get('enrollment', 0)) if pd.notna(study_row.get('enrollment')) else 0,
                'start_date': str(study_row.get('start_date', '')),
                'completion_date': str(study_row.get('completion_date', ''))
            }

            # Add detailed description
            if detailed_descriptions is not None:
                desc_rows = detailed_descriptions[detailed_descriptions['nct_id'] == nct_id]
                if not desc_rows.empty:
                    study_data['detailed_description'] = str(desc_rows.iloc[0]['description']) if 'description' in desc_rows.columns else ""

            # Add outcomes
            if design_outcomes is not None:
                outcome_rows = design_outcomes[design_outcomes['nct_id'] == nct_id]
                if not outcome_rows.empty:
                    outcomes = []
                    for _, outcome_row in outcome_rows.iterrows():
                        outcomes.append({
                            'outcome_type': str(outcome_row.get('outcome_type', '')),
                            'measure': str(outcome_row.get('measure', '')),
                            'description': str(outcome_row.get('description', ''))
                        })
                    study_data['outcomes'] = outcomes

            # Add eligibility criteria
            if eligibilities is not None:
                elig_rows = eligibilities[eligibilities['nct_id'] == nct_id]
                if not elig_rows.empty:
                    elig_row = elig_rows.iloc[0]
                    study_data['eligibility'] = {
                        'criteria': str(elig_row.get('criteria', '')),
                        'gender': str(elig_row.get('gender', '')),
                        'minimum_age': str(elig_row.get('minimum_age', '')),
                        'maximum_age': str(elig_row.get('maximum_age', ''))
                    }

            # Add interventions
            if interventions is not None:
                int_rows = interventions[interventions['nct_id'] == nct_id]
                if not int_rows.empty:
                    intervention_list = []
                    for _, int_row in int_rows.iterrows():
                        intervention_list.append({
                            'intervention_type': str(int_row.get('intervention_type', '')),
                            'name': str(int_row.get('name', '')),
                            'description': str(int_row.get('description', ''))
                        })
                    study_data['interventions'] = intervention_list

            extracted_studies.append(study_data)
            processed_count += 1

            # Progress logging
            if processed_count % 1000 == 0:
                mem_used, mem_avail, mem_pct = get_memory_usage()
                log_with_timestamp(f"Processed {processed_count:,} studies (skipped {skipped_count:,}), Memory: {mem_pct:.1f}%")

        log_with_timestamp(f"Text extraction complete: {processed_count:,} studies extracted, {skipped_count:,} skipped")
        return extracted_studies

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Extract text from AACT flat files for clinical trials processing"
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
    parser.add_argument(
        "--stats-only", action="store_true",
        help="Only print dataset statistics, don't extract"
    )

    args = parser.parse_args()

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Initialize extractor
        extractor = AACTTextExtractor(args.extract_dir)

        # Load extraction info
        if not extractor.load_extraction_info():
            log_with_timestamp("ERROR: Failed to load extraction info")
            return 1

        # Get statistics
        stats = extractor.get_dataset_stats()

        if args.stats_only:
            log_with_timestamp("Statistics only mode - exiting")
            return 0

        # Extract text from studies
        log_with_timestamp("=== Starting Text Extraction ===")

        extracted_studies = extractor.extract_studies_text(
            limit=args.limit,
            include_detailed_description=args.include_detailed_description,
            include_outcomes=args.include_outcomes,
            include_eligibility=args.include_eligibility,
            include_interventions=args.include_interventions,
            min_summary_length=args.min_summary_length,
            exclude_withdrawn=args.exclude_withdrawn
        )

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

        log_with_timestamp("=== Text Extraction Complete ===")
        return 0

    except Exception as e:
        log_with_timestamp(f"ERROR during extraction: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""
Text Extraction from AACT Database for Clinical Trials Pipeline

Extracts and processes text content from AACT PostgreSQL database
for embedding generation and FAISS indexing.
"""

import os
import sys
import json
import psycopg2
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
    """Extracts text content from AACT database for embedding generation."""

    def __init__(self, database_url: str):
        """Initialize the text extractor with database connection."""
        self.database_url = database_url
        self.connection = None

    def connect(self) -> bool:
        """Establish connection to AACT database."""
        try:
            log_with_timestamp("Connecting to AACT database...")
            self.connection = psycopg2.connect(self.database_url)
            self.connection.set_session(autocommit=True)
            log_with_timestamp("Database connection established")
            return True
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to connect to database: {e}")
            return False

    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            log_with_timestamp("Database connection closed")

    def get_database_stats(self) -> Dict[str, int]:
        """Get basic statistics about the AACT database."""
        log_with_timestamp("Getting database statistics...")

        queries = {
            'total_studies': 'SELECT COUNT(*) FROM studies',
            'studies_with_summary': 'SELECT COUNT(*) FROM studies WHERE brief_summary IS NOT NULL AND brief_summary != \'\'',
            'studies_with_description': 'SELECT COUNT(*) FROM studies WHERE detailed_description IS NOT NULL AND detailed_description != \'\'',
            'total_outcomes': 'SELECT COUNT(*) FROM design_outcomes',
            'total_eligibilities': 'SELECT COUNT(*) FROM eligibilities WHERE criteria IS NOT NULL AND criteria != \'\'',
            'total_conditions': 'SELECT COUNT(*) FROM conditions',
            'total_interventions': 'SELECT COUNT(*) FROM interventions'
        }

        stats = {}
        cursor = self.connection.cursor()

        try:
            for stat_name, query in queries.items():
                cursor.execute(query)
                result = cursor.fetchone()
                stats[stat_name] = result[0] if result else 0
                log_with_timestamp(f"  {stat_name}: {stats[stat_name]:,}")

            return stats

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to get database stats: {e}")
            return {}
        finally:
            cursor.close()

    def extract_studies_text(self, limit: Optional[int] = None,
                           include_detailed_description: bool = True,
                           include_outcomes: bool = True,
                           include_eligibility: bool = True,
                           include_interventions: bool = True,
                           min_summary_length: int = 50,
                           exclude_withdrawn: bool = True) -> List[Dict[str, Any]]:
        """Extract text content from studies with related information."""

        log_with_timestamp("Extracting studies text content...")

        # Build the main query
        query_parts = []

        # Base study information
        base_query = """
        SELECT DISTINCT
            s.nct_id,
            s.brief_title,
            s.official_title,
            s.brief_summary,
            s.overall_status,
            s.phase,
            s.study_type,
            s.study_first_submitted_date,
            s.start_date,
            s.completion_date,
            s.enrollment,
            s.number_of_arms,
            s.number_of_groups"""

        if include_detailed_description:
            base_query += ",\n            s.detailed_description"

        base_query += "\n        FROM studies s"

        # Add WHERE conditions
        where_conditions = []

        # Require brief_summary
        where_conditions.append("s.brief_summary IS NOT NULL")
        where_conditions.append("s.brief_summary != ''")

        if min_summary_length > 0:
            where_conditions.append(f"LENGTH(s.brief_summary) >= {min_summary_length}")

        if exclude_withdrawn:
            where_conditions.append("s.overall_status != 'Withdrawn'")

        if where_conditions:
            base_query += "\n        WHERE " + " AND ".join(where_conditions)

        if limit:
            base_query += f"\n        LIMIT {limit}"

        log_with_timestamp(f"Executing main query{'with limit ' + str(limit) if limit else ''}...")

        cursor = self.connection.cursor()
        studies = []

        try:
            cursor.execute(base_query)
            rows = cursor.fetchall()

            # Get column names
            col_names = [desc[0] for desc in cursor.description]

            log_with_timestamp(f"Found {len(rows)} studies to process")

            for i, row in enumerate(rows):
                study = dict(zip(col_names, row))

                # Log progress every 10,000 studies
                if (i + 1) % 10000 == 0:
                    log_with_timestamp(f"Processed {i + 1}/{len(rows)} studies...")

                studies.append(study)

            log_with_timestamp(f"Extracted text from {len(studies)} studies")

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to extract studies: {e}")
            raise
        finally:
            cursor.close()

        # Add related information if requested
        if include_outcomes or include_eligibility or include_interventions:
            studies = self._add_related_information(studies, include_outcomes,
                                                  include_eligibility, include_interventions)

        return studies

    def _add_related_information(self, studies: List[Dict[str, Any]],
                               include_outcomes: bool = True,
                               include_eligibility: bool = True,
                               include_interventions: bool = True) -> List[Dict[str, Any]]:
        """Add related information (outcomes, eligibility, interventions) to studies."""

        if not studies:
            return studies

        nct_ids = [study['nct_id'] for study in studies]
        nct_id_placeholders = ','.join(['%s'] * len(nct_ids))

        cursor = self.connection.cursor()

        try:
            # Get outcomes
            if include_outcomes:
                log_with_timestamp("Fetching outcomes data...")
                outcomes_query = f"""
                SELECT nct_id, outcome_type, measure, description, time_frame
                FROM design_outcomes
                WHERE nct_id IN ({nct_id_placeholders})
                AND measure IS NOT NULL AND measure != ''
                ORDER BY nct_id, outcome_type, id
                """

                cursor.execute(outcomes_query, nct_ids)
                outcomes_rows = cursor.fetchall()

                # Group outcomes by nct_id
                outcomes_by_nct = {}
                for nct_id, outcome_type, measure, description, time_frame in outcomes_rows:
                    if nct_id not in outcomes_by_nct:
                        outcomes_by_nct[nct_id] = {'primary': [], 'secondary': []}

                    outcome_text = measure
                    if description:
                        outcome_text += f": {description}"
                    if time_frame:
                        outcome_text += f" (Time frame: {time_frame})"

                    if outcome_type and outcome_type.lower() == 'primary':
                        outcomes_by_nct[nct_id]['primary'].append(outcome_text)
                    else:
                        outcomes_by_nct[nct_id]['secondary'].append(outcome_text)

                log_with_timestamp(f"Found outcomes for {len(outcomes_by_nct)} studies")

            # Get eligibility criteria
            if include_eligibility:
                log_with_timestamp("Fetching eligibility data...")
                eligibility_query = f"""
                SELECT nct_id, criteria, gender, minimum_age, maximum_age
                FROM eligibilities
                WHERE nct_id IN ({nct_id_placeholders})
                AND criteria IS NOT NULL AND criteria != ''
                """

                cursor.execute(eligibility_query, nct_ids)
                eligibility_rows = cursor.fetchall()

                eligibility_by_nct = {}
                for nct_id, criteria, gender, min_age, max_age in eligibility_rows:
                    eligibility_by_nct[nct_id] = {
                        'criteria': criteria,
                        'gender': gender,
                        'minimum_age': min_age,
                        'maximum_age': max_age
                    }

                log_with_timestamp(f"Found eligibility criteria for {len(eligibility_by_nct)} studies")

            # Get interventions
            if include_interventions:
                log_with_timestamp("Fetching interventions data...")
                interventions_query = f"""
                SELECT nct_id, intervention_type, name, description
                FROM interventions
                WHERE nct_id IN ({nct_id_placeholders})
                AND name IS NOT NULL AND name != ''
                ORDER BY nct_id, intervention_type, id
                """

                cursor.execute(interventions_query, nct_ids)
                interventions_rows = cursor.fetchall()

                interventions_by_nct = {}
                for nct_id, intervention_type, name, description in interventions_rows:
                    if nct_id not in interventions_by_nct:
                        interventions_by_nct[nct_id] = []

                    intervention_text = name
                    if intervention_type:
                        intervention_text = f"{intervention_type}: {intervention_text}"
                    if description:
                        intervention_text += f" - {description}"

                    interventions_by_nct[nct_id].append(intervention_text)

                log_with_timestamp(f"Found interventions for {len(interventions_by_nct)} studies")

            # Get conditions
            log_with_timestamp("Fetching conditions data...")
            conditions_query = f"""
            SELECT nct_id, name
            FROM conditions
            WHERE nct_id IN ({nct_id_placeholders})
            AND name IS NOT NULL AND name != ''
            ORDER BY nct_id, name
            """

            cursor.execute(conditions_query, nct_ids)
            conditions_rows = cursor.fetchall()

            conditions_by_nct = {}
            for nct_id, name in conditions_rows:
                if nct_id not in conditions_by_nct:
                    conditions_by_nct[nct_id] = []
                conditions_by_nct[nct_id].append(name)

            log_with_timestamp(f"Found conditions for {len(conditions_by_nct)} studies")

            # Add related information to studies
            for study in studies:
                nct_id = study['nct_id']

                if include_outcomes:
                    outcomes = outcomes_by_nct.get(nct_id, {'primary': [], 'secondary': []})
                    study['primary_outcomes'] = outcomes['primary']
                    study['secondary_outcomes'] = outcomes['secondary']

                if include_eligibility:
                    study['eligibility'] = eligibility_by_nct.get(nct_id, {})

                if include_interventions:
                    study['interventions'] = interventions_by_nct.get(nct_id, [])

                study['conditions'] = conditions_by_nct.get(nct_id, [])

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to fetch related information: {e}")
            raise
        finally:
            cursor.close()

        return studies

def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""

    # Remove excessive whitespace and normalize
    text = re.sub(r'\s+', ' ', text.strip())

    # Remove common artifacts
    text = re.sub(r'\r\n|\r|\n', ' ', text)
    text = re.sub(r'\t+', ' ', text)

    # Remove HTML tags if present
    text = re.sub(r'<[^>]+>', '', text)

    return text.strip()

def export_to_json(studies: List[Dict[str, Any]], output_file: str) -> None:
    """Export studies data to JSON file."""
    log_with_timestamp(f"Exporting {len(studies)} studies to {output_file}")

    try:
        with open(output_file, 'w') as f:
            json.dump(studies, f, indent=2, default=str, ensure_ascii=False)

        file_size_mb = os.path.getsize(output_file) / 1024 / 1024
        log_with_timestamp(f"Export complete: {file_size_mb:.1f}MB")

    except Exception as e:
        log_with_timestamp(f"ERROR: Failed to export to JSON: {e}")
        raise

def export_to_csv(studies: List[Dict[str, Any]], output_file: str) -> None:
    """Export studies data to CSV file."""
    log_with_timestamp(f"Exporting {len(studies)} studies to {output_file}")

    try:
        # Flatten the data for CSV export
        flattened_studies = []
        for study in studies:
            flat_study = study.copy()

            # Convert lists to strings
            for key, value in flat_study.items():
                if isinstance(value, list):
                    flat_study[key] = ' | '.join(str(v) for v in value)
                elif isinstance(value, dict):
                    # For eligibility, create a formatted string
                    if key == 'eligibility':
                        eligibility_parts = []
                        if value.get('criteria'):
                            eligibility_parts.append(value['criteria'])
                        if value.get('gender'):
                            eligibility_parts.append(f"Gender: {value['gender']}")
                        if value.get('minimum_age'):
                            eligibility_parts.append(f"Min age: {value['minimum_age']}")
                        if value.get('maximum_age'):
                            eligibility_parts.append(f"Max age: {value['maximum_age']}")
                        flat_study[key] = ' | '.join(eligibility_parts)
                    else:
                        flat_study[key] = str(value)

            flattened_studies.append(flat_study)

        df = pd.DataFrame(flattened_studies)
        df.to_csv(output_file, index=False)

        file_size_mb = os.path.getsize(output_file) / 1024 / 1024
        log_with_timestamp(f"Export complete: {file_size_mb:.1f}MB")

    except Exception as e:
        log_with_timestamp(f"ERROR: Failed to export to CSV: {e}")
        raise

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Extract text content from AACT database for clinical trials processing"
    )
    parser.add_argument(
        "--database-url", required=True,
        help="PostgreSQL database URL (e.g., postgresql://user:pass@localhost:5432/aact)"
    )
    parser.add_argument(
        "--output-json",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--output-csv",
        help="Output CSV file path"
    )
    parser.add_argument(
        "--limit", type=int,
        help="Limit number of studies to extract (for testing)"
    )
    parser.add_argument(
        "--min-summary-length", type=int, default=50,
        help="Minimum length for brief_summary (default: 50)"
    )
    parser.add_argument(
        "--exclude-withdrawn", action="store_true", default=True,
        help="Exclude withdrawn studies"
    )
    parser.add_argument(
        "--include-detailed-description", action="store_true", default=True,
        help="Include detailed_description field"
    )
    parser.add_argument(
        "--include-outcomes", action="store_true", default=True,
        help="Include outcomes information"
    )
    parser.add_argument(
        "--include-eligibility", action="store_true", default=True,
        help="Include eligibility criteria"
    )
    parser.add_argument(
        "--include-interventions", action="store_true", default=True,
        help="Include interventions information"
    )
    parser.add_argument(
        "--stats-only", action="store_true",
        help="Only show database statistics, don't extract data"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.stats_only and not args.output_json and not args.output_csv:
        log_with_timestamp("ERROR: Must specify --output-json and/or --output-csv, or use --stats-only")
        return 1

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Initialize extractor
        extractor = AACTTextExtractor(args.database_url)

        # Connect to database
        if not extractor.connect():
            return 1

        # Get database statistics
        stats = extractor.get_database_stats()

        if args.stats_only:
            log_with_timestamp("Database statistics complete")
            return 0

        # Extract studies
        log_with_timestamp("=== Starting Text Extraction ===")
        studies = extractor.extract_studies_text(
            limit=args.limit,
            include_detailed_description=args.include_detailed_description,
            include_outcomes=args.include_outcomes,
            include_eligibility=args.include_eligibility,
            include_interventions=args.include_interventions,
            min_summary_length=args.min_summary_length,
            exclude_withdrawn=args.exclude_withdrawn
        )

        if not studies:
            log_with_timestamp("No studies found matching criteria")
            return 1

        # Export data
        if args.output_json:
            export_to_json(studies, args.output_json)

        if args.output_csv:
            export_to_csv(studies, args.output_csv)

        log_with_timestamp("=== Text Extraction Complete ===")
        return 0

    except KeyboardInterrupt:
        log_with_timestamp("Extraction interrupted by user")
        return 1
    except Exception as e:
        log_with_timestamp(f"ERROR during extraction: {e}")
        return 1
    finally:
        if 'extractor' in locals():
            extractor.disconnect()

if __name__ == "__main__":
    sys.exit(main())
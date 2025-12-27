#!/usr/bin/env python3
"""
Combined Download and Extract Script for Clinical Trials Pipeline

This script combines download_aact.py and extract_text_optimized.py into a single
workflow that manages the entire download → extract → state management process.

Flow:
1. Check if today's snapshot exists
2. If exists and update mode and already processed today → SKIP ALL
3. Otherwise: Download (if needed) → Extract zip → Process trials → Update state
"""

import os
import sys
import json
import zipfile
import requests
import psutil
import pandas as pd
import argparse
import re
import glob
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional

# Import tracking database module for incremental updates
from tracking_db import TrialsTracker, compute_trial_hash

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

def write_processed_chunks_json(output_path: str, chunk_files: List[Dict], no_changes: bool = False):
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
            log_with_timestamp(f"Preserving metadata for {len(existing_chunks)} existing chunks")
        except Exception as e:
            log_with_timestamp(f"WARNING: Could not read existing state: {e}")

    # Start with ALL existing chunks to preserve everything
    chunks_dict = existing_chunks.copy()

    # Update/add chunks from chunk_files
    for chunk_info in chunk_files:
        chunk_filename = chunk_info['filename']

        if chunk_filename in chunks_dict:
            # Chunk exists - preserve all existing metadata
            # Only update the fields we know about
            chunks_dict[chunk_filename]['num_trials'] = chunk_info['num_trials']
            chunks_dict[chunk_filename]['size_mb'] = chunk_info['size_mb']
            if 'status' not in chunks_dict[chunk_filename]:
                chunks_dict[chunk_filename]['status'] = 'ready_to_process'
        else:
            # New chunk - create fresh entry
            chunks_dict[chunk_filename] = {
                'status': 'ready_to_process',
                'num_trials': chunk_info['num_trials'],
                'size_mb': chunk_info['size_mb']
            }

    processed_chunks = {
        'last_update': datetime.now().isoformat(),
        'no_changes': no_changes,
        'chunks': chunks_dict
    }

    with open(output_path, 'w') as f:
        json.dump(processed_chunks, f, indent=2)

    log_with_timestamp(f"Written processed_chunks.json: {output_path}")

def determine_run_mode(processed_chunks_path: str, tracking_db_path: str) -> str:
    """
    Determine run mode based on state file and tracking DB.

    Returns:
        "skip": Already processed today, nothing to do
        "fresh": No state file, do full processing
        "update": State file exists but last_update != today, do incremental update
    """
    today = datetime.now().strftime('%Y-%m-%d')

    # Check if state file exists
    if not os.path.exists(processed_chunks_path):
        log_with_timestamp("No state file found → FRESH RUN")
        log_with_timestamp("Will process all trials and create tracking DB")
        return "fresh"

    # Check if tracking DB exists
    if not os.path.exists(tracking_db_path):
        log_with_timestamp("State file exists but no tracking DB → FRESH RUN")
        return "fresh"

    # Read state file to check last_update
    try:
        with open(processed_chunks_path, 'r') as f:
            state = json.load(f)

        last_update = state.get('last_update', '')
        last_update_date = last_update[:10] if last_update else ''

        if last_update_date == today:
            log_with_timestamp(f"✓ Already processed today ({today})")
            log_with_timestamp("→ SKIP (no work needed)")
            return "skip"
        else:
            log_with_timestamp(f"Last update: {last_update_date}, Today: {today}")
            log_with_timestamp("→ UPDATE MODE (incremental)")
            return "update"

    except Exception as e:
        log_with_timestamp(f"WARNING: Could not read state file: {e}")
        log_with_timestamp("→ FRESH RUN")
        return "fresh"


class AACTDownloader:
    """Downloads and manages AACT flat file exports."""

    def __init__(self, base_url: str = "https://aact.ctti-clinicaltrials.org/downloads"):
        """Initialize the AACT downloader."""
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BioYoda Clinical Trials Pipeline'
        })

    def get_latest_snapshot_info(self) -> dict:
        """Get information about the latest AACT flat file snapshot."""
        log_with_timestamp(f"Fetching snapshot information from {self.base_url}")

        try:
            response = self.session.get(self.base_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for "Flat Text Files" section
            flat_files_section = None
            for heading in soup.find_all(['h2', 'h3', 'h4', 'strong', 'b']):
                if 'flat' in heading.get_text().lower() and 'text' in heading.get_text().lower():
                    flat_files_section = heading
                    break

            if not flat_files_section:
                # Fallback: find all DigitalOcean Spaces links
                all_links = []
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if 'digitaloceanspaces.com' in href and 'Download File' in link.get_text():
                        all_links.append(href)

                if len(all_links) >= 2:
                    flat_file_url = all_links[1]  # Second link is flat files
                    snapshot_info = {
                        'filename': f"aact_flat_files_{datetime.now().strftime('%Y%m%d')}.zip",
                        'url': flat_file_url,
                        'type': 'flat_files'
                    }
                    log_with_timestamp(f"Found flat file snapshot: {snapshot_info['filename']}")
                    return snapshot_info
                else:
                    raise ValueError(f"Could not find flat file link. Found {len(all_links)} links.")

            # If we found the section, look for download link
            parent = flat_files_section.find_parent()
            download_link = None
            for link in parent.find_all('a', href=True):
                if 'digitaloceanspaces.com' in link['href']:
                    download_link = link['href']
                    break

            if not download_link:
                raise ValueError("Found flat file section but no download link")

            snapshot_info = {
                'filename': f"aact_flat_files_{datetime.now().strftime('%Y%m%d')}.zip",
                'url': download_link,
                'type': 'flat_files'
            }

            log_with_timestamp(f"Found flat file snapshot: {snapshot_info['filename']}")
            return snapshot_info

        except requests.RequestException as e:
            log_with_timestamp(f"ERROR: Failed to fetch snapshot information: {e}")
            raise
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to parse snapshot page: {e}")
            raise

    def check_existing_snapshot(self, download_dir: str) -> Optional[str]:
        """Check if we have today's snapshot. Returns path if exists, None otherwise."""
        today_str = datetime.now().strftime('%Y%m%d')
        existing_snapshots = glob.glob(os.path.join(download_dir, "aact_flat_files_*.zip"))

        if not existing_snapshots:
            return None

        for snapshot_path in existing_snapshots:
            snapshot_name = os.path.basename(snapshot_path)
            match = re.search(r'aact_flat_files_(\d{8})\.zip', snapshot_name)
            if match:
                file_date = match.group(1)
                if file_date == today_str:
                    # Found today's snapshot
                    return snapshot_path
                else:
                    # Found old snapshot - clean it up
                    log_with_timestamp(f"Removing old snapshot from {file_date}: {snapshot_name}")
                    try:
                        os.remove(snapshot_path)
                    except Exception as e:
                        log_with_timestamp(f"WARNING: Could not remove old snapshot: {e}")

        return None

    def download_snapshot(self, snapshot_info: dict, download_dir: str) -> str:
        """Download the AACT flat file snapshot if not already present."""
        filename = snapshot_info['filename']
        url = snapshot_info['url']
        local_path = os.path.join(download_dir, filename)

        # Check for existing snapshot
        existing_snapshot = self.check_existing_snapshot(download_dir)

        if existing_snapshot:
            file_size = os.path.getsize(existing_snapshot)
            log_with_timestamp(f"Today's snapshot already exists: {os.path.basename(existing_snapshot)} ({file_size/1024/1024:.1f}MB)")
            return existing_snapshot

        log_with_timestamp(f"Downloading flat file snapshot from {url}")
        os.makedirs(download_dir, exist_ok=True)

        try:
            response = self.session.get(url, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            last_log_mb = 0

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        current_mb = downloaded / (1024 * 1024)
                        if current_mb - last_log_mb >= 100:
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                log_with_timestamp(f"Downloaded {current_mb:.1f}MB ({progress:.1f}%)")
                            else:
                                log_with_timestamp(f"Downloaded {current_mb:.1f}MB")
                            last_log_mb = current_mb

            final_size = os.path.getsize(local_path)
            log_with_timestamp(f"Download complete: {final_size/1024/1024:.1f}MB")
            return local_path

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to download: {e}")
            if os.path.exists(local_path):
                os.remove(local_path)
            raise

    def extract_snapshot(self, zip_path: str, extract_dir: str) -> dict:
        """Extract the AACT flat file snapshot and return info about extracted files."""
        log_with_timestamp(f"Extracting snapshot to {extract_dir}")
        os.makedirs(extract_dir, exist_ok=True)

        try:
            extracted_files = {}
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                log_with_timestamp(f"Archive contains {len(file_list)} files")

                for file_info in zip_ref.infolist():
                    zip_ref.extract(file_info, extract_dir)

                    filename = file_info.filename
                    if filename.endswith('.txt'):
                        table_name = os.path.splitext(os.path.basename(filename))[0]
                        file_path = os.path.join(extract_dir, filename)
                        file_size = os.path.getsize(file_path)
                        extracted_files[table_name] = {
                            'path': file_path,
                            'size_mb': file_size / 1024 / 1024
                        }

            log_with_timestamp(f"Extracted {len(extracted_files)} table files")

            # Save extraction_info.json for the extract script
            info_path = os.path.join(extract_dir, 'extraction_info.json')
            info = {
                'extraction_date': datetime.now().isoformat(),
                'tables': extracted_files,
                'total_files': len(extracted_files),
                'total_size_mb': sum(f['size_mb'] for f in extracted_files.values())
            }
            with open(info_path, 'w') as f:
                json.dump(info, f, indent=2)

            return extracted_files

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to extract snapshot: {e}")
            raise


class AACTTextExtractor:
    """Extracts text from AACT flat files using pandas."""

    def __init__(self, extract_dir: str):
        self.extract_dir = extract_dir
        self.extraction_info = None

    def load_extraction_info(self) -> bool:
        """Load extraction info JSON."""
        info_path = os.path.join(self.extract_dir, 'extraction_info.json')

        if not os.path.exists(info_path):
            log_with_timestamp(f"ERROR: extraction_info.json not found in {self.extract_dir}")
            return False

        try:
            with open(info_path, 'r') as f:
                self.extraction_info = json.load(f)
            log_with_timestamp(f"Loaded extraction info: {self.extraction_info['total_files']} tables")
            return True
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to load extraction info: {e}")
            return False

    def load_table(self, table_name: str) -> Optional[pd.DataFrame]:
        """Load a table from the extracted flat files."""
        if not self.extraction_info:
            return None

        if table_name not in self.extraction_info['tables']:
            log_with_timestamp(f"WARNING: Table '{table_name}' not found")
            return None

        table_info = self.extraction_info['tables'][table_name]
        table_path = table_info['path']

        if not os.path.exists(table_path):
            return None

        try:
            log_with_timestamp(f"Loading table: {table_name} ({table_info['size_mb']:.1f}MB)")
            df = pd.read_csv(table_path, sep='|', low_memory=False)
            log_with_timestamp(f"  Loaded {len(df):,} rows")
            return df
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to load table {table_name}: {e}")
            return None

    def extract_adverse_events_summary(self, nct_id: str, trial_events: pd.DataFrame) -> Dict[str, Any]:
        """
        Extract summary adverse events data for a trial.

        Returns lightweight summary suitable for filtering/RAG.
        Includes counts, top common events, and affected organ systems.

        Args:
            nct_id: Trial NCT ID
            trial_events: Pre-filtered DataFrame containing only this trial's events
        """
        if len(trial_events) == 0:
            return {
                'has_events': False,
                'serious_events_count': 0,
                'other_events_count': 0
            }

        # Count by type
        serious = trial_events[trial_events['event_type'] == 'serious']
        other = trial_events[trial_events['event_type'] == 'other']

        # Get unique event terms (not counts per group, just unique events)
        serious_terms = set(serious['adverse_event_term'].dropna())
        other_terms = set(other['adverse_event_term'].dropna())

        # Calculate total subjects at risk (max across groups)
        total_at_risk = trial_events['subjects_at_risk'].max()
        if pd.isna(total_at_risk):
            total_at_risk = 0

        # Get most common events (top 5 by subjects affected)
        # Group by event term and sum subjects affected across groups
        event_counts = trial_events.groupby('adverse_event_term').agg({
            'subjects_affected': 'sum',
            'organ_system': 'first'  # Get organ system for each event
        }).reset_index()

        # Sort by subjects affected and get top 5
        top_events = event_counts.nlargest(5, 'subjects_affected')

        common_events = []
        for _, row in top_events.iterrows():
            term = row['adverse_event_term']
            count = row['subjects_affected']
            organ_sys = row['organ_system']

            if pd.notna(term) and pd.notna(count):
                percentage = round(float(count) / total_at_risk * 100, 1) if total_at_risk > 0 else 0
                common_events.append({
                    'term': str(term),
                    'organ_system': str(organ_sys) if pd.notna(organ_sys) else '',
                    'subjects_affected': int(count),
                    'percentage': percentage
                })

        # Get affected organ systems (unique, limited to 10)
        organ_systems = [str(os) for os in trial_events['organ_system'].dropna().unique()[:10]]

        return {
            'has_events': True,
            'serious_events_count': len(serious_terms),
            'other_events_count': len(other_terms),
            'total_subjects_at_risk': int(total_at_risk),
            'common_events': common_events,
            'organ_systems_affected': organ_systems
        }

    def extract_studies_text(self, limit: Optional[int] = None,
                            include_detailed_description: bool = True,
                            include_outcomes: bool = True,
                            include_eligibility: bool = True,
                            include_interventions: bool = True,
                            include_conditions: bool = True,
                            include_sponsors: bool = True,
                            include_facilities: bool = True,
                            include_study_arms: bool = True,
                            include_publications: bool = True,
                            include_adverse_events: bool = True,
                            min_summary_length: int = 50,
                            exclude_withdrawn: bool = True,
                            nct_ids_file: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract text using efficient pandas merge operations."""

        log_with_timestamp("Starting text extraction...")

        # Load main studies table
        studies = self.load_table('studies')
        if studies is None:
            return []

        log_with_timestamp(f"Initial studies count: {len(studies):,}")

        # Filter by NCT ID list if provided
        nct_ids_filter_applied = False
        if nct_ids_file and os.path.exists(nct_ids_file):
            log_with_timestamp(f"Loading NCT ID filter from: {nct_ids_file}")
            nct_ids = []
            with open(nct_ids_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        nct_ids.append(line)

            studies = studies[studies['nct_id'].isin(nct_ids)].copy()
            log_with_timestamp(f"Filtered to {len(studies):,} studies")
            nct_ids_filter_applied = True
        elif exclude_withdrawn and 'overall_status' in studies.columns:
            original_count = len(studies)
            studies = studies[studies['overall_status'] != 'Withdrawn'].copy()
            log_with_timestamp(f"Filtered out {original_count - len(studies):,} withdrawn studies")

        # Load and merge brief summaries
        brief_summaries = self.load_table('brief_summaries')
        if brief_summaries is None:
            return []

        merged = studies.merge(
            brief_summaries[['nct_id', 'description']],
            on='nct_id',
            how='left'
        )
        merged.rename(columns={'description': 'brief_summary'}, inplace=True)

        # Filter by summary length
        merged['summary_length'] = merged['brief_summary'].fillna('').str.len()
        merged = merged[merged['summary_length'] >= min_summary_length].copy()

        # Apply limit if specified
        if limit and not nct_ids_filter_applied:
            merged = merged.head(limit)

        kept_nct_ids = set(merged['nct_id'].values)
        log_with_timestamp(f"Processing {len(kept_nct_ids):,} studies")

        # Add detailed descriptions
        if include_detailed_description:
            detailed_descriptions = self.load_table('detailed_descriptions')
            if detailed_descriptions is not None:
                merged = merged.merge(
                    detailed_descriptions[['nct_id', 'description']],
                    on='nct_id',
                    how='left',
                    suffixes=('', '_detailed')
                )
                merged.rename(columns={'description_detailed': 'detailed_description'}, inplace=True)

        # Add eligibility
        if include_eligibility:
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

        # Process outcomes (one-to-many)
        outcomes_dict = {}
        if include_outcomes:
            design_outcomes = self.load_table('design_outcomes')
            if design_outcomes is not None:
                design_outcomes = design_outcomes[design_outcomes['nct_id'].isin(kept_nct_ids)]
                for nct_id, group in design_outcomes.groupby('nct_id'):
                    outcomes_dict[nct_id] = []
                    for _, row in group.iterrows():
                        outcomes_dict[nct_id].append({
                            'outcome_type': str(row.get('outcome_type', '')),
                            'measure': str(row.get('measure', '')),
                            'description': str(row.get('description', ''))
                        })

        # Process interventions (one-to-many)
        interventions_dict = {}
        if include_interventions:
            interventions = self.load_table('interventions')
            if interventions is not None:
                interventions = interventions[interventions['nct_id'].isin(kept_nct_ids)]
                for nct_id, group in interventions.groupby('nct_id'):
                    interventions_dict[nct_id] = []
                    for _, row in group.iterrows():
                        interventions_dict[nct_id].append({
                            'intervention_type': str(row.get('intervention_type', '')),
                            'name': str(row.get('name', '')),
                            'description': str(row.get('description', ''))
                        })

        # Process conditions/diseases (one-to-many)
        conditions_dict = {}
        if include_conditions:
            conditions = self.load_table('conditions')
            if conditions is not None:
                conditions = conditions[conditions['nct_id'].isin(kept_nct_ids)]
                log_with_timestamp(f"Processing conditions for {len(conditions):,} condition entries")
                for nct_id, group in conditions.groupby('nct_id'):
                    conditions_dict[nct_id] = []
                    for _, row in group.iterrows():
                        condition_name = str(row.get('name', ''))
                        if condition_name and condition_name != 'nan':
                            conditions_dict[nct_id].append(condition_name)

        # Process sponsors (one-to-many)
        sponsors_dict = {}
        if include_sponsors:
            sponsors = self.load_table('sponsors')
            if sponsors is not None:
                sponsors = sponsors[sponsors['nct_id'].isin(kept_nct_ids)]
                log_with_timestamp(f"Processing sponsors for {len(sponsors):,} sponsor entries")
                for nct_id, group in sponsors.groupby('nct_id'):
                    sponsors_dict[nct_id] = []
                    for _, row in group.iterrows():
                        sponsor_name = str(row.get('name', ''))
                        if sponsor_name and sponsor_name != 'nan':
                            sponsors_dict[nct_id].append({
                                'name': sponsor_name,
                                'agency_class': str(row.get('agency_class', '')),
                                'role': str(row.get('lead_or_collaborator', ''))
                            })

        # Process facilities/locations (one-to-many)
        facilities_dict = {}
        if include_facilities:
            facilities = self.load_table('facilities')
            if facilities is not None:
                facilities = facilities[facilities['nct_id'].isin(kept_nct_ids)]
                log_with_timestamp(f"Processing facilities for {len(facilities):,} facility entries")
                for nct_id, group in facilities.groupby('nct_id'):
                    facilities_dict[nct_id] = []
                    for _, row in group.iterrows():
                        facility_name = str(row.get('name', ''))
                        if facility_name and facility_name != 'nan':
                            facilities_dict[nct_id].append({
                                'name': facility_name,
                                'city': str(row.get('city', '')),
                                'state': str(row.get('state', '')),
                                'country': str(row.get('country', '')),
                                'status': str(row.get('status', ''))
                            })

        # Process study arms/groups (one-to-many)
        study_arms_dict = {}
        if include_study_arms:
            design_groups = self.load_table('design_groups')
            if design_groups is not None:
                design_groups = design_groups[design_groups['nct_id'].isin(kept_nct_ids)]
                log_with_timestamp(f"Processing study arms for {len(design_groups):,} arm entries")
                for nct_id, group in design_groups.groupby('nct_id'):
                    study_arms_dict[nct_id] = []
                    for _, row in group.iterrows():
                        arm_title = str(row.get('title', ''))
                        if arm_title and arm_title != 'nan':
                            study_arms_dict[nct_id].append({
                                'title': arm_title,
                                'type': str(row.get('group_type', '')),
                                'description': str(row.get('description', ''))
                            })

        # Process publications/references (one-to-many)
        publications_dict = {}
        if include_publications:
            study_references = self.load_table('study_references')
            if study_references is not None:
                study_references = study_references[study_references['nct_id'].isin(kept_nct_ids)]
                log_with_timestamp(f"Processing publications for {len(study_references):,} reference entries")
                for nct_id, group in study_references.groupby('nct_id'):
                    publications_dict[nct_id] = []
                    for _, row in group.iterrows():
                        pmid_raw = row.get('pmid', '')
                        # Convert to string and clean up (remove .0 from floats)
                        pmid = str(pmid_raw).replace('.0', '') if pd.notna(pmid_raw) else ''
                        # Only include references with valid PMIDs
                        if pmid and pmid != 'nan' and pmid != '':
                            publications_dict[nct_id].append({
                                'pmid': pmid,
                                'reference_type': str(row.get('reference_type', '')),
                                'citation': str(row.get('citation', ''))
                            })

        # Process adverse events (summary extraction)
        adverse_events_dict = {}
        if include_adverse_events:
            reported_events = self.load_table('reported_events')
            if reported_events is not None:
                # Filter to only kept trials
                reported_events = reported_events[reported_events['nct_id'].isin(kept_nct_ids)]
                log_with_timestamp(f"Processing adverse events for {len(reported_events):,} event records")

                # Get unique trials with events
                trials_with_events = reported_events['nct_id'].unique()
                log_with_timestamp(f"Found {len(trials_with_events):,} trials with adverse events data")

                # Pre-group events by nct_id for O(1) lookup instead of O(n) scan
                log_with_timestamp("Pre-grouping adverse events by trial (this is fast)...")
                grouped_events = reported_events.groupby('nct_id')
                log_with_timestamp("Grouping complete. Extracting summaries...")

                # Extract summary for each trial using pre-grouped data
                for i, nct_id in enumerate(trials_with_events):
                    try:
                        trial_events = grouped_events.get_group(nct_id)
                        adverse_events_dict[nct_id] = self.extract_adverse_events_summary(
                            nct_id, trial_events
                        )
                    except KeyError:
                        # No events for this trial (shouldn't happen but be safe)
                        pass

                    # Progress every 10K trials
                    if (i + 1) % 10000 == 0:
                        log_with_timestamp(f"  Processed {i + 1:,}/{len(trials_with_events):,} adverse event summaries...")

                log_with_timestamp(f"Extracted adverse events summaries for {len(adverse_events_dict):,} trials")

        # Convert to list of dicts
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

            if include_detailed_description and 'detailed_description' in row:
                study_data['detailed_description'] = str(row.get('detailed_description', ''))

            if include_eligibility and 'criteria' in row:
                study_data['eligibility'] = {
                    'criteria': str(row.get('criteria', '')),
                    'gender': str(row.get('gender', '')),
                    'minimum_age': str(row.get('minimum_age', '')),
                    'maximum_age': str(row.get('maximum_age', ''))
                }

            if nct_id in outcomes_dict:
                study_data['outcomes'] = outcomes_dict[nct_id]

            if nct_id in interventions_dict:
                study_data['interventions'] = interventions_dict[nct_id]

            if nct_id in conditions_dict:
                study_data['conditions'] = conditions_dict[nct_id]
            else:
                study_data['conditions'] = []

            if nct_id in sponsors_dict:
                study_data['sponsors'] = sponsors_dict[nct_id]
            else:
                study_data['sponsors'] = []

            if nct_id in facilities_dict:
                study_data['facilities'] = facilities_dict[nct_id]
            else:
                study_data['facilities'] = []

            if nct_id in study_arms_dict:
                study_data['study_arms'] = study_arms_dict[nct_id]
            else:
                study_data['study_arms'] = []

            if nct_id in publications_dict:
                study_data['publications'] = publications_dict[nct_id]
            else:
                study_data['publications'] = []

            if nct_id in adverse_events_dict:
                study_data['adverse_events_summary'] = adverse_events_dict[nct_id]
            else:
                study_data['adverse_events_summary'] = {
                    'has_events': False,
                    'serious_events_count': 0,
                    'other_events_count': 0
                }

            extracted_studies.append(study_data)

        log_with_timestamp(f"Extraction complete: {len(extracted_studies):,} studies")
        return extracted_studies


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Combined download and extract for clinical trials"
    )
    parser.add_argument("--download-dir", required=True)
    parser.add_argument("--extract-dir", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--processed-chunks-output", required=True)
    parser.add_argument("--tracking-db", required=True)
    parser.add_argument("--chunk-size", type=int, default=0)
    parser.add_argument("--min-summary-length", type=int, default=50)
    parser.add_argument("--include-detailed-description", action="store_true", default=True)
    parser.add_argument("--include-outcomes", action="store_true", default=True)
    parser.add_argument("--include-eligibility", action="store_true", default=True)
    parser.add_argument("--include-interventions", action="store_true", default=True)
    parser.add_argument("--include-conditions", action="store_true", default=True)
    parser.add_argument("--include-sponsors", action="store_true", default=True)
    parser.add_argument("--include-facilities", action="store_true", default=True)
    parser.add_argument("--include-study-arms", action="store_true", default=True)
    parser.add_argument("--include-publications", action="store_true", default=True)
    parser.add_argument("--include-adverse-events", action="store_true", default=True)
    parser.add_argument("--exclude-withdrawn", action="store_true", default=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--nct-ids-file")

    args = parser.parse_args()

    # System info
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # ====================================================================
        # STEP 1: Determine what mode to run in
        # ====================================================================
        run_mode = determine_run_mode(args.processed_chunks_output, args.tracking_db)

        if run_mode == "skip":
            log_with_timestamp("=== COMPLETE (nothing to do) ===")

            # IMPORTANT: Update the file timestamp so Snakemake knows this rule ran
            # This ensures the checkpoint always executes even when skipping
            if os.path.exists(args.processed_chunks_output):
                with open(args.processed_chunks_output, 'r') as f:
                    state = json.load(f)

                num_chunks = len(state.get('chunks', {}))
                log_with_timestamp(f"Preserving state: {num_chunks} chunks")

                # Write back to update file modification time
                with open(args.processed_chunks_output, 'w') as f:
                    json.dump(state, f, indent=2)

                log_with_timestamp("✓ State file updated (timestamp only, all metadata preserved)")

            return 0

        # ====================================================================
        # STEP 2: Download snapshot
        # ====================================================================
        log_with_timestamp("=== STEP 1: Download ===")
        downloader = AACTDownloader()
        snapshot_info = downloader.get_latest_snapshot_info()
        snapshot_path = downloader.download_snapshot(snapshot_info, args.download_dir)

        # ====================================================================
        # STEP 3: Extract snapshot (always extract when running)
        # ====================================================================
        log_with_timestamp("=== STEP 2: Extract ===")
        extracted_files = downloader.extract_snapshot(snapshot_path, args.extract_dir)

        # ====================================================================
        # STEP 4: Process trials and generate chunks
        # ====================================================================
        log_with_timestamp("=== STEP 3: Process Trials ===")

        extractor = AACTTextExtractor(args.extract_dir)
        if not extractor.load_extraction_info():
            return 1

        extracted_studies = extractor.extract_studies_text(
            limit=args.limit,
            include_detailed_description=args.include_detailed_description,
            include_outcomes=args.include_outcomes,
            include_eligibility=args.include_eligibility,
            include_interventions=args.include_interventions,
            include_conditions=args.include_conditions,
            include_sponsors=args.include_sponsors,
            include_facilities=args.include_facilities,
            include_study_arms=args.include_study_arms,
            include_publications=args.include_publications,
            include_adverse_events=args.include_adverse_events,
            min_summary_length=args.min_summary_length,
            exclude_withdrawn=args.exclude_withdrawn,
            nct_ids_file=args.nct_ids_file
        )

        if not extracted_studies:
            log_with_timestamp("WARNING: No studies extracted")
            return 1

        # ====================================================================
        # STEP 5: Filter to changes only (if in update mode)
        # ====================================================================
        if run_mode == "update":
            log_with_timestamp("=== UPDATE MODE: Identifying changes ===")

            if not os.path.exists(args.tracking_db):
                log_with_timestamp("ERROR: Update mode but no tracking DB (shouldn't happen)")
                return 1

            tracker = TrialsTracker(args.tracking_db)
            known_nct_ids = set(tracker.get_all_nct_ids())
            log_with_timestamp(f"Trials in tracking DB: {len(known_nct_ids):,}")

            new_trials = []
            updated_trials = []

            for trial in extracted_studies:
                nct_id = trial['nct_id']
                trial_hash = compute_trial_hash(trial)

                if nct_id not in known_nct_ids:
                    new_trials.append(trial)
                else:
                    db_record = tracker.get_trial(nct_id)
                    if db_record and trial_hash != db_record['content_hash']:
                        updated_trials.append(trial)

            log_with_timestamp(f"New trials: {len(new_trials):,}")
            log_with_timestamp(f"Updated trials: {len(updated_trials):,}")

            extracted_studies = new_trials + updated_trials

            if not extracted_studies:
                log_with_timestamp("No changes detected - updating last_update timestamp only")

                # Update last_update timestamp while preserving existing chunks
                if os.path.exists(args.processed_chunks_output):
                    try:
                        with open(args.processed_chunks_output, 'r') as f:
                            existing_state = json.load(f)

                        # Update only the timestamp, keep existing chunks
                        existing_state['last_update'] = datetime.now().isoformat()
                        existing_state['no_changes'] = False  # Keep chunks available for processing

                        with open(args.processed_chunks_output, 'w') as f:
                            json.dump(existing_state, f, indent=2)

                        log_with_timestamp("State file updated with new timestamp, chunks preserved")
                    except Exception as e:
                        log_with_timestamp(f"WARNING: Could not update state file: {e}")

                return 0

        # ====================================================================
        # STEP 6: Generate chunks and update state
        # ====================================================================
        output_dir = os.path.dirname(os.path.abspath(args.output_json))
        os.makedirs(output_dir, exist_ok=True)

        if args.chunk_size > 0:
            # Chunked output
            log_with_timestamp(f"=== Chunking: {args.chunk_size} trials per chunk ===")

            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(output_dir))))
            raw_chunked_dir = os.path.join(base_dir, "raw_data", "clinical_trials", "chunked")
            os.makedirs(raw_chunked_dir, exist_ok=True)

            if run_mode == "update":
                date_prefix = datetime.now().strftime('%Y%m%d')
                chunk_prefix = f"trials_update_{date_prefix}_chunk"

                # Clean up old update chunks
                old_chunks = glob.glob(os.path.join(raw_chunked_dir, "trials_update_*.json"))
                for old_chunk in old_chunks:
                    if date_prefix not in os.path.basename(old_chunk):
                        log_with_timestamp(f"Removing old chunk: {os.path.basename(old_chunk)}")
                        os.remove(old_chunk)
            else:
                chunk_prefix = "trials_chunk"

            total_studies = len(extracted_studies)
            num_chunks = (total_studies + args.chunk_size - 1) // args.chunk_size

            chunk_files = []
            for chunk_idx in range(num_chunks):
                start_idx = chunk_idx * args.chunk_size
                end_idx = min(start_idx + args.chunk_size, total_studies)
                chunk_data = extracted_studies[start_idx:end_idx]

                chunk_filename = f"{chunk_prefix}_{chunk_idx+1:04d}.json"
                chunk_path = os.path.join(raw_chunked_dir, chunk_filename)

                with open(chunk_path, 'w') as f:
                    json.dump(chunk_data, f, indent=2)

                chunk_size_mb = os.path.getsize(chunk_path) / 1024 / 1024
                chunk_files.append({
                    'filename': chunk_filename,
                    'num_trials': len(chunk_data),
                    'size_mb': round(chunk_size_mb, 2)
                })

            write_processed_chunks_json(args.processed_chunks_output, chunk_files, no_changes=False)
            log_with_timestamp(f"Created {num_chunks} chunks")

        else:
            # Single file output
            log_with_timestamp("=== Single file output ===")
            with open(args.output_json, 'w') as f:
                json.dump(extracted_studies, f, indent=2)

            json_size = os.path.getsize(args.output_json) / 1024 / 1024

            single_file_info = [{
                'filename': os.path.basename(args.output_json),
                'num_trials': len(extracted_studies),
                'size_mb': round(json_size, 2)
            }]
            write_processed_chunks_json(args.processed_chunks_output, single_file_info, no_changes=False)

        # ====================================================================
        # STEP 7: Update tracking database
        # ====================================================================
        if args.tracking_db:
            log_with_timestamp("=== Updating Tracking Database ===")
            tracker = TrialsTracker(args.tracking_db)

            tracking_records = []
            for study in extracted_studies:
                last_update_date = study.get('last_update_submitted',
                                            study.get('completion_date',
                                                     datetime.now().strftime('%Y-%m-%d')))
                content_hash = compute_trial_hash(study)

                tracking_records.append({
                    'nct_id': study['nct_id'],
                    'last_update_date': last_update_date,
                    'content_hash': content_hash
                })

            tracker.add_or_update_batch(tracking_records, batch_size=1000)
            log_with_timestamp(f"Updated {len(tracking_records):,} records in tracking DB")

        log_with_timestamp("=== COMPLETE ===")
        return 0

    except Exception as e:
        log_with_timestamp(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

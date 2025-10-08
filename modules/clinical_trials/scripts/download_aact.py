#!/usr/bin/env python3
"""
AACT Flat Files Download for Clinical Trials Pipeline

Downloads the latest AACT flat file export (pipe-delimited TSV files)
and extracts them for processing.
"""

import os
import sys
import json
import time
import zipfile
import requests
import psutil
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
import argparse

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

            # Parse HTML to find the flat file export link
            soup = BeautifulSoup(response.content, 'html.parser')

            # AACT page structure: find sections with headers, then get the download link
            # Look for "Flat Text Files" section
            flat_files_section = None
            for heading in soup.find_all(['h2', 'h3', 'h4', 'strong', 'b']):
                if 'flat' in heading.get_text().lower() and 'text' in heading.get_text().lower():
                    flat_files_section = heading
                    break

            if not flat_files_section:
                # Fallback: find all DigitalOcean Spaces links and take the second one
                # (first is PostgreSQL dump, second is flat files, third is COVID)
                all_links = []
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if 'digitaloceanspaces.com' in href and 'Download File' in link.get_text():
                        all_links.append(href)

                if len(all_links) >= 2:
                    flat_file_url = all_links[1]  # Second link is flat files
                    log_with_timestamp(f"Found flat file link (position-based): {flat_file_url}")

                    snapshot_info = {
                        'filename': f"aact_flat_files_{datetime.now().strftime('%Y%m%d')}.zip",
                        'url': flat_file_url,
                        'text': 'Flat Text Files',
                        'type': 'flat_files'
                    }

                    log_with_timestamp(f"Found flat file snapshot: {snapshot_info['filename']}")
                    return snapshot_info
                else:
                    raise ValueError(f"Could not find flat file link. Found {len(all_links)} DigitalOcean links.")

            # If we found the section, look for download link near it
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
                'text': 'Flat Text Files',
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

    def download_snapshot(self, snapshot_info: dict, download_dir: str, force: bool = False) -> str:
        """Download the AACT flat file snapshot."""
        filename = snapshot_info['filename']
        url = snapshot_info['url']
        local_path = os.path.join(download_dir, filename)

        # Check if file already exists
        if os.path.exists(local_path) and not force:
            file_size = os.path.getsize(local_path)
            log_with_timestamp(f"Snapshot already exists: {local_path} ({file_size/1024/1024:.1f}MB)")
            log_with_timestamp("Skipping download (use --force to re-download)")
            return local_path
        elif os.path.exists(local_path) and force:
            log_with_timestamp(f"Force mode: removing existing file {local_path}")
            os.remove(local_path)

        log_with_timestamp(f"Downloading flat file snapshot from {url}")
        log_with_timestamp(f"Saving to: {local_path}")

        try:
            # Create directory if it doesn't exist
            os.makedirs(download_dir, exist_ok=True)

            # Download with progress tracking
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

                        # Log progress every 100MB
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

        except requests.RequestException as e:
            log_with_timestamp(f"ERROR: Failed to download snapshot: {e}")
            if os.path.exists(local_path):
                os.remove(local_path)
            raise
        except Exception as e:
            log_with_timestamp(f"ERROR: Unexpected error during download: {e}")
            if os.path.exists(local_path):
                os.remove(local_path)
            raise

    def extract_snapshot(self, zip_path: str, extract_dir: str, skip_if_exists: bool = False) -> dict:
        """Extract the AACT flat file snapshot and return info about extracted files."""

        # Check if extraction already exists
        extraction_info_path = os.path.join(extract_dir, 'extraction_info.json')
        if skip_if_exists and os.path.exists(extraction_info_path):
            log_with_timestamp(f"Extraction info already exists: {extraction_info_path}")
            log_with_timestamp("Skipping extraction (use --force to re-extract)")

            # Load and return existing extraction info
            try:
                with open(extraction_info_path, 'r') as f:
                    info = json.load(f)
                extracted_files = info.get('tables', {})
                log_with_timestamp(f"Loaded existing extraction info: {len(extracted_files)} tables")
                return extracted_files
            except Exception as e:
                log_with_timestamp(f"WARNING: Could not load extraction info: {e}")
                log_with_timestamp("Proceeding with fresh extraction...")

        log_with_timestamp(f"Extracting snapshot to {extract_dir}")

        try:
            os.makedirs(extract_dir, exist_ok=True)

            extracted_files = {}
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                log_with_timestamp(f"Archive contains {len(file_list)} files")

                # Extract all files
                for file_info in zip_ref.infolist():
                    zip_ref.extract(file_info, extract_dir)

                    # Track important table files
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

            # Log important tables
            important_tables = ['studies', 'brief_summaries', 'detailed_descriptions',
                               'design_outcomes', 'eligibilities', 'interventions']
            for table in important_tables:
                if table in extracted_files:
                    info = extracted_files[table]
                    log_with_timestamp(f"  {table}: {info['size_mb']:.1f}MB")

            return extracted_files

        except zipfile.BadZipFile as e:
            log_with_timestamp(f"ERROR: Invalid zip file: {e}")
            raise
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to extract snapshot: {e}")
            raise

    def save_extraction_info(self, extracted_files: dict, output_path: str) -> None:
        """Save information about extracted files for use by other scripts."""
        info = {
            'extraction_date': datetime.now().isoformat(),
            'tables': extracted_files,
            'total_files': len(extracted_files),
            'total_size_mb': sum(f['size_mb'] for f in extracted_files.values())
        }

        with open(output_path, 'w') as f:
            json.dump(info, f, indent=2)

        log_with_timestamp(f"Extraction info saved to {output_path}")

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Download and extract AACT flat files for clinical trials processing"
    )
    parser.add_argument(
        "--download-dir", default="./raw_data/clinical_trials",
        help="Directory to store downloaded files"
    )
    parser.add_argument(
        "--extract-dir", default="./raw_data/clinical_trials/extracted",
        help="Directory to extract files to"
    )
    parser.add_argument(
        "--download-only", action="store_true",
        help="Only download, don't extract"
    )
    parser.add_argument(
        "--extract-only",
        help="Only extract from existing file (provide file path)"
    )
    parser.add_argument(
        "--skip-if-exists", action="store_true", default=True,
        help="Skip download/extraction if files already exist (default: True)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-download and re-extraction even if files exist"
    )

    args = parser.parse_args()

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        downloader = AACTDownloader()
        download_path = None

        # Override skip_if_exists with force flag
        skip_if_exists = args.skip_if_exists and not args.force

        # Download phase
        if not args.extract_only:
            log_with_timestamp("=== Starting AACT Flat Files Download ===")

            if args.force:
                log_with_timestamp("Force mode enabled: will re-download and re-extract")
            elif skip_if_exists:
                log_with_timestamp("Skip mode enabled: will skip if files exist")

            # Get latest snapshot info
            snapshot_info = downloader.get_latest_snapshot_info()

            # Download snapshot
            download_path = downloader.download_snapshot(snapshot_info, args.download_dir, force=args.force)

            if args.download_only:
                log_with_timestamp("Download complete! Use --extract-only to extract the files.")
                return 0

        # Extract phase
        if not args.download_only:
            log_with_timestamp("=== Starting Extraction ===")

            extract_file = args.extract_only or download_path
            if not extract_file or not os.path.exists(extract_file):
                log_with_timestamp("ERROR: No zip file available for extraction")
                return 1

            # Extract files
            extracted_files = downloader.extract_snapshot(extract_file, args.extract_dir, skip_if_exists=skip_if_exists)

            # Save extraction info for other scripts
            info_path = os.path.join(args.extract_dir, 'extraction_info.json')
            downloader.save_extraction_info(extracted_files, info_path)

            log_with_timestamp("=== Download and Extraction Complete ===")
            log_with_timestamp(f"Extracted {len(extracted_files)} tables to {args.extract_dir}")
            log_with_timestamp(f"Total size: {sum(f['size_mb'] for f in extracted_files.values()):.1f}MB")

        return 0

    except Exception as e:
        log_with_timestamp(f"ERROR during setup: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
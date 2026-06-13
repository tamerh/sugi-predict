#!/usr/bin/env python3
"""
USPTO Manual File Handler

Handles manually downloaded USPTO patent XML files.
Since USPTO bulk data portal requires CAPTCHA, files must be downloaded manually.

Manual Download Instructions:
1. Visit: https://data.uspto.gov/bulkdata/datasets/PTGRXML (Grants)
2. Visit: https://data.uspto.gov/bulkdata/datasets/APPXML (Applications)
3. Download ZIP files manually (bypass CAPTCHA)
4. Place in manual directory (configured in config.yaml)

Filename Pattern: ip[ag]YYMMDD.zip
- ipa251016.zip = Applications for week ending 2025-10-16
- ipg251014.zip = Grants for week ending 2025-10-14

Usage:
    # Process manual files
    python download_uspto.py --raw-dir work/raw_data/patents/uspto/2025-10-29 \
        --manual-dir /path/to/manual_downloads
"""

import os
import sys
import requests
import time
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from tqdm import tqdm


def log(message: str) -> None:
    """Print message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)


class USPTODownloader:
    """Handles USPTO patent data files (manual downloads only)."""

    def __init__(self, raw_dir: Path, manual_dir: Optional[Path] = None, test_mode: bool = False, debug: bool = False):
        self.raw_dir = Path(raw_dir)
        self.manual_dir = Path(manual_dir) if manual_dir else None
        self.test_mode = test_mode
        self.debug = debug

        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        log(f"USPTO File Handler initialized")
        log(f"Output directory: {self.raw_dir}")
        log(f"Manual directory: {self.manual_dir}")
        log(f"Test mode: {test_mode}")

    def list_manual_files(self) -> List[Dict]:
        """
        List manually downloaded USPTO files from manual directory.

        Returns:
            List of file info dicts with 'path', 'filename', 'date', 'dataset'

        Raises:
            FileNotFoundError: If manual directory doesn't exist or no files found
        """
        if not self.manual_dir:
            raise ValueError("Manual directory not configured")

        if not self.manual_dir.exists():
            raise FileNotFoundError(
                f"Manual download directory not found: {self.manual_dir}\n"
                f"Please download USPTO files manually and place them in this directory.\n"
                f"Instructions:\n"
                f"  1. Visit: https://data.uspto.gov/bulkdata/datasets/PTGRXML (Grants)\n"
                f"  2. Visit: https://data.uspto.gov/bulkdata/datasets/APPXML (Applications)\n"
                f"  3. Download ZIP files manually\n"
                f"  4. Place in: {self.manual_dir}"
            )

        log(f"Scanning manual directory: {self.manual_dir}")

        files = []
        for file_path in self.manual_dir.glob("*.zip"):
            filename = file_path.name

            # Parse filename: ip[ag]YYMMDD.zip
            # ipa = applications, ipg = grants
            if filename.startswith('ipa'):
                dataset = 'application'
            elif filename.startswith('ipg'):
                dataset = 'grant'
            else:
                log(f"Warning: Skipping unrecognized file: {filename}")
                continue

            # Extract date from filename
            file_date = self._parse_uspto_filename(filename)

            if file_date:
                files.append({
                    'path': file_path,
                    'filename': filename,
                    'date': file_date,
                    'dataset': dataset
                })
                log(f"  Found: {filename} ({dataset}, {file_date.strftime('%Y-%m-%d')})")
            else:
                log(f"Warning: Could not parse date from filename: {filename}")

        if not files:
            raise FileNotFoundError(
                f"No USPTO ZIP files found in manual directory: {self.manual_dir}\n"
                f"Expected filename pattern: ipa251016.zip or ipg251014.zip\n"
                f"Please download files manually and place them in this directory."
            )

        log(f"Found {len(files)} manual USPTO files")
        return sorted(files, key=lambda x: x['date'])

    def _parse_uspto_filename(self, filename: str) -> Optional[datetime]:
        """
        Parse USPTO filename to extract date.

        Filename pattern: ip[ag]YYMMDD.zip
        - ipa251016.zip -> 2025-10-16 (Applications)
        - ipg251014.zip -> 2025-10-14 (Grants)

        Args:
            filename: USPTO ZIP filename

        Returns:
            datetime object or None if parsing fails
        """
        try:
            # Remove extension
            name = filename.replace('.zip', '')

            # Extract date part (last 6 digits)
            # ipa251016 -> 251016
            date_str = name[-6:]

            # Parse YYMMDD
            yy = int(date_str[0:2])
            mm = int(date_str[2:4])
            dd = int(date_str[4:6])

            # Convert YY to YYYY
            # Heuristic: if YY >= 90, assume 19YY, else 20YY
            if yy >= 90:
                yyyy = 1900 + yy
            else:
                yyyy = 2000 + yy

            return datetime(yyyy, mm, dd)
        except Exception as e:
            if self.debug:
                log(f"Could not parse date from {filename}: {e}")
            return None

    def organize_manual_files(self) -> Dict:
        """
        Organize manually downloaded USPTO files.
        Creates symlinks in the output directory pointing to manual files.

        Returns:
            Dict with statistics

        Raises:
            FileNotFoundError: If manual directory doesn't exist or no files found
        """
        log("\n" + "="*60)
        log("Organizing manually downloaded USPTO files")
        log("="*60)

        # List manual files (this will raise error if directory missing or empty)
        manual_files = self.list_manual_files()

        stats = {
            'total_files': len(manual_files),
            'organized': 0,
            'skipped': 0,
            'files': []
        }

        for file_info in manual_files:
            source_path = file_info['path']
            filename = file_info['filename']
            target_path = self.raw_dir / filename

            # Skip if symlink already exists
            if target_path.exists():
                if target_path.is_symlink() and target_path.resolve() == source_path.resolve():
                    log(f"  Already organized: {filename}")
                    stats['skipped'] += 1
                else:
                    log(f"  File exists (removing old): {filename}")
                    target_path.unlink()
                    os.symlink(source_path, target_path)
                    stats['organized'] += 1
            else:
                # Create symlink
                os.symlink(source_path, target_path)
                log(f"  Organized: {filename}")
                stats['organized'] += 1

            stats['files'].append({
                'filename': filename,
                'date': file_info['date'].strftime('%Y-%m-%d'),
                'dataset': file_info['dataset']
            })

        log(f"\nOrganization complete:")
        log(f"  Total files: {stats['total_files']}")
        log(f"  Organized: {stats['organized']}")
        log(f"  Skipped (already exists): {stats['skipped']}")

        return stats

    def download_file(self, file_info: Dict) -> bool:
        """Download a single USPTO file."""
        url = file_info['url']
        filename = file_info['filename']
        output_path = self.raw_dir / filename

        # Skip if already exists
        if output_path.exists():
            log(f"Already exists: {filename}")
            return True

        log(f"Downloading: {filename}")

        try:
            response = requests.get(url, stream=True, timeout=300)
            response.raise_for_status()

            # Get file size
            total_size = int(response.headers.get('content-length', 0))

            # Download with progress bar
            with open(output_path, 'wb') as f:
                if total_size > 0:
                    with tqdm(total=total_size, unit='B', unit_scale=True, desc=filename) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                else:
                    # No content-length header
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            log(f"Downloaded: {filename} ({total_size / 1024 / 1024:.1f} MB)")
            return True

        except Exception as e:
            log(f"Error downloading {filename}: {e}")
            if output_path.exists():
                output_path.unlink()  # Remove partial file
            return False

    def download_latest(self, datasets: List[str] = ['application', 'grant'],
                       year: int = None, limit_files: int = None,
                       tracking_file: Path = None) -> Dict:
        """
        Download latest USPTO files.

        Args:
            datasets: List of datasets to download ('application' and/or 'grant')
            year: Year to download (default: current year)
            limit_files: Limit number of files per dataset (for testing)
            tracking_file: JSON file tracking already downloaded files

        Returns:
            Dict with download statistics
        """
        if year is None:
            year = datetime.now().year

        # Load tracking data
        already_downloaded = set()
        if tracking_file and tracking_file.exists():
            with open(tracking_file) as f:
                tracking = json.load(f)
                already_downloaded = set(tracking.get('sources', {}).get('uspto', {}).get('files_downloaded', []))

        stats = {
            'total_files': 0,
            'downloaded': 0,
            'skipped': 0,
            'failed': 0,
            'files': []
        }

        for dataset in datasets:
            log(f"\n{'='*60}")
            log(f"Processing dataset: {dataset}")
            log(f"{'='*60}")

            # List available files
            available_files = self.list_available_files(dataset, year, weeks_back=8)

            if limit_files:
                available_files = available_files[:limit_files]

            stats['total_files'] += len(available_files)

            for file_info in available_files:
                filename = file_info['filename']

                # Check if already downloaded
                if filename in already_downloaded:
                    log(f"Already downloaded (tracking): {filename}")
                    stats['skipped'] += 1
                    continue

                # Download
                success = self.download_file(file_info)

                if success:
                    stats['downloaded'] += 1
                    stats['files'].append(filename)
                else:
                    stats['failed'] += 1

        log(f"\n{'='*60}")
        log(f"Download Summary")
        log(f"{'='*60}")
        log(f"Total files: {stats['total_files']}")
        log(f"Downloaded: {stats['downloaded']}")
        log(f"Skipped: {stats['skipped']}")
        log(f"Failed: {stats['failed']}")

        return stats


def main():
    parser = argparse.ArgumentParser(description='Organize manually downloaded USPTO patent data')
    parser.add_argument('--raw-dir', type=str, required=True,
                       help='Raw data output directory')
    parser.add_argument('--manual-dir', type=str, required=True,
                       help='Directory containing manually downloaded USPTO ZIP files')
    parser.add_argument('--test-mode', action='store_true',
                       help='Test mode')
    parser.add_argument('--debug', action='store_true',
                       help='Debug mode (verbose logging)')

    args = parser.parse_args()

    try:
        # Create handler
        handler = USPTODownloader(
            raw_dir=Path(args.raw_dir),
            manual_dir=Path(args.manual_dir),
            test_mode=args.test_mode,
            debug=args.debug
        )

        # Organize manual files
        stats = handler.organize_manual_files()

        log("\nUSPTO file organization complete!")
        log(f"Files ready in: {args.raw_dir}")

    except FileNotFoundError as e:
        log(f"\nERROR: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"\nERROR: Unexpected error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

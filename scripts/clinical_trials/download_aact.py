#!/usr/bin/env python3
"""
AACT Database Download and Setup for Clinical Trials Pipeline

Downloads the latest AACT PostgreSQL snapshot and sets up the database
for text extraction and processing.
"""

import os
import sys
import json
import time
import requests
import subprocess
import psutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
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
    """Downloads and manages AACT database snapshots."""

    def __init__(self, base_url: str = "https://aact.ctti-clinicaltrials.org/snapshots"):
        """Initialize the AACT downloader."""
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BioYoda Clinical Trials Pipeline'
        })

    def get_latest_snapshot_info(self) -> dict:
        """Get information about the latest AACT snapshot."""
        log_with_timestamp(f"Fetching snapshot information from {self.base_url}")

        try:
            response = self.session.get(self.base_url, timeout=30)
            response.raise_for_status()

            # Parse HTML to find the latest snapshot
            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for download links (AACT typically provides .dmp files)
            snapshot_links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.endswith('.dmp') or href.endswith('.zip'):
                    snapshot_links.append({
                        'filename': os.path.basename(href),
                        'url': urljoin(self.base_url, href),
                        'text': link.get_text().strip()
                    })

            if not snapshot_links:
                raise ValueError("No snapshot files found on the downloads page")

            # Sort by filename (usually contains date) to get latest
            latest_snapshot = sorted(snapshot_links, key=lambda x: x['filename'])[-1]

            log_with_timestamp(f"Found latest snapshot: {latest_snapshot['filename']}")
            return latest_snapshot

        except requests.RequestException as e:
            log_with_timestamp(f"ERROR: Failed to fetch snapshot information: {e}")
            raise
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to parse snapshot page: {e}")
            raise

    def download_snapshot(self, snapshot_info: dict, download_dir: str) -> str:
        """Download the AACT snapshot file."""
        filename = snapshot_info['filename']
        url = snapshot_info['url']
        local_path = os.path.join(download_dir, filename)

        # Check if file already exists
        if os.path.exists(local_path):
            file_size = os.path.getsize(local_path)
            log_with_timestamp(f"Snapshot already exists: {local_path} ({file_size/1024/1024:.1f}MB)")
            return local_path

        log_with_timestamp(f"Downloading snapshot from {url}")
        log_with_timestamp(f"Saving to: {local_path}")

        try:
            # Create directory if it doesn't exist
            os.makedirs(download_dir, exist_ok=True)

            # Download with progress tracking
            response = self.session.get(url, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Log progress every 100MB
                        if downloaded % (100 * 1024 * 1024) == 0:
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                log_with_timestamp(f"Downloaded {downloaded/1024/1024:.1f}MB ({progress:.1f}%)")
                            else:
                                log_with_timestamp(f"Downloaded {downloaded/1024/1024:.1f}MB")

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

class PostgreSQLManager:
    """Manages PostgreSQL database operations for AACT."""

    def __init__(self, host: str = "localhost", port: str = "5432",
                 user: str = None, password: str = ""):
        """Initialize PostgreSQL manager."""
        self.host = host
        self.port = port
        self.user = user or os.getenv('USER')
        self.password = password

    def check_postgres_connection(self) -> bool:
        """Check if PostgreSQL is accessible."""
        log_with_timestamp("Checking PostgreSQL connection...")

        try:
            cmd = [
                'psql',
                f'--host={self.host}',
                f'--port={self.port}',
                f'--username={self.user}',
                '--command=SELECT version();',
                '--quiet',
                'postgres'
            ]

            env = os.environ.copy()
            if self.password:
                env['PGPASSWORD'] = self.password

            result = subprocess.run(cmd, capture_output=True, text=True, env=env)

            if result.returncode == 0:
                log_with_timestamp("PostgreSQL connection successful")
                return True
            else:
                log_with_timestamp(f"PostgreSQL connection failed: {result.stderr}")
                return False

        except FileNotFoundError:
            log_with_timestamp("ERROR: psql command not found. Please install PostgreSQL client.")
            return False
        except Exception as e:
            log_with_timestamp(f"ERROR: Unexpected error checking PostgreSQL: {e}")
            return False

    def database_exists(self, database_name: str) -> bool:
        """Check if database exists."""
        try:
            cmd = [
                'psql',
                f'--host={self.host}',
                f'--port={self.port}',
                f'--username={self.user}',
                '--tuples-only',
                '--quiet',
                '--command=SELECT 1 FROM pg_database WHERE datname=\'{}\''.format(database_name),
                'postgres'
            ]

            env = os.environ.copy()
            if self.password:
                env['PGPASSWORD'] = self.password

            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            return result.returncode == 0 and result.stdout.strip() == '1'

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to check database existence: {e}")
            return False

    def create_database(self, database_name: str) -> bool:
        """Create database if it doesn't exist."""
        if self.database_exists(database_name):
            log_with_timestamp(f"Database '{database_name}' already exists")
            return True

        log_with_timestamp(f"Creating database '{database_name}'...")

        try:
            cmd = [
                'psql',
                f'--host={self.host}',
                f'--port={self.port}',
                f'--username={self.user}',
                '--command=CREATE DATABASE "{}";'.format(database_name),
                'postgres'
            ]

            env = os.environ.copy()
            if self.password:
                env['PGPASSWORD'] = self.password

            result = subprocess.run(cmd, capture_output=True, text=True, env=env)

            if result.returncode == 0:
                log_with_timestamp(f"Database '{database_name}' created successfully")
                return True
            else:
                log_with_timestamp(f"ERROR: Failed to create database: {result.stderr}")
                return False

        except Exception as e:
            log_with_timestamp(f"ERROR: Unexpected error creating database: {e}")
            return False

    def drop_database(self, database_name: str) -> bool:
        """Drop database if it exists."""
        if not self.database_exists(database_name):
            log_with_timestamp(f"Database '{database_name}' does not exist")
            return True

        log_with_timestamp(f"Dropping database '{database_name}'...")

        try:
            cmd = [
                'psql',
                f'--host={self.host}',
                f'--port={self.port}',
                f'--username={self.user}',
                '--command=DROP DATABASE "{}";'.format(database_name),
                'postgres'
            ]

            env = os.environ.copy()
            if self.password:
                env['PGPASSWORD'] = self.password

            result = subprocess.run(cmd, capture_output=True, text=True, env=env)

            if result.returncode == 0:
                log_with_timestamp(f"Database '{database_name}' dropped successfully")
                return True
            else:
                log_with_timestamp(f"ERROR: Failed to drop database: {result.stderr}")
                return False

        except Exception as e:
            log_with_timestamp(f"ERROR: Unexpected error dropping database: {e}")
            return False

    def restore_database(self, dump_file: str, database_name: str) -> bool:
        """Restore database from dump file."""
        if not os.path.exists(dump_file):
            log_with_timestamp(f"ERROR: Dump file not found: {dump_file}")
            return False

        log_with_timestamp(f"Restoring database from {dump_file}")
        log_with_timestamp(f"This may take 10-30 minutes depending on system performance...")

        try:
            cmd = [
                'pg_restore',
                f'--host={self.host}',
                f'--port={self.port}',
                f'--username={self.user}',
                '--dbname={}'.format(database_name),
                '--verbose',
                '--clean',
                '--no-owner',
                '--no-privileges',
                dump_file
            ]

            env = os.environ.copy()
            if self.password:
                env['PGPASSWORD'] = self.password

            # Run restore process
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            end_time = time.time()

            duration_minutes = (end_time - start_time) / 60

            if result.returncode == 0:
                log_with_timestamp(f"Database restoration completed successfully in {duration_minutes:.1f} minutes")
                return True
            else:
                log_with_timestamp(f"ERROR: Database restoration failed: {result.stderr}")
                # Print stdout as well, as pg_restore sometimes puts useful info there
                if result.stdout:
                    log_with_timestamp(f"Restore output: {result.stdout}")
                return False

        except Exception as e:
            log_with_timestamp(f"ERROR: Unexpected error during database restoration: {e}")
            return False

    def get_table_info(self, database_name: str) -> dict:
        """Get information about tables in the database."""
        log_with_timestamp(f"Getting table information from {database_name}")

        try:
            cmd = [
                'psql',
                f'--host={self.host}',
                f'--port={self.port}',
                f'--username={self.user}',
                f'--dbname={database_name}',
                '--tuples-only',
                '--quiet',
                '--command=SELECT table_name, table_type FROM information_schema.tables WHERE table_schema=\'public\' ORDER BY table_name;'
            ]

            env = os.environ.copy()
            if self.password:
                env['PGPASSWORD'] = self.password

            result = subprocess.run(cmd, capture_output=True, text=True, env=env)

            if result.returncode == 0:
                tables = {}
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        parts = line.strip().split('|')
                        if len(parts) >= 2:
                            table_name = parts[0].strip()
                            table_type = parts[1].strip()
                            tables[table_name] = table_type

                log_with_timestamp(f"Found {len(tables)} tables in database")
                return tables
            else:
                log_with_timestamp(f"ERROR: Failed to get table info: {result.stderr}")
                return {}

        except Exception as e:
            log_with_timestamp(f"ERROR: Unexpected error getting table info: {e}")
            return {}

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Download and setup AACT database for clinical trials processing"
    )
    parser.add_argument(
        "--download-dir", default="./data/raw/clinical_trials",
        help="Directory to store downloaded files"
    )
    parser.add_argument(
        "--database-name", default="aact_clinical_trials",
        help="Name for the PostgreSQL database"
    )
    parser.add_argument(
        "--recreate", action="store_true",
        help="Drop and recreate database if it exists"
    )
    parser.add_argument(
        "--download-only", action="store_true",
        help="Only download, don't restore database"
    )
    parser.add_argument(
        "--restore-only",
        help="Only restore database from existing file (provide file path)"
    )

    args = parser.parse_args()

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Initialize managers
        downloader = AACTDownloader()
        postgres = PostgreSQLManager()

        # Check PostgreSQL connection
        if not args.download_only:
            if not postgres.check_postgres_connection():
                log_with_timestamp("ERROR: Cannot connect to PostgreSQL. Please ensure it's installed and running.")
                return 1

        download_path = None

        # Download phase
        if not args.restore_only:
            log_with_timestamp("=== Starting AACT Download ===")

            # Get latest snapshot info
            snapshot_info = downloader.get_latest_snapshot_info()

            # Download snapshot
            download_path = downloader.download_snapshot(snapshot_info, args.download_dir)

            if args.download_only:
                log_with_timestamp("Download complete! Use --restore-only to restore the database.")
                return 0

        # Restore phase
        if not args.download_only:
            log_with_timestamp("=== Starting Database Restoration ===")

            restore_file = args.restore_only or download_path
            if not restore_file or not os.path.exists(restore_file):
                log_with_timestamp("ERROR: No dump file available for restoration")
                return 1

            # Handle database recreation
            if args.recreate and postgres.database_exists(args.database_name):
                if not postgres.drop_database(args.database_name):
                    return 1

            # Create database
            if not postgres.create_database(args.database_name):
                return 1

            # Restore database
            if not postgres.restore_database(restore_file, args.database_name):
                return 1

            # Get table information
            tables = postgres.get_table_info(args.database_name)
            key_tables = ['studies', 'design_outcomes', 'eligibilities', 'conditions', 'interventions']

            log_with_timestamp("Database restoration verification:")
            for table in key_tables:
                status = "✓ Found" if table in tables else "✗ Missing"
                log_with_timestamp(f"  {table}: {status}")

        log_with_timestamp("=== AACT Setup Complete ===")
        return 0

    except KeyboardInterrupt:
        log_with_timestamp("Setup interrupted by user")
        return 1
    except Exception as e:
        log_with_timestamp(f"ERROR during setup: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
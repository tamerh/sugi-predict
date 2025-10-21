#!/usr/bin/env python3
"""
Patents File Tracking Utility

Combines JSON and SQLite tracking for patent data:
- JSON: File/release-level tracking (which Parquet files processed, Qdrant insertion)
- SQLite: Patent-level tracking (individual patent IDs, content hashes for change detection)

This enables efficient incremental updates similar to clinical_trials module.

Tracking file format (JSON):
{
    "last_update": "2025-10-18T10:00:00",
    "current_release": "2025-10-15",
    "releases": {
        "2025-10-15": {
            "download_date": "2025-10-18T09:00:00",
            "files": {
                "patents.parquet": {
                    "processed_date": "2025-10-18T09:30:00",
                    "patents_count": 17000000,
                    "status": "completed",
                    "qdrant_inserted": true
                },
                "compounds.parquet": {
                    "processed_date": "2025-10-18T09:45:00",
                    "compounds_count": 20000000,
                    "status": "completed",
                    "qdrant_inserted": true
                }
            }
        }
    }
}

SQLite database schema:
    patents (
        patent_id TEXT PRIMARY KEY,
        title TEXT,
        pub_date TEXT,
        content_hash TEXT,
        last_processed_date TEXT,
        release_version TEXT
    )
"""

import json
import os
import fcntl
import time
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set, List, Any


def compute_patent_hash(patent_data: Dict[str, Any]) -> str:
    """
    Compute hash of patent content for change detection.

    Args:
        patent_data: Patent dictionary with fields

    Returns:
        SHA256 hash of content
    """
    # Fields to include in hash (order matters)
    hash_fields = [
        'patent_id',
        'title',
        'abstract',
        'claims',
        'description',
        'ipc_codes',
        'assignees'
    ]

    content_str = ''
    for field in hash_fields:
        value = patent_data.get(field, '')
        if isinstance(value, list):
            value = '|'.join(sorted(str(v) for v in value))
        content_str += str(value)

    return hashlib.sha256(content_str.encode('utf-8')).hexdigest()


class PatentsFileTracker:
    """Manages JSON-based tracking of processed patent files and releases."""

    def __init__(self, tracking_file: str):
        """
        Initialize file tracker.

        Args:
            tracking_file: Path to tracking JSON file
        """
        self.tracking_file = Path(tracking_file)
        self.tracking_data = self._load()

    def _load(self) -> Dict:
        """Load tracking data from file or create new structure."""
        if self.tracking_file.exists():
            try:
                with open(self.tracking_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load tracking file: {e}")
                print("Creating new tracking structure")
                return self._new_structure()
        else:
            return self._new_structure()

    def _new_structure(self) -> Dict:
        """Create new tracking structure."""
        return {
            "last_update": None,
            "current_release": None,
            "releases": {}
        }

    def _save(self):
        """Save tracking data to file with file locking."""
        # Create directory if needed
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)

        # Ensure file exists
        if not self.tracking_file.exists():
            with open(self.tracking_file, 'w') as f:
                json.dump(self._new_structure(), f)

        # Use file locking to prevent concurrent writes
        max_retries = 10
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                with open(self.tracking_file, 'r+') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        f.seek(0)
                        try:
                            current_data = json.load(f)
                        except (json.JSONDecodeError, ValueError):
                            current_data = self._new_structure()

                        # Merge our changes
                        current_data['last_update'] = self.tracking_data['last_update']
                        current_data['current_release'] = self.tracking_data['current_release']

                        for release, release_info in self.tracking_data['releases'].items():
                            current_data['releases'][release] = release_info

                        # Write back
                        f.seek(0)
                        f.truncate()
                        json.dump(current_data, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())

                        self.tracking_data = current_data
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

                return

            except (IOError, OSError) as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    raise RuntimeError(f"Failed to save tracking file after {max_retries} attempts: {e}")

    def get_current_release(self) -> Optional[str]:
        """Get the current release version."""
        return self.tracking_data.get('current_release')

    def set_current_release(self, release_version: str):
        """Set the current release version."""
        self.tracking_data['current_release'] = release_version
        self.tracking_data['last_update'] = datetime.now().isoformat()

        if release_version not in self.tracking_data['releases']:
            self.tracking_data['releases'][release_version] = {
                'download_date': datetime.now().isoformat(),
                'files': {}
            }

        self._save()

    def is_file_processed(self, release_version: str, filename: str) -> bool:
        """
        Check if a file in a release has been processed.

        Args:
            release_version: Release date (e.g., "2025-10-15")
            filename: Parquet filename (e.g., "patents.parquet")

        Returns:
            True if file is completed
        """
        release = self.tracking_data['releases'].get(release_version, {})
        file_info = release.get('files', {}).get(filename, {})
        return file_info.get('status') == 'completed'

    def mark_file_processed(self, release_version: str, filename: str,
                           count: Optional[int] = None, status: str = 'completed'):
        """
        Mark a file as processed.

        Args:
            release_version: Release date
            filename: Parquet filename
            count: Number of records processed
            status: Processing status
        """
        if release_version not in self.tracking_data['releases']:
            self.tracking_data['releases'][release_version] = {
                'download_date': datetime.now().isoformat(),
                'files': {}
            }

        # Preserve existing qdrant_inserted status
        existing = self.tracking_data['releases'][release_version]['files'].get(filename, {})
        qdrant_inserted = existing.get('qdrant_inserted', False)

        count_field = 'patents_count' if 'patent' in filename.lower() else 'compounds_count'

        self.tracking_data['releases'][release_version]['files'][filename] = {
            'processed_date': datetime.now().isoformat(),
            count_field: count,
            'status': status,
            'qdrant_inserted': qdrant_inserted
        }

        self.tracking_data['last_update'] = datetime.now().isoformat()
        self._save()

    def is_inserted_to_qdrant(self, release_version: str, filename: str) -> bool:
        """Check if a file has been inserted to Qdrant."""
        release = self.tracking_data['releases'].get(release_version, {})
        file_info = release.get('files', {}).get(filename, {})
        return file_info.get('qdrant_inserted', False)

    def mark_inserted_to_qdrant(self, release_version: str, filename: str):
        """Mark a file as inserted to Qdrant."""
        if release_version not in self.tracking_data['releases']:
            print(f"Warning: Release {release_version} not found, creating entry")
            self.tracking_data['releases'][release_version] = {
                'download_date': datetime.now().isoformat(),
                'files': {}
            }

        if filename not in self.tracking_data['releases'][release_version]['files']:
            print(f"Warning: {filename} not in tracking, adding entry")
            self.tracking_data['releases'][release_version]['files'][filename] = {
                'processed_date': datetime.now().isoformat(),
                'status': 'completed'
            }

        self.tracking_data['releases'][release_version]['files'][filename]['qdrant_inserted'] = True
        self.tracking_data['releases'][release_version]['files'][filename]['qdrant_inserted_date'] = datetime.now().isoformat()
        self.tracking_data['last_update'] = datetime.now().isoformat()
        self._save()

    def get_files_not_inserted_to_qdrant(self, release_version: Optional[str] = None) -> Set[str]:
        """
        Get files that have been processed but not inserted to Qdrant.

        Args:
            release_version: Specific release or None for current

        Returns:
            Set of filenames needing insertion
        """
        if release_version is None:
            release_version = self.get_current_release()

        if not release_version:
            return set()

        not_inserted = set()
        release = self.tracking_data['releases'].get(release_version, {})

        for filename, info in release.get('files', {}).items():
            if info.get('status') == 'completed' and not info.get('qdrant_inserted', False):
                not_inserted.add(filename)

        return not_inserted

    def get_stats(self) -> Dict:
        """Get tracking statistics."""
        total_releases = len(self.tracking_data['releases'])
        current_release = self.tracking_data.get('current_release')

        total_files = 0
        completed_files = 0
        qdrant_inserted = 0

        for release_info in self.tracking_data['releases'].values():
            files = release_info.get('files', {})
            total_files += len(files)
            completed_files += sum(1 for f in files.values() if f.get('status') == 'completed')
            qdrant_inserted += sum(1 for f in files.values() if f.get('qdrant_inserted', False))

        return {
            'total_releases': total_releases,
            'current_release': current_release,
            'total_files': total_files,
            'completed_files': completed_files,
            'qdrant_inserted': qdrant_inserted,
            'qdrant_pending': completed_files - qdrant_inserted,
            'last_update': self.tracking_data.get('last_update')
        }


class PatentsDBTracker:
    """Manages SQLite database for tracking individual patents (like clinical_trials)."""

    def __init__(self, db_path: str):
        """
        Initialize the patents DB tracker.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def init_database(self):
        """Create tracking table and indices."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patents (
                    patent_id TEXT PRIMARY KEY,
                    title TEXT,
                    pub_date TEXT,
                    content_hash TEXT,
                    last_processed_date TEXT,
                    release_version TEXT
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_patent_id ON patents(patent_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON patents(content_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_release ON patents(release_version)")

            conn.commit()

    def get_patent(self, patent_id: str) -> Optional[Dict[str, str]]:
        """Get patent information from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM patents WHERE patent_id = ?",
                (patent_id,)
            )
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    def add_or_update_patent(self, patent_id: str, title: str, pub_date: str,
                            content_hash: str, release_version: str):
        """Add or update patent record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO patents
                (patent_id, title, pub_date, content_hash, last_processed_date, release_version)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
            """, (patent_id, title, pub_date, content_hash, release_version))

            conn.commit()

    def add_or_update_batch(self, patents: List[Dict[str, str]], batch_size: int = 1000):
        """
        Add or update multiple patents in batches.

        Args:
            patents: List of dicts with keys: patent_id, title, pub_date, content_hash, release_version
            batch_size: Number of records per batch
        """
        with sqlite3.connect(self.db_path) as conn:
            for i in range(0, len(patents), batch_size):
                batch = patents[i:i + batch_size]
                conn.executemany("""
                    INSERT OR REPLACE INTO patents
                    (patent_id, title, pub_date, content_hash, last_processed_date, release_version)
                    VALUES (?, ?, ?, ?, datetime('now'), ?)
                """, [(p['patent_id'], p['title'], p['pub_date'], p['content_hash'], p['release_version'])
                      for p in batch])

            conn.commit()

    def get_all_patent_ids(self, release_version: Optional[str] = None) -> List[str]:
        """
        Get all tracked patent IDs.

        Args:
            release_version: Optional filter by release

        Returns:
            List of patent IDs
        """
        with sqlite3.connect(self.db_path) as conn:
            if release_version:
                cursor = conn.execute(
                    "SELECT patent_id FROM patents WHERE release_version = ?",
                    (release_version,)
                )
            else:
                cursor = conn.execute("SELECT patent_id FROM patents")

            return [row[0] for row in cursor.fetchall()]

    def patent_exists(self, patent_id: str) -> bool:
        """Check if patent exists in database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM patents WHERE patent_id = ? LIMIT 1",
                (patent_id,)
            )
            return cursor.fetchone() is not None

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM patents")
            total_patents = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(DISTINCT release_version) FROM patents")
            total_releases = cursor.fetchone()[0]

            cursor = conn.execute("SELECT MIN(last_processed_date) FROM patents")
            oldest_processed = cursor.fetchone()[0]

            cursor = conn.execute("SELECT MAX(last_processed_date) FROM patents")
            newest_processed = cursor.fetchone()[0]

            db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
            db_size_mb = db_size_bytes / (1024 * 1024)

            return {
                "total_patents": total_patents,
                "total_releases": total_releases,
                "oldest_processed": oldest_processed,
                "newest_processed": newest_processed,
                "db_size_mb": round(db_size_mb, 2),
                "db_path": str(self.db_path)
            }

    def reset(self):
        """Delete all records from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM patents")
            conn.commit()


# CLI interface for tracking utility
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Patents tracking utility')
    parser.add_argument('--tracking-file', required=True, help='Path to tracking JSON file')
    parser.add_argument('--db-file', help='Path to tracking SQLite database (optional)')
    parser.add_argument('command', choices=['stats', 'list', 'check', 'reset'],
                       help='Command to execute')
    parser.add_argument('--release', help='Release version (for check command)')
    parser.add_argument('--file', help='File to check (for check command)')

    args = parser.parse_args()

    # Initialize file tracker
    file_tracker = PatentsFileTracker(args.tracking_file)

    if args.command == 'stats':
        print("\n=== File Tracking Statistics ===")
        stats = file_tracker.get_stats()
        for key, value in stats.items():
            print(f"{key}: {value}")

        if args.db_file and os.path.exists(args.db_file):
            db_tracker = PatentsDBTracker(args.db_file)
            print("\n=== Database Statistics ===")
            db_stats = db_tracker.get_stats()
            for key, value in db_stats.items():
                print(f"{key}: {value}")

    elif args.command == 'list':
        print("\n=== Tracked Releases ===")
        for release, info in file_tracker.tracking_data['releases'].items():
            print(f"\nRelease: {release}")
            print(f"  Downloaded: {info.get('download_date')}")
            print(f"  Files:")
            for filename, file_info in info.get('files', {}).items():
                status = file_info.get('status', 'unknown')
                qdrant = '✓' if file_info.get('qdrant_inserted') else '✗'
                print(f"    {filename}: {status} (Qdrant: {qdrant})")

    elif args.command == 'check':
        if not args.release or not args.file:
            print("ERROR: --release and --file required for check command")
            exit(1)

        processed = file_tracker.is_file_processed(args.release, args.file)
        qdrant = file_tracker.is_inserted_to_qdrant(args.release, args.file)

        print(f"\nFile: {args.file}")
        print(f"Release: {args.release}")
        print(f"Processed: {processed}")
        print(f"Qdrant inserted: {qdrant}")

    elif args.command == 'reset':
        confirm = input("Are you sure you want to reset tracking? (yes/no): ")
        if confirm.lower() == 'yes':
            file_tracker.tracking_data = file_tracker._new_structure()
            file_tracker._save()
            print("File tracking reset")

            if args.db_file and os.path.exists(args.db_file):
                db_tracker = PatentsDBTracker(args.db_file)
                db_tracker.reset()
                print("Database tracking reset")
        else:
            print("Reset cancelled")

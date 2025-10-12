#!/usr/bin/env python3
"""
PubMed File Tracking Utility

Simple JSON-based tracking system to track which PubMed files have been processed.
This enables incremental updates without reprocessing everything.

Tracking file format:
{
    "last_update": "2025-01-15T10:30:00",
    "files": {
        "baseline/pubmed25n0001.xml.gz": {
            "processed_date": "2025-01-10T10:30:00",
            "vectors_count": 50000,
            "status": "completed"
        },
        "updatefiles/pubmed25n1234.xml.gz": {
            "processed_date": "2025-01-15T08:15:00",
            "vectors_count": 1500,
            "status": "completed"
        }
    }
}
"""

import json
import os
import fcntl
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set


class PubMedTracker:
    """Manages tracking of processed PubMed files."""

    def __init__(self, tracking_file: str):
        """
        Initialize tracker.

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
            "files": {}
        }

    def _save(self):
        """Save tracking data to file with file locking to prevent race conditions."""
        # Create directory if needed
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)

        # Ensure file exists
        if not self.tracking_file.exists():
            with open(self.tracking_file, 'w') as f:
                json.dump(self._new_structure(), f)

        # Use file locking to prevent concurrent writes
        max_retries = 10
        retry_delay = 0.1  # 100ms

        for attempt in range(max_retries):
            try:
                # Open file for reading and writing
                with open(self.tracking_file, 'r+') as f:
                    # Acquire exclusive lock (blocks until available)
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        # Read current data from file
                        f.seek(0)
                        try:
                            current_data = json.load(f)
                        except (json.JSONDecodeError, ValueError):
                            # File might be empty or corrupted, use our data
                            current_data = self._new_structure()

                        # Merge our changes with current data
                        for filename, info in self.tracking_data['files'].items():
                            current_data['files'][filename] = info
                        current_data['last_update'] = self.tracking_data['last_update']

                        # Write merged data back
                        f.seek(0)
                        f.truncate()
                        json.dump(current_data, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())  # Ensure written to disk

                        # Update our in-memory copy
                        self.tracking_data = current_data

                    finally:
                        # Release lock
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

                # Success!
                return

            except (IOError, OSError) as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    raise RuntimeError(f"Failed to save tracking file after {max_retries} attempts: {e}")

    def is_processed(self, filename: str) -> bool:
        """
        Check if a file has been processed.

        Args:
            filename: Relative filename (e.g., "baseline/pubmed25n0001.xml.gz")

        Returns:
            True if file is in tracking and marked as completed
        """
        file_info = self.tracking_data["files"].get(filename)
        if file_info:
            return file_info.get("status") == "completed"
        return False

    def get_processed_files(self, subdir: Optional[str] = None) -> Set[str]:
        """
        Get set of processed files.

        Args:
            subdir: Optional subdirectory filter (e.g., "baseline" or "updatefiles")

        Returns:
            Set of processed filenames
        """
        processed = set()
        for filename, info in self.tracking_data["files"].items():
            if info.get("status") == "completed":
                if subdir is None or filename.startswith(subdir + "/"):
                    processed.add(filename)
        return processed

    def get_unprocessed_files(self, available_files: Set[str]) -> Set[str]:
        """
        Get files that need processing.

        Args:
            available_files: Set of available files (from FTP or local)

        Returns:
            Set of files that are not yet processed
        """
        processed = self.get_processed_files()
        return available_files - processed

    def mark_processed(self, filename: str, vectors_count: Optional[int] = None,
                      status: str = "completed"):
        """
        Mark a file as processed.

        Args:
            filename: Relative filename (e.g., "baseline/pubmed25n0001.xml.gz")
            vectors_count: Number of vectors generated (optional)
            status: Processing status (default: "completed")
        """
        # Preserve existing qdrant_inserted status if it exists
        existing = self.tracking_data["files"].get(filename, {})
        qdrant_inserted = existing.get("qdrant_inserted", False)

        self.tracking_data["files"][filename] = {
            "processed_date": datetime.now().isoformat(),
            "vectors_count": vectors_count,
            "status": status,
            "qdrant_inserted": qdrant_inserted
        }
        self.tracking_data["last_update"] = datetime.now().isoformat()
        self._save()

    def mark_failed(self, filename: str, error: str):
        """
        Mark a file as failed.

        Args:
            filename: Relative filename
            error: Error message
        """
        self.tracking_data["files"][filename] = {
            "processed_date": datetime.now().isoformat(),
            "vectors_count": None,
            "status": "failed",
            "error": error,
            "qdrant_inserted": False
        }
        self._save()

    def is_inserted_to_qdrant(self, filename: str) -> bool:
        """
        Check if a file has been inserted to Qdrant.

        Args:
            filename: Relative filename (e.g., "baseline/pubmed25n0001.xml.gz")

        Returns:
            True if file has been inserted to Qdrant
        """
        file_info = self.tracking_data["files"].get(filename)
        if file_info:
            return file_info.get("qdrant_inserted", False)
        return False

    def mark_inserted_to_qdrant(self, filename: str):
        """
        Mark a file as inserted to Qdrant.

        Args:
            filename: Relative filename (e.g., "baseline/pubmed25n0001.xml.gz")
        """
        if filename not in self.tracking_data["files"]:
            print(f"Warning: {filename} not in tracking, adding entry")
            self.tracking_data["files"][filename] = {
                "processed_date": datetime.now().isoformat(),
                "vectors_count": None,
                "status": "completed"
            }

        self.tracking_data["files"][filename]["qdrant_inserted"] = True
        self.tracking_data["files"][filename]["qdrant_inserted_date"] = datetime.now().isoformat()
        self.tracking_data["last_update"] = datetime.now().isoformat()
        self._save()

    def get_files_not_inserted_to_qdrant(self, subdir: Optional[str] = None) -> Set[str]:
        """
        Get files that have been processed but not yet inserted to Qdrant.

        Args:
            subdir: Optional subdirectory filter (e.g., "baseline" or "updatefiles")

        Returns:
            Set of filenames that need Qdrant insertion
        """
        not_inserted = set()
        for filename, info in self.tracking_data["files"].items():
            # Only include completed files
            if info.get("status") == "completed":
                # Check if not inserted to Qdrant
                if not info.get("qdrant_inserted", False):
                    if subdir is None or filename.startswith(subdir + "/"):
                        not_inserted.add(filename)
        return not_inserted

    def get_stats(self) -> Dict:
        """
        Get tracking statistics.

        Returns:
            Dict with statistics
        """
        total = len(self.tracking_data["files"])
        completed = sum(1 for f in self.tracking_data["files"].values()
                       if f.get("status") == "completed")
        failed = sum(1 for f in self.tracking_data["files"].values()
                    if f.get("status") == "failed")

        baseline_files = sum(1 for f in self.tracking_data["files"].keys()
                            if f.startswith("baseline/"))
        update_files = sum(1 for f in self.tracking_data["files"].keys()
                          if f.startswith("updatefiles/"))

        total_vectors = sum(f.get("vectors_count", 0) or 0
                           for f in self.tracking_data["files"].values())

        # Qdrant insertion stats
        qdrant_inserted = sum(1 for f in self.tracking_data["files"].values()
                             if f.get("qdrant_inserted", False))
        qdrant_pending = sum(1 for f in self.tracking_data["files"].values()
                            if f.get("status") == "completed" and not f.get("qdrant_inserted", False))

        return {
            "total_files": total,
            "completed": completed,
            "failed": failed,
            "baseline_files": baseline_files,
            "update_files": update_files,
            "total_vectors": total_vectors,
            "qdrant_inserted": qdrant_inserted,
            "qdrant_pending": qdrant_pending,
            "last_update": self.tracking_data.get("last_update")
        }

    def reset(self):
        """Reset tracking data (use with caution!)."""
        self.tracking_data = self._new_structure()
        self._save()

    def remove_file(self, filename: str):
        """
        Remove a file from tracking.

        Args:
            filename: Relative filename to remove
        """
        if filename in self.tracking_data["files"]:
            del self.tracking_data["files"][filename]
            self._save()


def main():
    """Command-line interface for tracking utilities."""
    import argparse

    parser = argparse.ArgumentParser(
        description="PubMed file tracking utilities"
    )
    parser.add_argument(
        '--tracking-file',
        required=True,
        help='Path to tracking JSON file'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Init command
    subparsers.add_parser('init', help='Initialize tracking file')

    # Stats command
    subparsers.add_parser('stats', help='Show tracking statistics')

    # List command
    list_parser = subparsers.add_parser('list', help='List processed files')
    list_parser.add_argument('--subdir', help='Filter by subdirectory')

    # Check command
    check_parser = subparsers.add_parser('check', help='Check if file is processed')
    check_parser.add_argument('filename', help='File to check')

    # Mark command
    mark_parser = subparsers.add_parser('mark', help='Mark file as processed')
    mark_parser.add_argument('filename', help='File to mark')
    mark_parser.add_argument('--vectors', type=int, help='Number of vectors')

    # Reset command
    subparsers.add_parser('reset', help='Reset tracking (WARNING: deletes all tracking data)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    tracker = PubMedTracker(args.tracking_file)

    if args.command == 'init':
        print(f"Initialized tracking file: {args.tracking_file}")
        tracker._save()

    elif args.command == 'stats':
        stats = tracker.get_stats()
        print("\n=== PubMed Tracking Statistics ===")
        print(f"Total files tracked: {stats['total_files']}")
        print(f"  - Completed: {stats['completed']}")
        print(f"  - Failed: {stats['failed']}")
        print(f"Baseline files: {stats['baseline_files']}")
        print(f"Update files: {stats['update_files']}")
        print(f"Total vectors: {stats['total_vectors']:,}")
        print(f"\nQdrant Insertion:")
        print(f"  - Inserted: {stats['qdrant_inserted']}")
        print(f"  - Pending: {stats['qdrant_pending']}")
        print(f"\nLast update: {stats['last_update']}")

    elif args.command == 'list':
        files = tracker.get_processed_files(args.subdir)
        print(f"\n=== Processed Files ({len(files)}) ===")
        for f in sorted(files):
            info = tracker.tracking_data["files"][f]
            print(f"{f}: {info['vectors_count']} vectors ({info['processed_date']})")

    elif args.command == 'check':
        is_proc = tracker.is_processed(args.filename)
        if is_proc:
            info = tracker.tracking_data["files"][args.filename]
            print(f"✓ {args.filename} is processed")
            print(f"  Vectors: {info['vectors_count']}")
            print(f"  Date: {info['processed_date']}")
        else:
            print(f"✗ {args.filename} is NOT processed")

    elif args.command == 'mark':
        tracker.mark_processed(args.filename, args.vectors)
        print(f"✓ Marked {args.filename} as processed")

    elif args.command == 'reset':
        confirm = input("WARNING: This will delete all tracking data. Type 'yes' to confirm: ")
        if confirm.lower() == 'yes':
            tracker.reset()
            print("✓ Tracking data reset")
        else:
            print("Cancelled")


if __name__ == "__main__":
    main()

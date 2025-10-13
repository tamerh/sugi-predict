#!/usr/bin/env python3
"""
Clinical Trials Chunk Tracking Utility

JSON-based tracking system to track which chunks have been processed and inserted.
This enables incremental updates and prevents reprocessing/reinsertion.

Tracking file format:
{
    "last_update": "2025-01-15T10:30:00",
    "chunks": {
        "trials_chunk_0001.json": {
            "processed_date": "2025-01-10T10:30:00",
            "vectors_count": 50000,
            "status": "completed",
            "qdrant_inserted": false
        },
        "trials_update_20250115_chunk_0001.json": {
            "processed_date": "2025-01-15T08:15:00",
            "vectors_count": 1500,
            "status": "completed",
            "qdrant_inserted": true
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


class ChunkTracker:
    """Manages tracking of processed clinical trials chunks."""

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
            "chunks": {}
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
                        for chunkname, info in self.tracking_data['chunks'].items():
                            current_data['chunks'][chunkname] = info
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

    def is_processed(self, chunk_name: str) -> bool:
        """
        Check if a chunk has been processed.

        Args:
            chunk_name: Chunk filename (e.g., "trials_chunk_0001.json")

        Returns:
            True if chunk is in tracking and marked as completed
        """
        chunk_info = self.tracking_data["chunks"].get(chunk_name)
        if chunk_info:
            return chunk_info.get("status") == "completed"
        return False

    def get_processed_chunks(self, filter_prefix: Optional[str] = None) -> Set[str]:
        """
        Get set of processed chunks.

        Args:
            filter_prefix: Optional prefix filter (e.g., "trials_update" for update chunks only)

        Returns:
            Set of processed chunk names
        """
        processed = set()
        for chunk_name, info in self.tracking_data["chunks"].items():
            if info.get("status") == "completed":
                if filter_prefix is None or chunk_name.startswith(filter_prefix):
                    processed.add(chunk_name)
        return processed

    def get_unprocessed_chunks(self, available_chunks: Set[str]) -> Set[str]:
        """
        Get chunks that need processing.

        Args:
            available_chunks: Set of available chunk files

        Returns:
            Set of chunks that are not yet processed
        """
        processed = self.get_processed_chunks()
        return available_chunks - processed

    def mark_processed(self, chunk_name: str, vectors_count: Optional[int] = None,
                      status: str = "completed"):
        """
        Mark a chunk as processed.

        Args:
            chunk_name: Chunk filename (e.g., "trials_chunk_0001.json")
            vectors_count: Number of vectors generated (optional)
            status: Processing status (default: "completed")
        """
        # Preserve existing qdrant_inserted status if it exists
        existing = self.tracking_data["chunks"].get(chunk_name, {})
        qdrant_inserted = existing.get("qdrant_inserted", False)

        self.tracking_data["chunks"][chunk_name] = {
            "processed_date": datetime.now().isoformat(),
            "vectors_count": vectors_count,
            "status": status,
            "qdrant_inserted": qdrant_inserted
        }
        self.tracking_data["last_update"] = datetime.now().isoformat()
        self._save()

    def mark_failed(self, chunk_name: str, error: str):
        """
        Mark a chunk as failed.

        Args:
            chunk_name: Chunk filename
            error: Error message
        """
        self.tracking_data["chunks"][chunk_name] = {
            "processed_date": datetime.now().isoformat(),
            "vectors_count": None,
            "status": "failed",
            "error": error,
            "qdrant_inserted": False
        }
        self._save()

    def is_inserted_to_qdrant(self, chunk_name: str) -> bool:
        """
        Check if a chunk has been inserted to Qdrant.

        Args:
            chunk_name: Chunk filename (e.g., "trials_chunk_0001.json")

        Returns:
            True if chunk has been inserted to Qdrant
        """
        chunk_info = self.tracking_data["chunks"].get(chunk_name)
        if chunk_info:
            return chunk_info.get("qdrant_inserted", False)
        return False

    def mark_inserted_to_qdrant(self, chunk_name: str):
        """
        Mark a chunk as inserted to Qdrant.

        Args:
            chunk_name: Chunk filename (e.g., "trials_chunk_0001.json")
        """
        if chunk_name not in self.tracking_data["chunks"]:
            print(f"Warning: {chunk_name} not in tracking, adding entry")
            self.tracking_data["chunks"][chunk_name] = {
                "processed_date": datetime.now().isoformat(),
                "vectors_count": None,
                "status": "completed"
            }

        self.tracking_data["chunks"][chunk_name]["qdrant_inserted"] = True
        self.tracking_data["chunks"][chunk_name]["qdrant_inserted_date"] = datetime.now().isoformat()
        self.tracking_data["last_update"] = datetime.now().isoformat()
        self._save()

    def get_chunks_not_inserted_to_qdrant(self, filter_prefix: Optional[str] = None) -> Set[str]:
        """
        Get chunks that have been processed but not yet inserted to Qdrant.

        Args:
            filter_prefix: Optional prefix filter (e.g., "trials_update" for update chunks only)

        Returns:
            Set of chunk names that need Qdrant insertion
        """
        not_inserted = set()
        for chunk_name, info in self.tracking_data["chunks"].items():
            # Only include completed chunks
            if info.get("status") == "completed":
                # Check if not inserted to Qdrant
                if not info.get("qdrant_inserted", False):
                    if filter_prefix is None or chunk_name.startswith(filter_prefix):
                        not_inserted.add(chunk_name)
        return not_inserted

    def get_stats(self) -> Dict:
        """
        Get tracking statistics.

        Returns:
            Dict with statistics
        """
        total = len(self.tracking_data["chunks"])
        completed = sum(1 for c in self.tracking_data["chunks"].values()
                       if c.get("status") == "completed")
        failed = sum(1 for c in self.tracking_data["chunks"].values()
                    if c.get("status") == "failed")

        full_chunks = sum(1 for c in self.tracking_data["chunks"].keys()
                         if c.startswith("trials_chunk_"))
        update_chunks = sum(1 for c in self.tracking_data["chunks"].keys()
                           if c.startswith("trials_update_"))

        total_vectors = sum(c.get("vectors_count", 0) or 0
                           for c in self.tracking_data["chunks"].values())

        # Qdrant insertion stats
        qdrant_inserted = sum(1 for c in self.tracking_data["chunks"].values()
                             if c.get("qdrant_inserted", False))
        qdrant_pending = sum(1 for c in self.tracking_data["chunks"].values()
                            if c.get("status") == "completed" and not c.get("qdrant_inserted", False))

        return {
            "total_chunks": total,
            "completed": completed,
            "failed": failed,
            "full_chunks": full_chunks,
            "update_chunks": update_chunks,
            "total_vectors": total_vectors,
            "qdrant_inserted": qdrant_inserted,
            "qdrant_pending": qdrant_pending,
            "last_update": self.tracking_data.get("last_update")
        }

    def reset(self):
        """Reset tracking data (use with caution!)."""
        self.tracking_data = self._new_structure()
        self._save()

    def remove_chunk(self, chunk_name: str):
        """
        Remove a chunk from tracking.

        Args:
            chunk_name: Chunk filename to remove
        """
        if chunk_name in self.tracking_data["chunks"]:
            del self.tracking_data["chunks"][chunk_name]
            self._save()


def main():
    """Command-line interface for tracking utilities."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Clinical Trials chunk tracking utilities"
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
    list_parser = subparsers.add_parser('list', help='List processed chunks')
    list_parser.add_argument('--filter', help='Filter by prefix (e.g., "trials_update")')

    # Check command
    check_parser = subparsers.add_parser('check', help='Check if chunk is processed')
    check_parser.add_argument('chunk_name', help='Chunk to check')

    # Mark command
    mark_parser = subparsers.add_parser('mark', help='Mark chunk as processed')
    mark_parser.add_argument('chunk_name', help='Chunk to mark')
    mark_parser.add_argument('--vectors', type=int, help='Number of vectors')

    # Reset command
    subparsers.add_parser('reset', help='Reset tracking (WARNING: deletes all tracking data)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    tracker = ChunkTracker(args.tracking_file)

    if args.command == 'init':
        print(f"Initialized tracking file: {args.tracking_file}")
        tracker._save()

    elif args.command == 'stats':
        stats = tracker.get_stats()
        print("\n=== Clinical Trials Chunk Tracking Statistics ===")
        print(f"Total chunks tracked: {stats['total_chunks']}")
        print(f"  - Completed: {stats['completed']}")
        print(f"  - Failed: {stats['failed']}")
        print(f"Full chunks: {stats['full_chunks']}")
        print(f"Update chunks: {stats['update_chunks']}")
        print(f"Total vectors: {stats['total_vectors']:,}")
        print(f"\nQdrant Insertion:")
        print(f"  - Inserted: {stats['qdrant_inserted']}")
        print(f"  - Pending: {stats['qdrant_pending']}")
        print(f"\nLast update: {stats['last_update']}")

    elif args.command == 'list':
        chunks = tracker.get_processed_chunks(args.filter)
        print(f"\n=== Processed Chunks ({len(chunks)}) ===")
        for c in sorted(chunks):
            info = tracker.tracking_data["chunks"][c]
            qdrant_status = "✓ inserted" if info.get("qdrant_inserted") else "⏳ pending"
            print(f"{c}: {info['vectors_count']} vectors ({info['processed_date']}) [{qdrant_status}]")

    elif args.command == 'check':
        is_proc = tracker.is_processed(args.chunk_name)
        if is_proc:
            info = tracker.tracking_data["chunks"][args.chunk_name]
            print(f"✓ {args.chunk_name} is processed")
            print(f"  Vectors: {info['vectors_count']}")
            print(f"  Date: {info['processed_date']}")
            print(f"  Qdrant inserted: {info.get('qdrant_inserted', False)}")
        else:
            print(f"✗ {args.chunk_name} is NOT processed")

    elif args.command == 'mark':
        tracker.mark_processed(args.chunk_name, args.vectors)
        print(f"✓ Marked {args.chunk_name} as processed")

    elif args.command == 'reset':
        confirm = input("WARNING: This will delete all tracking data. Type 'yes' to confirm: ")
        if confirm.lower() == 'yes':
            tracker.reset()
            print("✓ Tracking data reset")
        else:
            print("Cancelled")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Merge Clinical Trials Indices for BioYoda Pipeline

Merges individual clinical trial FAISS indices and metadata into master files,
following the same pattern as the PubMed merge0.py script.
"""

import os
import sys
import json
import faiss
import glob
import argparse
import psutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import numpy as np

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

class ClinicalTrialsMerger:
    """Merges individual clinical trial indices into master files."""

    def __init__(self, vector_dimension: int):
        """Initialize the merger."""
        self.vector_dimension = vector_dimension

    def find_index_files(self, processed_dir: str) -> List[str]:
        """Find all clinical trial index files in the processed directory."""
        log_with_timestamp(f"Searching for index files in: {processed_dir}")

        index_pattern = os.path.join(processed_dir, "**", "*.index")
        index_files = glob.glob(index_pattern, recursive=True)

        log_with_timestamp(f"Found {len(index_files)} index files")

        if len(index_files) == 0:
            log_with_timestamp("No index files found. Please run trial processing first.")
            return []

        # Sort files for consistent processing order
        index_files.sort()

        # Log first few files for verification
        for i, index_file in enumerate(index_files[:5]):
            log_with_timestamp(f"  {i+1}. {os.path.basename(index_file)}")

        if len(index_files) > 5:
            log_with_timestamp(f"  ... and {len(index_files) - 5} more files")

        return index_files

    def validate_index_file(self, index_path: str) -> bool:
        """Validate that an index file is readable and has correct dimensions."""
        try:
            index = faiss.read_index(index_path)
            if index.d != self.vector_dimension:
                log_with_timestamp(f"ERROR: Dimension mismatch in {index_path}. Expected {self.vector_dimension}, got {index.d}")
                return False

            if index.ntotal == 0:
                log_with_timestamp(f"WARNING: Empty index file: {index_path}")
                return False

            return True

        except Exception as e:
            log_with_timestamp(f"ERROR: Cannot read index file {index_path}: {e}")
            return False

    def load_metadata_file(self, metadata_path: str) -> Dict[str, Any]:
        """Load metadata file corresponding to an index file."""
        if not os.path.exists(metadata_path):
            log_with_timestamp(f"WARNING: Metadata file not found: {metadata_path}")
            return {}

        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            if not isinstance(metadata, dict):
                log_with_timestamp(f"WARNING: Invalid metadata format in {metadata_path}")
                return {}

            return metadata

        except Exception as e:
            log_with_timestamp(f"ERROR: Cannot read metadata file {metadata_path}: {e}")
            return {}

    def merge_indices_and_metadata(self, index_files: List[str],
                                 output_index: str, output_metadata: str) -> bool:
        """Merge all index files and metadata into master files."""
        log_with_timestamp("=== Starting Index and Metadata Merge ===")

        # Validate all index files first
        valid_files = []
        for index_file in index_files:
            if self.validate_index_file(index_file):
                valid_files.append(index_file)

        if not valid_files:
            log_with_timestamp("ERROR: No valid index files found")
            return False

        log_with_timestamp(f"Merging {len(valid_files)} valid index files")

        # Initialize master index
        master_index = faiss.IndexFlatL2(self.vector_dimension)
        master_metadata = {}
        total_vectors = 0

        # Process each index file
        for file_idx, index_file in enumerate(valid_files):
            log_with_timestamp(f"Processing file {file_idx + 1}/{len(valid_files)}: {os.path.basename(index_file)}")

            try:
                # Load index
                index = faiss.read_index(index_file)
                log_with_timestamp(f"  Loaded index: {index.ntotal} vectors, {index.d} dimensions")

                # Load corresponding metadata
                metadata_file = index_file.replace('.index', '_metadata.json')
                metadata = self.load_metadata_file(metadata_file)

                if metadata and len(metadata) != index.ntotal:
                    log_with_timestamp(f"  WARNING: Metadata count ({len(metadata)}) != vector count ({index.ntotal})")

                # Add vectors to master index
                if index.ntotal > 0:
                    # Extract vectors from index
                    vectors = np.zeros((index.ntotal, index.d), dtype=np.float32)
                    for i in range(index.ntotal):
                        vectors[i] = index.reconstruct(i)

                    master_index.add(vectors)

                    # Add metadata with adjusted indices
                    for old_idx, chunk_data in metadata.items():
                        new_idx = total_vectors + int(old_idx)
                        master_metadata[str(new_idx)] = chunk_data

                    total_vectors += index.ntotal
                    log_with_timestamp(f"  Added {index.ntotal} vectors. Total: {total_vectors}")

                # Memory cleanup
                del index, metadata
                if 'vectors' in locals():
                    del vectors

                # Report memory usage every 10 files
                if (file_idx + 1) % 10 == 0:
                    used_mb, avail_mb, percent = get_memory_usage()
                    log_with_timestamp(f"  Progress: {file_idx + 1}/{len(valid_files)} files. Memory: {used_mb:.1f}MB used ({percent:.1f}%)")

            except Exception as e:
                log_with_timestamp(f"ERROR processing {index_file}: {e}")
                continue

        # Verify final results
        if master_index.ntotal == 0:
            log_with_timestamp("ERROR: No vectors were successfully merged")
            return False

        log_with_timestamp(f"Merge complete: {master_index.ntotal} total vectors")
        log_with_timestamp(f"Metadata entries: {len(master_metadata)}")

        # Save master index
        log_with_timestamp(f"Saving master index to: {output_index}")
        try:
            os.makedirs(os.path.dirname(output_index), exist_ok=True)
            faiss.write_index(master_index, output_index)

            index_size_mb = os.path.getsize(output_index) / 1024 / 1024
            log_with_timestamp(f"Master index saved: {index_size_mb:.1f}MB")

        except Exception as e:
            log_with_timestamp(f"ERROR saving master index: {e}")
            return False

        # Save master metadata
        log_with_timestamp(f"Saving master metadata to: {output_metadata}")
        try:
            os.makedirs(os.path.dirname(output_metadata), exist_ok=True)
            with open(output_metadata, 'w') as f:
                json.dump(master_metadata, f, indent=2, default=str, ensure_ascii=False)

            metadata_size_mb = os.path.getsize(output_metadata) / 1024 / 1024
            log_with_timestamp(f"Master metadata saved: {metadata_size_mb:.1f}MB")

        except Exception as e:
            log_with_timestamp(f"ERROR saving master metadata: {e}")
            return False

        # Final validation
        try:
            validation_index = faiss.read_index(output_index)
            if validation_index.ntotal != len(master_metadata):
                log_with_timestamp(f"WARNING: Index vectors ({validation_index.ntotal}) != metadata entries ({len(master_metadata)})")
            else:
                log_with_timestamp("✓ Final validation passed: index and metadata counts match")

        except Exception as e:
            log_with_timestamp(f"WARNING: Could not validate final files: {e}")

        return True

    def create_summary_report(self, index_files: List[str], output_index: str,
                            output_metadata: str) -> None:
        """Create a summary report of the merge process."""
        log_with_timestamp("Creating merge summary report...")

        try:
            # Load final files for statistics
            final_index = faiss.read_index(output_index)
            with open(output_metadata, 'r') as f:
                final_metadata = json.load(f)

            # Analyze chunk types
            chunk_types = {}
            trial_count = set()
            phase_count = {}
            status_count = {}

            for chunk_data in final_metadata.values():
                chunk_type = chunk_data.get('chunk_type', 'unknown')
                chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1

                nct_id = chunk_data.get('nct_id')
                if nct_id:
                    trial_count.add(nct_id)

                phase = chunk_data.get('phase', 'Unknown')
                phase_count[phase] = phase_count.get(phase, 0) + 1

                status = chunk_data.get('overall_status', 'Unknown')
                status_count[status] = status_count.get(status, 0) + 1

            # Create report
            report = {
                'merge_timestamp': datetime.now().isoformat(),
                'input_files': len(index_files),
                'total_vectors': final_index.ntotal,
                'total_metadata_entries': len(final_metadata),
                'unique_trials': len(trial_count),
                'vector_dimension': final_index.d,
                'chunk_types': chunk_types,
                'phase_distribution': dict(sorted(phase_count.items())),
                'status_distribution': dict(sorted(status_count.items())),
                'file_sizes': {
                    'index_mb': os.path.getsize(output_index) / 1024 / 1024,
                    'metadata_mb': os.path.getsize(output_metadata) / 1024 / 1024
                }
            }

            # Save report
            report_path = output_metadata.replace('.json', '_report.json')
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)

            log_with_timestamp(f"Merge report saved: {report_path}")

            # Print summary
            log_with_timestamp("=== Merge Summary ===")
            log_with_timestamp(f"Total trials processed: {len(trial_count):,}")
            log_with_timestamp(f"Total text chunks: {final_index.ntotal:,}")
            log_with_timestamp(f"Vector dimension: {final_index.d}")

            log_with_timestamp("Chunk type distribution:")
            for chunk_type, count in sorted(chunk_types.items()):
                percentage = (count / final_index.ntotal) * 100
                log_with_timestamp(f"  {chunk_type}: {count:,} ({percentage:.1f}%)")

            log_with_timestamp("Top study phases:")
            for phase, count in sorted(phase_count.items(), key=lambda x: x[1], reverse=True)[:5]:
                percentage = (count / final_index.ntotal) * 100
                log_with_timestamp(f"  {phase}: {count:,} ({percentage:.1f}%)")

        except Exception as e:
            log_with_timestamp(f"WARNING: Could not create summary report: {e}")

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Merge clinical trial indices and metadata into master files"
    )
    parser.add_argument(
        "--processed-dir", required=True,
        help="Directory containing processed clinical trial indices"
    )
    parser.add_argument(
        "--output-index", required=True,
        help="Output path for master FAISS index"
    )
    parser.add_argument(
        "--output-metadata", required=True,
        help="Output path for master metadata JSON"
    )
    parser.add_argument(
        "--vector-dimension", type=int, default=768,
        help="Expected vector dimension (default: 768)"
    )

    args = parser.parse_args()

    # Validate input directory
    if not os.path.exists(args.processed_dir):
        log_with_timestamp(f"ERROR: Processed directory not found: {args.processed_dir}")
        return 1

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Initialize merger
        merger = ClinicalTrialsMerger(args.vector_dimension)

        # Find index files
        index_files = merger.find_index_files(args.processed_dir)
        if not index_files:
            return 1

        # Perform merge
        success = merger.merge_indices_and_metadata(
            index_files, args.output_index, args.output_metadata
        )

        if not success:
            log_with_timestamp("Merge failed")
            return 1

        # Create summary report
        merger.create_summary_report(index_files, args.output_index, args.output_metadata)

        log_with_timestamp("=== Clinical Trials Merge Complete ===")
        return 0

    except KeyboardInterrupt:
        log_with_timestamp("Merge interrupted by user")
        return 1
    except Exception as e:
        log_with_timestamp(f"ERROR during merge: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
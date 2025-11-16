#!/usr/bin/env python3
"""
Protein Embeddings Processing for BioYoda Pipeline

Processes ESM-2 protein embeddings to create FAISS indices for semantic
protein similarity search.

This script:
1. Loads all_embeddings.h5 (ESM-2 embeddings from SwissProt)
2. Splits into chunks for efficient processing
3. Creates FAISS indices for protein similarity search
4. Prepares metadata for Qdrant insertion
"""

import os
import sys
import json
import faiss
import numpy as np
import h5py
import argparse
import psutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional


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


class ProteinEmbeddingsProcessor:
    """Processes ESM-2 protein embeddings for similarity search."""

    def __init__(self, vector_dimension: int = 640):
        """
        Initialize the protein embeddings processor.

        Args:
            vector_dimension: Dimension of ESM-2 embeddings (640 for t30, 1280 for t33, etc.)
        """
        self.vector_dimension = vector_dimension

    def load_embeddings_h5(self, h5_path: str) -> Tuple[np.ndarray, List[str]]:
        """
        Load embeddings from HDF5 file.

        Args:
            h5_path: Path to all_embeddings.h5 file

        Returns:
            Tuple of (embeddings array, protein IDs list)
        """
        log_with_timestamp(f"Loading embeddings from {h5_path}")

        try:
            with h5py.File(h5_path, 'r') as f:
                # Load embeddings and IDs
                embeddings = f['embeddings'][:]
                ids_raw = f['ids'][:]

                # Convert IDs to strings (they may be stored as bytes)
                if ids_raw.dtype == object or ids_raw.dtype.kind in ('S', 'U'):
                    # Bytes or unicode strings
                    protein_ids = [
                        id_val.decode('utf-8') if isinstance(id_val, bytes) else str(id_val)
                        for id_val in ids_raw
                    ]
                else:
                    protein_ids = [str(id_val) for id_val in ids_raw]

                log_with_timestamp(f"Loaded {len(protein_ids):,} protein embeddings")
                log_with_timestamp(f"Embedding dimension: {embeddings.shape[1]}")
                log_with_timestamp(f"First 3 protein IDs: {protein_ids[:3]}")

                # Verify dimension matches expected
                if embeddings.shape[1] != self.vector_dimension:
                    log_with_timestamp(f"WARNING: Expected dimension {self.vector_dimension}, got {embeddings.shape[1]}")
                    self.vector_dimension = embeddings.shape[1]

                return embeddings, protein_ids

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to load HDF5 file: {e}")
            raise

    def parse_uniprot_id(self, full_id: str) -> Dict[str, str]:
        """
        Parse UniProt ID to extract components.

        UniProt FASTA IDs have format: sp|Q6GZX4|001R_FRG3G
        or: tr|Q6GZX4|001R_FRG3G

        Args:
            full_id: Full UniProt ID string

        Returns:
            Dictionary with parsed components
        """
        parts = full_id.split('|')

        if len(parts) >= 3:
            # Standard UniProt format
            return {
                'protein_id': full_id,
                'uniprot_id': parts[1],
                'entry_name': parts[2],
                'database': parts[0]  # 'sp' or 'tr'
            }
        elif len(parts) == 2:
            # Simplified format
            return {
                'protein_id': full_id,
                'uniprot_id': parts[0],
                'entry_name': parts[1],
                'database': 'unknown'
            }
        else:
            # Unknown format, use as-is
            return {
                'protein_id': full_id,
                'uniprot_id': full_id,
                'entry_name': '',
                'database': 'unknown'
            }

    def create_metadata(self, protein_ids: List[str], start_idx: int, end_idx: int) -> List[Dict[str, Any]]:
        """
        Create metadata dictionaries for a chunk of proteins.

        Args:
            protein_ids: List of all protein IDs
            start_idx: Start index for this chunk
            end_idx: End index for this chunk

        Returns:
            List of metadata dictionaries
        """
        metadata = []

        for i in range(start_idx, end_idx):
            protein_id = protein_ids[i]

            # Parse UniProt ID
            parsed = self.parse_uniprot_id(protein_id)

            # Create metadata dict for Qdrant
            meta = {
                'protein_id': parsed['protein_id'],
                'uniprot_id': parsed['uniprot_id'],
                'entry_name': parsed['entry_name'],
                'database': parsed['database'],
                'chunk_index': i  # Original index for reference
            }

            metadata.append(meta)

        return metadata

    def create_faiss_index(self, embeddings: np.ndarray, normalize: bool = True) -> faiss.Index:
        """
        Create FAISS index from protein embeddings.

        Args:
            embeddings: Numpy array of embeddings
            normalize: Whether to L2-normalize for cosine similarity (default: True)

        Returns:
            FAISS index
        """
        log_with_timestamp(f"Creating FAISS index for {len(embeddings):,} embeddings...")

        if len(embeddings) == 0:
            log_with_timestamp("ERROR: No embeddings to index")
            return None

        try:
            # Ensure array is C-contiguous and float32
            if embeddings.dtype != np.float32:
                log_with_timestamp("Converting embeddings to float32...")
                embeddings = embeddings.astype(np.float32)

            if not embeddings.flags['C_CONTIGUOUS']:
                log_with_timestamp("Making array C-contiguous...")
                embeddings = np.ascontiguousarray(embeddings)

            # Normalize for cosine similarity if requested
            if normalize:
                log_with_timestamp("Normalizing embeddings for cosine similarity...")
                faiss.normalize_L2(embeddings)

            log_with_timestamp(f"Embeddings ready: dtype={embeddings.dtype}, shape={embeddings.shape}")

            # Use IndexFlatIP for cosine similarity (after L2 normalization)
            # Or IndexFlatL2 for L2 distance
            if normalize:
                log_with_timestamp("Creating FAISS IndexFlatIP (cosine similarity)...")
                index = faiss.IndexFlatIP(self.vector_dimension)
            else:
                log_with_timestamp("Creating FAISS IndexFlatL2 (L2 distance)...")
                index = faiss.IndexFlatL2(self.vector_dimension)

            log_with_timestamp(f"Adding {len(embeddings):,} vectors to index...")
            index.add(embeddings)

            log_with_timestamp(f"FAISS index created: {index.ntotal} vectors")
            return index

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to create FAISS index: {e}")
            raise

    def save_index_and_metadata(self, index: faiss.Index, metadata: List[Dict[str, Any]],
                                index_path: str, metadata_path: str) -> bool:
        """Save FAISS index and metadata to files."""
        try:
            # Save FAISS index
            log_with_timestamp(f"Saving FAISS index to {index_path}")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            faiss.write_index(index, index_path)

            # Save metadata
            log_with_timestamp(f"Saving metadata to {metadata_path}")
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)

            # Convert to dict with string keys (required for Qdrant insertion script)
            metadata_dict = {str(i): protein for i, protein in enumerate(metadata)}

            with open(metadata_path, 'w') as f:
                json.dump(metadata_dict, f, indent=2, ensure_ascii=False)

            # Report file sizes
            index_size_mb = os.path.getsize(index_path) / 1024 / 1024
            metadata_size_mb = os.path.getsize(metadata_path) / 1024 / 1024

            log_with_timestamp(f"Files saved successfully:")
            log_with_timestamp(f"  Index: {index_size_mb:.1f}MB")
            log_with_timestamp(f"  Metadata: {metadata_size_mb:.1f}MB")

            return True

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to save files: {e}")
            return False


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Process ESM-2 protein embeddings to create FAISS indices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all embeddings with default chunk size
  %(prog)s --input all_embeddings.h5 \\
      --output-dir data_processing/qdrant/ \\
      --chunk-size 10000

  # Single chunk (no splitting)
  %(prog)s --input all_embeddings.h5 \\
      --output-dir data_processing/qdrant/ \\
      --chunk-size 0

  # Test mode with limit
  %(prog)s --input all_embeddings.h5 \\
      --output-dir test_output/ \\
      --limit 1000
        """
    )
    parser.add_argument(
        "--input", required=True,
        help="Input HDF5 file with ESM-2 embeddings (all_embeddings.h5)"
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Output directory for FAISS indices and metadata"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=10000,
        help="Number of proteins per chunk (0 = single chunk, default: 10000)"
    )
    parser.add_argument(
        "--vector-dimension", type=int, default=640,
        help="Dimension of ESM-2 embeddings (default: 640 for t30 model)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of proteins to process (for testing)"
    )
    parser.add_argument(
        "--no-normalize", action='store_true',
        help="Do not normalize embeddings (use L2 distance instead of cosine)"
    )

    args = parser.parse_args()

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        log_with_timestamp("=== Starting Protein Embeddings Processing ===")

        # Initialize processor
        processor = ProteinEmbeddingsProcessor(args.vector_dimension)

        # Load embeddings
        embeddings, protein_ids = processor.load_embeddings_h5(args.input)

        # Apply limit if specified
        if args.limit and args.limit < len(protein_ids):
            log_with_timestamp(f"Limiting to first {args.limit:,} proteins")
            embeddings = embeddings[:args.limit]
            protein_ids = protein_ids[:args.limit]

        total_proteins = len(protein_ids)
        log_with_timestamp(f"Processing {total_proteins:,} proteins")

        # Determine chunking strategy
        if args.chunk_size == 0 or total_proteins <= args.chunk_size:
            # Single chunk
            log_with_timestamp("Creating single chunk (no splitting)")
            chunks = [(0, total_proteins)]
            chunk_names = ["proteins"]
        else:
            # Multiple chunks
            num_chunks = (total_proteins + args.chunk_size - 1) // args.chunk_size
            log_with_timestamp(f"Splitting into {num_chunks} chunks of ~{args.chunk_size:,} proteins")

            chunks = []
            for i in range(num_chunks):
                start_idx = i * args.chunk_size
                end_idx = min((i + 1) * args.chunk_size, total_proteins)
                chunks.append((start_idx, end_idx))

            chunk_names = [f"proteins_chunk_{i:04d}" for i in range(num_chunks)]

        # Process each chunk
        for chunk_idx, ((start_idx, end_idx), chunk_name) in enumerate(zip(chunks, chunk_names)):
            log_with_timestamp(f"\n=== Processing chunk {chunk_idx + 1}/{len(chunks)}: {chunk_name} ===")
            log_with_timestamp(f"Proteins {start_idx:,} to {end_idx:,} ({end_idx - start_idx:,} proteins)")

            # Extract chunk embeddings
            chunk_embeddings = embeddings[start_idx:end_idx]

            # Create metadata
            chunk_metadata = processor.create_metadata(protein_ids, start_idx, end_idx)

            # Create FAISS index
            index = processor.create_faiss_index(chunk_embeddings, normalize=not args.no_normalize)
            if index is None:
                return 1

            # Save index and metadata
            index_path = os.path.join(args.output_dir, f"{chunk_name}.index")
            metadata_path = os.path.join(args.output_dir, f"{chunk_name}.json")

            if not processor.save_index_and_metadata(index, chunk_metadata, index_path, metadata_path):
                return 1

            log_with_timestamp(f"Chunk {chunk_idx + 1}/{len(chunks)} complete")

        log_with_timestamp("\n=== Protein Embeddings Processing Complete ===")
        log_with_timestamp(f"Created {len(chunks)} FAISS index file(s) in {args.output_dir}")
        return 0

    except KeyboardInterrupt:
        log_with_timestamp("Processing interrupted by user")
        return 1
    except Exception as e:
        log_with_timestamp(f"ERROR during processing: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

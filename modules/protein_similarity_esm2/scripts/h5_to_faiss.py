#!/usr/bin/env python3
"""
Convert H5 embeddings to FAISS index + JSON metadata

Following patents/clinical_trials pattern:
- Input: H5 file with embeddings
- Output: .index (FAISS) + .json (metadata)
"""

import argparse
import h5py
import json
import numpy as np
import faiss
from pathlib import Path


def h5_to_faiss(h5_file, index_file, metadata_file, vector_dim):
    """
    Convert H5 embeddings to FAISS index and JSON metadata.

    Args:
        h5_file: Path to input H5 file
        index_file: Path to output FAISS index file
        metadata_file: Path to output JSON metadata file
        vector_dim: Expected vector dimension
    """
    print(f"Reading embeddings from: {h5_file}")

    # Read H5 file
    with h5py.File(h5_file, 'r') as f:
        embeddings = f['embeddings'][:]
        protein_ids = [id.decode('utf-8') for id in f['ids'][:]]

    num_proteins = len(protein_ids)
    actual_dim = embeddings.shape[1]

    print(f"  Proteins: {num_proteins:,}")
    print(f"  Dimensions: {actual_dim}")

    # Verify dimension
    if actual_dim != vector_dim:
        print(f"WARNING: Expected dimension {vector_dim}, got {actual_dim}")

    # Create FAISS index (L2 distance, same as patents/clinical_trials)
    print(f"Creating FAISS index...")
    index = faiss.IndexFlatL2(actual_dim)

    # Add vectors to index
    embeddings_np = np.array(embeddings, dtype=np.float32)
    index.add(embeddings_np)

    print(f"  Added {index.ntotal:,} vectors to index")

    # Write FAISS index
    print(f"Writing FAISS index: {index_file}")
    faiss.write_index(index, str(index_file))

    # Create metadata (following patents/clinical_trials format - dictionary with string keys)
    metadata = {}
    for i, protein_id in enumerate(protein_ids):
        metadata[str(i)] = {
            'protein_id': protein_id,
            'uniprot_id': protein_id
        }

    # Write metadata as JSON
    print(f"Writing metadata: {metadata_file}")
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"✓ Conversion complete!")
    print(f"  FAISS index: {index_file} ({index.ntotal:,} vectors)")
    print(f"  Metadata: {metadata_file} ({len(metadata):,} entries)")


def main():
    parser = argparse.ArgumentParser(
        description='Convert H5 embeddings to FAISS index + JSON metadata'
    )

    parser.add_argument('h5_file', type=Path,
                       help='Input H5 file with embeddings')
    parser.add_argument('index_file', type=Path,
                       help='Output FAISS index file (.index)')
    parser.add_argument('metadata_file', type=Path,
                       help='Output JSON metadata file (.json)')
    parser.add_argument('--vector-dim', type=int, default=1280,
                       help='Expected vector dimension (default: 1280 for ESM-2 650M)')

    args = parser.parse_args()

    # Validate input
    if not args.h5_file.exists():
        print(f"Error: H5 file not found: {args.h5_file}")
        return 1

    # Create output directories
    args.index_file.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_file.parent.mkdir(parents=True, exist_ok=True)

    # Convert
    h5_to_faiss(args.h5_file, args.index_file, args.metadata_file, args.vector_dim)

    return 0


if __name__ == '__main__':
    exit(main())

#!/usr/bin/env python3
"""
Create FAISS index from ESM-2 embeddings

Builds an efficient vector similarity search index
"""

import argparse
import faiss
import h5py
import numpy as np
import pickle
from pathlib import Path

def create_faiss_index(embeddings_file, output_index, output_metadata, index_type='Flat'):
    """
    Create FAISS index from embeddings

    Args:
        embeddings_file: Path to HDF5 file with embeddings
        output_index: Path to save FAISS index
        output_metadata: Path to save protein ID mapping
        index_type: Type of index ('Flat', 'IVF', 'HNSW')
    """

    print("=" * 80)
    print("Creating FAISS Index from ESM-2 Embeddings")
    print("=" * 80)

    # Load embeddings
    print(f"Loading embeddings from {embeddings_file}")
    with h5py.File(embeddings_file, 'r') as f:
        embeddings = f['embeddings'][:]
        protein_ids = f['ids'][:].astype(str)

    print(f"Loaded {len(protein_ids)} protein embeddings")
    print(f"Embedding dimension: {embeddings.shape[1]}")

    # Normalize embeddings for cosine similarity
    print("Normalizing embeddings for cosine similarity...")
    faiss.normalize_L2(embeddings)

    # Create index based on size
    dimension = embeddings.shape[1]
    n_proteins = len(protein_ids)

    print(f"\nBuilding {index_type} index...")

    if index_type == 'Flat' or n_proteins < 10000:
        # Use flat index for small datasets (exact search)
        index = faiss.IndexFlatIP(dimension)  # Inner Product (cosine after normalization)
        print(f"Using Flat index (exact search)")

    elif index_type == 'IVF':
        # Use IVF for medium datasets (approximate search)
        nlist = min(int(np.sqrt(n_proteins)), 1000)  # Number of clusters
        quantizer = faiss.IndexFlatIP(dimension)
        index = faiss.IndexIVFFlat(quantizer, dimension, nlist, faiss.METRIC_INNER_PRODUCT)

        print(f"Using IVF index with {nlist} clusters")
        print("Training index...")
        index.train(embeddings)

    elif index_type == 'HNSW':
        # Use HNSW for large datasets (very fast approximate search)
        M = 32  # Number of connections per layer
        index = faiss.IndexHNSWFlat(dimension, M, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = 40
        print(f"Using HNSW index with M={M}")

    else:
        raise ValueError(f"Unknown index type: {index_type}")

    # Add vectors to index
    print(f"Adding {n_proteins} vectors to index...")
    index.add(embeddings)

    print(f"Index total vectors: {index.ntotal}")

    # Save index
    print(f"Saving FAISS index to {output_index}")
    faiss.write_index(index, str(output_index))

    # Save metadata (protein IDs mapping)
    print(f"Saving metadata to {output_metadata}")
    metadata = {
        'protein_ids': protein_ids,
        'dimension': dimension,
        'num_proteins': n_proteins,
        'index_type': index_type,
    }

    with open(output_metadata, 'wb') as f:
        pickle.dump(metadata, f)

    # Calculate index size
    index_size = Path(output_index).stat().st_size / 1024 / 1024
    metadata_size = Path(output_metadata).stat().st_size / 1024 / 1024

    print("\n" + "=" * 80)
    print("FAISS Index Creation Complete!")
    print("=" * 80)
    print(f"Index file: {output_index} ({index_size:.2f} MB)")
    print(f"Metadata file: {output_metadata} ({metadata_size:.2f} MB)")
    print(f"Total proteins indexed: {n_proteins}")
    print(f"Embedding dimension: {dimension}")
    print(f"Index type: {index_type}")
    print("=" * 80)


def test_search(index_file, metadata_file, query_id=None, k=10):
    """Test search functionality"""

    print("\nTesting search functionality...")

    # Load index and metadata
    index = faiss.read_index(str(index_file))

    with open(metadata_file, 'rb') as f:
        metadata = pickle.load(f)

    protein_ids = metadata['protein_ids']

    # Load embeddings to get a query
    with h5py.File(embeddings_file, 'r') as f:
        embeddings = f['embeddings'][:]
        ids = f['ids'][:].astype(str)

    # Normalize query
    faiss.normalize_L2(embeddings)

    # Get query vector
    if query_id:
        query_idx = np.where(ids == query_id)[0]
        if len(query_idx) == 0:
            print(f"Query ID {query_id} not found")
            return
        query_idx = query_idx[0]
    else:
        query_idx = 0

    query_vector = embeddings[query_idx:query_idx+1]
    query_protein = ids[query_idx]

    # Search
    scores, indices = index.search(query_vector, k)

    print(f"\nQuery protein: {query_protein}")
    print(f"Top {k} similar proteins:")
    print("-" * 60)
    for i, (idx, score) in enumerate(zip(indices[0], scores[0]), 1):
        print(f"{i:2d}. {protein_ids[idx]:40s} (similarity: {score:.4f})")
    print("-" * 60)


def main():
    parser = argparse.ArgumentParser(description='Create FAISS index from ESM-2 embeddings')
    parser.add_argument('embeddings_h5', type=Path, help='Input HDF5 embeddings file')
    parser.add_argument('output_index', type=Path, help='Output FAISS index file')
    parser.add_argument('--metadata', type=Path, help='Output metadata file (default: <index>.pkl)')
    parser.add_argument('--index-type', choices=['Flat', 'IVF', 'HNSW'], default='auto',
                       help='Index type (auto selects based on size)')
    parser.add_argument('--test', action='store_true', help='Run test search after creation')
    parser.add_argument('--test-id', help='Protein ID for test query')

    args = parser.parse_args()

    # Default metadata path
    if args.metadata is None:
        args.metadata = args.output_index.with_suffix('.pkl')

    # Auto-select index type
    if args.index_type == 'auto':
        with h5py.File(args.embeddings_h5, 'r') as f:
            n_proteins = len(f['ids'])

        if n_proteins < 10000:
            index_type = 'Flat'
        elif n_proteins < 1000000:
            index_type = 'IVF'
        else:
            index_type = 'HNSW'

        print(f"Auto-selected index type: {index_type} (based on {n_proteins:,} proteins)")
    else:
        index_type = args.index_type

    # Create output directory
    args.output_index.parent.mkdir(parents=True, exist_ok=True)

    # Create index
    create_faiss_index(args.embeddings_h5, args.output_index, args.metadata, index_type)

    # Test if requested
    if args.test:
        global embeddings_file
        embeddings_file = args.embeddings_h5
        test_search(args.output_index, args.metadata, args.test_id)


if __name__ == '__main__':
    main()

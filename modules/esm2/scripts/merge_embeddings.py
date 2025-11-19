#!/usr/bin/env python3
"""
Merge embedding HDF5 files from multiple chunks
"""

import argparse
import h5py
import numpy as np
from pathlib import Path

def merge_embeddings(output_file, input_files):
    """Merge multiple HDF5 embedding files into one"""

    print(f"Merging {len(input_files)} embedding files")

    all_embeddings = []
    all_ids = []

    # Read all chunk files
    for input_file in input_files:
        print(f"Reading {input_file}")

        with h5py.File(input_file, 'r') as f:
            embeddings = f['embeddings'][:]
            ids = f['ids'][:].astype(str)  # Convert bytes to str

            all_embeddings.append(embeddings)
            all_ids.extend(ids)

            print(f"  {len(ids)} sequences, shape {embeddings.shape}")

    # Concatenate all embeddings
    all_embeddings = np.vstack(all_embeddings)
    all_ids = np.array(all_ids, dtype=object)

    print(f"\nTotal embeddings: {len(all_ids)}")
    print(f"Merged shape: {all_embeddings.shape}")

    # Save merged file
    print(f"Saving to {output_file}")
    with h5py.File(output_file, 'w') as f:
        f.create_dataset('embeddings', data=all_embeddings, compression='gzip')

        # Store IDs as strings
        dt = h5py.string_dtype(encoding='utf-8')
        f.create_dataset('ids', data=all_ids, dtype=dt)

        # Metadata
        f.attrs['num_sequences'] = len(all_ids)
        f.attrs['embedding_dim'] = all_embeddings.shape[1]
        f.attrs['num_chunks'] = len(input_files)

    print(f"Merge complete!")
    print(f"Output file size: {Path(output_file).stat().st_size / 1024 / 1024:.2f} MB")


def main():
    parser = argparse.ArgumentParser(description='Merge embedding HDF5 files')
    parser.add_argument('output', type=Path, help='Output merged HDF5 file')
    parser.add_argument('inputs', type=Path, nargs='+', help='Input HDF5 files')

    args = parser.parse_args()

    # Create output directory
    args.output.parent.mkdir(parents=True, exist_ok=True)

    merge_embeddings(args.output, args.inputs)


if __name__ == '__main__':
    main()

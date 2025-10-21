#!/usr/bin/env python3
"""
Create a smaller test dataset from full PubMed collection
Samples first N files for faster benchmarking

Usage:
    python create_test_dataset.py --num-files 50 --output-dir /localscratch/tgur/test_data
"""

import argparse
import json
import shutil
from pathlib import Path
import faiss
import numpy as np


def sample_faiss_files(source_dir: Path, num_files: int, output_dir: Path):
    """Copy first N FAISS index files to output directory"""

    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all index files
    index_files = sorted(source_dir.glob("*.index"))[:num_files]

    if not index_files:
        print(f"No index files found in {source_dir}")
        return

    print(f"Sampling {len(index_files)} files from {source_dir}")

    total_vectors = 0

    for idx_file in index_files:
        # Copy index file
        json_file = idx_file.with_suffix('.json')

        # Load to count vectors
        index = faiss.read_index(str(idx_file))
        num_vectors = index.ntotal
        total_vectors += num_vectors

        # Copy files
        shutil.copy2(idx_file, output_dir / idx_file.name)
        if json_file.exists():
            shutil.copy2(json_file, output_dir / json_file.name)

        print(f"  {idx_file.name}: {num_vectors:,} vectors")

    print(f"\nTotal vectors in test set: {total_vectors:,}")
    print(f"Output directory: {output_dir}")

    # Save manifest
    manifest = {
        "source_dir": str(source_dir),
        "num_files": len(index_files),
        "total_vectors": total_vectors,
        "files": [f.name for f in index_files]
    }

    with open(output_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    return total_vectors


def main():
    parser = argparse.ArgumentParser(description="Create test dataset from PubMed collection")
    parser.add_argument(
        "--source-dir",
        default="/data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2/snapshots/out_all/data/processed/pubmed/baseline",
        help="Source directory with FAISS files"
    )
    parser.add_argument("--num-files", type=int, default=50, help="Number of files to sample")
    parser.add_argument("--output-dir", required=True, help="Output directory for test data")

    args = parser.parse_args()

    total_vectors = sample_faiss_files(
        Path(args.source_dir),
        args.num_files,
        Path(args.output_dir)
    )

    print("\n" + "="*60)
    print("Test dataset created successfully!")
    print("="*60)
    print(f"\nYou can now insert this to Qdrant for quick testing:")
    print(f"  Total size: ~{args.num_files * 50}MB (vs 109GB full)")
    print(f"  Vectors: ~{total_vectors:,} (vs 31.5M full)")
    print(f"\nTo insert to local Qdrant:")
    print(f"  python modules/qdrant/scripts/insert_from_faiss.py \\")
    print(f"    --faiss-dir {args.output_dir} \\")
    print(f"    --qdrant-url http://localhost:6333 \\")
    print(f"    --collection pubmed_test")


if __name__ == "__main__":
    main()

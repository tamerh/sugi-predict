#!/usr/bin/env python3
"""
Split FASTA file into chunks for distributed processing
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime
from Bio import SeqIO
from tqdm import tqdm


def count_sequences(fasta_file):
    """Count total sequences in FASTA file"""
    count = 0
    with open(fasta_file, 'r') as f:
        for line in f:
            if line.startswith('>'):
                count += 1
    return count


def split_fasta(input_file, num_chunks, output_dir, state_file=None):
    """
    Split FASTA file into N chunks

    Args:
        input_file: Path to input FASTA file
        num_chunks: Number of chunks to create
        output_dir: Directory to write chunk files
        state_file: Optional path to write processed_chunks.json state file
    """
    # Create output directory
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # First pass: count sequences
    print("Counting sequences...")
    total_sequences = count_sequences(input_file)
    print(f"Total sequences: {total_sequences:,}")

    # Calculate chunk size
    chunk_size = total_sequences // num_chunks
    remainder = total_sequences % num_chunks

    print(f"Splitting into {num_chunks} chunks")
    print(f"Chunk size: ~{chunk_size:,} sequences per chunk")

    # Open all output files
    output_files = []
    output_handles = []
    for i in range(num_chunks):
        chunk_file = output_dir / f"chunk_{i+1:03d}.fasta"
        output_files.append(chunk_file)
        output_handles.append(open(chunk_file, 'w'))

    # Second pass: distribute sequences
    current_chunk = 0
    sequences_in_chunk = 0

    # Determine chunk size for current chunk (some chunks get +1 for remainder)
    current_chunk_size = chunk_size + (1 if current_chunk < remainder else 0)

    print("\nSplitting sequences...")
    with tqdm(total=total_sequences, unit='seq') as pbar:
        for record in SeqIO.parse(input_file, 'fasta'):
            # Write to current chunk
            SeqIO.write(record, output_handles[current_chunk], 'fasta')
            sequences_in_chunk += 1
            pbar.update(1)

            # Move to next chunk if current is full
            if sequences_in_chunk >= current_chunk_size:
                current_chunk += 1
                sequences_in_chunk = 0

                # Update chunk size for next chunk
                if current_chunk < num_chunks:
                    current_chunk_size = chunk_size + (1 if current_chunk < remainder else 0)

    # Close all files
    for handle in output_handles:
        handle.close()

    # Report chunk statistics and build state dict
    print("\nChunk statistics:")
    chunks_dict = {}

    for i, chunk_file in enumerate(output_files):
        chunk_seqs = count_sequences(chunk_file)
        chunk_size_mb = chunk_file.stat().st_size / (1024 * 1024)
        print(f"  Chunk {i+1:03d}: {chunk_seqs:6,} sequences, {chunk_size_mb:6.1f} MB - {chunk_file.name}")

        # Build state entry following patents/clinical_trials convention
        chunks_dict[chunk_file.name] = {
            'status': 'ready_to_process',
            'num_proteins': chunk_seqs,
            'size_mb': round(chunk_size_mb, 2)
        }

    print(f"\nTotal chunks created: {len(output_files)}")
    print(f"Output directory: {output_dir}")

    # Write state file if requested (following patents/clinical_trials format)
    if state_file:
        state_file = Path(state_file)
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state_data = {
            'last_update': datetime.now().isoformat(),
            'no_changes': False,
            'chunks': chunks_dict
        }

        with open(state_file, 'w') as f:
            json.dump(state_data, f, indent=2)

        print(f"\nState file written: {state_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Split FASTA file into chunks for distributed processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Split into 20 chunks
  %(prog)s uniprot_swissprot.fasta 20 chunks/

  # Split into 50 chunks
  %(prog)s uniprot_trembl.fasta 50 chunks/
        """
    )

    parser.add_argument('input_fasta', type=Path,
                       help='Input FASTA file')
    parser.add_argument('num_chunks', type=int,
                       help='Number of chunks to create')
    parser.add_argument('output_dir', type=Path,
                       help='Output directory for chunk files')
    parser.add_argument('--state-file', type=Path,
                       help='Optional: Write processed_chunks.json state file')

    args = parser.parse_args()

    # Validate inputs
    if not args.input_fasta.exists():
        print(f"Error: Input file not found: {args.input_fasta}", file=sys.stderr)
        sys.exit(1)

    if args.num_chunks < 1:
        print(f"Error: num_chunks must be >= 1", file=sys.stderr)
        sys.exit(1)

    # Run splitting
    split_fasta(args.input_fasta, args.num_chunks, args.output_dir, args.state_file)


if __name__ == '__main__':
    main()

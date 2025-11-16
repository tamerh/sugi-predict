#!/usr/bin/env python3
"""
Download UniProt FASTA file (SwissProt or TrEMBL)
"""

import argparse
import gzip
import shutil
import sys
from pathlib import Path
import urllib.request
from tqdm import tqdm


class DownloadProgressBar(tqdm):
    """Progress bar for downloads"""
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


def download_file(url, output_path):
    """Download file with progress bar"""
    print(f"Downloading from: {url}")
    print(f"Saving to: {output_path}")

    with DownloadProgressBar(unit='B', unit_scale=True, miniters=1, desc=url.split('/')[-1]) as t:
        urllib.request.urlretrieve(url, filename=output_path, reporthook=t.update_to)


def decompress_gzip(input_path, output_path, limit=0):
    """Decompress gzip file with optional sequence limit"""
    print(f"Decompressing {input_path}...")
    if limit > 0:
        print(f"Limiting to first {limit:,} sequences (test mode)")

    sequences_written = 0
    with gzip.open(input_path, 'rb') as f_in:
        with open(output_path, 'wb') as f_out:
            if limit > 0:
                # Read line by line and stop after N sequences
                in_sequence = False
                for line in f_in:
                    if line.startswith(b'>'):
                        if sequences_written >= limit:
                            break
                        sequences_written += 1
                        in_sequence = True
                    if in_sequence:
                        f_out.write(line)
            else:
                # No limit - copy entire file
                shutil.copyfileobj(f_in, f_out)

    if limit > 0:
        print(f"Decompressed {sequences_written:,} sequences to {output_path}")
    else:
        print(f"Decompressed to {output_path}")


def count_sequences(fasta_path):
    """Count number of sequences in FASTA file"""
    count = 0
    with open(fasta_path, 'r') as f:
        for line in f:
            if line.startswith('>'):
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description='Download UniProt FASTA file')
    parser.add_argument('--dataset', required=True, choices=['swissprot', 'trembl', 'both', 'test'],
                       help='Dataset to download')
    parser.add_argument('--output-dir', required=True, type=Path,
                       help='Output directory for downloaded files')
    parser.add_argument('--keep-compressed', action='store_true',
                       help='Keep the compressed .gz file after decompression')
    parser.add_argument('--limit', type=int, default=0,
                       help='Limit number of sequences (test mode, 0=no limit)')

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # URLs for different datasets
    urls = {
        'swissprot': 'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz',
        'trembl': 'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_trembl.fasta.gz'
    }

    # Handle "test" option - use SwissProt with limit
    if args.dataset == 'test':
        print("=" * 80)
        print("TEST MODE: Downloading SwissProt with limit")
        print("=" * 80)

        url = urls['swissprot']
        filename = "uniprot_test.fasta"
        compressed_path = args.output_dir / f"{filename}.gz"
        decompressed_path = args.output_dir / filename

        # Check if output file already exists (skip download)
        if decompressed_path.exists():
            num_sequences = count_sequences(decompressed_path)
            print(f"\n✓ File already exists: {decompressed_path}")
            print(f"  Number of sequences: {num_sequences:,}")
            print("  Skipping download (use --force to re-download)")

            # Still write metadata
            metadata_path = args.output_dir / f"{filename}.metadata.txt"
            if not metadata_path.exists():
                with open(metadata_path, 'w') as f:
                    f.write(f"dataset: test\n")
                    f.write(f"source: swissprot (limited)\n")
                    f.write(f"url: {url}\n")
                    f.write(f"num_sequences: {num_sequences}\n")
                    f.write(f"file: {filename}\n")
            return

        # Download
        download_file(url, compressed_path)

        # Decompress with limit
        limit = args.limit if args.limit > 0 else 1000  # Default to 1000 for test mode
        decompress_gzip(compressed_path, decompressed_path, limit=limit)

        # Count sequences
        num_sequences = count_sequences(decompressed_path)
        print(f"\nDownload complete!")
        print(f"Dataset: test (SwissProt subset)")
        print(f"Number of sequences: {num_sequences:,}")
        print(f"Output file: {decompressed_path}")

        # Remove compressed file
        if not args.keep_compressed:
            compressed_path.unlink()
            print(f"Removed compressed file: {compressed_path}")

        # Write metadata
        metadata_path = args.output_dir / f"{filename}.metadata.txt"
        with open(metadata_path, 'w') as f:
            f.write(f"dataset: test\n")
            f.write(f"source: swissprot (limited)\n")
            f.write(f"url: {url}\n")
            f.write(f"num_sequences: {num_sequences}\n")
            f.write(f"limit_applied: {limit}\n")
            f.write(f"file: {filename}\n")

        print(f"Metadata written to: {metadata_path}")

    # Handle "both" option - download and concatenate SwissProt + TrEMBL
    elif args.dataset == 'both':
        print("=" * 80)
        print("Downloading BOTH SwissProt and TrEMBL")
        print("=" * 80)

        datasets_to_download = ['swissprot', 'trembl']
        downloaded_files = []
        total_sequences = 0

        # Download both datasets
        for dataset in datasets_to_download:
            print(f"\n{'=' * 80}")
            print(f"Downloading {dataset.upper()}")
            print(f"{'=' * 80}")

            url = urls[dataset]
            filename = f"uniprot_{dataset}.fasta"
            compressed_path = args.output_dir / f"{filename}.gz"
            decompressed_path = args.output_dir / filename

            # Download
            download_file(url, compressed_path)

            # Decompress (no limit for "both" mode)
            decompress_gzip(compressed_path, decompressed_path, limit=0)

            # Count sequences
            num_sequences = count_sequences(decompressed_path)
            print(f"{dataset.upper()}: {num_sequences:,} sequences")

            downloaded_files.append(decompressed_path)
            total_sequences += num_sequences

            # Remove compressed file
            if not args.keep_compressed:
                compressed_path.unlink()

        # Concatenate both files
        print(f"\n{'=' * 80}")
        print("Concatenating SwissProt + TrEMBL")
        print(f"{'=' * 80}")

        combined_path = args.output_dir / "uniprot_both.fasta"
        with open(combined_path, 'w') as outfile:
            for fasta_file in downloaded_files:
                with open(fasta_file, 'r') as infile:
                    shutil.copyfileobj(infile, outfile)
                print(f"Added {fasta_file.name} to combined file")

        print(f"\nCombined file created: {combined_path}")
        print(f"Total sequences: {total_sequences:,}")

        # Write metadata
        metadata_path = args.output_dir / "uniprot_both.fasta.metadata.txt"
        with open(metadata_path, 'w') as f:
            f.write(f"dataset: both\n")
            f.write(f"sources: swissprot, trembl\n")
            f.write(f"num_sequences: {total_sequences}\n")
            f.write(f"file: uniprot_both.fasta\n")

        print(f"Metadata written to: {metadata_path}")

    else:
        # Single dataset download
        url = urls[args.dataset]
        filename = f"uniprot_{args.dataset}.fasta"
        compressed_path = args.output_dir / f"{filename}.gz"
        decompressed_path = args.output_dir / filename

        # Check if output file already exists (skip download)
        if decompressed_path.exists():
            num_sequences = count_sequences(decompressed_path)
            print(f"\n✓ File already exists: {decompressed_path}")
            print(f"  Number of sequences: {num_sequences:,}")
            print("  Skipping download (use --force to re-download)")

            # Still write metadata
            metadata_path = args.output_dir / f"{filename}.metadata.txt"
            if not metadata_path.exists():
                with open(metadata_path, 'w') as f:
                    f.write(f"dataset: {args.dataset}\n")
                    f.write(f"url: {url}\n")
                    f.write(f"num_sequences: {num_sequences}\n")
                    f.write(f"file: {filename}\n")
            return

        # Download
        download_file(url, compressed_path)

        # Decompress with optional limit
        decompress_gzip(compressed_path, decompressed_path, limit=args.limit)

        # Count sequences
        num_sequences = count_sequences(decompressed_path)
        print(f"\nDownload complete!")
        print(f"Dataset: {args.dataset}")
        print(f"Number of sequences: {num_sequences:,}")
        print(f"Output file: {decompressed_path}")

        # Optionally remove compressed file
        if not args.keep_compressed:
            compressed_path.unlink()
            print(f"Removed compressed file: {compressed_path}")

        # Write metadata
        metadata_path = args.output_dir / f"{filename}.metadata.txt"
        with open(metadata_path, 'w') as f:
            f.write(f"dataset: {args.dataset}\n")
            f.write(f"url: {url}\n")
            f.write(f"num_sequences: {num_sequences}\n")
            f.write(f"file: {filename}\n")

        print(f"Metadata written to: {metadata_path}")


if __name__ == '__main__':
    main()

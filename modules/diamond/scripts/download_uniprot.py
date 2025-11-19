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


def decompress_gzip(input_path, output_path):
    """Decompress gzip file"""
    print(f"Decompressing {input_path}...")

    with gzip.open(input_path, 'rb') as f_in:
        with open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

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

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Handle test mode - copy from test fixture
    if args.dataset == 'test':
        print("=" * 80)
        print("TEST MODE: Using local test fixture")
        print("=" * 80)

        # Path to test fixture (relative to project root)
        test_fixture = Path(__file__).parent.parent.parent.parent / "tests/fixtures/protein_similarity_diamond/test_proteins.fasta"
        output_path = args.output_dir / "test_proteins.fasta"

        if not test_fixture.exists():
            print(f"ERROR: Test fixture not found: {test_fixture}")
            print("Please ensure test fixture exists at: tests/fixtures/protein_similarity_diamond/test_proteins.fasta")
            sys.exit(1)

        # Copy test file
        print(f"Copying test fixture from: {test_fixture}")
        print(f"To: {output_path}")
        shutil.copy(test_fixture, output_path)

        # Count sequences
        num_sequences = count_sequences(output_path)
        print(f"\nTest dataset ready!")
        print(f"Number of sequences: {num_sequences:,}")
        print(f"Output file: {output_path}")

        # Write metadata
        metadata_path = args.output_dir / "test_proteins.fasta.metadata.txt"
        with open(metadata_path, 'w') as f:
            f.write(f"dataset: test\n")
            f.write(f"source: {test_fixture}\n")
            f.write(f"num_sequences: {num_sequences}\n")
            f.write(f"file: test_proteins.fasta\n")

        print(f"Metadata written to: {metadata_path}")
        return

    # URLs for different datasets
    urls = {
        'swissprot': 'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz',
        'trembl': 'https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_trembl.fasta.gz'
    }

    # Handle "both" option - download and concatenate SwissProt + TrEMBL
    if args.dataset == 'both':
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

            # Decompress
            decompress_gzip(compressed_path, decompressed_path)

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

        # Download
        download_file(url, compressed_path)

        # Decompress
        decompress_gzip(compressed_path, decompressed_path)

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

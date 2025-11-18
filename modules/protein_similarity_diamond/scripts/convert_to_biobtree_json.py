#!/usr/bin/env python3
"""
Convert DIAMOND similarity TSV to BioBTree JSON format

Reads filtered TSV results and converts to JSON format for BioBTree ingestion.
Extracts UniProt accessions from full IDs (sp|Q6GZX4|... → Q6GZX4)
"""

import argparse
import json
import pandas as pd
from pathlib import Path
from collections import defaultdict


def extract_accession(protein_id):
    """
    Extract UniProt accession from full ID

    Examples:
        sp|Q6GZX4|001R_FRG3G → Q6GZX4
        tr|A0A000|EXAMPLE → A0A000
        Q6GZX4 → Q6GZX4 (already accession)
    """
    if '|' in protein_id:
        parts = protein_id.split('|')
        if len(parts) >= 2:
            return parts[1]
    return protein_id


def convert_tsv_to_biobtree_json(tsv_file, output_json, dataset="swissprot"):
    """
    Convert DIAMOND TSV results to BioBTree JSON format

    Args:
        tsv_file: Path to filtered TSV file (query_id, target_id, identity, ...)
        output_json: Path to output JSON file
        dataset: Dataset name (swissprot, trembl, test)
    """
    print(f"Reading TSV file: {tsv_file}")

    # Read TSV file
    # DIAMOND blastp output format 6 columns:
    # query_id, target_id, identity, alignment_length, mismatches, gap_opens,
    # q_start, q_end, s_start, s_end, evalue, bitscore
    # Note: filter_top_k.py adds a header row, so we use header=0
    df = pd.read_csv(
        tsv_file,
        sep='\t',
        header=0  # Use first row as header (from filter_top_k.py)
    )

    print(f"  Total similarity pairs: {len(df):,}")

    # Extract accessions
    df['query_accession'] = df['query_id'].apply(extract_accession)
    df['target_accession'] = df['target_id'].apply(extract_accession)

    # Group by query protein
    protein_similarities = []
    grouped = df.groupby('query_accession')

    print(f"  Unique query proteins: {len(grouped):,}")

    for query_acc, group in grouped:
        # Sort by bitscore descending (best matches first)
        group_sorted = group.sort_values('bitscore', ascending=False)

        # Create similar proteins list
        similar_proteins = []
        for _, row in group_sorted.iterrows():
            similar_proteins.append({
                'target_id': row['target_accession'],
                'identity': round(float(row['identity']), 2),
                'alignment_length': int(row['alignment_length']),
                'evalue': float(row['evalue']),
                'bitscore': round(float(row['bitscore']), 1)
            })

        # Create entry for this query protein
        protein_similarities.append({
            'query_id': query_acc,
            'dataset': dataset,
            'num_similar': len(similar_proteins),
            'similar_proteins': similar_proteins
        })

    # Create BioBTree JSON structure
    biobtree_data = {
        'protein_similarities': protein_similarities
    }

    # Write JSON
    print(f"Writing BioBTree JSON: {output_json}")
    with open(output_json, 'w') as f:
        json.dump(biobtree_data, f, indent=2)

    print(f"✓ Conversion complete!")
    print(f"  Output: {output_json}")
    print(f"  Proteins: {len(protein_similarities):,}")
    print(f"  Total similarities: {len(df):,}")


def main():
    parser = argparse.ArgumentParser(
        description='Convert DIAMOND TSV to BioBTree JSON format'
    )

    parser.add_argument('tsv_file', type=Path,
                       help='Input TSV file (filtered DIAMOND results)')
    parser.add_argument('output_json', type=Path,
                       help='Output JSON file for BioBTree')
    parser.add_argument('--dataset', type=str, default='swissprot',
                       help='Dataset name (swissprot, trembl, test)')

    args = parser.parse_args()

    # Validate input
    if not args.tsv_file.exists():
        print(f"ERROR: TSV file not found: {args.tsv_file}")
        return 1

    # Create output directory
    args.output_json.parent.mkdir(parents=True, exist_ok=True)

    # Convert
    convert_tsv_to_biobtree_json(args.tsv_file, args.output_json, args.dataset)

    return 0


if __name__ == '__main__':
    exit(main())

#!/usr/bin/env python3
"""
Filter DIAMOND results to keep top-K most similar proteins for each query
"""

import argparse
import sys
from pathlib import Path
from collections import defaultdict
import heapq
from tqdm import tqdm


def count_lines(file_path):
    """Count lines in file"""
    with open(file_path, 'r') as f:
        return sum(1 for _ in f)


def parse_diamond_line(line):
    """
    Parse one line of DIAMOND output (outfmt 6)

    Returns: (query_id, target_id, identity, alignment_length, evalue, bitscore)
    """
    fields = line.strip().split('\t')

    query_id = fields[0]
    target_id = fields[1]
    identity = float(fields[2])
    alignment_length = int(fields[3])
    evalue = float(fields[10])
    bitscore = float(fields[11])

    return query_id, target_id, identity, alignment_length, evalue, bitscore


def filter_top_k(input_file, output_file, k=1000, min_identity=0.0):
    """
    Filter DIAMOND results to keep top-K per query

    Strategy:
    - Read all results into memory grouped by query
    - For each query, keep top-K by bitscore
    - Write filtered results

    Args:
        input_file: Input DIAMOND TSV file
        output_file: Output filtered TSV file
        k: Number of top results to keep per query
        min_identity: Minimum percent identity threshold
    """
    print(f"Reading results from: {input_file}")
    print(f"Keeping top-{k} per query")
    print(f"Minimum identity: {min_identity}%")

    # Dictionary to store results per query
    # Structure: {query_id: [(bitscore, line), ...]}
    results_by_query = defaultdict(list)

    # Count total lines for progress bar
    total_lines = count_lines(input_file)
    print(f"Total input lines: {total_lines:,}")

    # Read all results
    print("\nReading and grouping by query...")
    with open(input_file, 'r') as f:
        for line in tqdm(f, total=total_lines, unit='lines'):
            try:
                query_id, target_id, identity, aln_len, evalue, bitscore = parse_diamond_line(line)

                # Skip self-hits
                if query_id == target_id:
                    continue

                # Skip low-identity hits
                if identity < min_identity:
                    continue

                # Add to query's results
                results_by_query[query_id].append((bitscore, line))

            except Exception as e:
                print(f"Warning: Could not parse line: {line[:100]}...", file=sys.stderr)
                print(f"Error: {e}", file=sys.stderr)
                continue

    print(f"\nUnique query proteins: {len(results_by_query):,}")

    # Filter to top-K per query and write output
    print(f"\nFiltering to top-{k} per query and writing output...")

    total_output_lines = 0
    queries_with_results = 0

    with open(output_file, 'w') as out:
        # Write header
        out.write("query_id\ttarget_id\tidentity\talignment_length\tmismatches\t"
                 "gap_opens\tq_start\tq_end\ts_start\ts_end\tevalue\tbitscore\n")

        for query_id in tqdm(sorted(results_by_query.keys()), unit='queries'):
            # Get all results for this query
            query_results = results_by_query[query_id]

            # Sort by bitscore (descending) and take top-K
            # heapq.nlargest is efficient for getting top-K from large list
            top_k_results = heapq.nlargest(k, query_results, key=lambda x: x[0])

            # Write top-K results
            for bitscore, line in top_k_results:
                out.write(line)
                total_output_lines += 1

            if len(top_k_results) > 0:
                queries_with_results += 1

    print(f"\nFiltering complete!")
    print(f"Queries with results: {queries_with_results:,}")
    print(f"Total output lines: {total_output_lines:,}")
    print(f"Average hits per query: {total_output_lines / max(queries_with_results, 1):.1f}")
    print(f"Output written to: {output_file}")

    # Calculate compression ratio
    compression_ratio = (1 - total_output_lines / max(total_lines, 1)) * 100
    print(f"Compression: {compression_ratio:.1f}% reduction in size")


def main():
    parser = argparse.ArgumentParser(
        description='Filter DIAMOND results to keep top-K per query',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Keep top-1000 per query
  %(prog)s merged_results.tsv filtered_results.tsv --k 1000

  # Keep top-500 with minimum 30% identity
  %(prog)s merged_results.tsv filtered_results.tsv --k 500 --min-identity 30
        """
    )

    parser.add_argument('input_file', type=Path,
                       help='Input DIAMOND results TSV file')
    parser.add_argument('output_file', type=Path,
                       help='Output filtered TSV file')
    parser.add_argument('--k', type=int, default=1000,
                       help='Number of top results to keep per query (default: 1000)')
    parser.add_argument('--min-identity', type=float, default=0.0,
                       help='Minimum percent identity threshold (default: 0.0)')

    args = parser.parse_args()

    # Validate inputs
    if not args.input_file.exists():
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    if args.k < 1:
        print(f"Error: k must be >= 1", file=sys.stderr)
        sys.exit(1)

    if args.min_identity < 0 or args.min_identity > 100:
        print(f"Error: min_identity must be between 0 and 100", file=sys.stderr)
        sys.exit(1)

    # Create output directory if needed
    args.output_file.parent.mkdir(parents=True, exist_ok=True)

    # Run filtering
    filter_top_k(args.input_file, args.output_file, k=args.k, min_identity=args.min_identity)


if __name__ == '__main__':
    main()

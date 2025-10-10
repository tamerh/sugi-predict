#!/usr/bin/env python3
"""
Generate PubMed Test Fixture

Extracts diverse abstracts from production PubMed data to create a small
test fixture file for deterministic testing.

Usage:
    python tests/scripts/generate_pubmed_fixture.py \
        --source-dir /path/to/pubmed/raw_data \
        --output tests/fixtures/pubmed/test_abstracts.xml.gz \
        --num-abstracts 50
"""

import os
import sys
import gzip
import argparse
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Set


def log(message: str):
    """Print log message."""
    print(f"[INFO] {message}")


def parse_pubmed_file(xml_path: str, max_abstracts: int = None) -> List[ET.Element]:
    """Parse a PubMed XML file and extract article elements using streaming."""
    articles = []

    try:
        log(f"Parsing {xml_path}")

        with gzip.open(xml_path, 'rt', encoding='utf-8') as f:
            # Use iterparse for memory-efficient streaming
            context = ET.iterparse(f, events=('end',))

            for event, elem in context:
                if elem.tag == 'PubmedArticle':
                    # Only include articles with abstracts
                    abstract = elem.find('.//Abstract/AbstractText')
                    if abstract is not None and abstract.text:
                        # Make a copy to preserve the element
                        article_copy = ET.fromstring(ET.tostring(elem))
                        articles.append(article_copy)

                    # Clear element to save memory
                    elem.clear()

                    if max_abstracts and len(articles) >= max_abstracts:
                        break

        log(f"  Found {len(articles)} articles with abstracts")
        return articles

    except Exception as e:
        log(f"  ERROR parsing {xml_path}: {e}")
        return []


def extract_diverse_abstracts(source_dir: str, num_abstracts: int = 50,
                              max_files: int = 10) -> List[ET.Element]:
    """Extract diverse abstracts from multiple PubMed files."""

    # Find XML files
    source_path = Path(source_dir)
    baseline_files = list(source_path.glob('baseline/*.xml.gz'))
    update_files = list(source_path.glob('updatefiles/*.xml.gz'))

    all_files = baseline_files + update_files

    if not all_files:
        log(f"ERROR: No XML files found in {source_dir}")
        return []

    log(f"Found {len(baseline_files)} baseline files and {len(update_files)} update files")

    # Sample files randomly for diversity
    random.seed(42)  # Fixed seed for reproducibility
    sampled_files = random.sample(all_files, min(max_files, len(all_files)))

    log(f"Sampling {len(sampled_files)} files for diversity")

    # Extract abstracts from sampled files
    all_articles = []
    abstracts_per_file = max(num_abstracts // len(sampled_files), 10)

    for xml_file in sampled_files:
        articles = parse_pubmed_file(str(xml_file), max_abstracts=abstracts_per_file)
        all_articles.extend(articles)

        if len(all_articles) >= num_abstracts:
            break

    # Shuffle and limit to requested number
    random.shuffle(all_articles)
    selected_articles = all_articles[:num_abstracts]

    log(f"Selected {len(selected_articles)} diverse abstracts")

    return selected_articles


def create_fixture_file(articles: List[ET.Element], output_path: str):
    """Create a valid PubMed XML fixture file."""

    log(f"Creating fixture file: {output_path}")

    # Create PubmedArticleSet root element
    root = ET.Element('PubmedArticleSet')

    # Add articles
    for article in articles:
        root.append(article)

    # Create XML tree
    tree = ET.ElementTree(root)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Write to compressed file
    with gzip.open(output_path, 'wt', encoding='utf-8') as f:
        # Write XML declaration and DOCTYPE
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        f.write('<!DOCTYPE PubmedArticleSet SYSTEM "http://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_250101.dtd">\n')

        # Write tree
        tree.write(f, encoding='unicode', xml_declaration=False)

    # Report file size
    size_kb = os.path.getsize(output_path) / 1024
    log(f"Fixture created: {size_kb:.1f} KB")

    # Extract and show PMIDs for reference
    pmids = []
    for article in articles:
        pmid_elem = article.find('.//PMID')
        if pmid_elem is not None:
            pmids.append(pmid_elem.text)

    log(f"PMIDs included: {', '.join(pmids[:10])}{'...' if len(pmids) > 10 else ''}")

    # Save PMID list for reference
    pmid_list_path = output_path.replace('.xml.gz', '_pmids.txt')
    with open(pmid_list_path, 'w') as f:
        for pmid in pmids:
            f.write(f"{pmid}\n")

    log(f"PMID list saved to: {pmid_list_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate PubMed test fixture from production data"
    )
    parser.add_argument(
        '--source-dir', required=True,
        help='Source directory containing PubMed raw data (baseline/ and updatefiles/)'
    )
    parser.add_argument(
        '--output', required=True,
        help='Output path for test fixture (e.g., tests/fixtures/pubmed/test_abstracts.xml.gz)'
    )
    parser.add_argument(
        '--num-abstracts', type=int, default=50,
        help='Number of abstracts to extract (default: 50)'
    )
    parser.add_argument(
        '--max-files', type=int, default=10,
        help='Maximum number of source files to sample (default: 10)'
    )

    args = parser.parse_args()

    log("=" * 80)
    log("PubMed Fixture Generation")
    log("=" * 80)
    log(f"Source: {args.source_dir}")
    log(f"Output: {args.output}")
    log(f"Target abstracts: {args.num_abstracts}")
    log("")

    # Extract diverse abstracts
    articles = extract_diverse_abstracts(
        args.source_dir,
        num_abstracts=args.num_abstracts,
        max_files=args.max_files
    )

    if not articles:
        log("ERROR: No articles extracted")
        return 1

    # Create fixture file
    create_fixture_file(articles, args.output)

    log("")
    log("=" * 80)
    log("Fixture generation complete!")
    log("=" * 80)

    return 0


if __name__ == '__main__':
    sys.exit(main())

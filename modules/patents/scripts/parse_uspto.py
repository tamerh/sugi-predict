#!/usr/bin/env python3
"""
USPTO XML Parser with SureChEMBL Filtering

Parses USPTO XML files but ONLY extracts patents that exist in SureChEMBL.
This filters for biomedical/chemical patents and drastically reduces processing.

Input:
    - USPTO XML files (ZIP archives)
    - US patent IDs from SureChEMBL (text file, one ID per line)

Output:
    - Parquet file with filtered patent data (abstract, claims, description)

Usage:
    python parse_uspto.py \
        --input-dir raw_data/patents/uspto/2025-10-29/raw \
        --filter-ids state/patents/2025-10-29/us_patent_ids.txt \
        --output raw_data/patents/uspto/2025-10-29/parsed.parquet
"""

import os
import sys
import argparse
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Set, Optional
from datetime import datetime
import pandas as pd
from tqdm import tqdm


def log(message: str) -> None:
    """Print message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)


class USPTOParser:
    """Parses USPTO XML files with SureChEMBL filtering."""

    def __init__(self, filter_ids: Set[str], debug: bool = False):
        self.filter_ids = filter_ids
        self.debug = debug
        self.stats = {
            'total_parsed': 0,
            'matched': 0,
            'skipped': 0
        }

    def parse_zip_file(self, zip_path: Path) -> List[Dict]:
        """
        Parse a USPTO ZIP file and extract matching patents.

        Args:
            zip_path: Path to ZIP file

        Returns:
            List of patent dicts
        """
        log(f"Parsing: {zip_path.name}")

        patents = []

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # USPTO ZIPs typically contain one or more XML files
                xml_files = [f for f in zf.namelist() if f.endswith('.xml')]

                for xml_file in xml_files:
                    with zf.open(xml_file) as f:
                        file_patents = self.parse_xml_file(f)
                        patents.extend(file_patents)

        except Exception as e:
            log(f"Error parsing {zip_path.name}: {e}")

        return patents

    def parse_xml_file(self, xml_file) -> List[Dict]:
        """
        Parse USPTO XML file by splitting into individual patent documents.

        USPTO XMLs contain multiple root elements (one per patent) concatenated.
        We read line-by-line, accumulate each patent, and parse individually.
        """
        patents = []

        try:
            # Convert to text stream if needed
            import io
            if isinstance(xml_file, io.BytesIO) or not hasattr(xml_file, 'read'):
                text_stream = io.TextIOWrapper(xml_file, encoding='utf-8', errors='ignore')
            else:
                # For ZipExtFile, read and create text stream
                content = xml_file.read()
                text_stream = io.StringIO(content.decode('utf-8', errors='ignore'))

            if self.debug:
                log(f"  Starting line-by-line patent extraction...")

            # Accumulate lines for current patent
            current_patent_lines = []
            in_patent = False
            patent_tag = None

            for line in text_stream:
                # Check for start of patent document
                if '<us-patent-application' in line:
                    in_patent = True
                    patent_tag = 'us-patent-application'
                    current_patent_lines = [line]
                elif '<us-patent-grant' in line:
                    in_patent = True
                    patent_tag = 'us-patent-grant'
                    current_patent_lines = [line]
                elif in_patent:
                    current_patent_lines.append(line)

                    # Check for end of patent document
                    if f'</{patent_tag}>' in line:
                        # We have a complete patent - parse it
                        patent_xml = ''.join(current_patent_lines)

                        try:
                            # Add XML declaration and parse
                            full_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + patent_xml
                            root = ET.fromstring(full_xml.encode('utf-8'))

                            # Extract patent data
                            patent_data = self.extract_patent_data(root)

                            self.stats['total_parsed'] += 1

                            # Check if this patent is in SureChEMBL
                            if patent_data and patent_data['patent_number'] in self.filter_ids:
                                self.stats['matched'] += 1
                                patents.append(patent_data)

                                if self.stats['matched'] % 100 == 0:
                                    log(f"  Matched {self.stats['matched']} patents so far...")
                            else:
                                self.stats['skipped'] += 1

                                # Debug: show first and last few patent numbers from each file
                                if self.debug and (self.stats['total_parsed'] <= 5 or
                                                  (self.stats['total_parsed'] >= 6460 and self.stats['total_parsed'] <= 6470)):
                                    log(f"    DEBUG: Patent #{self.stats['total_parsed']}: '{patent_data.get('patent_number') if patent_data else 'None'}' not in SureChEMBL filter")

                            # Log progress every 1000 patents
                            if self.stats['total_parsed'] % 1000 == 0:
                                log(f"  Processed {self.stats['total_parsed']} patents ({self.stats['matched']} matched)...")

                        except ET.ParseError as e:
                            if self.debug:
                                log(f"  XML parse error for individual patent: {e}")
                        except Exception as e:
                            if self.debug:
                                log(f"  Error parsing individual patent: {e}")

                        # Reset for next patent (free memory)
                        current_patent_lines = []
                        in_patent = False
                        patent_tag = None

        except Exception as e:
            log(f"Error reading XML file: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()

        return patents

    def extract_patent_data(self, elem: ET.Element) -> Optional[Dict]:
        """
        Extract patent data from XML element.

        Args:
            elem: us-patent-application or us-patent-grant element

        Returns:
            Dict with patent data or None if extraction failed
        """
        try:
            # Extract patent number
            patent_number = self._extract_patent_number(elem)
            if not patent_number:
                return None

            # Extract text fields
            title = self._extract_title(elem)
            abstract = self._extract_abstract(elem)
            claims = self._extract_claims(elem)
            description = self._extract_description(elem)
            pub_date = self._extract_publication_date(elem)

            return {
                'patent_number': patent_number,
                'title': title,
                'abstract': abstract,
                'claims': claims,
                'description': description,
                'publication_date': pub_date
            }

        except Exception as e:
            if self.debug:
                log(f"Error extracting patent data: {e}")
            return None

    def _extract_patent_number(self, elem: ET.Element) -> Optional[str]:
        """
        Extract patent number in SureChEMBL format: US-NNNNNNN-XX

        Examples:
            US-20250318453-A1 (application)
            US-12187654-B2 (grant)
        """
        # Try different paths for different XML formats
        paths = [
            './/publication-reference/document-id/doc-number',
            './/document-id/doc-number',
            './/us-bibliographic-data-application/publication-reference/document-id/doc-number',
            './/us-bibliographic-data-grant/publication-reference/document-id/doc-number'
        ]

        doc_number = None
        for path in paths:
            el = elem.find(path)
            if el is not None and el.text:
                doc_number = el.text.strip()
                break

        if not doc_number:
            return None

        # Extract kind code
        kind_paths = [
            './/publication-reference/document-id/kind',
            './/document-id/kind'
        ]

        kind_code = None
        for path in kind_paths:
            el = elem.find(path)
            if el is not None and el.text:
                kind_code = el.text.strip()
                break

        # Format as: US-NNNNNNN-XX (matching SureChEMBL format, NO year)
        if doc_number:
            # Remove any country prefix from doc_number
            doc_number = doc_number.replace('US', '').strip()
            formatted = f"US-{doc_number}"
            if kind_code:
                formatted += f"-{kind_code}"
            return formatted

        return None

    def _extract_title(self, elem: ET.Element) -> Optional[str]:
        """Extract patent title."""
        paths = [
            './/invention-title',
            './/us-bibliographic-data-application//invention-title',
            './/us-bibliographic-data-grant//invention-title'
        ]

        for path in paths:
            el = elem.find(path)
            if el is not None and el.text:
                return el.text.strip()

        return None

    def _extract_abstract(self, elem: ET.Element) -> Optional[str]:
        """Extract patent abstract."""
        abstract_elem = elem.find('.//abstract')

        if abstract_elem is not None:
            # Extract all text from abstract, including nested elements
            text_parts = []
            for p in abstract_elem.iter():
                if p.text:
                    text_parts.append(p.text.strip())
                if p.tail:
                    text_parts.append(p.tail.strip())

            text = ' '.join(text_parts)
            return text if text else None

        return None

    def _extract_claims(self, elem: ET.Element) -> Optional[str]:
        """
        Extract patent claims (first 3 claims, max 2000 chars).
        """
        claims_elem = elem.find('.//claims')

        if claims_elem is not None:
            claims = []

            for claim in claims_elem.findall('.//claim'):
                # Extract claim text
                claim_text_parts = []
                for p in claim.iter():
                    if p.text:
                        claim_text_parts.append(p.text.strip())
                    if p.tail:
                        claim_text_parts.append(p.tail.strip())

                claim_text = ' '.join(claim_text_parts)
                if claim_text:
                    claims.append(claim_text)

                # Limit to first 3 claims
                if len(claims) >= 3:
                    break

            # Join and truncate
            combined = ' '.join(claims)
            if len(combined) > 2000:
                combined = combined[:2000] + '...'

            return combined if combined else None

        return None

    def _extract_description(self, elem: ET.Element) -> Optional[str]:
        """
        Extract patent description (first 1000 chars).
        """
        desc_elem = elem.find('.//description')

        if desc_elem is not None:
            # Extract text
            text_parts = []
            for p in desc_elem.iter():
                if p.text:
                    text_parts.append(p.text.strip())
                if p.tail:
                    text_parts.append(p.tail.strip())

            text = ' '.join(text_parts)

            # Truncate to 1000 chars
            if len(text) > 1000:
                text = text[:1000] + '...'

            return text if text else None

        return None

    def _extract_publication_date(self, elem: ET.Element) -> Optional[str]:
        """Extract publication date."""
        paths = [
            './/publication-reference/document-id/date',
            './/document-id/date'
        ]

        for path in paths:
            el = elem.find(path)
            if el is not None and el.text:
                return el.text.strip()

        return None


def load_filter_ids(filter_file: Path) -> Set[str]:
    """
    Load US patent IDs from SureChEMBL filter file.

    File format: one patent ID per line
    Example:
        US-2024-123456-A1
        US-2024-234567-B2
    """
    log(f"Loading filter IDs from {filter_file}")

    if not filter_file.exists():
        log(f"ERROR: Filter file not found: {filter_file}")
        sys.exit(1)

    filter_ids = set()
    with open(filter_file) as f:
        for line in f:
            patent_id = line.strip()
            if patent_id:
                filter_ids.add(patent_id)

    log(f"Loaded {len(filter_ids)} patent IDs from SureChEMBL")

    return filter_ids


def parse_all_files(input_dir: Path, filter_ids: Set[str], debug: bool = False) -> pd.DataFrame:
    """
    Parse all USPTO ZIP files in directory.

    Args:
        input_dir: Directory containing ZIP files
        filter_ids: Set of patent IDs to keep
        debug: Enable debug logging

    Returns:
        DataFrame with all matched patents
    """
    log(f"Parsing USPTO files from {input_dir}")

    # Find all ZIP files
    zip_files = sorted(input_dir.glob('*.zip'))

    if not zip_files:
        log(f"ERROR: No ZIP files found in {input_dir}")
        sys.exit(1)

    log(f"Found {len(zip_files)} ZIP files")

    # Parse all files
    parser = USPTOParser(filter_ids=filter_ids, debug=debug)

    all_patents = []

    for zip_file in tqdm(zip_files, desc="Parsing USPTO files"):
        patents = parser.parse_zip_file(zip_file)
        all_patents.extend(patents)

    # Print statistics
    log(f"\n{'='*60}")
    log(f"Parsing Statistics")
    log(f"{'='*60}")
    log(f"Total patents parsed: {parser.stats['total_parsed']}")
    log(f"Matched with SureChEMBL: {parser.stats['matched']} ({parser.stats['matched']/max(parser.stats['total_parsed'], 1)*100:.1f}%)")
    log(f"Skipped (not biomedical): {parser.stats['skipped']}")

    # Convert to DataFrame
    if all_patents:
        df = pd.DataFrame(all_patents)
        log(f"Created DataFrame with {len(df)} patents")
        return df
    else:
        log("WARNING: No matching patents found!")
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description='Parse USPTO XML files with SureChEMBL filtering')
    parser.add_argument('--input-dir', type=str, required=True,
                       help='Directory containing USPTO ZIP files')
    parser.add_argument('--filter-ids', type=str, required=True,
                       help='File with US patent IDs from SureChEMBL')
    parser.add_argument('--output', type=str, required=True,
                       help='Output parquet file')
    parser.add_argument('--debug', action='store_true',
                       help='Debug mode (verbose logging)')

    args = parser.parse_args()

    # Load filter IDs
    filter_ids = load_filter_ids(Path(args.filter_ids))

    # Parse files
    df = parse_all_files(
        input_dir=Path(args.input_dir),
        filter_ids=filter_ids,
        debug=args.debug
    )

    # Save to parquet
    if not df.empty:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df.to_parquet(output_path, index=False)
        log(f"Saved {len(df)} patents to {output_path}")
        log(f"File size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        log("ERROR: No patents to save")
        sys.exit(1)

    log("\nParsing complete!")


if __name__ == '__main__':
    main()

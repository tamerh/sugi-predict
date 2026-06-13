#!/usr/bin/env python3
"""
Patent Text Processing for BioYoda Pipeline

Processes patent Parquet data from SureChEMBL to create FAISS embeddings
for semantic search, following the same pattern as the clinical trials pipeline.

This script processes patent text (title, abstract, description, claims) into
chunked embeddings using S-BioBERT model (768 dimensions, same as PubMed/ClinicalTrials).
"""

import os
import sys
import json
import faiss
import numpy as np
import argparse
import psutil
import pandas as pd
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from sentence_transformers import SentenceTransformer


def log_with_timestamp(message: str) -> None:
    """Prints a message with a prepended timestamp and memory usage."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    print(f"[{timestamp}] [MEM: {memory_mb:.1f}MB] {message}", flush=True)


def get_memory_usage() -> tuple:
    """Returns current memory usage in MB (used, available, percentage)."""
    memory = psutil.virtual_memory()
    return (
        memory.used / 1024 / 1024,
        memory.available / 1024 / 1024,
        memory.percent
    )


class PatentTextProcessor:
    """Processes patent text into chunks for embedding generation."""

    def __init__(self, max_chunk_length: int = 500, min_text_length: int = 50):
        """Initialize the text processor."""
        self.max_chunk_length = max_chunk_length
        self.min_text_length = min_text_length

    def clean_text(self, text: str) -> str:
        """Clean and normalize patent text content."""
        if not text:
            return ""

        # Handle NaN/None
        if pd.isna(text):
            return ""

        # Convert to string if needed
        text = str(text)

        # Remove excessive whitespace and normalize
        text = re.sub(r'\s+', ' ', text.strip())

        # Remove common artifacts
        text = re.sub(r'\r\n|\r|\n', ' ', text)
        text = re.sub(r'\t+', ' ', text)

        # Remove HTML/XML tags if present
        text = re.sub(r'<[^>]+>', '', text)

        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

        return text.strip()

    def chunk_long_text(self, text: str, max_length: int) -> List[str]:
        """Split long text into chunks while preserving sentence boundaries."""
        if not text or len(text) <= max_length:
            return [text] if text else []

        chunks = []
        sentences = re.split(r'[.!?]+', text)
        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # If adding this sentence would exceed max_length
            if len(current_chunk) + len(sentence) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += ". " + sentence
                else:
                    current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def process_patent_to_chunks(self, patent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process a single patent into text chunks for embedding.

        Supports both:
        - SureChEMBL data (title only)
        - USPTO-enriched data (title + abstract + claims + description)

        Args:
            patent: Patent dictionary with fields from SureChEMBL (and optionally USPTO)

        Returns:
            List of chunk dictionaries with text and metadata
        """
        chunks = []

        # Get patent identifier (could be 'patent_number' or 'patent_id')
        patent_id = patent.get('patent_number', patent.get('patent_id', ''))

        if not patent_id:
            return chunks

        # Extract and clean fields
        # SureChEMBL always has title
        title = self.clean_text(patent.get('title', ''))

        # USPTO enrichment fields (may be None for non-US or non-enriched patents)
        abstract = self.clean_text(patent.get('abstract', ''))
        claims = self.clean_text(patent.get('claims', ''))
        description = self.clean_text(patent.get('description', ''))

        # Check if this patent has full text
        has_full_text = patent.get('has_full_text', False)

        # Core metadata
        family_id = patent.get('family_id', '')
        pub_date = patent.get('publication_date', patent.get('pub_date', ''))

        # Get classification codes (could be 'ipc', 'cpc', etc.)
        ipc_codes = patent.get('ipc', patent.get('ipc_codes', []))
        cpc_codes = patent.get('cpc', [])

        # Get assignees (note: field name has typo 'asignee' in SureChEMBL data)
        assignees = patent.get('asignee', patent.get('assignees', []))

        # Ensure lists - handle numpy arrays, pandas Series, NaN, and None values
        def safe_to_list(value):
            """Safely convert various types to list, handling NaN, None, arrays, etc."""
            # Handle None
            if value is None:
                return []

            # Handle scalar NaN (float('nan'), np.nan, pd.NA)
            try:
                if pd.isna(value):
                    return []
            except (TypeError, ValueError):
                # pd.isna() failed (e.g., for arrays), continue processing
                pass

            # Already a list
            if isinstance(value, list):
                return [x for x in value if x is not None and (not isinstance(x, float) or not pd.isna(x))]

            # Handle iterables (arrays, Series) but not strings
            if hasattr(value, '__iter__') and not isinstance(value, str):
                return [x for x in value if x is not None and (not isinstance(x, float) or not pd.isna(x))]

            # Single value
            return [value]

        ipc_codes = safe_to_list(ipc_codes)
        cpc_codes = safe_to_list(cpc_codes)
        assignees = safe_to_list(assignees)

        # Combine classification codes
        all_codes = list(set(ipc_codes + cpc_codes))

        # Create searchable text based on available fields
        # For USPTO-enriched patents: title + abstract + claims + description
        # For title-only patents: just title (repeated for weight)
        text_parts = []

        if title:
            # Title is most important - repeat it twice for higher weight
            text_parts.append(title)
            text_parts.append(title)

        if has_full_text:
            # Add USPTO full text fields
            if abstract:
                text_parts.append(abstract)

            if claims:
                text_parts.append(claims)

            if description:
                text_parts.append(description)

        # Combine all text
        searchable_text = ' '.join(text_parts)

        # Create a single chunk per patent with combined text
        if searchable_text and len(searchable_text) >= self.min_text_length:
            chunks.append({
                'patent_id': patent_id,
                'chunk_type': 'full' if has_full_text else 'title_only',
                'chunk_id': 0,
                'text': searchable_text,
                'title': title,
                'has_full_text': has_full_text,
                'text_source': patent.get('text_source', 'surechembl_only'),
                'family_id': family_id,
                'pub_date': str(pub_date) if pub_date else '',
                'ipc_codes': ipc_codes,
                'cpc_codes': cpc_codes,
                'classification_codes': all_codes,
                'assignees': assignees
            })

        return chunks


class PatentsProcessor:
    """Main processor for patent data to create FAISS embeddings."""

    def __init__(self, model_name: str, vector_dimension: int, encode_batch_size: int = 128, num_workers: int = 1):
        """Initialize the processor with embedding model."""
        self.model_name = model_name
        self.vector_dimension = vector_dimension
        self.encode_batch_size = encode_batch_size
        self.num_workers = num_workers
        self.model = None
        self.text_processor = PatentTextProcessor()

    def load_model(self) -> bool:
        """Load the sentence transformer model."""
        try:
            import torch
            log_with_timestamp(f"Loading model: {self.model_name}")

            # Check for GPU availability
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            log_with_timestamp(f"Using device: {device}")

            self.model = SentenceTransformer(self.model_name, device=device)

            # For CPU, warn about large batch sizes
            if device == 'cpu':
                log_with_timestamp(f"CPU workers: {self.num_workers}")
                if self.encode_batch_size > 64:
                    log_with_timestamp(f"WARNING: Large batch size ({self.encode_batch_size}) on CPU may be slow")

            # Verify model dimension
            test_embedding = self.model.encode("test")
            actual_dim = len(test_embedding)

            if actual_dim != self.vector_dimension:
                log_with_timestamp(f"ERROR: Model dimension mismatch. Expected {self.vector_dimension}, got {actual_dim}")
                return False

            log_with_timestamp(f"Model loaded successfully. Dimension: {actual_dim}")
            return True

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to load model: {e}")
            return False

    def load_patents_from_parquet(self, parquet_file: str, limit: Optional[int] = None,
                                  batch_size: int = 100000, patent_ids_file: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Load patents from SureChEMBL Parquet file using batch/chunked reading.

        Args:
            parquet_file: Path to patents.parquet file
            limit: Optional limit on number of patents to load
            batch_size: Number of patents to load per batch (default: 100K)
            patent_ids_file: Optional file with patent IDs to filter (one per line)

        Returns:
            List of patent dictionaries
        """
        log_with_timestamp(f"Loading patents from {parquet_file}")

        try:
            import pyarrow.parquet as pq

            # Load patent IDs filter if provided
            filter_ids = None
            if patent_ids_file and os.path.exists(patent_ids_file):
                log_with_timestamp(f"Loading patent IDs filter from {patent_ids_file}")
                with open(patent_ids_file, 'r') as f:
                    filter_ids = set(line.strip() for line in f if line.strip() and not line.startswith('#'))
                log_with_timestamp(f"Will filter for {len(filter_ids):,} specific patent IDs")

            # Open parquet file
            parquet_file_obj = pq.ParquetFile(parquet_file)
            total_rows = parquet_file_obj.metadata.num_rows

            log_with_timestamp(f"Total patents in file: {total_rows:,}")

            # When filtering by IDs, we need to scan all rows
            if filter_ids:
                log_with_timestamp(f"Scanning for patents matching {len(filter_ids):,} IDs...")
            else:
                # Determine how many rows to read
                rows_to_read = limit if limit and limit < total_rows else total_rows
                log_with_timestamp(f"Will process: {rows_to_read:,} patents")

            patents = []
            rows_read = 0

            # Read in batches
            for batch in parquet_file_obj.iter_batches(batch_size=batch_size):
                df_batch = batch.to_pandas()
                rows_read += len(df_batch)

                # Apply patent ID filter if provided
                if filter_ids:
                    df_batch = df_batch[df_batch['patent_number'].isin(filter_ids)]

                # Check if we've found enough patents
                if limit and not filter_ids and len(patents) + len(df_batch) > limit:
                    # Take only what we need (only when not using ID filter)
                    remaining = limit - len(patents)
                    df_batch = df_batch.head(remaining)

                # Convert batch to records
                if len(df_batch) > 0:
                    patents.extend(df_batch.to_dict('records'))

                if filter_ids:
                    log_with_timestamp(f"  Scanned {rows_read:,} / {total_rows:,} patents, found {len(patents):,} matches")
                else:
                    log_with_timestamp(f"  Loaded batch: {len(patents):,} / {rows_to_read:,} patents")

                # Stop if we've reached the limit (non-filter mode)
                if limit and not filter_ids and len(patents) >= limit:
                    break

                # Stop if we've found all IDs (filter mode)
                if filter_ids and len(patents) >= len(filter_ids):
                    log_with_timestamp(f"Found all {len(filter_ids):,} requested patents")
                    break

            log_with_timestamp(f"Successfully loaded {len(patents):,} patent records")
            return patents

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to load Parquet file: {e}")
            raise

    def process_patents_batch(self, patents: List[Dict[str, Any]]) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """Process a batch of patents to create embeddings."""
        log_with_timestamp(f"Processing batch with {len(patents)} patents...")

        all_chunks = []
        all_texts = []

        # Process each patent into chunks
        for patent_idx, patent in enumerate(patents):
            chunks = self.text_processor.process_patent_to_chunks(patent)

            for chunk in chunks:
                chunk['global_chunk_id'] = len(all_chunks)
                all_chunks.append(chunk)
                all_texts.append(chunk['text'])

            # Log progress every 1000 patents
            if (patent_idx + 1) % 1000 == 0:
                log_with_timestamp(f"  Processed {patent_idx + 1}/{len(patents)} patents, {len(all_chunks)} chunks so far")

        log_with_timestamp(f"Generated {len(all_chunks)} text chunks from {len(patents)} patents")

        if not all_texts:
            log_with_timestamp("No text chunks generated from patents")
            return np.array([]).reshape(0, self.vector_dimension), []

        # Generate embeddings
        log_with_timestamp(f"Generating embeddings (batch_size={self.encode_batch_size})...")

        try:
            import torch
            # Set number of threads for PyTorch
            if self.num_workers > 1:
                torch.set_num_threads(self.num_workers)

            embeddings = self.model.encode(
                all_texts,
                batch_size=self.encode_batch_size,
                show_progress_bar=True,
                convert_to_numpy=True
            )

            log_with_timestamp(f"Generated {len(embeddings)} embeddings with dimension {embeddings.shape[1]}")
            return embeddings, all_chunks

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to generate embeddings: {e}")
            raise

    def create_faiss_index(self, embeddings: np.ndarray) -> faiss.Index:
        """Create FAISS index from embeddings."""
        log_with_timestamp(f"Creating FAISS index for {len(embeddings)} vectors...")

        if len(embeddings) == 0:
            log_with_timestamp("ERROR: No embeddings to index")
            return None

        try:
            index = faiss.IndexFlatL2(self.vector_dimension)
            index.add(embeddings.astype(np.float32))
            log_with_timestamp(f"FAISS index created: {index.ntotal} vectors")
            return index

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to create FAISS index: {e}")
            raise

    def save_index_and_metadata(self, index: faiss.Index, metadata: List[Dict[str, Any]],
                               index_path: str, metadata_path: str) -> bool:
        """Save FAISS index and metadata to files."""
        try:
            # Save FAISS index
            log_with_timestamp(f"Saving FAISS index to {index_path}")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            faiss.write_index(index, index_path)

            # Save metadata
            log_with_timestamp(f"Saving metadata to {metadata_path}")
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            metadata_dict = {str(i): chunk for i, chunk in enumerate(metadata)}

            with open(metadata_path, 'w') as f:
                json.dump(metadata_dict, f, indent=2, default=str, ensure_ascii=False)

            # Report file sizes
            index_size_mb = os.path.getsize(index_path) / 1024 / 1024
            metadata_size_mb = os.path.getsize(metadata_path) / 1024 / 1024

            log_with_timestamp(f"Files saved successfully:")
            log_with_timestamp(f"  Index: {index_size_mb:.1f}MB")
            log_with_timestamp(f"  Metadata: {metadata_size_mb:.1f}MB")

            return True

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to save files: {e}")
            return False


def enrich_patents_with_uspto(patents: List[Dict[str, Any]], uspto_parquet_file: str) -> List[Dict[str, Any]]:
    """
    Enrich US patents with full text from USPTO data.

    This is the SIMPLE approach: Load all USPTO data into memory once (10 GB),
    then enrich patents with O(1) dictionary lookup.

    Args:
        patents: List of patent dicts from SureChEMBL
        uspto_parquet_file: Path to USPTO parsed parquet file

    Returns:
        List of enriched patent dicts
    """
    log_with_timestamp(f"Loading USPTO data into memory...")
    start_time = datetime.now()

    # Load USPTO data into memory
    uspto_df = pd.read_parquet(uspto_parquet_file)

    log_with_timestamp(f"Loaded {len(uspto_df)} USPTO patents")
    mem_used, mem_avail, mem_pct = get_memory_usage()
    log_with_timestamp(f"Memory after USPTO load: {mem_used:.1f}MB used, {mem_avail:.1f}MB available ({mem_pct:.1f}%)")

    # Create fast dictionary lookup: patent_number -> USPTO data
    # USPTO-Chem historical data has: patent_number, title, abstract, publication_date
    uspto_lookup = {}
    for _, row in uspto_df.iterrows():
        uspto_lookup[row['patent_number']] = {
            'title': row.get('title', ''),
            'abstract': row.get('abstract', ''),
            'publication_date': row.get('publication_date', '')
        }

    load_time = (datetime.now() - start_time).total_seconds()
    log_with_timestamp(f"Created USPTO lookup dictionary in {load_time:.1f}s")

    # Enrich patents
    enriched_count = 0
    us_count = 0

    for patent in patents:
        if patent.get('country') == 'US':
            us_count += 1
            patent_num = patent.get('patent_number')

            if patent_num and patent_num in uspto_lookup:
                # Enrich with USPTO historical data (title + abstract)
                uspto_data = uspto_lookup[patent_num]

                # Override title with USPTO title if available (more complete)
                if uspto_data['title']:
                    patent['title'] = uspto_data['title']

                # Add abstract from USPTO
                patent['abstract'] = uspto_data['abstract']

                # Update publication_date if USPTO has more precise date
                if uspto_data['publication_date']:
                    patent['publication_date'] = uspto_data['publication_date']

                patent['has_full_text'] = True
                patent['text_source'] = 'surechembl+uspto'
                enriched_count += 1
            else:
                # US patent but no USPTO data
                patent['has_full_text'] = False
                patent['text_source'] = 'surechembl_only'
        else:
            # Non-US patent (EP, WO, etc)
            patent['has_full_text'] = False
            patent['text_source'] = 'surechembl_only'

    log_with_timestamp(f"Enrichment complete:")
    log_with_timestamp(f"  Total US patents: {us_count}")
    log_with_timestamp(f"  Enriched with full text: {enriched_count} ({enriched_count/max(us_count,1)*100:.1f}%)")
    log_with_timestamp(f"  Title-only: {us_count - enriched_count}")

    return patents


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Process patent data from SureChEMBL to create FAISS embeddings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process patents from Parquet file
  %(prog)s --input patents.parquet \\
      --output-index work/data/processed/patents/text/patents_batch_0001.index \\
      --output-metadata work/data/processed/patents/text/patents_batch_0001.json

  # Test mode with limit
  %(prog)s --input patents.parquet \\
      --output-index test.index \\
      --output-metadata test.json \\
      --limit 100
        """
    )
    parser.add_argument(
        "--input", required=True,
        help="Input Parquet file with patent data (from SureChEMBL)"
    )
    parser.add_argument(
        "--output-index", required=True,
        help="Output FAISS index file path"
    )
    parser.add_argument(
        "--output-metadata", required=True,
        help="Output metadata JSON file path"
    )
    parser.add_argument(
        "--model-name", default="pritamdeka/S-BioBERT-snli-multinli-stsb",
        help="Sentence transformer model name (default: S-BioBERT)"
    )
    parser.add_argument(
        "--vector-dimension", type=int, default=768,
        help="Expected vector dimension (default: 768 for S-BioBERT)"
    )
    parser.add_argument(
        "--encode-batch-size", type=int, default=128,
        help="Batch size for model encoding (default: 128)"
    )
    parser.add_argument(
        "--num-workers", type=int, default=1,
        help="Number of CPU workers for parallel encoding (default: 1)"
    )
    parser.add_argument(
        "--max-chunk-length", type=int, default=500,
        help="Maximum chunk length for text splitting (default: 500)"
    )
    parser.add_argument(
        "--min-text-length", type=int, default=50,
        help="Minimum text length for inclusion (default: 50)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of patents to process (for testing)"
    )
    parser.add_argument(
        "--uspto-data", type=str, default=None,
        help="Optional USPTO parquet file for full-text enrichment"
    )
    parser.add_argument(
        "--patent-ids-file", type=str, default=None,
        help="Optional file with patent IDs to filter (one per line, for testing enrichment)"
    )

    args = parser.parse_args()

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Initialize processor
        log_with_timestamp("=== Starting Patent Processing ===")
        processor = PatentsProcessor(
            args.model_name,
            args.vector_dimension,
            args.encode_batch_size,
            args.num_workers
        )
        processor.text_processor.max_chunk_length = args.max_chunk_length
        processor.text_processor.min_text_length = args.min_text_length

        # Load model
        if not processor.load_model():
            return 1

        # Load patents from Parquet
        patents = processor.load_patents_from_parquet(
            args.input,
            limit=args.limit,
            patent_ids_file=args.patent_ids_file
        )

        if not patents:
            log_with_timestamp("No patents to process")
            return 1

        # Enrich US patents with USPTO full text (if available)
        if args.uspto_data and os.path.exists(args.uspto_data):
            log_with_timestamp(f"Loading USPTO data for enrichment from {args.uspto_data}")
            patents = enrich_patents_with_uspto(patents, args.uspto_data)

        # Process patents
        embeddings, metadata = processor.process_patents_batch(patents)

        if len(embeddings) == 0:
            log_with_timestamp("ERROR: No embeddings generated from patents")
            return 1

        log_with_timestamp(f"Generated {len(embeddings)} embeddings from {len(patents)} patents")

        # Create FAISS index
        index = processor.create_faiss_index(embeddings)
        if index is None:
            return 1

        # Save index and metadata
        if not processor.save_index_and_metadata(index, metadata, args.output_index, args.output_metadata):
            return 1

        log_with_timestamp("=== Patent Processing Complete ===")
        return 0

    except KeyboardInterrupt:
        log_with_timestamp("Processing interrupted by user")
        return 1
    except Exception as e:
        log_with_timestamp(f"ERROR during processing: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

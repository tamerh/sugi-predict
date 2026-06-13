#!/usr/bin/env python3
"""
Patent Compounds Processing for BioYoda Pipeline

Processes compound data from SureChEMBL to create FAISS indices with chemical
fingerprints for structure similarity search.

This script:
1. Loads compounds.parquet (SMILES, InChI, molecular properties)
2. Generates Morgan fingerprints (ECFP) using RDKit
3. Creates FAISS indices for chemical similarity search
4. Links compounds to patents via patent_compound_map.parquet
"""

import os
import sys
import json
import faiss
import numpy as np
import argparse
import psutil
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional


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


class CompoundProcessor:
    """Processes chemical compounds to generate fingerprints for similarity search."""

    def __init__(self, fingerprint_bits: int = 2048, radius: int = 2, existing_ids: set = None):
        """
        Initialize the compound processor.

        Args:
            fingerprint_bits: Number of bits for Morgan fingerprint (default: 2048)
            radius: Radius for Morgan fingerprint (default: 2 = ECFP4)
        """
        self.fingerprint_bits = fingerprint_bits
        self.radius = radius
        self.existing_ids = existing_ids if existing_ids is not None else set()
        self.rdkit_available = False

        # Try to import RDKit
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem, rdMolDescriptors
            self.Chem = Chem
            self.AllChem = AllChem
            self.rdMolDescriptors = rdMolDescriptors

            # Try to use new MorganGenerator API (RDKit 2022+)
            try:
                from rdkit.Chem import rdFingerprintGenerator
                self.fp_generator = rdFingerprintGenerator.GetMorganGenerator(
                    radius=self.radius,
                    fpSize=self.fingerprint_bits
                )
                self.use_new_api = True
                log_with_timestamp("RDKit loaded successfully (using MorganGenerator)")
            except (ImportError, AttributeError):
                # Fall back to old API
                self.use_new_api = False
                log_with_timestamp("RDKit loaded successfully (using legacy API)")

            self.rdkit_available = True
        except ImportError:
            log_with_timestamp("ERROR: RDKit not available. Install with: mamba install -c conda-forge rdkit")

    def smiles_to_fingerprint(self, smiles: str) -> Optional[np.ndarray]:
        """
        Convert SMILES string to Morgan fingerprint.

        Args:
            smiles: SMILES string

        Returns:
            Fingerprint as numpy array or None if invalid
        """
        if not self.rdkit_available:
            return None

        try:
            mol = self.Chem.MolFromSmiles(smiles)
            if mol is None:
                return None

            # Generate Morgan fingerprint (ECFP) using new or old API
            if self.use_new_api:
                # New API (RDKit 2022+) - no deprecation warnings
                fp = self.fp_generator.GetFingerprint(mol)
            else:
                # Legacy API for older RDKit versions
                fp = self.AllChem.GetMorganFingerprintAsBitVect(
                    mol,
                    radius=self.radius,
                    nBits=self.fingerprint_bits
                )

            # Convert to numpy array
            arr = np.zeros((self.fingerprint_bits,), dtype=np.float32)
            self.AllChem.DataStructs.ConvertToNumpyArray(fp, arr)

            return arr

        except Exception as e:
            # Invalid SMILES, silently skip
            return None

    def process_compounds_batch(self, compounds: List[Dict[str, Any]]) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """
        Process a batch of compounds to generate fingerprints.

        Args:
            compounds: List of compound dictionaries

        Returns:
            Tuple of (fingerprints array, metadata list)
        """
        log_with_timestamp(f"Processing {len(compounds)} compounds...")

        # Pre-allocate array to avoid memory issues with np.vstack()
        # Allocate for all compounds, trim later to actual valid count
        fingerprints_array = np.zeros((len(compounds), self.fingerprint_bits), dtype=np.float32)
        metadata = []
        valid_count = 0
        invalid_count = 0
        skipped_existing = 0

        for idx, compound in enumerate(compounds):
            # Extract compound data
            # Try multiple column name variations (id, surechembl_id, compound_id)
            surechembl_id = compound.get('id', compound.get('surechembl_id', compound.get('compound_id', '')))
            # Convert to string and add SCHEMBL prefix if it's just a number
            if surechembl_id and not isinstance(surechembl_id, str):
                surechembl_id = f"SCHEMBL{surechembl_id}"

            # Compound ID-delta: skip compounds already fingerprinted (additive update).
            if surechembl_id and surechembl_id in self.existing_ids:
                skipped_existing += 1
                continue

            smiles = compound.get('smiles', '')
            inchi = compound.get('inchi', '')
            molecular_weight = compound.get('molecular_weight', compound.get('mol_weight', None))
            formula = compound.get('formula', compound.get('molecular_formula', ''))

            # Skip if no SMILES
            if not smiles or pd.isna(smiles):
                invalid_count += 1
                continue

            # Generate fingerprint
            fp = self.smiles_to_fingerprint(smiles)
            if fp is None:
                invalid_count += 1
                continue

            # Create metadata
            # NOTE: Patent-compound mappings should be handled by biobtree, not stored here
            # This metadata is only for Qdrant chemical similarity search
            meta = {
                'surechembl_id': surechembl_id,
                'smiles': smiles,
                'inchi': inchi if not pd.isna(inchi) else '',
                'molecular_weight': float(molecular_weight) if molecular_weight and not pd.isna(molecular_weight) else None,
                'formula': formula if not pd.isna(formula) else ''
            }

            # Store in pre-allocated array (no append/vstack needed!)
            fingerprints_array[valid_count] = fp
            metadata.append(meta)
            valid_count += 1

            # Log progress every 10000 compounds
            if (idx + 1) % 10000 == 0:
                log_with_timestamp(f"  Processed {idx + 1}/{len(compounds)} compounds "
                                 f"(valid: {valid_count}, invalid: {invalid_count})")

        log_with_timestamp(f"Completed: {valid_count} valid fingerprints, {invalid_count} invalid/skipped, {skipped_existing} already-fingerprinted (delta)")

        if valid_count > 0:
            # Trim array to actual valid count (remove unfilled rows)
            fingerprints_array = fingerprints_array[:valid_count]
            return fingerprints_array, metadata
        else:
            return np.array([]).reshape(0, self.fingerprint_bits), []


class CompoundsFAISSProcessor:
    """Main processor for compound data to create FAISS indices."""

    def __init__(self, fingerprint_bits: int = 2048, radius: int = 2, existing_ids: set = None):
        """Initialize the FAISS processor."""
        self.fingerprint_bits = fingerprint_bits
        self.radius = radius
        self.compound_processor = CompoundProcessor(fingerprint_bits, radius, existing_ids)

        if not self.compound_processor.rdkit_available:
            raise RuntimeError("RDKit is required for compound processing")

    def iter_compounds_from_parquet(self, parquet_file: str, limit: Optional[int] = None,
                                    batch_size: int = 100000):
        """
        Iterate over compounds from SureChEMBL Parquet file using true streaming.

        Args:
            parquet_file: Path to compounds.parquet file
            limit: Optional limit on number of compounds to process
            batch_size: Number of compounds to yield per batch (default: 100K)

        Yields:
            Batches of compound dictionaries
        """
        log_with_timestamp(f"Loading compounds from {parquet_file}")

        try:
            import pyarrow.parquet as pq

            # Open parquet file
            parquet_file_obj = pq.ParquetFile(parquet_file)
            total_rows = parquet_file_obj.metadata.num_rows

            log_with_timestamp(f"Total compounds in file: {total_rows:,}")

            # Determine how many rows to read
            rows_to_read = limit if limit and limit < total_rows else total_rows
            log_with_timestamp(f"Will process: {rows_to_read:,} compounds")

            rows_read = 0

            # Read in batches
            for batch in parquet_file_obj.iter_batches(batch_size=batch_size):
                df_batch = batch.to_pandas()

                # Check if we've read enough
                if limit and rows_read + len(df_batch) > limit:
                    # Take only what we need
                    remaining = limit - rows_read
                    df_batch = df_batch.head(remaining)

                # Convert batch to records
                compounds_batch = df_batch.to_dict('records')
                rows_read += len(df_batch)

                log_with_timestamp(f"  Loaded batch: {rows_read:,} / {rows_to_read:,} compounds")

                yield compounds_batch

                # Stop if we've reached the limit
                if limit and rows_read >= limit:
                    break

            log_with_timestamp(f"Successfully processed {rows_read:,} compound records")

        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to load Parquet file: {e}")
            raise

    def get_compound_patent_mapping_for_batch(self, map_file: str, compound_ids: set,
                                              max_rows: Optional[int] = None) -> Dict[str, List[str]]:
        """
        Load patent-compound mapping for a specific batch of compound IDs.

        Streams through the mapping file and only keeps mappings for the given compound IDs.

        Args:
            map_file: Path to patent_compound_map.parquet
            compound_ids: Set of compound IDs to filter for
            max_rows: Optional maximum number of rows to scan (for faster testing)

        Returns:
            Dictionary mapping compound_id -> list of patent_ids
        """
        if not os.path.exists(map_file):
            log_with_timestamp(f"WARNING: Compound map file not found: {map_file}")
            return {}

        try:
            import pyarrow.parquet as pq

            compound_to_patents = {}
            parquet_file_obj = pq.ParquetFile(map_file)
            total_rows = parquet_file_obj.metadata.num_rows
            rows_read = 0

            # Determine actual limit
            scan_limit = max_rows if max_rows else total_rows
            if max_rows:
                log_with_timestamp(f"Limiting mapping scan to first {max_rows:,} rows (out of {total_rows:,})")

            # Convert SCHEMBL IDs to numeric IDs for filtering (e.g., "SCHEMBL1" -> 1)
            numeric_compound_ids = set()
            for cid in compound_ids:
                if isinstance(cid, str) and cid.startswith('SCHEMBL'):
                    try:
                        numeric_compound_ids.add(int(cid.replace('SCHEMBL', '')))
                    except ValueError:
                        pass  # Skip invalid IDs
                elif isinstance(cid, (int, np.integer)):
                    numeric_compound_ids.add(int(cid))

            # Stream through mapping file
            for batch in parquet_file_obj.iter_batches(batch_size=1000000):  # 1M rows per batch
                df_batch = batch.to_pandas()

                # Check if we need to truncate this batch
                if max_rows and rows_read + len(df_batch) > max_rows:
                    remaining = max_rows - rows_read
                    df_batch = df_batch.head(remaining)

                rows_read += len(df_batch)

                # Filter for our compound IDs (check both possible column names)
                id_col = 'surechembl_id' if 'surechembl_id' in df_batch.columns else 'compound_id'
                if id_col in df_batch.columns:
                    # Filter using numeric IDs
                    df_filtered = df_batch[df_batch[id_col].isin(numeric_compound_ids)]

                    # Build mapping - convert back to SCHEMBL format
                    for cid, patent_id in zip(df_filtered[id_col], df_filtered['patent_id']):
                        if pd.notna(cid) and pd.notna(patent_id):
                            # Convert numeric compound ID to SCHEMBL format
                            cid_key = f"SCHEMBL{int(cid)}"
                            if cid_key not in compound_to_patents:
                                compound_to_patents[cid_key] = []
                            compound_to_patents[cid_key].append(int(patent_id))

                if rows_read % 5000000 == 0:
                    log_with_timestamp(f"  Processed {rows_read:,} / {scan_limit:,} mappings, found {len(compound_to_patents):,} compound mappings")

                # Stop if we've reached the limit
                if max_rows and rows_read >= max_rows:
                    log_with_timestamp(f"Reached scan limit of {max_rows:,} rows")
                    break

            log_with_timestamp(f"Scanned {rows_read:,} mapping rows, loaded mappings for {len(compound_to_patents):,} compounds")
            return compound_to_patents

        except Exception as e:
            log_with_timestamp(f"WARNING: Failed to load compound map: {e}")
            return {}

    def create_faiss_index(self, fingerprints: np.ndarray) -> faiss.Index:
        """Create FAISS index from fingerprints."""
        log_with_timestamp(f"Creating FAISS index for {len(fingerprints)} fingerprints...")

        if len(fingerprints) == 0:
            log_with_timestamp("ERROR: No fingerprints to index")
            return None

        try:
            # Ensure array is C-contiguous and float32 without creating a copy if possible
            if fingerprints.dtype != np.float32:
                log_with_timestamp("Converting fingerprints to float32...")
                fingerprints = fingerprints.astype(np.float32)

            if not fingerprints.flags['C_CONTIGUOUS']:
                log_with_timestamp("Making array C-contiguous...")
                fingerprints = np.ascontiguousarray(fingerprints)

            log_with_timestamp(f"Fingerprints ready: dtype={fingerprints.dtype}, shape={fingerprints.shape}, C-contiguous={fingerprints.flags['C_CONTIGUOUS']}")

            # Use simple flat index (no training needed)
            # For Morgan fingerprints, we use L2 distance on bit vectors
            log_with_timestamp(f"Creating FAISS IndexFlatL2...")
            index = faiss.IndexFlatL2(self.fingerprint_bits)

            log_with_timestamp(f"Adding {len(fingerprints)} vectors to index...")
            index.add(fingerprints)

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
            metadata_dict = {str(i): compound for i, compound in enumerate(metadata)}

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


def load_existing_ids(path):
    """Load already-fingerprinted surechembl_ids to skip (incremental ID-delta).
    One id per line (e.g. SCHEMBL123), optionally gzipped. Returns a set."""
    if not path:
        return set()
    import gzip, os
    log_with_timestamp(f"Loading existing surechembl_ids from {path}...")
    if not os.path.exists(path):
        log_with_timestamp(f"Warning: {path} not found; proceeding without ID-delta skip.")
        return set()
    opener = gzip.open if path.endswith('.gz') else open
    s = set()
    with opener(path, 'rt') as f:
        for ln in f:
            v = ln.strip()
            if v:
                s.add(v)
    log_with_timestamp(f"Loaded {len(s):,} existing surechembl_ids (will be skipped).")
    return s


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Process compound data from SureChEMBL to create FAISS fingerprint indices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process compounds with patent mapping (streaming mode)
  %(prog)s --input compounds.parquet \\
      --compound-map patent_compound_map.parquet \\
      --output-index work/data/processed/patents/compounds/compounds_batch_0001.index \\
      --output-metadata work/data/processed/patents/compounds/compounds_batch_0001.json \\
      --processing-batch-size 100000

  # Test mode with limit
  %(prog)s --input compounds.parquet \\
      --output-index test.index \\
      --output-metadata test.json \\
      --limit 1000
        """
    )
    parser.add_argument(
        "--input", required=True,
        help="Input Parquet file with compound data (from SureChEMBL)"
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
        "--fingerprint-bits", type=int, default=2048,
        help="Number of bits for Morgan fingerprint (default: 2048)"
    )
    parser.add_argument(
        "--radius", type=int, default=2,
        help="Radius for Morgan fingerprint (default: 2 = ECFP4)"
    )
    parser.add_argument(
        "--existing-ids", type=str, default=None,
        help="File of already-fingerprinted surechembl_ids (one per line, optionally .gz). "
             "When set, those compounds are skipped (incremental ID-delta)."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of compounds to process (for testing)"
    )
    parser.add_argument(
        "--processing-batch-size", type=int, default=100000,
        help="Number of compounds to process per batch (default: 100K)"
    )

    args = parser.parse_args()

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Initialize processor
        log_with_timestamp("=== Starting Compound Processing (Streaming Mode) ===")
        existing_ids = load_existing_ids(args.existing_ids)
        processor = CompoundsFAISSProcessor(
            args.fingerprint_bits,
            args.radius,
            existing_ids
        )

        # NOTE: Patent-compound mappings are handled by biobtree, not stored in FAISS metadata
        # This script only creates fingerprint indices for chemical similarity search

        # Process compounds in batches (pre-allocated array approach)
        log_with_timestamp("=== Step 3: Processing compounds in batches ===")

        # First pass: Count total compounds to determine array size
        log_with_timestamp("Counting total compounds to process...")
        if args.limit:
            total_compounds = args.limit
        else:
            import pyarrow.parquet as pq
            parquet_file_obj = pq.ParquetFile(args.input)
            total_compounds = parquet_file_obj.metadata.num_rows

        log_with_timestamp(f"Total compounds to process: {total_compounds:,}")

        # Pre-allocate the final array ONCE (avoids fragmentation)
        # We'll allocate for all compounds, then trim to actual valid count at the end
        estimated_memory_gb = (total_compounds * args.fingerprint_bits * 4) / 1024**3
        log_with_timestamp(f"Estimated memory needed: {estimated_memory_gb:.2f} GB")
        log_with_timestamp(f"Pre-allocating final array ({total_compounds} x {args.fingerprint_bits})...")

        try:
            final_fingerprints = np.zeros((total_compounds, args.fingerprint_bits), dtype=np.float32)
            log_with_timestamp(f"Successfully allocated {estimated_memory_gb:.2f} GB array")
        except Exception as e:
            log_with_timestamp(f"ERROR: Failed to allocate final array: {e}")
            log_with_timestamp(f"You need at least {estimated_memory_gb:.2f} GB of available RAM")
            return 1

        all_metadata = []
        offset = 0  # Current position in final array
        batch_num = 0

        # Second pass: Process compounds and fill the pre-allocated array
        for compounds_batch in processor.iter_compounds_from_parquet(
            args.input,
            limit=args.limit,
            batch_size=args.processing_batch_size
        ):
            batch_num += 1
            log_with_timestamp(f"Processing batch {batch_num} with {len(compounds_batch):,} compounds")

            # Process this batch (generates smaller temporary array)
            fingerprints, metadata = processor.compound_processor.process_compounds_batch(compounds_batch)

            if len(fingerprints) > 0:
                # Copy directly into pre-allocated array (no append/vstack needed!)
                batch_size = len(fingerprints)
                final_fingerprints[offset:offset + batch_size] = fingerprints
                all_metadata.extend(metadata)
                offset += batch_size

                log_with_timestamp(f"Copied {batch_size:,} fingerprints to final array at offset {offset - batch_size:,}")

            log_with_timestamp(f"Batch {batch_num} complete. Total processed so far: {offset:,}")

            # Force garbage collection after each batch to free temporary arrays
            import gc
            del fingerprints
            del metadata
            gc.collect()

        if offset == 0:
            log_with_timestamp("ERROR: No fingerprints generated from compounds")
            return 1

        # Trim array to actual valid count (remove unfilled rows)
        if offset < total_compounds:
            log_with_timestamp(f"Trimming array from {total_compounds:,} to {offset:,} valid compounds")
            final_fingerprints = final_fingerprints[:offset]

        log_with_timestamp(f"Final fingerprints shape: {final_fingerprints.shape}")

        # Create FAISS index
        index = processor.create_faiss_index(final_fingerprints)
        if index is None:
            return 1

        # Save index and metadata
        if not processor.save_index_and_metadata(index, all_metadata, args.output_index, args.output_metadata):
            return 1

        log_with_timestamp("=== Compound Processing Complete ===")
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

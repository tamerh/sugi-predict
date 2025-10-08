#!/usr/bin/env python3
"""
Clinical Trials Chunk Processing for BioYoda Pipeline

Processes a single chunk of clinical trial JSON data to create FAISS embeddings.
This is optimized for parallel execution where each chunk runs independently.
"""

import os
import sys
import json
import faiss
import numpy as np
import argparse
import psutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from sentence_transformers import SentenceTransformer

# Reuse text processor from process_trials
# Import from the same directory
sys.path.insert(0, os.path.dirname(__file__))
from process_trials import TrialTextProcessor, log_with_timestamp, get_memory_usage


class ClinicalTrialsChunkProcessor:
    """Processor for a single chunk of clinical trials data."""

    def __init__(self, model_name: str, vector_dimension: int, encode_batch_size: int = 128, num_workers: int = 1):
        """Initialize the chunk processor with embedding model."""
        self.model_name = model_name
        self.vector_dimension = vector_dimension
        self.encode_batch_size = encode_batch_size
        self.num_workers = num_workers
        self.model = None
        self.text_processor = TrialTextProcessor()

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

    def process_chunk(self, trials: List[Dict[str, Any]]) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """Process a chunk of trials to create embeddings."""
        log_with_timestamp(f"Processing chunk with {len(trials)} trials...")

        all_chunks = []
        all_texts = []

        # Process each trial into chunks
        for trial_idx, trial in enumerate(trials):
            chunks = self.text_processor.process_trial_to_chunks(trial)

            for chunk in chunks:
                chunk['global_chunk_id'] = len(all_chunks)
                all_chunks.append(chunk)
                all_texts.append(chunk['text'])

            # Log progress every 1000 trials
            if (trial_idx + 1) % 1000 == 0:
                log_with_timestamp(f"  Processed {trial_idx + 1}/{len(trials)} trials, {len(all_chunks)} chunks so far")

        log_with_timestamp(f"Generated {len(all_chunks)} text chunks from {len(trials)} trials")

        if not all_texts:
            log_with_timestamp("No text chunks generated from trials")
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


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Process a single chunk of clinical trials data to create FAISS embeddings"
    )
    parser.add_argument(
        "--input-json", required=True,
        help="Input JSON file with chunk of trial data"
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
        help="Sentence transformer model name"
    )
    parser.add_argument(
        "--vector-dimension", type=int, default=768,
        help="Expected vector dimension"
    )
    parser.add_argument(
        "--encode-batch-size", type=int, default=128,
        help="Batch size for model encoding"
    )
    parser.add_argument(
        "--num-workers", type=int, default=1,
        help="Number of CPU workers for parallel encoding"
    )
    parser.add_argument(
        "--max-chunk-length", type=int, default=500,
        help="Maximum chunk length for text splitting"
    )
    parser.add_argument(
        "--min-text-length", type=int, default=50,
        help="Minimum text length for inclusion"
    )

    args = parser.parse_args()

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Load input chunk
        log_with_timestamp(f"Loading trial chunk from {args.input_json}")
        with open(args.input_json, 'r') as f:
            trials = json.load(f)

        log_with_timestamp(f"Loaded {len(trials)} trials from chunk file")

        if not trials:
            log_with_timestamp("No trials to process in this chunk")
            return 1

        # Initialize processor
        log_with_timestamp("=== Starting Clinical Trials Chunk Processing ===")
        processor = ClinicalTrialsChunkProcessor(
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

        # Process chunk
        embeddings, metadata = processor.process_chunk(trials)

        if len(embeddings) == 0:
            log_with_timestamp("ERROR: No embeddings generated from chunk")
            return 1

        log_with_timestamp(f"Generated {len(embeddings)} embeddings from {len(trials)} trials")

        # Create FAISS index
        index = processor.create_faiss_index(embeddings)
        if index is None:
            return 1

        # Save index and metadata
        if not processor.save_index_and_metadata(index, metadata, args.output_index, args.output_metadata):
            return 1

        log_with_timestamp("=== Clinical Trials Chunk Processing Complete ===")
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

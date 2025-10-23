#!/usr/bin/env python3
"""
Clinical Trials Processing for BioYoda Pipeline

Processes extracted clinical trial text data to create FAISS embeddings,
following the same pattern as the PubMed pipeline.
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

import re

def log_with_timestamp(message: str) -> None:
    """Prints a message with a prepended timestamp and memory usage."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    print(f"[{timestamp}] [MEM: {memory_mb:.1f}MB] {message}")

def get_memory_usage() -> tuple:
    """Returns current memory usage in MB (used, available, percentage)."""
    memory = psutil.virtual_memory()
    return (
        memory.used / 1024 / 1024,
        memory.available / 1024 / 1024,
        memory.percent
    )

class TrialTextProcessor:
    """Processes clinical trial text into chunks for embedding generation."""

    def __init__(self, max_chunk_length: int = 500, min_text_length: int = 50):
        """Initialize the text processor."""
        self.max_chunk_length = max_chunk_length
        self.min_text_length = min_text_length

    def clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        if not text:
            return ""

        # Remove excessive whitespace and normalize
        text = re.sub(r'\s+', ' ', text.strip())

        # Remove common artifacts
        text = re.sub(r'\r\n|\r|\n', ' ', text)
        text = re.sub(r'\t+', ' ', text)

        # Remove HTML tags if present
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

    def process_trial_to_chunks(self, trial: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process a single trial into multiple text chunks for embedding."""
        chunks = []
        nct_id = trial.get('nct_id', '')

        if not nct_id:
            return chunks

        # Core summary chunk (always include)
        brief_title = self.clean_text(trial.get('brief_title', ''))
        brief_summary = self.clean_text(trial.get('brief_summary', ''))

        if brief_summary and len(brief_summary) >= self.min_text_length:
            core_text = f"Title: {brief_title}. Summary: {brief_summary}"
            chunks.append({
                'nct_id': nct_id,
                'chunk_type': 'summary',
                'chunk_id': 0,
                'text': core_text,
                'brief_title': brief_title,
                'overall_status': trial.get('overall_status', ''),
                'phase': trial.get('phase', ''),
                'study_type': trial.get('study_type', ''),
                'conditions': trial.get('conditions', []),
                'interventions': trial.get('interventions', []),
                'sponsors': trial.get('sponsors', []),
                'facilities': trial.get('facilities', []),
                'study_arms': trial.get('study_arms', [])
            })

        # Detailed description chunks
        detailed_description = self.clean_text(trial.get('detailed_description', ''))
        if detailed_description and len(detailed_description) >= self.min_text_length:
            desc_chunks = self.chunk_long_text(detailed_description, self.max_chunk_length)
            for i, chunk_text in enumerate(desc_chunks):
                if len(chunk_text) >= self.min_text_length:
                    chunks.append({
                        'nct_id': nct_id,
                        'chunk_type': 'description',
                        'chunk_id': i,
                        'text': f"Description: {chunk_text}",
                        'brief_title': brief_title,
                        'overall_status': trial.get('overall_status', ''),
                        'phase': trial.get('phase', ''),
                        'study_type': trial.get('study_type', ''),
                        'conditions': trial.get('conditions', []),
                        'interventions': trial.get('interventions', []),
                        'sponsors': trial.get('sponsors', []),
                        'facilities': trial.get('facilities', []),
                        'study_arms': trial.get('study_arms', [])
                    })

        # Primary outcomes
        primary_outcomes = trial.get('primary_outcomes', [])
        if primary_outcomes:
            outcomes_text = ' | '.join(primary_outcomes)
            outcomes_text = self.clean_text(outcomes_text)
            if len(outcomes_text) >= self.min_text_length:
                chunks.append({
                    'nct_id': nct_id,
                    'chunk_type': 'primary_outcome',
                    'chunk_id': 0,
                    'text': f"Primary Outcomes: {outcomes_text}",
                    'brief_title': brief_title,
                    'overall_status': trial.get('overall_status', ''),
                    'phase': trial.get('phase', ''),
                    'study_type': trial.get('study_type', ''),
                    'conditions': trial.get('conditions', []),
                    'interventions': trial.get('interventions', []),
                    'sponsors': trial.get('sponsors', []),
                    'facilities': trial.get('facilities', []),
                    'study_arms': trial.get('study_arms', [])
                })

        # Secondary outcomes
        secondary_outcomes = trial.get('secondary_outcomes', [])
        if secondary_outcomes:
            outcomes_text = ' | '.join(secondary_outcomes)
            outcomes_text = self.clean_text(outcomes_text)
            if len(outcomes_text) >= self.min_text_length:
                chunks.append({
                    'nct_id': nct_id,
                    'chunk_type': 'secondary_outcome',
                    'chunk_id': 0,
                    'text': f"Secondary Outcomes: {outcomes_text}",
                    'brief_title': brief_title,
                    'overall_status': trial.get('overall_status', ''),
                    'phase': trial.get('phase', ''),
                    'study_type': trial.get('study_type', ''),
                    'conditions': trial.get('conditions', []),
                    'interventions': trial.get('interventions', []),
                    'sponsors': trial.get('sponsors', []),
                    'facilities': trial.get('facilities', []),
                    'study_arms': trial.get('study_arms', [])
                })

        # Eligibility criteria
        eligibility = trial.get('eligibility', {})
        if eligibility and eligibility.get('criteria'):
            criteria_text = self.clean_text(eligibility['criteria'])
            if len(criteria_text) >= self.min_text_length:
                # Add intervention context for better semantic matching
                intervention_context = ""
                interventions = trial.get('interventions', [])
                if interventions:
                    # Extract intervention names for context
                    intervention_names = [inv.get('name', '') for inv in interventions if inv.get('name')]
                    if intervention_names:
                        intervention_context = f"Study intervention: {', '.join(intervention_names)}. "

                # Add demographic info if available
                demo_parts = []
                if eligibility.get('gender'):
                    demo_parts.append(f"Gender: {eligibility['gender']}")
                if eligibility.get('minimum_age'):
                    demo_parts.append(f"Min age: {eligibility['minimum_age']}")
                if eligibility.get('maximum_age'):
                    demo_parts.append(f"Max age: {eligibility['maximum_age']}")

                full_criteria = criteria_text
                if demo_parts:
                    full_criteria = f"{criteria_text} Demographics: {', '.join(demo_parts)}"

                # Split eligibility if too long (accounting for intervention context)
                eligibility_chunks = self.chunk_long_text(full_criteria, self.max_chunk_length)
                for i, chunk_text in enumerate(eligibility_chunks):
                    if len(chunk_text) >= self.min_text_length:
                        # Prepend intervention context to eligibility text for embedding
                        full_text = f"{intervention_context}Eligibility: {chunk_text}"
                        chunks.append({
                            'nct_id': nct_id,
                            'chunk_type': 'eligibility',
                            'chunk_id': i,
                            'text': full_text,
                            'brief_title': brief_title,
                            'overall_status': trial.get('overall_status', ''),
                            'phase': trial.get('phase', ''),
                            'study_type': trial.get('study_type', ''),
                            'conditions': trial.get('conditions', []),
                            'interventions': trial.get('interventions', []),
                            'sponsors': trial.get('sponsors', []),
                            'facilities': trial.get('facilities', []),
                            'study_arms': trial.get('study_arms', [])
                        })

        return chunks

class ClinicalTrialsProcessor:
    """Main processor for clinical trials data to create FAISS embeddings."""

    def __init__(self, model_name: str, vector_dimension: int, encode_batch_size: int = 128, num_workers: int = 1):
        """Initialize the processor with embedding model."""
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

            # For CPU, warn about large batch sizes and log worker count
            if device == 'cpu':
                log_with_timestamp(f"CPU workers: {self.num_workers}")
                if self.encode_batch_size > 64:
                    log_with_timestamp(f"WARNING: Large batch size ({self.encode_batch_size}) on CPU may be slow")
                    log_with_timestamp(f"Recommend: --encode-batch-size 32 for optimal CPU performance")

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

    def process_trials_batch(self, trials: List[Dict[str, Any]],
                           batch_start_idx: int = 0) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """Process a batch of trials to create embeddings."""
        log_with_timestamp(f"Processing batch of {len(trials)} trials...")

        all_chunks = []
        all_texts = []

        # Process each trial into chunks
        for trial_idx, trial in enumerate(trials):
            chunks = self.text_processor.process_trial_to_chunks(trial)

            for chunk in chunks:
                chunk['global_chunk_id'] = len(all_chunks) + batch_start_idx
                all_chunks.append(chunk)
                all_texts.append(chunk['text'])

            # Log progress every 1000 trials
            if (trial_idx + 1) % 1000 == 0:
                log_with_timestamp(f"  Processed {trial_idx + 1}/{len(trials)} trials, {len(all_chunks)} chunks so far")

        log_with_timestamp(f"Generated {len(all_chunks)} text chunks from {len(trials)} trials")

        if not all_texts:
            log_with_timestamp("No text chunks generated from trials")
            return np.array([]).reshape(0, self.vector_dimension), []

        # Generate embeddings in batches
        log_with_timestamp(f"Generating embeddings (batch_size={self.encode_batch_size})...")

        # For single worker, use simple encoding. For multi-worker, let encode handle it internally
        if self.num_workers > 1:
            log_with_timestamp(f"Using {self.num_workers} CPU workers for parallel encoding...")

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
            # Create index
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
            faiss.write_index(index, index_path)

            # Save metadata
            log_with_timestamp(f"Saving metadata to {metadata_path}")
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
        description="Process clinical trials data to create FAISS embeddings"
    )
    parser.add_argument(
        "--input-json", required=True,
        help="Input JSON file with extracted trial data"
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
        "--batch-size", type=int, default=1000,
        help="Number of trials to process at once"
    )
    parser.add_argument(
        "--encode-batch-size", type=int, default=128,
        help="Batch size for model encoding (larger = faster, more memory)"
    )
    parser.add_argument(
        "--num-workers", type=int, default=1,
        help="Number of CPU workers for parallel encoding (0 = auto, recommend 8-16 for CPU)"
    )
    parser.add_argument(
        "--max-chunk-length", type=int, default=500,
        help="Maximum chunk length for text splitting"
    )
    parser.add_argument(
        "--min-text-length", type=int, default=50,
        help="Minimum text length for inclusion"
    )
    parser.add_argument(
        "--limit", type=int,
        help="Limit number of trials to process (for testing)"
    )

    args = parser.parse_args()

    # System information
    memory = psutil.virtual_memory()
    log_with_timestamp(f"System RAM: {memory.total / 1024**3:.1f}GB total, {memory.available / 1024**3:.1f}GB available")

    try:
        # Load input data
        log_with_timestamp(f"Loading trials data from {args.input_json}")
        with open(args.input_json, 'r') as f:
            trials = json.load(f)

        log_with_timestamp(f"Loaded {len(trials)} trials from input file")

        if args.limit:
            trials = trials[:args.limit]
            log_with_timestamp(f"Limited to {len(trials)} trials for testing")

        if not trials:
            log_with_timestamp("No trials to process")
            return 1

        # Initialize processor
        log_with_timestamp("=== Starting Clinical Trials Processing ===")
        processor = ClinicalTrialsProcessor(args.model_name, args.vector_dimension, args.encode_batch_size, args.num_workers)
        processor.text_processor.max_chunk_length = args.max_chunk_length
        processor.text_processor.min_text_length = args.min_text_length

        # Load model
        if not processor.load_model():
            return 1

        # Process trials in batches
        all_embeddings = []
        all_metadata = []
        processed_trials = 0

        while processed_trials < len(trials):
            batch_end = min(processed_trials + args.batch_size, len(trials))
            batch_trials = trials[processed_trials:batch_end]

            log_with_timestamp(f"Processing trials {processed_trials + 1}-{batch_end} of {len(trials)}")

            batch_embeddings, batch_metadata = processor.process_trials_batch(
                batch_trials, len(all_metadata)
            )

            if len(batch_embeddings) > 0:
                all_embeddings.append(batch_embeddings)
                all_metadata.extend(batch_metadata)

            processed_trials = batch_end

            # Report progress
            used_mb, avail_mb, percent = get_memory_usage()
            log_with_timestamp(f"Progress: {processed_trials}/{len(trials)} trials. Memory: {used_mb:.1f}MB used ({percent:.1f}%)")

        # Combine all embeddings
        if not all_embeddings:
            log_with_timestamp("ERROR: No embeddings generated")
            return 1

        log_with_timestamp("Combining all embeddings...")
        final_embeddings = np.vstack(all_embeddings)

        log_with_timestamp(f"Final dataset: {len(final_embeddings)} embeddings from {len(trials)} trials")

        # Create FAISS index
        index = processor.create_faiss_index(final_embeddings)
        if index is None:
            return 1

        # Save index and metadata
        os.makedirs(os.path.dirname(args.output_index), exist_ok=True)
        os.makedirs(os.path.dirname(args.output_metadata), exist_ok=True)

        if not processor.save_index_and_metadata(index, all_metadata, args.output_index, args.output_metadata):
            return 1

        log_with_timestamp("=== Clinical Trials Processing Complete ===")
        return 0

    except KeyboardInterrupt:
        log_with_timestamp("Processing interrupted by user")
        return 1
    except Exception as e:
        log_with_timestamp(f"ERROR during processing: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
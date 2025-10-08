"""
Unit tests for merge functionality (merge0.py)

Tests the critical merge logic that combines multiple FAISS indices
and metadata files into a single master index.
"""
import pytest
import faiss
import json
import numpy as np
from pathlib import Path

from merge0 import merge_all_parts


class TestMergeFunction:
    """Test suite for the merge_all_parts function"""

    def test_merge_creates_output_files(self, temp_dir, sample_index_files):
        """Test that merge creates the expected output files"""
        output_dir = temp_dir / 'output'

        merge_all_parts(
            processed_dir=str(temp_dir),
            output_dir=str(output_dir),
            vector_dim=768
        )

        # Check output files exist
        assert (output_dir / 'master_pubmed.index').exists()
        assert (output_dir / 'master_metadata.json').exists()

    def test_merge_preserves_all_vectors(self, temp_dir, sample_index_files):
        """Test that merged index contains all vectors from parts"""
        output_dir = temp_dir / 'output'

        merge_all_parts(
            processed_dir=str(temp_dir),
            output_dir=str(output_dir),
            vector_dim=768
        )

        # Load merged index
        merged_index = faiss.read_index(str(output_dir / 'master_pubmed.index'))

        # Check total vector count
        expected_total = sample_index_files['total_vectors']
        assert merged_index.ntotal == expected_total, \
            f"Expected {expected_total} vectors, got {merged_index.ntotal}"

    def test_merge_preserves_vector_dimension(self, temp_dir, sample_index_files):
        """Test that vector dimension is preserved during merge"""
        output_dir = temp_dir / 'output'

        merge_all_parts(
            processed_dir=str(temp_dir),
            output_dir=str(output_dir),
            vector_dim=768
        )

        merged_index = faiss.read_index(str(output_dir / 'master_pubmed.index'))

        assert merged_index.d == 768, \
            f"Expected dimension 768, got {merged_index.d}"

    def test_metadata_alignment_with_vectors(self, temp_dir, sample_index_files):
        """CRITICAL: Test that metadata count matches vector count"""
        output_dir = temp_dir / 'output'

        merge_all_parts(
            processed_dir=str(temp_dir),
            output_dir=str(output_dir),
            vector_dim=768
        )

        # Load results
        merged_index = faiss.read_index(str(output_dir / 'master_pubmed.index'))
        with open(output_dir / 'master_metadata.json') as f:
            merged_metadata = json.load(f)

        # Critical check: counts must match
        assert merged_index.ntotal == len(merged_metadata), \
            f"Vector count ({merged_index.ntotal}) doesn't match metadata count ({len(merged_metadata)})"

    def test_metadata_keys_are_sequential(self, temp_dir, sample_index_files):
        """Test that metadata keys are re-indexed sequentially"""
        output_dir = temp_dir / 'output'

        merge_all_parts(
            processed_dir=str(temp_dir),
            output_dir=str(output_dir),
            vector_dim=768
        )

        with open(output_dir / 'master_metadata.json') as f:
            merged_metadata = json.load(f)

        # Keys should be sequential integers starting from 0
        keys = sorted([int(k) for k in merged_metadata.keys()])
        expected_keys = list(range(len(merged_metadata)))

        assert keys == expected_keys, \
            "Metadata keys should be sequential starting from 0"

    def test_merge_with_empty_directory(self, temp_dir):
        """Test merge behavior with no index files"""
        output_dir = temp_dir / 'output'
        empty_dir = temp_dir / 'empty'
        empty_dir.mkdir()

        # Should handle gracefully (currently logs error and returns)
        merge_all_parts(
            processed_dir=str(empty_dir),
            output_dir=str(output_dir),
            vector_dim=768
        )

        # Output files should NOT be created for empty input
        assert not (output_dir / 'master_pubmed.index').exists()

    def test_merge_preserves_pmid_data(self, temp_dir, sample_index_files):
        """Test that PMID data is preserved in metadata"""
        output_dir = temp_dir / 'output'

        merge_all_parts(
            processed_dir=str(temp_dir),
            output_dir=str(output_dir),
            vector_dim=768
        )

        with open(output_dir / 'master_metadata.json') as f:
            merged_metadata = json.load(f)

        # Check that all entries have required fields
        for key, value in merged_metadata.items():
            assert 'pmid' in value, f"Entry {key} missing 'pmid' field"
            assert 'chunk_text' in value, f"Entry {key} missing 'chunk_text' field"
            assert value['pmid'].startswith('PMID'), \
                f"PMID format incorrect: {value['pmid']}"


class TestMergeEdgeCases:
    """Test edge cases and error conditions"""

    def test_mismatched_dimensions_fails(self, temp_dir, sample_index_files):
        """Test that merging with wrong dimension is detected"""
        output_dir = temp_dir / 'output'

        # Try to merge with wrong dimension
        # This should fail when trying to add vectors
        with pytest.raises(Exception):  # FAISS will raise an error
            merge_all_parts(
                processed_dir=str(temp_dir),
                output_dir=str(output_dir),
                vector_dim=384  # Wrong dimension!
            )

    def test_single_file_merge(self, temp_dir):
        """Test merge with only one index file"""
        # Create single index file
        index = faiss.IndexFlatL2(768)
        vectors = [[1.0] * 768]
        index.add(np.array(vectors, dtype='float32'))

        index_path = temp_dir / 'single.index'
        faiss.write_index(index, str(index_path))

        metadata = {0: {'pmid': 'PMID123', 'chunk_text': 'Test'}}
        with open(temp_dir / 'single.json', 'w') as f:
            json.dump(metadata, f)

        output_dir = temp_dir / 'output'
        merge_all_parts(
            processed_dir=str(temp_dir),
            output_dir=str(output_dir),
            vector_dim=768
        )

        # Should successfully merge single file
        merged_index = faiss.read_index(str(output_dir / 'master_pubmed.index'))
        assert merged_index.ntotal == 1


# Import numpy for single file test
import numpy as np

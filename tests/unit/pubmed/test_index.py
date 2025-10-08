"""
Unit tests for index creation functionality (index.py)

Tests the core PubMed XML processing and FAISS index creation
"""
import pytest
import gzip
import json
import faiss
from pathlib import Path

from index import process_file, load_deleted_pmids


class TestDeletedPMIDLoading:
    """Test loading and filtering of deleted PMIDs"""

    def test_load_deleted_pmids_returns_set(self, sample_deleted_pmids):
        """Test that deleted PMIDs are loaded into a set"""
        deleted = load_deleted_pmids(str(sample_deleted_pmids))

        assert isinstance(deleted, set)
        assert len(deleted) > 0

    def test_deleted_pmids_content(self, sample_deleted_pmids):
        """Test that correct PMIDs are loaded"""
        deleted = load_deleted_pmids(str(sample_deleted_pmids))

        assert '87654321' in deleted
        assert '99999999' in deleted
        assert len(deleted) == 2

    def test_missing_deleted_file_returns_empty_set(self, temp_dir):
        """Test behavior when deleted PMIDs file doesn't exist"""
        non_existent = temp_dir / 'nonexistent.gz'
        deleted = load_deleted_pmids(str(non_existent))

        assert isinstance(deleted, set)
        assert len(deleted) == 0


class TestIndexCreation:
    """Test FAISS index creation from PubMed XML"""

    def test_process_file_creates_outputs(self, temp_dir, sample_pubmed_xml, sample_deleted_pmids):
        """Test that process_file creates index and metadata files"""
        output_dir = temp_dir / 'output'
        output_dir.mkdir()

        deleted_pmids = load_deleted_pmids(str(sample_deleted_pmids))

        # Use small model for testing
        process_file(
            input_path=str(sample_pubmed_xml),
            output_dir=str(output_dir),
            deleted_pmids_set=deleted_pmids,
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            vector_dim=384,
            limit=10
        )

        base_name = sample_pubmed_xml.stem.replace('.xml', '')
        assert (output_dir / f'{base_name}.index').exists()
        assert (output_dir / f'{base_name}.json').exists()

    def test_deleted_pmids_are_filtered(self, temp_dir, sample_pubmed_xml, sample_deleted_pmids):
        """CRITICAL: Test that deleted PMIDs are excluded from index"""
        output_dir = temp_dir / 'output'
        output_dir.mkdir()

        deleted_pmids = load_deleted_pmids(str(sample_deleted_pmids))

        process_file(
            input_path=str(sample_pubmed_xml),
            output_dir=str(output_dir),
            deleted_pmids_set=deleted_pmids,
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            vector_dim=384
        )

        base_name = sample_pubmed_xml.stem.replace('.xml', '')
        metadata_path = output_dir / f'{base_name}.json'

        with open(metadata_path) as f:
            metadata = json.load(f)

        # PMID 87654321 is deleted, so should only have 1 entry (12345678)
        assert len(metadata) == 1

        # Check that remaining PMID is correct
        pmids = [entry['pmid'] for entry in metadata.values()]
        assert '12345678' in pmids
        assert '87654321' not in pmids

    def test_vector_dimensions_match(self, temp_dir, sample_pubmed_xml, sample_deleted_pmids):
        """Test that created vectors have correct dimension"""
        output_dir = temp_dir / 'output'
        output_dir.mkdir()

        deleted_pmids = load_deleted_pmids(str(sample_deleted_pmids))
        vector_dim = 384

        process_file(
            input_path=str(sample_pubmed_xml),
            output_dir=str(output_dir),
            deleted_pmids_set=deleted_pmids,
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            vector_dim=vector_dim
        )

        base_name = sample_pubmed_xml.stem.replace('.xml', '')
        index_path = output_dir / f'{base_name}.index'

        index = faiss.read_index(str(index_path))
        assert index.d == vector_dim

    def test_index_metadata_alignment(self, temp_dir, sample_pubmed_xml, sample_deleted_pmids):
        """CRITICAL: Test that index vectors match metadata entries"""
        output_dir = temp_dir / 'output'
        output_dir.mkdir()

        deleted_pmids = load_deleted_pmids(str(sample_deleted_pmids))

        process_file(
            input_path=str(sample_pubmed_xml),
            output_dir=str(output_dir),
            deleted_pmids_set=deleted_pmids,
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            vector_dim=384
        )

        base_name = sample_pubmed_xml.stem.replace('.xml', '')
        index = faiss.read_index(str(output_dir / f'{base_name}.index'))

        with open(output_dir / f'{base_name}.json') as f:
            metadata = json.load(f)

        assert index.ntotal == len(metadata), \
            f"Index has {index.ntotal} vectors but metadata has {len(metadata)} entries"

    def test_limit_parameter_works(self, temp_dir, sample_pubmed_xml, sample_deleted_pmids):
        """Test that limit parameter restricts number of processed abstracts"""
        output_dir = temp_dir / 'output'
        output_dir.mkdir()

        deleted_pmids = load_deleted_pmids(str(sample_deleted_pmids))

        # Process with limit=1
        process_file(
            input_path=str(sample_pubmed_xml),
            output_dir=str(output_dir),
            deleted_pmids_set=deleted_pmids,
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            vector_dim=384,
            limit=1
        )

        base_name = sample_pubmed_xml.stem.replace('.xml', '')
        with open(output_dir / f'{base_name}.json') as f:
            metadata = json.load(f)

        # Should have exactly 1 entry (limit=1)
        assert len(metadata) == 1

    def test_skips_existing_output(self, temp_dir, sample_pubmed_xml, sample_deleted_pmids):
        """Test that processing is skipped if output already exists"""
        output_dir = temp_dir / 'output'
        output_dir.mkdir()

        deleted_pmids = load_deleted_pmids(str(sample_deleted_pmids))
        base_name = sample_pubmed_xml.stem.replace('.xml', '')

        # Create dummy existing files
        (output_dir / f'{base_name}.index').touch()
        (output_dir / f'{base_name}.json').touch()

        initial_mtime = (output_dir / f'{base_name}.index').stat().st_mtime

        # Try to process - should skip
        process_file(
            input_path=str(sample_pubmed_xml),
            output_dir=str(output_dir),
            deleted_pmids_set=deleted_pmids,
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            vector_dim=384
        )

        # File should not be modified
        final_mtime = (output_dir / f'{base_name}.index').stat().st_mtime
        assert initial_mtime == final_mtime


class TestMetadataContent:
    """Test metadata content and structure"""

    def test_metadata_has_required_fields(self, temp_dir, sample_pubmed_xml, sample_deleted_pmids):
        """Test that metadata contains required fields"""
        output_dir = temp_dir / 'output'
        output_dir.mkdir()

        deleted_pmids = load_deleted_pmids(str(sample_deleted_pmids))

        process_file(
            input_path=str(sample_pubmed_xml),
            output_dir=str(output_dir),
            deleted_pmids_set=deleted_pmids,
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            vector_dim=384
        )

        base_name = sample_pubmed_xml.stem.replace('.xml', '')
        with open(output_dir / f'{base_name}.json') as f:
            metadata = json.load(f)

        for entry in metadata.values():
            assert 'pmid' in entry
            assert 'chunk_text' in entry
            assert 'Title:' in entry['chunk_text']
            assert 'Abstract:' in entry['chunk_text']

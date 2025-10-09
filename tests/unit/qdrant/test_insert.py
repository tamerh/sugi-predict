"""
Unit tests for Qdrant insertion functions

Tests the core functionality of insert_from_faiss.py without requiring
a running Qdrant server.
"""
import pytest
import json
import faiss
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add modules to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "modules" / "qdrant" / "scripts"))

from insert_from_faiss import (
    find_faiss_files,
    load_faiss_and_metadata,
    create_collection_if_needed
)


class TestFindFaissFiles:
    """Test FAISS file discovery"""

    def test_finds_index_files_in_directory(self, tmp_path):
        """Test finding .index files in a directory"""
        # Create test structure
        test_dir = tmp_path / "test_data"
        test_dir.mkdir()

        # Create some .index files
        (test_dir / "file1.index").touch()
        (test_dir / "file2.index").touch()
        (test_dir / "file3.txt").touch()  # Should be ignored

        # Find files
        files = find_faiss_files(str(test_dir))

        # Verify
        assert len(files) == 2
        assert all(f.endswith('.index') for f in files)
        assert sorted([Path(f).name for f in files]) == ['file1.index', 'file2.index']

    def test_finds_files_recursively(self, tmp_path):
        """Test recursive discovery of .index files"""
        # Create nested structure
        base = tmp_path / "data"
        sub1 = base / "processed" / "pubmed" / "baseline"
        sub2 = base / "processed" / "pubmed" / "updatefiles"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)

        # Create files in different subdirectories
        (sub1 / "baseline_001.index").touch()
        (sub1 / "baseline_002.index").touch()
        (sub2 / "update_001.index").touch()

        # Find all files
        files = find_faiss_files(str(base))

        # Verify
        assert len(files) == 3
        assert all('.index' in f for f in files)

    def test_returns_sorted_list(self, tmp_path):
        """Test that files are returned in sorted order"""
        test_dir = tmp_path / "data"
        test_dir.mkdir()

        # Create files in reverse order
        (test_dir / "file3.index").touch()
        (test_dir / "file1.index").touch()
        (test_dir / "file2.index").touch()

        files = find_faiss_files(str(test_dir))
        file_names = [Path(f).name for f in files]

        assert file_names == sorted(file_names)

    def test_returns_empty_list_if_no_files(self, tmp_path):
        """Test handling of directory with no .index files"""
        test_dir = tmp_path / "empty"
        test_dir.mkdir()

        files = find_faiss_files(str(test_dir))

        assert files == []


class TestLoadFaissAndMetadata:
    """Test loading FAISS indices and metadata"""

    def test_loads_faiss_index_and_json_metadata(self, tmp_path):
        """Test loading FAISS index with JSON metadata"""
        # Create a simple FAISS index
        dim = 768
        n_vectors = 10
        vectors = np.random.random((n_vectors, dim)).astype('float32')
        index = faiss.IndexFlatL2(dim)
        index.add(vectors)

        # Save index
        index_path = tmp_path / "test.index"
        faiss.write_index(index, str(index_path))

        # Create metadata (JSON format)
        metadata = {str(i): {'pmid': f'PMID{i}', 'text': f'Text {i}'} for i in range(n_vectors)}
        metadata_path = tmp_path / "test.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f)

        # Load
        loaded_index, loaded_metadata = load_faiss_and_metadata(str(index_path))

        # Verify
        assert loaded_index.ntotal == n_vectors
        assert loaded_index.d == dim
        assert len(loaded_metadata) == n_vectors
        assert loaded_metadata['0']['pmid'] == 'PMID0'

    def test_handles_missing_metadata_file(self, tmp_path):
        """Test error handling when metadata file is missing"""
        # Create index without metadata
        dim = 768
        index = faiss.IndexFlatL2(dim)
        index.add(np.random.random((5, dim)).astype('float32'))

        index_path = tmp_path / "test.index"
        faiss.write_index(index, str(index_path))

        # Should raise an error
        with pytest.raises(FileNotFoundError):
            load_faiss_and_metadata(str(index_path))


class TestPointCreation:
    """Test point creation for Qdrant insertion"""

    def test_point_structure_with_qdrant_models(self):
        """Test that PointStruct can be created with correct structure"""
        from qdrant_client.models import PointStruct

        # Create a sample point
        vector = np.random.random(768).astype('float32').tolist()
        payload = {'pmid': 'PMID123', 'title': 'Test Title'}

        point = PointStruct(
            id=1000,
            vector=vector,
            payload=payload
        )

        # Verify structure
        assert point.id == 1000
        assert len(point.vector) == 768
        assert point.payload['pmid'] == 'PMID123'
        assert point.payload['title'] == 'Test Title'

    def test_batch_of_points(self):
        """Test creating a batch of points"""
        from qdrant_client.models import PointStruct

        batch = []
        for i in range(3):
            vector = np.random.random(768).astype('float32').tolist()
            payload = {'id': f'TEST{i}', 'index': i}
            point = PointStruct(id=1000+i, vector=vector, payload=payload)
            batch.append(point)

        assert len(batch) == 3
        assert all(isinstance(p, PointStruct) for p in batch)
        assert batch[0].id == 1000
        assert batch[2].id == 1002


class TestQdrantClientMock:
    """Test Qdrant client operations with mocking"""

    @patch('insert_from_faiss.QdrantClient')
    def test_create_collection_if_needed_creates_new_collection(self, mock_client_class):
        """Test collection creation when it doesn't exist"""
        from insert_from_faiss import create_collection_if_needed

        # Mock client that raises exception (collection doesn't exist)
        mock_client = Mock()
        mock_client.get_collection.side_effect = Exception("Not found")
        mock_client_class.return_value = mock_client

        # Call function
        create_collection_if_needed(mock_client, "test_collection", vector_size=768)

        # Verify create_collection was called
        mock_client.create_collection.assert_called_once()
        call_args = mock_client.create_collection.call_args
        assert call_args.kwargs['collection_name'] == "test_collection"

    @patch('insert_from_faiss.QdrantClient')
    def test_create_collection_if_needed_skips_existing(self, mock_client_class):
        """Test that existing collection is not recreated"""
        from insert_from_faiss import create_collection_if_needed

        # Mock client that returns existing collection
        mock_client = Mock()
        mock_client.get_collection.return_value = {'name': 'test_collection'}
        mock_client_class.return_value = mock_client

        # Call function
        create_collection_if_needed(mock_client, "test_collection")

        # Verify create_collection was NOT called
        mock_client.create_collection.assert_not_called()


class TestIntegrationHelpers:
    """Test helper functions for integration"""

    def test_logging_functions_dont_crash(self):
        """Test that logging functions can be called without errors"""
        from insert_from_faiss import log_with_timestamp, init_logging

        # These should not raise errors
        log_with_timestamp("Test message")
        # Note: init_logging requires actual file system, tested in integration tests

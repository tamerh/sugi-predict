"""
Unit tests for configuration validation

Tests configuration file structure and validation logic
"""
import pytest
import yaml
from pathlib import Path


class TestConfigValidation:
    """Test configuration file validation"""

    def test_config_file_exists(self):
        """Test that main config file exists"""
        config_path = Path('config/config.yaml')
        assert config_path.exists(), "config/config.yaml not found"

    def test_test_config_exists(self):
        """Test that test config file exists"""
        config_path = Path('config/test_config.yaml')
        assert config_path.exists(), "config/test_config.yaml not found"

    def test_config_has_required_top_level_keys(self):
        """Test that config has required top-level keys"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        required_keys = ['base_dir', 'pubmed', 'clinical_trials', 'qdrant']
        for key in required_keys:
            assert key in config, f"Missing required config key: {key}"

    def test_pubmed_config_structure(self):
        """Test PubMed configuration structure"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        pubmed = config['pubmed']
        required_fields = ['model_name', 'vector_dimension', 'batch_size']

        for field in required_fields:
            assert field in pubmed, f"Missing PubMed config field: {field}"

    def test_clinical_trials_config_structure(self):
        """Test clinical trials configuration structure"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        ct = config['clinical_trials']
        required_fields = ['model_name', 'vector_dimension', 'batch_size']

        for field in required_fields:
            assert field in ct, f"Missing clinical_trials config field: {field}"

    def test_vector_dimensions_are_integers(self):
        """Test that vector dimensions are valid integers"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        assert isinstance(config['pubmed']['vector_dimension'], int)
        assert isinstance(config['clinical_trials']['vector_dimension'], int)

        # Common dimensions
        valid_dims = [384, 768, 1024, 1536]
        assert config['pubmed']['vector_dimension'] in valid_dims
        assert config['clinical_trials']['vector_dimension'] in valid_dims

    def test_memory_settings_are_reasonable(self):
        """Test that memory settings are reasonable values"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        # Memory should be at least 1GB, at most 512GB
        min_mem = 1024  # 1GB
        max_mem = 524288  # 512GB

        mem_fields = [
            config['pubmed'].get('process_memory_mb'),
            config['clinical_trials'].get('process_memory_mb'),
        ]

        for mem in mem_fields:
            if mem is not None:
                assert min_mem <= mem <= max_mem, \
                    f"Memory {mem}MB outside reasonable range ({min_mem}-{max_mem})"

    def test_test_config_has_debug_mode(self):
        """Test that test config enables debug/test mode"""
        with open('config/test_config.yaml') as f:
            config = yaml.safe_load(f)

        # Test config should have debug or test mode enabled
        assert config['pubmed'].get('debug_mode') is True or \
               config['pubmed'].get('test_mode') is True


class TestPathConstruction:
    """Test path construction logic from config"""

    def test_base_dir_exists_in_config(self):
        """Test that base_dir is defined"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        assert 'base_dir' in config
        assert isinstance(config['base_dir'], str)
        assert len(config['base_dir']) > 0

    def test_paths_can_be_constructed(self, mock_config):
        """Test that paths can be constructed from config"""
        import os

        base_dir = mock_config['base_dir']

        # Simulate path construction from Snakefile
        raw_dir = os.path.join(base_dir, 'raw_data', 'pubmed')
        processed_dir = os.path.join(base_dir, 'data', 'processed', 'pubmed')
        merged_dir = os.path.join(base_dir, 'data', 'merged', 'pubmed')

        # Paths should be well-formed
        assert 'raw_data/pubmed' in raw_dir
        assert 'data/processed/pubmed' in processed_dir
        assert 'data/merged/pubmed' in merged_dir


class TestModelConfiguration:
    """Test model-related configuration"""

    def test_model_names_are_valid_strings(self):
        """Test that model names are properly formatted"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        pubmed_model = config['pubmed']['model_name']
        ct_model = config['clinical_trials']['model_name']

        assert isinstance(pubmed_model, str)
        assert isinstance(ct_model, str)
        assert len(pubmed_model) > 0
        assert len(ct_model) > 0

    def test_models_are_consistent(self):
        """Test that models are consistent across modules"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        # For consistency, both should use the same model
        pubmed_model = config['pubmed']['model_name']
        ct_model = config['clinical_trials']['model_name']

        assert pubmed_model == ct_model, \
            "Models should be consistent across modules for compatibility"

    def test_dimensions_match_models(self):
        """Test that vector dimensions match the specified models"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        # S-BioBERT should be 768d, MiniLM should be 384d
        model_name = config['pubmed']['model_name']
        vector_dim = config['pubmed']['vector_dimension']

        if 'BioBERT' in model_name or 'biobert' in model_name.lower():
            assert vector_dim == 768, "BioBERT should use 768 dimensions"
        elif 'MiniLM' in model_name:
            assert vector_dim == 384, "MiniLM should use 384 dimensions"


class TestQdrantConfiguration:
    """Test Qdrant-specific configuration"""

    def test_qdrant_config_exists(self):
        """Test that Qdrant configuration exists"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        assert 'qdrant' in config

    def test_batch_size_is_reasonable(self):
        """Test that Qdrant batch size is reasonable"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        batch_size = config['qdrant'].get('batch_size')
        if batch_size is not None:
            assert 1 <= batch_size <= 10000, \
                f"Batch size {batch_size} outside reasonable range (1-10000)"

    def test_collection_names_defined(self):
        """Test that collection names are defined"""
        with open('config/config.yaml') as f:
            config = yaml.safe_load(f)

        pubmed_collection = config['pubmed'].get('qdrant', {}).get('collection_name')
        ct_collection = config['clinical_trials'].get('qdrant', {}).get('collection_name')

        if pubmed_collection:
            assert isinstance(pubmed_collection, str)
            assert len(pubmed_collection) > 0

        if ct_collection:
            assert isinstance(ct_collection, str)
            assert len(ct_collection) > 0

"""
Configuration management for BioYoda Search API
"""
import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class APIConfig:
    """API Configuration Manager"""

    def __init__(self, config_path: str = None):
        """
        Initialize configuration from YAML file

        Args:
            config_path: Path to configuration YAML file. If None, uses BIOYODA_CONFIG env var
                        or defaults to config.yaml (test_config.yaml in test mode)
        """
        if config_path is None:
            # Check for environment variable
            config_path = os.environ.get('BIOYODA_CONFIG')

            if config_path is None:
                # Auto-detect based on environment
                # If we're in test mode (check if test_out exists), use test_config
                test_out = Path("../../test_out")
                if test_out.exists():
                    config_path = "../../config/test_config.yaml"
                    logger.info("Test mode detected (test_out/ exists), using test_config.yaml")
                else:
                    config_path = "../../config/config.yaml"
                    logger.info("Production mode, using config.yaml")

        self.config_path = config_path
        self._config = self._load_config()

        # Extract commonly used values
        self.qdrant_url = self._get_qdrant_url()

        # Build collection -> model mapping
        # Each collection may use a different embedding model during indexing
        self.collection_models = self._build_collection_model_mapping()

        # Legacy single model (for backward compatibility, use pubmed model)
        self.model_name = self._config['pubmed']['model_name']
        self.vector_dimension = self._config['pubmed']['vector_dimension']

        self.default_limit = self._config['search']['default_limit']
        self.max_limit = self._config['search']['max_limit']
        self.collections = self._config['collections']
        self.rag = self._config.get('rag', None)

        logger.info(f"Configuration loaded from: {config_path}")
        logger.info(f"Qdrant URL: {self.qdrant_url}")
        logger.info(f"Collection-Model mappings:")
        for collection, model in self.collection_models.items():
            logger.info(f"  - {collection}: {model}")
        logger.info(f"Vector dimension: {self.vector_dimension}")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        config_file = Path(self.config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(config_file) as f:
            config = yaml.safe_load(f)

        return config

    def _build_collection_model_mapping(self) -> Dict[str, str]:
        """
        Build mapping of collection names to their embedding models.

        Each collection (e.g., pubmed_abstracts, clinical_trials) may have been
        indexed with a different embedding model. This mapping ensures we use
        the correct model when encoding queries for each collection.

        Returns:
            Dict mapping collection name -> model name
        """
        mapping = {}

        # Map collection names to their source config sections
        # Collection "pubmed_abstracts" -> config section "pubmed"
        # Collection "clinical_trials" -> config section "clinical_trials"
        # Collection "patents_text" -> config section "patents"
        collection_to_config = {
            "pubmed_abstracts": "pubmed",
            "clinical_trials": "clinical_trials",
            "patents_text": "patents"
        }

        for collection_name, config_key in collection_to_config.items():
            if config_key in self._config:
                model_name = self._config[config_key].get('model_name')
                if model_name:
                    mapping[collection_name] = model_name
                else:
                    logger.warning(f"No model_name found for {config_key}, using pubmed model as fallback")
                    mapping[collection_name] = self._config['pubmed']['model_name']

        if not mapping:
            # Fallback: use pubmed model for all collections
            logger.warning("Could not build collection-model mapping, using pubmed model for all")
            mapping = {
                "pubmed_abstracts": self._config['pubmed']['model_name'],
                "clinical_trials": self._config['pubmed']['model_name']
            }

        return mapping

    def _get_qdrant_url(self) -> str:
        """
        Get Qdrant URL, trying multiple sources:
        1. Environment variable QDRANT_URL
        2. Connection info file (from running server)
        3. Default from config file
        """
        # Try environment variable first
        if 'QDRANT_URL' in os.environ:
            url = os.environ['QDRANT_URL']
            logger.info(f"Using Qdrant URL from environment: {url}")
            return url

        # Try connection info file
        connection_info_path = self._config.get('qdrant_api', {}).get('connection_info_path')
        if connection_info_path:
            conn_file = Path(connection_info_path)
            if conn_file.exists():
                try:
                    with open(conn_file) as f:
                        for line in f:
                            if line.startswith('QDRANT_URL='):
                                url = line.split('=', 1)[1].strip()
                                logger.info(f"Using Qdrant URL from connection file: {url}")
                                return url
                except Exception as e:
                    logger.warning(f"Could not read connection info file: {e}")

        # Fall back to default
        url = self._config.get('qdrant_api', {}).get('url', 'http://localhost:6333')
        logger.info(f"Using default Qdrant URL: {url}")
        return url

    def get_collection_config(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific collection"""
        return self.collections.get(collection_name)

    def get_all_collection_names(self) -> list:
        """Get list of all configured collection names"""
        return list(self.collections.keys())


# Global configuration instance
# This will be initialized on first import
config: Optional[APIConfig] = None


def init_config(config_path: str = None) -> APIConfig:
    """
    Initialize global configuration

    Args:
        config_path: Path to configuration file (optional, auto-detects if None)

    Returns:
        Initialized APIConfig instance
    """
    global config
    config = APIConfig(config_path)
    return config


def get_config() -> APIConfig:
    """
    Get global configuration instance (auto-initializes if needed)

    Returns:
        APIConfig instance
    """
    global config
    if config is None:
        # Auto-initialize (will auto-detect config file)
        config = init_config()
    return config

#!/usr/bin/env python3
"""
Simple configuration loader for BioYoda project.
Loads settings from bioyoda.env file.
"""

import os
from pathlib import Path
from typing import Dict, Optional

class BioYodaConfig:
    """Simple configuration loader for .env file."""

    def __init__(self, env_file: Optional[str] = None):
        """Initialize configuration loader."""
        if env_file is None:
            # Look for bioyoda.env in project root
            current_dir = Path(__file__).parent
            # First try current directory (for modules/pubmed/scripts/)
            env_file = current_dir / "pubmed.env"
            # Fallback to old location (for scripts/pubmed/)
            if not env_file.exists():
                project_root = current_dir.parent.parent  # Go up two levels to project root
                env_file = project_root / "scripts/pubmed/pubmed.env"

        self.env_file = Path(env_file)
        self.config = self._load_env()

    def _load_env(self) -> Dict[str, str]:
        """Load environment variables from .env file."""
        config = {}

        if not self.env_file.exists():
            raise FileNotFoundError(f"Environment file not found: {self.env_file}")

        with open(self.env_file, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if line.startswith('#') or not line:
                    continue

                # Parse key=value pairs
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")  # Remove quotes
                    config[key] = value

        return config

    def get(self, key: str, default: Optional[str] = None) -> str:
        """Get configuration value."""
        return self.config.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """Get configuration value as integer."""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get configuration value as boolean."""
        value = self.get(key)
        if value is None:
            return default
        return value.lower() in ('true', '1', 'yes', 'on')

    def get_path(self, key: str, relative_to_project: bool = True) -> Optional[Path]:
        """Get configuration value as Path object."""
        value = self.get(key)
        if value is None:
            return None

        path = Path(value)

        # If relative and not absolute, make it relative to project root
        if relative_to_project and not path.is_absolute():
            project_root = Path(self.get('PROJECT_ROOT', '.'))
            path = project_root / path

        return path

    def is_debug(self) -> bool:
        """Check if debug mode is enabled."""
        return self.get_bool('DEBUG_MODE')

    def get_sample_size(self) -> Optional[int]:
        """Get debug sample size."""
        if self.is_debug():
            return self.get_int('DEBUG_SAMPLE_SIZE', 10)
        return None

    def __getitem__(self, key: str) -> str:
        """Allow dictionary-style access."""
        return self.get(key)


# Global config instance
_config = None

def get_config() -> BioYodaConfig:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = BioYodaConfig()
    return _config


# Example usage and testing
if __name__ == "__main__":
    config = get_config()

    print("BioYoda Configuration Test")
    print("=" * 30)
    print(f"Project name: {config.get('PROJECT_NAME')}")
    print(f"Environment: {config.get('ENVIRONMENT')}")
    print(f"Vector model: {config.get('VECTOR_MODEL')}")
    print(f"Debug mode: {config.is_debug()}")
    print(f"Sample size: {config.get_sample_size()}")
    print(f"Project root: {config.get_path('PROJECT_ROOT')}")
    print(f"Raw PubMed dir: {config.get_path('RAW_PUBMED_DIR')}")
    print(f"Batch size: {config.get_int('PUBMED_BATCH_SIZE')}")
    print(f"Merge method: {config.get('PUBMED_MERGE_METHOD')}")
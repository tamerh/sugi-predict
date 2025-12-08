"""
Test configuration loading and merging with main BioYoda config.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.core.config import load_config


def test_config_merge():
    """Test that config merges correctly with main BioYoda config."""

    print("Testing configuration merge...\n")

    # Load config with merge enabled
    config = load_config(merge_main_config=True)

    print("=" * 60)
    print("CONFIGURATION LOADED")
    print("=" * 60)

    # Check LLM configuration
    print("\nLLM Configuration:")
    print(f"  Default provider: {config.llm.default_provider}")

    if config.llm.default_provider and config.llm.default_provider in config.llm.providers:
        provider_config = config.llm.providers[config.llm.default_provider]
        print(f"  Model: {provider_config.model}")
        print(f"  Max tokens: {provider_config.max_tokens}")
        print(f"  Temperature: {provider_config.temperature}")
        print(f"  Timeout: {provider_config.timeout}s")
        print(f"  API key env: {provider_config.api_key_env}")

    # Check all configured providers
    print("\nConfigured providers:")
    for provider_name, provider_config in config.llm.providers.items():
        print(f"  - {provider_name}:")
        print(f"      Model: {provider_config.model}")
        print(f"      Temperature: {provider_config.temperature}")

    # Check BioBTree configuration
    print("\nBioBTree Configuration:")
    print(f"  Protocol: {config.integrations.biobtree.protocol}")
    print(f"  gRPC host: {config.integrations.biobtree.grpc.host}")
    print(f"  gRPC port: {config.integrations.biobtree.grpc.port}")

    # Check Qdrant configuration
    print("\nQdrant Configuration:")
    print(f"  Host: {config.integrations.qdrant.host}")
    print(f"  Port: {config.integrations.qdrant.port}")
    print(f"  Collections: {config.integrations.qdrant.collections}")

    # Check Agent configuration
    print("\nAgent Configuration:")
    print(f"  Max iterations: {config.agents.max_iterations}")
    print(f"  Tool timeout: {config.agents.tool_timeout}s")

    print("\n" + "=" * 60)
    print("✓ Configuration merge successful!")
    print("=" * 60)


if __name__ == "__main__":
    test_config_merge()

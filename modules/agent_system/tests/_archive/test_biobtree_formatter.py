"""Test BioBTree result formatting."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.core.config import get_config
from modules.agent_system.integrations.biobtree_client import create_biobtree_client
from modules.agent_system.utils.biobtree_formatter import (
    filter_canonical_proteins,
    format_biobtree_results
)


async def test_formatter():
    """Test the formatter with real BioBTree data."""
    config = get_config()
    client = create_biobtree_client(config.integrations.biobtree)

    async with client:
        # Test with multiple genes
        print("="*70)
        print("Testing with TP53 and BRCA1")
        print("="*70)

        response = await client.map_query(
            terms=["TP53", "BRCA1"],
            mapfilter=">>ensembl>>uniprot"
        )

        # Test 1: Filter canonical proteins (all species)
        print("\n1. All canonical proteins:")
        print("-" * 70)
        filtered = filter_canonical_proteins(response)
        for item in filtered:
            print(f"{item['gene']:8s} ({item['species']:10s}) -> {item['protein']['identifier']}: {item['protein']['name']}")

        # Test 2: Human only
        print("\n2. Human canonical proteins only:")
        print("-" * 70)
        human_only = filter_canonical_proteins(response, human_only=True)
        for item in human_only:
            print(f"{item['gene']:8s} -> {item['protein']['identifier']}: {item['protein']['name']}")

        # Test 3: Formatted output (all species)
        print("\n3. Formatted output (all species):")
        print("-" * 70)
        formatted = format_biobtree_results(response, show_all_species=True)
        print(formatted)

        # Test 4: Formatted output (human only)
        print("\n4. Formatted output (human only):")
        print("-" * 70)
        formatted_human = format_biobtree_results(response, human_only=True)
        print(formatted_human)

        # Test 5: Formatted output (prioritize human)
        print("\n5. Formatted output (prioritize human, one per gene):")
        print("-" * 70)
        formatted_prioritize = format_biobtree_results(response, show_all_species=False)
        print(formatted_prioritize)


if __name__ == "__main__":
    asyncio.run(test_formatter())

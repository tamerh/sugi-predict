"""Test BioBTree native filtering capabilities."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.tools import setup_tools


async def test_native_filtering():
    """Test native BioBTree filtering via tool."""
    registry = setup_tools()

    print("="*70)
    print("BioBTree Native Filtering Test")
    print("="*70)

    # Test 1: Default (human + canonical)
    print("\nTest 1: Default filtering (human + canonical)")
    print("-" * 70)
    result1 = await registry.execute_tool(
        "biobtree_query",
        chain_query="TP53,BRCA1 >> ensembl >> uniprot"
        # defaults: species="homo_sapiens", canonical_only=True
    )
    print(f"Mapfilter: {result1.metadata['mapfilter']}")
    print(f"Summary: {result1.metadata['summary']}")
    print(f"Canonical proteins:")
    for item in result1.metadata['canonical_proteins']:
        print(f"  {item['gene']:8s} -> {item['protein']['identifier']}: {item['protein']['name']}")

    # Test 2: All species + canonical
    print("\nTest 2: All species, canonical only")
    print("-" * 70)
    result2 = await registry.execute_tool(
        "biobtree_query",
        chain_query="TP53 >> ensembl >> uniprot",
        species=None,  # All species
        canonical_only=True
    )
    print(f"Mapfilter: {result2.metadata['mapfilter']}")
    print(f"Summary: {result2.metadata['summary']}")
    print(f"Species found:")
    for item in result2.metadata['canonical_proteins']:
        print(f"  {item['species']:15s} {item['gene']:8s} -> {item['protein']['identifier']}")

    # Test 3: Human + all variants (no canonical filter)
    print("\nTest 3: Human, all variants/isoforms")
    print("-" * 70)
    result3 = await registry.execute_tool(
        "biobtree_query",
        chain_query="TP53 >> ensembl >> uniprot",
        species="homo_sapiens",
        canonical_only=False  # Include all isoforms
    )
    print(f"Mapfilter: {result3.metadata['mapfilter']}")
    print(f"Summary: {result3.metadata['summary']}")
    print(f"  (showing all {result3.metadata['total_targets']} isoforms/variants)")

    # Test 4: Mouse canonical
    print("\nTest 4: Mouse canonical proteins")
    print("-" * 70)
    result4 = await registry.execute_tool(
        "biobtree_query",
        chain_query="Brca1,Tp53 >> ensembl >> uniprot",
        species="mus_musculus",
        canonical_only=True
    )
    print(f"Mapfilter: {result4.metadata['mapfilter']}")
    print(f"Summary: {result4.metadata['summary']}")
    for item in result4.metadata['canonical_proteins']:
        print(f"  {item['gene']:8s} -> {item['protein']['identifier']}: {item['protein']['name']}")

    # Comparison
    print("\n" + "="*70)
    print("COMPARISON: Filtering Effectiveness")
    print("="*70)
    print(f"Default (human + canonical):     {result1.metadata['total_targets']} targets")
    print(f"All species (canonical):         {result2.metadata['total_targets']} targets")
    print(f"Human (all isoforms):            {result3.metadata['total_targets']} targets")
    print(f"Mouse (canonical):               {result4.metadata['total_targets']} targets")


if __name__ == "__main__":
    asyncio.run(test_native_filtering())

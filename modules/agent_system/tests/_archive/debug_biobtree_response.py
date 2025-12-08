"""Debug script to understand BioBTree response structure."""

import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.core.config import get_config
from modules.agent_system.integrations.biobtree_client import create_biobtree_client


async def debug_response():
    """Get and analyze raw BioBTree response."""
    config = get_config()
    client = create_biobtree_client(config.integrations.biobtree)

    async with client:
        print("="*70)
        print("Single term: TP53")
        print("="*70)
        result = await client.map_query(
            terms=["TP53"],
            mapfilter=">>ensembl>>uniprot",
            detail=False
        )
        print(json.dumps(result, indent=2))

        print("\n" + "="*70)
        print("Multiple terms: TP53, BRCA1")
        print("="*70)
        result2 = await client.map_query(
            terms=["TP53", "BRCA1"],
            mapfilter=">>ensembl>>uniprot",
            detail=False
        )
        print(json.dumps(result2, indent=2))


if __name__ == "__main__":
    asyncio.run(debug_response())

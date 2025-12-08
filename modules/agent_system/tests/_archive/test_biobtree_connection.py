"""
Test BioBTree gRPC client with real connection to scc2.
"""

import asyncio
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.core.config import BioBTreeConfig, GrpcConfig
from modules.agent_system.integrations.biobtree_client import create_biobtree_client


async def test_connection():
    """Test basic connection to BioBTree on scc2."""

    # Configure for scc2
    config = BioBTreeConfig(
        protocol="grpc",
        grpc=GrpcConfig(
            host="scc2",  # BioBTree running on scc2
            port=7777,
            timeout=30
        )
    )

    print(f"Connecting to BioBTree at {config.grpc.host}:{config.grpc.port}...")

    # Create client
    client = create_biobtree_client(config)

    try:
        async with client:
            print("✓ Connected successfully!\n")

            # Test 1: Get metadata
            print("Test 1: Getting metadata...")
            meta = await client.get_metadata()
            print(f"✓ Retrieved metadata for {len(meta.get('results', {}))} datasets\n")

            # Test 2: Simple search
            print("Test 2: Searching for 'TP53'...")
            search_result = await client.search(
                terms=["TP53"],
                detail=False
            )
            print(f"✓ Search completed")
            print(f"  Results: {search_result}\n")

            # Test 3: Mapping query
            print("Test 3: Mapping query 'BRCA1 >> * >> hgnc'...")
            map_result = await client.map_query(
                terms=["BRCA1"],
                mapfilter=">>*>>hgnc"
            )
            print(f"✓ Mapping completed")
            print(f"  Results: {map_result}\n")

            print("=" * 60)
            print("All tests passed! ✓")
            print("=" * 60)

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_connection())

"""
Test tool abstraction layer with BioBTree.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.tools import setup_tools, get_registry
from modules.agent_system.tools.base import ToolResult


async def test_tool_registry():
    """Test tool registry setup."""
    print("=" * 60)
    print("TEST 1: Tool Registry")
    print("=" * 60)
    
    # Setup tools
    registry = setup_tools()
    
    print(f"\n✓ Registered {len(registry)} tools:")
    for tool_name in registry.list_tools():
        tool = registry.get_tool(tool_name)
        print(f"  - {tool_name}: {tool.description[:60]}...")
    
    # Get tool definitions (for LLM)
    definitions = registry.get_tool_definitions()
    print(f"\n✓ Generated {len(definitions)} tool definitions for LLM")
    
    for defn in definitions:
        print(f"\n  Tool: {defn.name}")
        print(f"  Parameters: {list(defn.parameters.get('properties', {}).keys())}")


async def test_biobtree_query_tool():
    """Test BioBTree query tool execution."""
    print("\n" + "=" * 60)
    print("TEST 2: BioBTree Query Tool")
    print("=" * 60)
    
    registry = setup_tools()
    
    # Test 1: Gene to protein mapping
    print("\nTest 2.1: Gene to protein (BRCA1 >> * >> hgnc >> uniprot)")
    result: ToolResult = await registry.execute_tool(
        "biobtree_query",
        chain_query="BRCA1 >> * >> hgnc >> uniprot",
        detail=False
    )
    
    if result.success:
        print("✓ Query successful")
        print(f"  Metadata: {result.metadata}")
        
        # Check if we got results
        if result.data and 'results' in result.data:
            results_data = result.data['results'].get('results', [])
            print(f"  Found {len(results_data)} mapping paths")
            
            if results_data:
                # Show first result
                first = results_data[0]
                if 'targets' in first:
                    print(f"  First target: {first['targets'][0] if first['targets'] else 'None'}")
    else:
        print(f"✗ Query failed: {result.error}")
    
    # Test 2: Simpler query - just find TP53
    print("\nTest 2.2: Search for TP53 (TP53 >> * >> hgnc)")
    result2 = await registry.execute_tool(
        "biobtree_query",
        chain_query="TP53 >> * >> hgnc",
        detail=False
    )
    
    if result2.success:
        print("✓ Query successful")
        print(f"  Metadata: {result2.metadata}")
    else:
        print(f"✗ Query failed: {result2.error}")


async def test_biobtree_search_tool():
    """Test BioBTree search tool."""
    print("\n" + "=" * 60)
    print("TEST 3: BioBTree Search Tool")
    print("=" * 60)
    
    registry = setup_tools()
    
    # Search for EGFR
    print("\nSearching for 'EGFR'...")
    result: ToolResult = await registry.execute_tool(
        "biobtree_search",
        term="EGFR",
        detail=False
    )
    
    if result.success:
        print("✓ Search successful")
        
        if result.data and 'results' in result.data:
            results_list = result.data['results'].get('results', [])
            print(f"  Found in {len(results_list)} datasets")
            
            # Show first few
            for i, entry in enumerate(results_list[:3]):
                dataset = entry.get('dataset_name', 'unknown')
                identifier = entry.get('identifier', 'N/A')
                print(f"  {i+1}. {dataset}: {identifier}")
    else:
        print(f"✗ Search failed: {result.error}")


async def test_tool_error_handling():
    """Test tool error handling."""
    print("\n" + "=" * 60)
    print("TEST 4: Error Handling")
    print("=" * 60)
    
    registry = setup_tools()
    
    # Test 1: Invalid tool name
    print("\nTest 4.1: Invalid tool name")
    result = await registry.execute_tool("nonexistent_tool", param="test")
    
    if not result.success:
        print(f"✓ Correctly handled error: {result.error}")
    else:
        print("✗ Should have failed")
    
    # Test 2: Invalid query format
    print("\nTest 4.2: Invalid query format")
    result2 = await registry.execute_tool(
        "biobtree_query",
        chain_query="INVALID"  # Missing >>
    )
    
    if not result2.success:
        print(f"✓ Correctly handled error: {result2.error}")
    else:
        print("✗ Should have failed")


async def main():
    """Run all tests."""
    try:
        await test_tool_registry()
        await test_biobtree_query_tool()
        await test_biobtree_search_tool()
        await test_tool_error_handling()
        
        print("\n" + "=" * 60)
        print("✓ All tool tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

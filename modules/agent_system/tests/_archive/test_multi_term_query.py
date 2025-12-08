"""Test multi-term query support in BioBTree tool."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.llm import create_llm_provider, Message
from modules.agent_system.tools import setup_tools


SYSTEM_PROMPT = """You are a bioinformatics assistant with access to BioBTree database.

When the user asks about genes or proteins:
1. Use biobtree_query to look up the information
2. For MULTIPLE genes, use comma-separated format in ONE query

BioBTree query syntax:
- Single: "gene >> ensembl >> uniprot"
- Multiple: "gene1,gene2,gene3 >> ensembl >> uniprot"

Examples:
- "TP53 >> ensembl >> uniprot" (single gene)
- "BRCA1,TP53 >> ensembl >> uniprot" (multiple genes in one query)"""


async def test_query(query_text: str):
    """Test a single query."""
    print(f"\n{'='*70}")
    print(f"Query: {query_text}")
    print('='*70)

    # Setup
    provider = create_llm_provider()
    registry = setup_tools()
    tools = registry.get_tool_definitions()

    # Create messages
    messages = [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=query_text)
    ]

    # Get LLM response
    print("🤖 Calling LLM...")
    response = await provider.chat_with_functions(
        messages=messages,
        tools=tools,
        temperature=0.0,
        max_tokens=1000
    )

    # Check for function call
    if response.function_call:
        print(f"✓ LLM called tool: {response.function_call.name}")
        print(f"  Arguments: {response.function_call.arguments}")

        # Execute tool
        result = await registry.execute_tool(
            response.function_call.name,
            **response.function_call.arguments
        )

        if result.success:
            # Show canonical proteins from metadata
            canonical = result.metadata.get('canonical_proteins', [])
            summary = result.metadata.get('summary', 'Success')

            print(f"✓ Tool execution successful: {summary}")

            if canonical:
                print(f"  Human canonical proteins:")
                for item in canonical:
                    protein = item['protein']
                    print(f"    {item['gene']:8s} -> {protein['identifier']}: {protein['name']}")
            else:
                print(f"  (No human canonical proteins found)")
        else:
            print(f"✗ Tool execution failed: {result.error}")
            return False

        print(f"💰 Tokens used: {response.usage.get('total_tokens', 0)}")
        return True
    else:
        print(f"✗ LLM did not call a tool")
        print(f"  Response: {response.content[:200]}")
        return False


async def main():
    """Run test queries."""
    print("\n" + "="*70)
    print("Multi-Term Query Test")
    print("="*70)

    test_queries = [
        "What is the protein for TP53?",
        "Find proteins for BRCA1 and TP53",
        "Get protein IDs for EGFR, TP53, and BRCA1"
    ]

    results = []
    for query in test_queries:
        try:
            success = await test_query(query)
            results.append((query, success))
            await asyncio.sleep(1)  # Rate limiting
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            results.append((query, False))

    # Summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    passed = sum(1 for _, success in results if success)
    print(f"Passed: {passed}/{len(results)}")
    for query, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {query}")


if __name__ == "__main__":
    asyncio.run(main())

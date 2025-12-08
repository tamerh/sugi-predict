"""
Test LLM provider with function calling.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.llm import create_llm_provider, Message, ToolDefinition


async def test_llm_basic():
    """Test basic LLM chat."""
    print("=" * 60)
    print("TEST 1: Basic Chat (No Function Calling)")
    print("=" * 60)

    # Create provider (will use Gemini from config)
    provider = create_llm_provider()
    print(f"✓ Created provider: {provider.model}\n")

    # Test basic chat
    messages = [
        Message(role="system", content="You are a helpful assistant for bioinformatics questions."),
        Message(role="user", content="What is the TP53 gene? Answer in one sentence.")
    ]

    response = await provider.chat(
        messages=messages,
        temperature=0.0,
        max_tokens=100
    )

    print(f"User: {messages[1].content}")
    print(f"Assistant: {response.content}")
    print(f"\nUsage: {response.usage}")
    print(f"Finish reason: {response.finish_reason}\n")


async def test_llm_function_calling():
    """Test LLM with function calling."""
    print("=" * 60)
    print("TEST 2: Function Calling")
    print("=" * 60)

    # Create provider
    provider = create_llm_provider()

    # Define tools
    tools = [
        ToolDefinition(
            name="biobtree_query",
            description="Query BioBTree database using chain syntax to map biological entities across datasets",
            parameters={
                "type": "object",
                "properties": {
                    "chain_query": {
                        "type": "string",
                        "description": "Chain query like 'EGFR >> hgnc >> uniprot' to traverse relationships"
                    }
                },
                "required": ["chain_query"]
            }
        ),
        ToolDefinition(
            name="bioyoda_search",
            description="Semantic search across PubMed literature and clinical trials",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query text"
                    },
                    "collection": {
                        "type": "string",
                        "enum": ["pubmed", "clinical_trials"],
                        "description": "Collection to search in"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 10)"
                    }
                },
                "required": ["query", "collection"]
            }
        )
    ]

    # Test query that should trigger function call
    messages = [
        Message(
            role="system",
            content="You are a bioinformatics assistant. Use the biobtree_query tool to look up biological entities."
        ),
        Message(
            role="user",
            content="Find proteins for the gene BRCA1 using BioBTree. Use the tool to query BRCA1."
        )
    ]

    response = await provider.chat_with_functions(
        messages=messages,
        tools=tools,
        temperature=0.0,
        max_tokens=1000
    )

    print(f"User: {messages[1].content}")

    if response.function_call:
        print(f"\n✓ LLM called function: {response.function_call.name}")
        print(f"  Arguments: {response.function_call.arguments}")
    else:
        print(f"\nAssistant: {response.content}")

    print(f"\nUsage: {response.usage}")
    print(f"Finish reason: {response.finish_reason}\n")


async def main():
    """Run all tests."""
    try:
        await test_llm_basic()
        print("\n")
        await test_llm_function_calling()

        print("=" * 60)
        print("✓ All LLM tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

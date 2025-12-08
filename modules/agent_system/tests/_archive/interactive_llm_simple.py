"""
Simplified interactive LLM test with proper multi-turn handling.
"""

import asyncio
import sys
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.llm import create_llm_provider, Message, ToolDefinition
from modules.agent_system.tools import setup_tools


SYSTEM_PROMPT = """You are a bioinformatics assistant with access to BioBTree database for mapping biological identifiers.

## IMPORTANT: Answer directly when you know the answer!
For well-known proteins/genes, just answer from your knowledge:
- "What is P04637?" → Answer: "P04637 is the UniProt ID for TP53 (p53), a tumor suppressor protein..."
- "What does BRCA1 do?" → Answer from knowledge about BRCA1's function
- "What is TP53?" → Answer from knowledge about the gene/protein

## When to USE BioBTree tools:
- MAPPING identifiers between databases (gene → protein → drug targets)
- Finding CURRENT/AUTHORITATIVE IDs when unsure
- Discovering RELATIONSHIPS you don't know (what pathways involve X?)
- Handling MULTIPLE entities efficiently in one query
- When you need VERIFIED, up-to-date cross-references

## When NOT to use BioBTree:
- Basic facts about well-known genes/proteins - ANSWER DIRECTLY
- Conceptual questions (what does X do?) - ANSWER FROM KNOWLEDGE
- Literature/research questions - use bioyoda_search instead

## BioBTree Query Syntax:
Chain format: "identifier >> source_dataset >> target_dataset"

Common mappings:
- Gene to protein: "EGFR >> ensembl >> uniprot"
- Protein to gene: "P04637 >> uniprot >> ensembl"
- Gene to drugs: "EGFR >> ensembl >> uniprot >> chembl_target >> chembl_molecule"
- Gene to pathways: "TP53 >> ensembl >> uniprot >> reactome"
- Multiple terms: "BRCA1,TP53,EGFR >> ensembl >> uniprot"

Key datasets: ensembl (genes), uniprot (proteins), chembl_target, chembl_molecule (drugs/compounds), reactome (pathways), go (gene ontology), dbsnp (variants), drugbank

IMPORTANT: For multiple terms, use comma-separated format in ONE query."""


async def simple_query(user_input: str):
    """Execute a simple query with tool calling."""
    print(f"\n📝 Query: {user_input}")
    print("=" * 70)

    # Setup
    provider = create_llm_provider()
    registry = setup_tools()
    tools = registry.get_tool_definitions()

    # Create messages
    messages = [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=user_input)
    ]

    # Get LLM response
    print("🤖 Thinking...")
    response = await provider.chat_with_functions(
        messages=messages,
        tools=tools,
        temperature=0.0,
        max_tokens=1000
    )

    # Check for function call
    if response.function_call:
        print(f"\n🔧 Tool: {response.function_call.name}")
        print(f"   Args: {response.function_call.arguments}")

        # Execute tool
        result = await registry.execute_tool(
            response.function_call.name,
            **response.function_call.arguments
        )

        if result.success:
            print(f"   ✓ Executed successfully")

            # Handle lite mode response (default)
            if isinstance(result.data, dict) and result.data.get('mode') == 'lite':
                mappings = result.data.get('mappings', [])
                stats = result.data.get('stats', {})

                print(f"\n📊 Results (lite mode):")
                print(f"   Mapped: {stats.get('mapped', 0)}/{stats.get('total_terms', 0)} terms")
                print(f"   Total targets: {stats.get('total_targets', 0)}")

                for m in mappings:
                    input_term = m.get('input', 'N/A')
                    targets = m.get('targets', [])
                    target_ids = [t.get('id', 'N/A') for t in targets]
                    print(f"   {input_term} → {', '.join(target_ids)}")

            # Handle full mode response
            elif isinstance(result.data, dict) and 'results' in result.data:
                results_list = result.data['results'].get('results', [])

                print(f"\n📊 Results (full mode): Found {len(results_list)} mapping(s)")

                for i, mapping in enumerate(results_list[:3], 1):  # Show first 3
                    if 'targets' in mapping:
                        for target in mapping['targets'][:2]:  # Show first 2 targets
                            protein_id = target.get('identifier', 'N/A')
                            dataset = target.get('dataset_name', 'unknown')
                            print(f"   {i}. {dataset}: {protein_id}")

                            if 'uniprot' in target:
                                names = target['uniprot'].get('names', [])
                                if names:
                                    print(f"      Name: {names[0]}")
        else:
            print(f"   ✗ Error: {result.error}")

        # Show token usage
        if response.usage:
            print(f"\n💰 Tokens: {response.usage.get('total_tokens', 0)}")
    else:
        # Direct text response
        print(f"\n🤖 Response: {response.content}")
        print(f"\n💰 Tokens: {response.usage.get('total_tokens', 0)}")


async def main():
    """Run example queries."""
    print("=" * 70)
    print("BioYoda Simple Query Test")
    print("=" * 70)

    # Test queries - various scenarios
    queries = [
        # Basic gene to protein
        "What is the protein ID for TP53?",

        # Multiple genes
        "What are the protein IDs for TP53 and BRCA1?",

        # Reverse: protein to gene
        "What gene encodes the protein P04637?",

        # LLM should answer directly (basic knowledge)
        "What is P04637?",

        # Drug discovery chain
        "What drugs target EGFR?",
    ]

    for query in queries:
        try:
            await simple_query(query)
            print("\n")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

        # Wait a bit between queries to avoid rate limits
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())

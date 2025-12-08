"""
Interactive CLI for testing LLM with function calling.
"""

import asyncio
import sys
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.llm import create_llm_provider, Message, ToolDefinition
from modules.agent_system.tools import setup_tools, get_registry


# Define available tools
TOOLS = [
    ToolDefinition(
        name="biobtree_query",
        description="Query BioBTree database using chain syntax to map biological entities across datasets. Use >> to chain relationships.",
        parameters={
            "type": "object",
            "properties": {
                "chain_query": {
                    "type": "string",
                    "description": "Chain query like 'EGFR >> hgnc >> uniprot' or 'BRCA1 >> * >> hgnc' to traverse relationships"
                }
            },
            "required": ["chain_query"]
        }
    ),
    ToolDefinition(
        name="bioyoda_search",
        description="Semantic search across PubMed literature and clinical trials using natural language queries",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query"
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


SYSTEM_PROMPT = """You are a bioinformatics assistant with access to two powerful tools:

1. **biobtree_query**: For deterministic mapping across biological databases
   - Syntax: "term >> dataset >> dataset"
   - For MULTIPLE terms: Use comma-separated "term1,term2 >> dataset >> dataset"
   - Key datasets:
     - ensembl (genes, genomic coordinates)
     - uniprot (proteins, sequences)
     - chembl_target (drug targets)
     - chembl_compound (drugs)
     - dbsnp (genetic variants)
     - reactome (pathways)
   - Examples:
     - Single: "EGFR >> ensembl >> uniprot" (find protein for gene)
     - Multiple: "BRCA1,TP53,EGFR >> ensembl >> uniprot" (find proteins for multiple genes)

2. **bioyoda_search**: For semantic literature/clinical trial search
   - Use for: mechanisms, clinical outcomes, research findings
   - Collections: pubmed, clinical_trials

IMPORTANT INSTRUCTIONS:
- When user asks about MULTIPLE genes/proteins, use comma-separated format in ONE query
- Example: User says "TP53 and BRCA1" → Use "TP53,BRCA1 >> ensembl >> uniprot"
- NEVER write code or pseudocode - only use the provided tools
- BioBTree handles multiple terms efficiently in a single query"""


async def interactive_test():
    """Run interactive LLM test."""
    print("=" * 70)
    print("BioYoda LLM Interactive Test")
    print("=" * 70)

    # Create provider and setup tools
    provider = create_llm_provider()
    registry = setup_tools()

    print(f"\n✓ Using LLM: {provider.model}")
    print(f"✓ Provider: {provider.__class__.__name__}")
    print(f"✓ Tools registered: {len(registry)}\n")
    
    # Initialize conversation
    messages = [Message(role="system", content=SYSTEM_PROMPT)]
    
    print("Available tools:")
    for tool in TOOLS:
        print(f"  - {tool.name}: {tool.description}")
    
    print("\nExamples:")
    print("  'What is the protein ID for TP53 gene?'")
    print("  'Find proteins for BRCA1'")
    print("  'What drugs target EGFR?'")
    print("  'Search PubMed for TP53 cancer mechanisms'")
    print("  'Find clinical trials for immunotherapy'")
    print("\nType 'quit' to exit, 'reset' to clear conversation\n")
    
    conversation_count = 0
    
    while True:
        try:
            # Get user input
            user_input = input("\n📝 You: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
                
            if user_input.lower() == 'reset':
                messages = [Message(role="system", content=SYSTEM_PROMPT)]
                conversation_count = 0
                print("🔄 Conversation reset!")
                continue
            
            # Add user message
            messages.append(Message(role="user", content=user_input))
            conversation_count += 1
            
            print("\n🤖 Assistant: ", end="", flush=True)
            
            # Get LLM response
            response = await provider.chat_with_functions(
                messages=messages,
                tools=TOOLS,
                temperature=0.0,
                max_tokens=2000
            )
            
            # Check if LLM wants to call a function
            if response.function_call:
                print(f"\n\n🔧 Calling tool: {response.function_call.name}")
                print(f"   Arguments: {response.function_call.arguments}")

                # Actually execute the tool!
                result = await registry.execute_tool(
                    response.function_call.name,
                    **response.function_call.arguments
                )

                if result.success:
                    # Format the result nicely
                    if isinstance(result.data, dict):
                        # Simplify the result for display
                        tool_result = json.dumps(result.data, indent=2)[:500] + "..." if len(json.dumps(result.data)) > 500 else json.dumps(result.data, indent=2)
                    else:
                        tool_result = str(result.data)
                    print(f"   ✓ Success: {tool_result[:200]}...")
                else:
                    tool_result = f"Error: {result.error}"
                    print(f"   ✗ {tool_result}")
                
                # Add assistant's function call to conversation (Gemini uses "model" not "assistant")
                messages.append(Message(
                    role="assistant",
                    content=f"I'll call {response.function_call.name} to answer your question."
                ))

                # Add tool result as user message (Gemini only accepts "user" and "model" roles)
                messages.append(Message(
                    role="user",
                    content=f"Tool result from {response.function_call.name}: {tool_result}"
                ))
                
                # Get follow-up response from LLM
                print("\n🤖 Assistant: ", end="", flush=True)
                follow_up = await provider.chat(
                    messages=messages,
                    temperature=0.0,
                    max_tokens=1000
                )
                
                print(follow_up.content)
                messages.append(Message(role="assistant", content=follow_up.content))
                
            else:
                # Regular text response
                print(response.content)
                messages.append(Message(role="assistant", content=response.content))
            
            # Show token usage
            if response.usage:
                print(f"\n💰 Tokens: {response.usage.get('total_tokens', 0)} " +
                      f"(prompt: {response.usage.get('prompt_tokens', 0)}, " +
                      f"completion: {response.usage.get('completion_tokens', 0)})")
        
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Entry point."""
    try:
        asyncio.run(interactive_test())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


if __name__ == "__main__":
    main()

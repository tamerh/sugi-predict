#!/usr/bin/env python3
"""
Interactive CLI for testing BioYoda agent system.

Usage:
    python cli.py                    # Interactive mode with reasoning engine
    python cli.py "your query here"  # Single query mode
    python cli.py --direct "query"   # Bypass reasoning engine (direct LLM+tools)
"""

import asyncio
import sys
import json
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.llm import create_llm_provider, Message
from modules.agent_system.tools import setup_tools
from modules.agent_system.agents import create_reasoning_engine


# Direct mode system prompt (bypasses agent system)
DIRECT_SYSTEM_PROMPT = """You are a bioinformatics assistant with access to BioBTree database for mapping biological identifiers.

## IMPORTANT: Answer directly when you know the answer!
For well-known proteins/genes, just answer from your knowledge:
- "What is P04637?" → Answer: "P04637 is the UniProt ID for TP53 (p53), a tumor suppressor protein..."
- "What does BRCA1 do?" → Answer from knowledge about BRCA1's function

## When to USE BioBTree tools:
- MAPPING identifiers between databases (gene → protein → drug targets)
- Finding CURRENT/AUTHORITATIVE IDs when unsure
- Discovering RELATIONSHIPS (what pathways involve X?)
- Handling MULTIPLE entities efficiently in one query

## BioBTree Query Syntax:
Chain format: "identifier >> source_dataset >> target_dataset"

Common mappings:
- Gene to protein: "EGFR >> ensembl >> uniprot"
- Protein to gene: "P04637 >> uniprot >> ensembl"
- Multiple terms: "BRCA1,TP53,EGFR >> ensembl >> uniprot"

Key datasets: ensembl, uniprot, chembl_target, chembl_molecule, reactome, go, dbsnp"""


class AgentCLI:
    """Interactive CLI for testing the agent system."""

    def __init__(self, use_reasoning_engine: bool = True):
        self.use_reasoning_engine = use_reasoning_engine
        self.engine = None
        self.provider = None
        self.registry = None
        self.tools = None
        self.messages = []

    async def setup(self):
        """Initialize LLM and tools."""
        print("Setting up...")

        if self.use_reasoning_engine:
            # Use full agent system
            self.engine = create_reasoning_engine()
            print(f"Ready! Using Reasoning Engine")
            print(f"Agents: {', '.join(self.engine.agents.keys())}")
            print(f"Tools: {', '.join(self.engine.tool_registry.list_tools())}\n")
        else:
            # Direct mode (bypass agents)
            self.provider = create_llm_provider()
            self.registry = setup_tools()
            self.tools = self.registry.get_tool_definitions()
            self.messages = [Message(role="system", content=DIRECT_SYSTEM_PROMPT)]
            print(f"Ready! Direct mode using {self.provider.model}")
            print(f"Tools: {', '.join(t.name for t in self.tools)}\n")

    async def query(self, user_input: str) -> dict:
        """Execute a single query and return result."""
        if self.use_reasoning_engine:
            return await self._query_with_engine(user_input)
        else:
            return await self._query_direct(user_input)

    async def _query_with_engine(self, user_input: str) -> dict:
        """Query using reasoning engine."""
        result = {
            "query": user_input,
            "mode": "reasoning_engine",
            "agent_used": None,
            "routing": None,
            "tool_calls": [],
            "response": None,
            "error": None
        }

        try:
            response = await self.engine.process(user_input)
            result["response"] = response.answer
            result["agent_used"] = response.agent_used

            if response.routing_decision:
                result["routing"] = {
                    "agent": response.routing_decision.agent_name,
                    "confidence": response.routing_decision.confidence,
                    "reasoning": response.routing_decision.reasoning
                }

            if response.agent_result:
                result["tool_calls"] = response.agent_result.tool_calls
                result["reasoning_chain"] = response.agent_result.reasoning
                result["iterations"] = response.agent_result.iterations

        except Exception as e:
            result["error"] = str(e)

        return result

    async def _query_direct(self, user_input: str) -> dict:
        """Query using direct LLM + tools (bypasses agents)."""
        self.messages.append(Message(role="user", content=user_input))

        result = {
            "query": user_input,
            "mode": "direct",
            "tool_called": None,
            "tool_args": None,
            "tool_result": None,
            "response": None,
            "error": None
        }

        try:
            response = await self.provider.chat_with_functions(
                messages=self.messages,
                tools=self.tools,
                temperature=0.0,
                max_tokens=1000
            )

            if response.function_call:
                result["tool_called"] = response.function_call.name
                result["tool_args"] = response.function_call.arguments

                tool_result = await self.registry.execute_tool(
                    response.function_call.name,
                    **response.function_call.arguments
                )

                if tool_result.success:
                    result["tool_result"] = tool_result.data
                else:
                    result["error"] = tool_result.error
            else:
                result["response"] = response.content

        except Exception as e:
            result["error"] = str(e)

        return result

    def print_result(self, result: dict):
        """Pretty print a query result."""
        print(f"\n{'='*60}")
        print(f"Query: {result['query']}")
        print(f"Mode: {result.get('mode', 'unknown')}")
        print('='*60)

        # Reasoning engine mode
        if result.get("mode") == "reasoning_engine":
            routing = result.get("routing")
            if routing:
                print(f"\n🎯 Routing: {routing['agent']} (confidence: {routing['confidence']:.2f})")
                if routing.get("reasoning"):
                    print(f"   Reason: {routing['reasoning']}")

            if result.get("agent_used"):
                print(f"\n🤖 Agent: {result['agent_used']}")

            if result.get("tool_calls"):
                print(f"\n🔧 Tool Calls:")
                for tc in result["tool_calls"]:
                    print(f"   - {tc['tool']}({tc.get('args', {})})")
                    if tc.get("result"):
                        self._print_tool_result(tc["result"])

            if result.get("reasoning_chain"):
                print(f"\n💭 Reasoning:")
                for step in result["reasoning_chain"][:5]:  # Limit output
                    print(f"   {step[:100]}...")

            if result.get("response"):
                print(f"\n📝 Response:\n{result['response']}")

        # Direct mode
        elif result.get("mode") == "direct":
            if result["tool_called"]:
                print(f"\n🔧 Tool: {result['tool_called']}")
                print(f"   Args: {result['tool_args']}")

                if result["tool_result"]:
                    self._print_tool_result(result["tool_result"])

                if result["error"]:
                    print(f"\n❌ Error: {result['error']}")
            else:
                print(f"\n📝 Response:\n{result['response']}")

        if result.get("error") and result.get("mode") != "direct":
            print(f"\n❌ Error: {result['error']}")

    def _print_tool_result(self, data):
        """Print formatted tool result."""
        if isinstance(data, dict) and data.get('mode') == 'lite':
            stats = data.get('stats', {})
            print(f"\n   📊 Results: {stats.get('mapped', 0)}/{stats.get('total_terms', 0)} mapped")
            shown = 0
            for m in data.get('mappings', []):
                # Skip error mappings
                if m.get('error'):
                    continue
                targets = [t.get('id', '?') for t in m.get('targets', [])][:3]
                if not targets:
                    continue
                # Show: term (resolved_id) → targets
                term = m.get('term') or m.get('input', '?')
                resolved_id = m.get('input', '')
                if term != resolved_id and resolved_id:
                    print(f"      {term} ({resolved_id}) → {', '.join(targets)}")
                else:
                    print(f"      {term} → {', '.join(targets)}")
                shown += 1
                if shown >= 20:  # Limit to 20 for very large results
                    remaining = stats.get('mapped', 0) - shown
                    if remaining > 0:
                        print(f"      ... and {remaining} more")
                    break
        else:
            print(f"\n   📊 Result: {json.dumps(data, indent=2)[:300]}...")

    async def interactive(self):
        """Run interactive session."""
        mode_str = "Reasoning Engine" if self.use_reasoning_engine else "Direct Mode"
        print("\n" + "="*60)
        print(f"BioYoda Agent - Interactive CLI ({mode_str})")
        print("="*60)
        print("\nCommands:")
        print("  Type a question to query the agent")
        print("  'reset' - Clear conversation history")
        print("  'quit'  - Exit")
        print()

        await self.setup()

        while True:
            try:
                user_input = input("\n📝 You: ").strip()

                if not user_input:
                    continue
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("Goodbye!")
                    break
                if user_input.lower() == 'reset':
                    if not self.use_reasoning_engine:
                        self.messages = [Message(role="system", content=DIRECT_SYSTEM_PROMPT)]
                    print("🔄 Conversation reset")
                    continue

                result = await self.query(user_input)
                self.print_result(result)

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")

    async def single_query(self, query: str):
        """Run a single query and exit."""
        await self.setup()
        result = await self.query(query)
        self.print_result(result)


async def main():
    parser = argparse.ArgumentParser(description="BioYoda Agent CLI")
    parser.add_argument("query", nargs="*", help="Query to execute")
    parser.add_argument("--direct", "-d", action="store_true",
                       help="Use direct mode (bypass reasoning engine)")
    args = parser.parse_args()

    cli = AgentCLI(use_reasoning_engine=not args.direct)

    if args.query:
        query = " ".join(args.query)
        await cli.single_query(query)
    else:
        await cli.interactive()


if __name__ == "__main__":
    import sys
    import os

    # Suppress broken pipe errors and excepthook noise
    def _excepthook(type, value, tb):
        if type is BrokenPipeError:
            pass  # Suppress broken pipe
        else:
            sys.__excepthook__(type, value, tb)

    sys.excepthook = _excepthook

    try:
        asyncio.run(main())
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)

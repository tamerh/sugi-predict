#!/usr/bin/env python3
"""
Manual CLI for development with Claude Code acting as the LLM.

This allows testing the full agent pipeline with Claude providing
the LLM responses manually, while collecting fine-tuning data.

Usage:
    python -m tests.manual_cli "What drugs target EGFR?"
    python -m tests.manual_cli --interactive
"""

import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.llm import create_manual_provider
from modules.agent_system.tools import setup_tools
from modules.agent_system.agents import setup_agents, ReasoningEngine


def create_manual_engine(fine_tuning_file: str = None) -> ReasoningEngine:
    """Create reasoning engine with manual LLM provider."""

    # Create manual provider
    llm = create_manual_provider(fine_tuning_file=fine_tuning_file)

    # Setup tools
    tool_registry = setup_tools()

    # Setup agents with manual provider
    agents = setup_agents(llm=llm, tool_registry=tool_registry)

    # Create reasoning engine
    engine = ReasoningEngine(
        llm=llm,
        agents=agents,
        tool_registry=tool_registry
    )

    return engine


async def run_query(engine: ReasoningEngine, query: str):
    """Run a single query through the engine."""

    print(f"\n{'#'*60}")
    print(f"  QUERY: {query}")
    print('#'*60)

    try:
        result = await engine.process(query)

        print(f"\n{'='*60}")
        print("  RESULT")
        print('='*60)
        print(f"Agent used: {result.agent_used}")
        print(f"Answer: {result.answer[:500] if result.answer else 'None'}...")

        if result.agent_result:
            print(f"\nTool calls: {len(result.agent_result.tool_calls)}")
            for tc in result.agent_result.tool_calls:
                tool = tc.get('tool', '?')
                args = tc.get('args', {})
                success = tc.get('success', False)
                print(f"  - {tool}: {args} [{'OK' if success else 'FAIL'}]")

                # Show result preview
                if tc.get('result'):
                    result_str = str(tc['result'])
                    if len(result_str) > 200:
                        result_str = result_str[:200] + "..."
                    print(f"    Result: {result_str}")

        return result

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def interactive_mode(engine: ReasoningEngine):
    """Run interactive mode."""

    print("\n" + "="*60)
    print("  BioYoda Manual CLI - Interactive Mode")
    print("  Claude Code acts as the LLM")
    print("="*60)
    print("\nCommands:")
    print("  Type a query to process")
    print("  'quit' or 'exit' - Exit")
    print("  'agents' - Show available agents")
    print()

    while True:
        try:
            query = input("\n🔬 Query: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query:
            continue

        if query.lower() in ('quit', 'exit', 'q'):
            break

        if query.lower() == 'agents':
            print("Available agents:")
            for name, agent in engine.agents.items():
                print(f"  - {name}: {agent.description}")
            continue

        await run_query(engine, query)


async def main():
    parser = argparse.ArgumentParser(description="BioYoda Manual CLI")
    parser.add_argument("query", nargs="?", help="Query to process")
    parser.add_argument("--interactive", "-i", action="store_true",
                       help="Interactive mode")
    parser.add_argument("--fine-tuning-file", "-f", type=str,
                       default="data/fine_tuning/bioyoda_training.jsonl",
                       help="File to save fine-tuning data")
    args = parser.parse_args()

    # Create engine
    print("Setting up manual engine...")
    engine = create_manual_engine(fine_tuning_file=args.fine_tuning_file)
    print(f"Agents: {list(engine.agents.keys())}")
    print(f"Fine-tuning file: {args.fine_tuning_file}")

    if args.interactive or not args.query:
        await interactive_mode(engine)
    else:
        await run_query(engine, args.query)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")

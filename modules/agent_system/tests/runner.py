#!/usr/bin/env python3
"""
Test runner for BioYoda agent system.

Usage:
    python runner.py                 # Run all tests
    python runner.py --quick         # Run quick tests only
    python runner.py --section X     # Run specific section
    python runner.py --agent         # Use reasoning engine (default: direct mode)
    python runner.py --verbose       # Show detailed output
"""

import asyncio
import sys
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any

import yaml

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.llm import create_llm_provider, Message
from modules.agent_system.tools import setup_tools
from modules.agent_system.agents import create_reasoning_engine


SYSTEM_PROMPT = """You are a bioinformatics assistant with access to BioBTree database for mapping biological identifiers.

## IMPORTANT: Answer directly when you know the answer!
For well-known proteins/genes, just answer from your knowledge.

## When to USE BioBTree tools:
- MAPPING identifiers between databases
- Finding CURRENT/AUTHORITATIVE IDs when unsure
- Handling MULTIPLE entities efficiently

## BioBTree Query Syntax:
"identifier >> source_dataset >> target_dataset"
Examples: "TP53 >> ensembl >> uniprot", "TP53,BRCA1 >> ensembl >> uniprot"
Key datasets: ensembl, uniprot, chembl_target, chembl_molecule, reactome, go, dbsnp"""


class TestRunner:
    """Run tests from YAML file."""

    def __init__(self, verbose: bool = False, use_agent: bool = False):
        self.verbose = verbose
        self.use_agent = use_agent
        self.engine = None
        self.provider = None
        self.registry = None
        self.tools = None
        self.results = []

    async def setup(self):
        """Initialize LLM and tools."""
        if self.verbose:
            print("Setting up...")

        if self.use_agent:
            self.engine = create_reasoning_engine()
            if self.verbose:
                print(f"Using Reasoning Engine with agents: {list(self.engine.agents.keys())}")
        else:
            self.provider = create_llm_provider()
            self.registry = setup_tools()
            self.tools = self.registry.get_tool_definitions()
            if self.verbose:
                print(f"Using direct mode with {self.provider.model}")

    async def run_test(self, test: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single test case."""
        if self.use_agent:
            return await self._run_agent_test(test)
        else:
            return await self._run_direct_test(test)

    async def _run_agent_test(self, test: Dict[str, Any]) -> Dict[str, Any]:
        """Run test using reasoning engine."""
        result = {
            "name": test["name"],
            "query": test["query"],
            "passed": False,
            "agent_used": None,
            "tool_called": None,
            "response": None,
            "errors": []
        }

        try:
            response = await self.engine.process(test["query"])
            result["response"] = response.answer
            result["agent_used"] = response.agent_used

            if response.agent_result and response.agent_result.tool_calls:
                # Get last tool call
                last_call = response.agent_result.tool_calls[-1]
                result["tool_called"] = last_call.get("tool")
                result["tool_result"] = last_call.get("result")

            # Validate expectations
            result["passed"] = self._validate(test, result)

        except Exception as e:
            result["errors"].append(str(e))

        return result

    async def _run_direct_test(self, test: Dict[str, Any]) -> Dict[str, Any]:
        """Run test using direct LLM + tools."""
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=test["query"])
        ]

        result = {
            "name": test["name"],
            "query": test["query"],
            "passed": False,
            "tool_called": None,
            "response": None,
            "errors": []
        }

        try:
            response = await self.provider.chat_with_functions(
                messages=messages,
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
                    result["errors"].append(f"Tool error: {tool_result.error}")
            else:
                result["response"] = response.content

            result["passed"] = self._validate(test, result)

        except Exception as e:
            result["errors"].append(str(e))

        return result

    def _validate(self, test: Dict, result: Dict) -> bool:
        """Validate test result against expectations."""
        errors = result["errors"]

        # Check tool expectation
        expect_tool = test.get("expect_tool")
        if expect_tool is False:
            if result["tool_called"]:
                errors.append(f"Expected direct answer, but tool '{result['tool_called']}' was called")
                return False
        elif expect_tool:
            if result["tool_called"] != expect_tool:
                errors.append(f"Expected tool '{expect_tool}', got '{result['tool_called']}'")
                return False

        # Check agent expectation (for agent mode tests)
        expect_agent = test.get("expect_agent")
        if expect_agent and self.use_agent:
            if result.get("agent_used") != expect_agent:
                errors.append(f"Expected agent '{expect_agent}', got '{result.get('agent_used')}'")
                return False

        # Check expected content
        expect_contains = test.get("expect_contains", [])
        search_text = ""

        if result["response"]:
            search_text = result["response"].lower()
        elif result.get("tool_result"):
            search_text = json.dumps(result["tool_result"]).lower()

        for expected in expect_contains:
            if expected.lower() not in search_text:
                errors.append(f"Expected '{expected}' not found in result")
                return False

        # Check mapped count
        expect_mapped = test.get("expect_mapped")
        if expect_mapped is not None and result.get("tool_result"):
            data = result["tool_result"]
            if isinstance(data, dict) and "stats" in data:
                mapped = data["stats"].get("mapped", 0)
                if mapped < expect_mapped:
                    errors.append(f"Expected at least {expect_mapped} mapped, got {mapped}")
                    return False

        return len(errors) == 0

    def print_result(self, result: Dict, index: int):
        """Print single test result."""
        status = "✓" if result["passed"] else "✗"
        print(f"  {status} {result['name']}")

        if self.verbose or not result["passed"]:
            if result.get("agent_used"):
                print(f"      Agent: {result['agent_used']}")
            if result["tool_called"]:
                print(f"      Tool: {result['tool_called']}")
            if result["errors"]:
                for err in result["errors"]:
                    print(f"      ❌ {err}")

    async def run_section(self, section_name: str, tests: List[Dict], limit: int = None):
        """Run a section of tests."""
        print(f"\n{section_name}:")
        print("-" * 40)

        if limit:
            tests = tests[:limit]

        for i, test in enumerate(tests):
            result = await self.run_test(test)
            self.results.append(result)
            self.print_result(result, i)
            await asyncio.sleep(1)  # Rate limiting

    async def run_all(self, test_file: Path, quick: bool = False, section: str = None):
        """Run all tests from YAML file."""
        await self.setup()

        with open(test_file) as f:
            test_data = yaml.safe_load(f)

        mode = "Agent Mode" if self.use_agent else "Direct Mode"
        print("\n" + "=" * 50)
        print(f"BioYoda Test Runner ({mode})")
        print("=" * 50)

        if section:
            if section in test_data:
                await self.run_section(section, test_data[section])
            else:
                print(f"Section '{section}' not found")
                return
        elif quick:
            if "direct_answers" in test_data:
                await self.run_section("Direct Answers (quick)", test_data["direct_answers"][:2])
            if "biobtree_queries" in test_data:
                await self.run_section("BioBTree Queries (quick)", test_data["biobtree_queries"][:2])
        else:
            for section_name, tests in test_data.items():
                if isinstance(tests, list):
                    await self.run_section(section_name, tests)

        self.print_summary()

    def print_summary(self):
        """Print test summary."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed

        print("\n" + "=" * 50)
        print(f"Results: {passed}/{total} passed ({100*passed//total if total else 0}%)")

        if failed > 0:
            print(f"\nFailed tests:")
            for r in self.results:
                if not r["passed"]:
                    print(f"  - {r['name']}")
                    for err in r["errors"]:
                        print(f"    {err}")

        print("=" * 50)


async def main():
    parser = argparse.ArgumentParser(description="BioYoda Agent Test Runner")
    parser.add_argument("--quick", action="store_true", help="Run quick subset of tests")
    parser.add_argument("--section", type=str, help="Run specific section")
    parser.add_argument("--test", "-t", type=str, help="Run single test by name")
    parser.add_argument("--list", "-l", action="store_true", help="List all test names")
    parser.add_argument("--agent", "-a", action="store_true", help="Use reasoning engine instead of direct mode")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    test_file = Path(__file__).parent / "test_cases.yaml"

    if not test_file.exists():
        print(f"Test file not found: {test_file}")
        sys.exit(1)

    with open(test_file) as f:
        test_data = yaml.safe_load(f)

    if args.list:
        print("Available tests:")
        for section, tests in test_data.items():
            if isinstance(tests, list):
                print(f"\n  [{section}]")
                for t in tests:
                    print(f"    - {t['name']}")
        return

    if args.test:
        runner = TestRunner(verbose=True, use_agent=args.agent)
        await runner.setup()

        found = None
        for section, tests in test_data.items():
            if isinstance(tests, list):
                for t in tests:
                    if t["name"].lower() == args.test.lower() or args.test.lower() in t["name"].lower():
                        found = t
                        break
            if found:
                break

        if found:
            print(f"\nRunning: {found['name']}")
            print(f"Query: {found['query']}")
            print("-" * 40)
            result = await runner.run_test(found)
            runner.results.append(result)
            runner.print_result(result, 0)
            runner.print_summary()
        else:
            print(f"Test not found: {args.test}")
            print("Use --list to see available tests")
        return

    runner = TestRunner(verbose=args.verbose, use_agent=args.agent)
    await runner.run_all(test_file, quick=args.quick, section=args.section)


if __name__ == "__main__":
    import os

    # Suppress broken pipe errors and excepthook noise
    def _excepthook(type, value, tb):
        if type is BrokenPipeError:
            pass
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

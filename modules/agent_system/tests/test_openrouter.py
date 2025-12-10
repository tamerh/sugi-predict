#!/usr/bin/env python3
"""Test OpenRouter provider integration."""

import asyncio
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.llm import create_llm_provider
from modules.agent_system.llm.openrouter_provider import OpenRouterProvider
from modules.agent_system.core.config import get_config, reload_config


def get_openrouter_provider():
    """Get OpenRouter provider from config."""
    reload_config()  # Reload to pick up any changes
    return create_llm_provider("openrouter")


async def test_basic_chat():
    """Test basic chat without function calling."""
    try:
        provider = get_openrouter_provider()
    except ValueError as e:
        print(f"ERROR: {e}")
        return False

    print(f"\nTesting OpenRouter with model: {provider.model}")
    print("=" * 60)

    from modules.agent_system.llm.base import Message

    messages = [
        Message(role="system", content="You are a helpful bioinformatics assistant. Be concise."),
        Message(role="user", content="What is EGFR and why is it important in cancer research? Answer in 2 sentences.")
    ]

    print("\nSending test query...")
    response = await provider.chat(messages, max_tokens=200)

    print(f"\nResponse: {response.content}")
    print(f"Model used: {response.model}")
    print(f"Tokens: {response.usage}")

    return True


async def test_function_calling():
    """Test function calling capability."""
    try:
        provider = get_openrouter_provider()
    except ValueError as e:
        print(f"ERROR: {e}")
        return False

    print(f"\n\nTesting Function Calling with: {provider.model}")
    print("=" * 60)

    from modules.agent_system.llm.base import Message, ToolDefinition

    # Define a simple tool
    tool = ToolDefinition(
        name="biobtree_query",
        description="Query BioBTree database for biological identifier mappings",
        parameters={
            "type": "object",
            "properties": {
                "chain_query": {
                    "type": "string",
                    "description": "The mapping query chain (e.g., 'EGFR >> ensembl >> uniprot')"
                },
                "mode": {
                    "type": "string",
                    "enum": ["lite", "full"],
                    "description": "Response mode"
                }
            },
            "required": ["chain_query"]
        }
    )

    messages = [
        Message(role="system", content="You are a bioinformatics assistant. Use the biobtree_query tool to find drug information."),
        Message(role="user", content="Find the drugs that target EGFR protein")
    ]

    print("\nSending query with function calling...")
    response = await provider.chat_with_functions(messages, tools=[tool])

    print(f"\nContent: {response.content}")
    print(f"Function call: {response.function_call}")
    print(f"Model: {response.model}")

    if response.function_call:
        print(f"\nTool called: {response.function_call.name}")
        print(f"Arguments: {response.function_call.arguments}")
        return True
    else:
        print("\nNote: Model did not call function (may still be correct behavior)")
        return True


async def test_multiple_models():
    """Test different models available via OpenRouter."""
    # Get API key from config
    config = get_config()
    provider_config = config.llm.providers.get("openrouter")
    if not provider_config or not provider_config.api_key:
        print("Skipping multi-model test (no API key in config)")
        return False

    api_key = provider_config.api_key

    models = [
        "meta-llama/llama-3.3-70b-instruct",
        "meta-llama/llama-3.1-8b-instruct",
        "mistralai/mistral-small-24b-instruct-2501",
    ]

    print("\n\nTesting Multiple Models")
    print("=" * 60)

    from modules.agent_system.llm.base import Message

    messages = [
        Message(role="user", content="What does TP53 do? One sentence only.")
    ]

    for model in models:
        try:
            print(f"\n{model}:")
            provider = OpenRouterProvider(
                model=model,
                api_key=api_key,
                app_name="BioYoda-Test"
            )
            response = await provider.chat(messages, max_tokens=100)
            print(f"  {response.content[:150]}...")
            print(f"  Tokens: {response.usage.get('total_tokens', 'N/A')}")
        except Exception as e:
            print(f"  Error: {e}")

    return True


async def main():
    print("OpenRouter Provider Test")
    print("=" * 60)

    # Run tests
    success = await test_basic_chat()
    if success:
        await test_function_calling()
        await test_multiple_models()

    print("\n" + "=" * 60)
    print("Tests completed!")


if __name__ == "__main__":
    asyncio.run(main())

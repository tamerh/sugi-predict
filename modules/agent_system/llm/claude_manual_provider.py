"""Manual LLM provider for development with Claude Code.

This provider prints prompts and waits for manual input, allowing Claude Code
to act as the LLM during development. This enables:
1. Testing agent logic without API costs
2. Collecting fine-tuning data
3. Interactive debugging
"""

import json
import sys
from typing import Any, AsyncIterator, Dict, List, Optional
from datetime import datetime
from pathlib import Path

from .base import LLMProvider, LLMResponse, Message, FunctionCall, ToolDefinition


class ClaudeManualProvider(LLMProvider):
    """
    Manual LLM provider where Claude Code acts as the LLM.

    Prints prompts to stdout and reads responses from stdin,
    allowing interactive development and fine-tuning data collection.
    """

    def __init__(
        self,
        model: str = "claude-manual",
        api_key: str = "manual",
        fine_tuning_file: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize manual provider.

        Args:
            model: Model identifier (for logging)
            api_key: Not used, but required by base class
            fine_tuning_file: Path to save fine-tuning data (JSONL format)
            **kwargs: Additional config
        """
        super().__init__(model, api_key, **kwargs)
        self.fine_tuning_file = fine_tuning_file
        self.conversation_log = []

        # Create fine-tuning file if specified
        if fine_tuning_file:
            Path(fine_tuning_file).parent.mkdir(parents=True, exist_ok=True)

    def _print_separator(self, title: str):
        """Print a visual separator."""
        print(f"\n{'='*60}")
        print(f"  {title}")
        print('='*60)

    def _print_messages(self, messages: List[Message]):
        """Print messages for context."""
        for msg in messages:
            role_icon = {
                "system": "⚙️ ",
                "user": "👤",
                "assistant": "🤖",
                "tool": "🔧"
            }.get(msg.role, "  ")

            # Truncate long messages
            content = msg.content
            if len(content) > 500:
                content = content[:500] + "..."

            print(f"\n{role_icon} [{msg.role.upper()}]:")
            print(f"   {content}")

    def _print_tools(self, tools: List[ToolDefinition]):
        """Print available tools."""
        print("\n📦 Available Tools:")
        for tool in tools:
            print(f"   - {tool.name}: {tool.description[:60]}...")

    def _save_fine_tuning_example(
        self,
        messages: List[Message],
        response: LLMResponse
    ):
        """Save conversation as fine-tuning example."""
        if not self.fine_tuning_file:
            return

        # Build fine-tuning format
        ft_messages = []

        for msg in messages:
            ft_msg = {"role": msg.role, "content": msg.content}
            ft_messages.append(ft_msg)

        # Add assistant response
        if response.function_call:
            ft_messages.append({
                "role": "assistant",
                "content": response.content or "",
                "function_call": {
                    "name": response.function_call.name,
                    "arguments": json.dumps(response.function_call.arguments)
                }
            })
        else:
            ft_messages.append({
                "role": "assistant",
                "content": response.content
            })

        # Append to file
        example = {"messages": ft_messages, "timestamp": datetime.now().isoformat()}

        with open(self.fine_tuning_file, "a") as f:
            f.write(json.dumps(example) + "\n")

        print(f"\n💾 Saved to fine-tuning data: {self.fine_tuning_file}")

    async def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> LLMResponse:
        """Chat completion - manual input mode."""

        self._print_separator("CHAT REQUEST (no tools)")
        self._print_messages(messages)

        print("\n" + "-"*40)
        print("Enter your response (text only):")
        print("-"*40)

        # Read response
        try:
            response_text = input("> ").strip()
        except EOFError:
            response_text = ""

        response = LLMResponse(
            content=response_text,
            finish_reason="stop",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            model=self.model
        )

        return response

    async def chat_with_functions(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tool_choice: str = "auto",
        **kwargs
    ) -> LLMResponse:
        """Chat completion with function calling - manual input mode."""

        self._print_separator("FUNCTION CALL REQUEST")
        self._print_messages(messages)
        self._print_tools(tools)

        print("\n" + "-"*40)
        print("Enter response as JSON:")
        print('  Text only: {"content": "your response"}')
        print('  Tool call: {"tool": "tool_name", "args": {...}}')
        print('  Or type "skip" to return empty response')
        print("-"*40)

        # Read response
        try:
            response_input = input("> ").strip()
        except EOFError:
            response_input = "skip"

        # Parse response
        content = ""
        function_call = None

        if response_input.lower() == "skip":
            content = ""
        elif response_input.startswith("{"):
            try:
                data = json.loads(response_input)

                if "tool" in data:
                    # Tool call response
                    function_call = FunctionCall(
                        name=data["tool"],
                        arguments=data.get("args", {})
                    )
                    content = data.get("content", "")
                else:
                    # Text response
                    content = data.get("content", response_input)

            except json.JSONDecodeError:
                print("⚠️  Invalid JSON, treating as text response")
                content = response_input
        else:
            content = response_input

        response = LLMResponse(
            content=content,
            function_call=function_call,
            finish_reason="function_call" if function_call else "stop",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            model=self.model
        )

        # Save for fine-tuning
        self._save_fine_tuning_example(messages, response)

        return response

    async def stream(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream is not supported in manual mode - falls back to chat."""
        response = await self.chat(messages, temperature, **kwargs)
        yield response.content

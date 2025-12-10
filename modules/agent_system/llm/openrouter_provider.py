"""OpenRouter LLM provider with function calling support.

OpenRouter provides unified access to multiple LLM providers:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude 3)
- Google (Gemini)
- Mistral
- Groq (Llama, Mixtral)
- And many more

Uses OpenAI-compatible API format.
"""

import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional
from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse, Message, FunctionCall, ToolDefinition
from ..core.metrics import get_metrics


# Popular models available on OpenRouter (updated Dec 2024)
OPENROUTER_MODELS = {
    # OpenAI
    "openai/gpt-4o": "GPT-4o - Fast, capable",
    "openai/gpt-4o-mini": "GPT-4o mini - Fast, cheap",
    "openai/gpt-4-turbo": "GPT-4 Turbo - Powerful",

    # Anthropic
    "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet - Balanced",
    "anthropic/claude-3-opus": "Claude 3 Opus - Most capable",
    "anthropic/claude-3-haiku": "Claude 3 Haiku - Fast, cheap",

    # Google
    "google/gemini-2.0-flash-exp:free": "Gemini 2.0 Flash - Free tier",
    "google/gemini-pro-1.5": "Gemini Pro 1.5 - Long context",

    # Mistral
    "mistralai/mistral-large-2411": "Mistral Large - Powerful",
    "mistralai/mistral-small-2409": "Mistral Small - Fast",

    # Meta Llama (recommended)
    "meta-llama/llama-3.3-70b-instruct": "Llama 3.3 70B - Best open model",
    "meta-llama/llama-3.1-70b-instruct": "Llama 3.1 70B - Capable",
    "meta-llama/llama-3.1-8b-instruct": "Llama 3.1 8B - Fast, light",

    # DeepSeek
    "deepseek/deepseek-chat": "DeepSeek Chat",
    "deepseek/deepseek-coder": "DeepSeek Coder",

    # Qwen
    "qwen/qwen-2.5-72b-instruct": "Qwen 2.5 72B - Strong multilingual",
}


class OpenRouterProvider(LLMProvider):
    """
    OpenRouter LLM provider.

    Provides unified access to 100+ models from various providers
    through a single API endpoint.
    """

    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        model: str,
        api_key: str,
        app_name: str = "BioYoda",
        site_url: str = "",
        **kwargs
    ):
        """
        Initialize OpenRouter provider.

        Args:
            model: Model identifier (e.g., "openai/gpt-4o", "anthropic/claude-3-sonnet")
            api_key: OpenRouter API key
            app_name: Application name for tracking (shown in OpenRouter dashboard)
            site_url: Optional site URL for HTTP-Referer header
            **kwargs: Additional configuration (max_tokens, temperature, timeout)
        """
        super().__init__(model, api_key, **kwargs)

        self.app_name = app_name
        self.site_url = site_url
        self.max_tokens = kwargs.get('max_tokens', 4096)
        self.default_temperature = kwargs.get('temperature', 0.0)
        self.timeout = kwargs.get('timeout', 60)

        # Initialize async OpenAI client with OpenRouter base URL
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.OPENROUTER_BASE_URL,
            timeout=self.timeout,
            default_headers={
                "HTTP-Referer": site_url or "https://bioyoda.dev",
                "X-Title": app_name,
            }
        )

    def _messages_to_openai_format(self, messages: List[Message]) -> List[Dict]:
        """Convert messages to OpenAI format."""
        openai_messages = []

        for msg in messages:
            message_dict = {
                "role": msg.role,
                "content": msg.content
            }

            # Handle assistant messages with tool calls
            if msg.role == "assistant" and msg.tool_calls:
                message_dict["tool_calls"] = msg.tool_calls

            # Handle tool response messages
            if msg.role == "tool":
                if msg.tool_call_id:
                    message_dict["tool_call_id"] = msg.tool_call_id
                elif msg.name:
                    message_dict["tool_call_id"] = msg.name
                if msg.name:
                    message_dict["name"] = msg.name

            openai_messages.append(message_dict)

        return openai_messages

    def _tools_to_openai_format(self, tools: List[ToolDefinition]) -> List[Dict]:
        """Convert tool definitions to OpenAI function format."""
        openai_tools = []

        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })

        return openai_tools

    async def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> LLMResponse:
        """Chat completion without function calling."""

        openai_messages = self._messages_to_openai_format(messages)

        start_time = time.perf_counter()
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        latency_ms = (time.perf_counter() - start_time) * 1000

        choice = response.choices[0]
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        # Record metrics
        get_metrics().record_llm_call(
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms
        )

        return LLMResponse(
            content=choice.message.content or "",
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": response.usage.total_tokens if response.usage else 0
            },
            model=response.model
        )

    async def chat_with_functions(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tool_choice: str = "auto",
        **kwargs
    ) -> LLMResponse:
        """Chat completion with function calling support."""

        openai_messages = self._messages_to_openai_format(messages)
        openai_tools = self._tools_to_openai_format(tools)

        start_time = time.perf_counter()
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            tools=openai_tools if openai_tools else None,
            tool_choice=tool_choice if openai_tools else None,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        latency_ms = (time.perf_counter() - start_time) * 1000

        choice = response.choices[0]
        content = choice.message.content or ""
        function_call = None
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        # Record metrics
        get_metrics().record_llm_call(
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms
        )

        # Check for tool calls
        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]  # Take first tool call
            try:
                arguments = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                arguments = {}

            function_call = FunctionCall(
                name=tc.function.name,
                arguments=arguments,
                id=tc.id  # Include tool call ID for proper message threading
            )

        return LLMResponse(
            content=content,
            function_call=function_call,
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": response.usage.total_tokens if response.usage else 0
            },
            model=response.model
        )

    async def stream(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream chat completion."""

        openai_messages = self._messages_to_openai_format(messages)

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            temperature=temperature,
            stream=True,
            **kwargs
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    @classmethod
    def list_models(cls) -> Dict[str, str]:
        """Return dictionary of popular available models."""
        return OPENROUTER_MODELS.copy()

    @classmethod
    def get_model_info(cls, model: str) -> Optional[str]:
        """Get description for a model."""
        return OPENROUTER_MODELS.get(model)

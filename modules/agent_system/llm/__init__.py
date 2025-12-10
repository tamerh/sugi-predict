"""LLM provider framework for multi-provider support."""

from .base import LLMProvider, Message, FunctionCall, LLMResponse, ToolDefinition
from .factory import create_llm_provider, get_default_provider, create_manual_provider
from .claude_manual_provider import ClaudeManualProvider
from .openrouter_provider import OpenRouterProvider

__all__ = [
    "LLMProvider",
    "Message",
    "FunctionCall",
    "LLMResponse",
    "ToolDefinition",
    "create_llm_provider",
    "get_default_provider",
    "create_manual_provider",
    "ClaudeManualProvider",
    "OpenRouterProvider",
]

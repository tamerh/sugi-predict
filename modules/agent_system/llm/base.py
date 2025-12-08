"""Base LLM provider interface with function calling support."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from pydantic import BaseModel


class Message(BaseModel):
    """Chat message."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    name: Optional[str] = None  # For tool messages


class ToolDefinition(BaseModel):
    """Function/tool definition for LLM function calling."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON schema


class FunctionCall(BaseModel):
    """Function call from LLM."""
    name: str
    arguments: Dict[str, Any]


class LLMResponse(BaseModel):
    """LLM response with optional function call."""
    content: str
    function_call: Optional[FunctionCall] = None
    finish_reason: Optional[str] = None  # "stop", "length", "function_call", "tool_calls"
    usage: Dict[str, int] = {}  # token usage stats
    model: str = ""


class LLMProvider(ABC):
    """Base class for LLM providers with function calling support."""

    def __init__(self, model: str, api_key: str, **kwargs):
        """
        Initialize LLM provider.

        Args:
            model: Model identifier
            api_key: API key for provider
            **kwargs: Additional provider-specific configuration
        """
        self.model = model
        self.api_key = api_key
        self.config = kwargs

    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> LLMResponse:
        """
        Chat completion without function calling.

        Args:
            messages: List of messages in conversation
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            LLM response
        """
        pass

    @abstractmethod
    async def chat_with_functions(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tool_choice: str = "auto",
        **kwargs
    ) -> LLMResponse:
        """
        Chat completion with function calling support.

        Args:
            messages: List of messages in conversation
            tools: List of available tool definitions
            temperature: Sampling temperature (0-1, typically 0 for agents)
            max_tokens: Maximum tokens to generate
            tool_choice: "auto", "none", or specific tool name
            **kwargs: Provider-specific parameters

        Returns:
            LLM response with optional function call
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Stream chat completion.

        Args:
            messages: List of messages in conversation
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters

        Yields:
            Chunks of generated text
        """
        pass

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """
        Simple text generation (convenience method).

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            Generated text
        """
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))

        response = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        return response.content

    def validate_tool_definition(self, tool: ToolDefinition) -> bool:
        """
        Validate tool definition structure.

        Args:
            tool: Tool definition to validate

        Returns:
            True if valid
        """
        # Check required fields
        if not tool.name or not tool.description:
            return False

        # Check parameters schema
        if "type" not in tool.parameters:
            return False

        return True

"""Base tool abstraction for agent system."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel

from ..llm.base import ToolDefinition


class ToolResult(BaseModel):
    """Result from tool execution."""
    success: bool
    data: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


class Tool(ABC):
    """Base class for agent tools."""

    def __init__(self, name: str, description: str):
        """
        Initialize tool.

        Args:
            name: Tool name (used in function calling)
            description: Tool description for LLM
        """
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Tool execution result
        """
        pass

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """
        Get tool definition for LLM function calling.

        Returns:
            Tool definition with JSON schema
        """
        pass

    def validate_parameters(self, **kwargs) -> bool:
        """
        Validate tool parameters.

        Args:
            **kwargs: Parameters to validate

        Returns:
            True if valid
        """
        # Override in subclasses for custom validation
        return True

    async def __call__(self, **kwargs) -> ToolResult:
        """
        Convenience method to execute tool.

        Args:
            **kwargs: Tool parameters

        Returns:
            Tool result
        """
        return await self.execute(**kwargs)

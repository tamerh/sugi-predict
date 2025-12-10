"""Tool registry for managing available tools."""

import time
from typing import Dict, List, Optional

from .base import Tool, ToolResult
from ..llm.base import ToolDefinition
from ..core.metrics import get_metrics


class ToolRegistry:
    """Registry for managing and executing tools."""

    def __init__(self):
        """Initialize tool registry."""
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool to register
        """
        self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> None:
        """
        Unregister a tool.

        Args:
            tool_name: Name of tool to unregister
        """
        if tool_name in self._tools:
            del self._tools[tool_name]

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """
        Get tool by name.

        Args:
            tool_name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(tool_name)

    def get_all_tools(self) -> List[Tool]:
        """
        Get all registered tools.

        Returns:
            List of tools
        """
        return list(self._tools.values())

    def get_tool_definitions(self) -> List[ToolDefinition]:
        """
        Get tool definitions for LLM function calling.

        Returns:
            List of tool definitions
        """
        return [tool.get_definition() for tool in self._tools.values()]

    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of tool to execute
            **kwargs: Tool parameters

        Returns:
            Tool execution result
        """
        tool = self.get_tool(tool_name)

        if not tool:
            return ToolResult(
                success=False,
                data=None,
                error=f"Tool '{tool_name}' not found in registry"
            )

        # Validate parameters
        if not tool.validate_parameters(**kwargs):
            return ToolResult(
                success=False,
                data=None,
                error=f"Invalid parameters for tool '{tool_name}'"
            )

        # Execute tool with timing
        start_time = time.perf_counter()
        result = await tool.execute(**kwargs)
        latency_ms = (time.perf_counter() - start_time) * 1000

        # Record metrics
        get_metrics().record_tool_call(
            tool_name=tool_name,
            latency_ms=latency_ms,
            success=result.success
        )

        return result

    def list_tools(self) -> List[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def __len__(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)

    def __contains__(self, tool_name: str) -> bool:
        """Check if tool is registered."""
        return tool_name in self._tools


# Global tool registry instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """
    Get global tool registry instance.

    Returns:
        Tool registry singleton
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_registry() -> None:
    """Reset global tool registry."""
    global _registry
    _registry = ToolRegistry()

"""Factory functions for creating and setting up tools."""

from typing import List

from .base import Tool
from .biobtree_tool import BioBTreeQueryTool, BioBTreeSearchTool
from .registry import ToolRegistry, get_registry
from ..core.config import get_config
from ..integrations.biobtree_client import create_biobtree_client


def create_default_tools() -> List[Tool]:
    """
    Create default set of tools for agent system.

    Returns:
        List of initialized tools
    """
    config = get_config()

    # Create shared BioBTree client (persistent connection for efficiency)
    biobtree_client = create_biobtree_client(config.integrations.biobtree)

    # Create tools sharing the same client connection
    tools = [
        BioBTreeQueryTool(biobtree_client),
        BioBTreeSearchTool(biobtree_client),
    ]

    return tools


def setup_tools(registry: ToolRegistry = None) -> ToolRegistry:
    """
    Setup and register default tools.

    Args:
        registry: Optional tool registry. If None, uses global registry.

    Returns:
        Tool registry with registered tools
    """
    if registry is None:
        registry = get_registry()
    
    # Create and register default tools
    tools = create_default_tools()
    
    for tool in tools:
        registry.register(tool)
    
    return registry

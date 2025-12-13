"""Factory functions for creating and setting up tools."""

from typing import List

from .base import Tool
from .biobtree_tool import BioBTreeQueryTool, BioBTreeSearchTool
from .disease_drug_tool import DiseaseDrugDiscoveryTool
from .protein_similarity_tool import ProteinSimilarityTool
from .compound_similarity_tool import CompoundSimilarityTool
from .registry import ToolRegistry, get_registry
from ..core.config import get_config
from ..integrations.biobtree_client import create_biobtree_client
from ..integrations.qdrant_client import create_qdrant_client


def create_default_tools() -> List[Tool]:
    """
    Create default set of tools for agent system.

    Returns:
        List of initialized tools
    """
    config = get_config()

    # Create shared BioBTree client (persistent connection for efficiency)
    biobtree_client = create_biobtree_client(config.integrations.biobtree)

    # Create shared Qdrant client for vector search
    qdrant_client = create_qdrant_client(config.integrations.qdrant)

    # Create tools sharing the same client connections
    tools = [
        BioBTreeQueryTool(biobtree_client),
        BioBTreeSearchTool(biobtree_client),
        DiseaseDrugDiscoveryTool(biobtree_client),  # Specialized disease-drug tool
        ProteinSimilarityTool(qdrant_client, biobtree_client),  # ESM-2 protein similarity
        CompoundSimilarityTool(qdrant_client, biobtree_client),  # Morgan fingerprint similarity
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

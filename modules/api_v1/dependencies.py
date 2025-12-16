"""
Dependency injection for FastAPI.

Provides singleton instances of:
- BioBTree client
- Qdrant client
- Tool registry
- LLM provider
- Reasoning engine with agents
"""

import logging
from typing import Optional

from fastapi import Depends

# Agent system imports
from ..agent_system.core.config import get_config
from ..agent_system.integrations.biobtree_client import BioBTreeClient, create_biobtree_client
from ..agent_system.integrations.qdrant_client import BioYodaQdrantClient, create_qdrant_client
from ..agent_system.tools.registry import ToolRegistry
from ..agent_system.tools.factory import setup_tools
from ..agent_system.llm.base import LLMProvider
from ..agent_system.llm.factory import create_llm_provider
from ..agent_system.agents.reasoning_engine import ReasoningEngine
from ..agent_system.agents.factory import setup_agents

logger = logging.getLogger(__name__)

# Global singleton instances
_biobtree_client: Optional[BioBTreeClient] = None
_qdrant_client: Optional[BioYodaQdrantClient] = None
_tool_registry: Optional[ToolRegistry] = None
_llm_provider: Optional[LLMProvider] = None
_reasoning_engine: Optional[ReasoningEngine] = None


async def init_clients():
    """
    Initialize all clients and the agent system.
    Called during FastAPI lifespan startup.
    """
    global _biobtree_client, _qdrant_client, _tool_registry, _llm_provider, _reasoning_engine

    logger.info("Initializing clients and agent system...")

    # Load configuration
    config = get_config()
    logger.info(f"Configuration loaded")

    # Initialize BioBTree client
    logger.info("Connecting to BioBTree...")
    _biobtree_client = create_biobtree_client(config.integrations.biobtree)
    biobtree_cfg = config.integrations.biobtree
    if biobtree_cfg.protocol == "grpc":
        logger.info(f"BioBTree connected via gRPC at {biobtree_cfg.grpc.host}:{biobtree_cfg.grpc.port}")
    else:
        logger.info(f"BioBTree connected via REST at {biobtree_cfg.rest.host}:{biobtree_cfg.rest.port}")

    # Initialize Qdrant client
    logger.info("Connecting to Qdrant...")
    _qdrant_client = create_qdrant_client(config.integrations.qdrant)
    qdrant_cfg = config.integrations.qdrant
    logger.info(f"Qdrant connected at {qdrant_cfg.host}:{qdrant_cfg.port}")

    # Initialize tool registry with tools
    logger.info("Setting up tools...")
    _tool_registry = setup_tools()
    tool_names = _tool_registry.list_tools()
    logger.info(f"Tools registered: {tool_names}")

    # Initialize LLM provider
    logger.info("Initializing LLM provider...")
    _llm_provider = create_llm_provider()
    llm_cfg = config.llm
    provider_name = llm_cfg.default_provider or "default"
    provider_cfg = llm_cfg.providers.get(provider_name, {})
    model_name = provider_cfg.model if hasattr(provider_cfg, 'model') else "unknown"
    logger.info(f"LLM provider: {provider_name} ({model_name})")

    # Initialize agents and reasoning engine
    logger.info("Setting up agents and reasoning engine...")
    agents = setup_agents(_llm_provider, _tool_registry)
    _reasoning_engine = ReasoningEngine(
        llm=_llm_provider,
        tool_registry=_tool_registry,
        agents=agents
    )
    agent_names = list(agents.keys())
    logger.info(f"Agents registered: {agent_names}")

    logger.info("All clients and agents initialized successfully")


async def close_clients():
    """
    Close all clients gracefully.
    Called during FastAPI lifespan shutdown.
    """
    global _biobtree_client, _qdrant_client

    logger.info("Closing clients...")

    if _biobtree_client:
        # BioBTree client cleanup if needed
        pass

    if _qdrant_client:
        # Qdrant client cleanup if needed
        pass

    logger.info("All clients closed")


# Dependency functions for FastAPI injection

def get_biobtree_client() -> BioBTreeClient:
    """Get BioBTree client instance."""
    if _biobtree_client is None:
        raise RuntimeError("BioBTree client not initialized")
    return _biobtree_client


def get_qdrant_client() -> BioYodaQdrantClient:
    """Get Qdrant client instance."""
    if _qdrant_client is None:
        raise RuntimeError("Qdrant client not initialized")
    return _qdrant_client


def get_tool_registry() -> ToolRegistry:
    """Get tool registry instance."""
    if _tool_registry is None:
        raise RuntimeError("Tool registry not initialized")
    return _tool_registry


def get_llm_provider() -> LLMProvider:
    """Get LLM provider instance."""
    if _llm_provider is None:
        raise RuntimeError("LLM provider not initialized")
    return _llm_provider


def get_reasoning_engine() -> ReasoningEngine:
    """Get reasoning engine instance."""
    if _reasoning_engine is None:
        raise RuntimeError("Reasoning engine not initialized")
    return _reasoning_engine


# Dependency aliases for cleaner route signatures
BioBTreeDep = Depends(get_biobtree_client)
QdrantDep = Depends(get_qdrant_client)
ToolRegistryDep = Depends(get_tool_registry)
LLMDep = Depends(get_llm_provider)
ReasoningEngineDep = Depends(get_reasoning_engine)

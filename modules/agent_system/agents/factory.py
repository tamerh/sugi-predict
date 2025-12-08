"""Factory functions for creating agents and reasoning engine."""

from typing import Dict, Optional

from .base import Agent
from .id_mapping import IDMappingAgent
from .drug_discovery import DrugDiscoveryAgent
from .reasoning_engine import ReasoningEngine
from ..llm.base import LLMProvider
from ..llm.factory import create_llm_provider
from ..tools.registry import ToolRegistry
from ..tools.factory import setup_tools


def create_agent(
    agent_name: str,
    llm: LLMProvider,
    tool_registry: ToolRegistry,
    system_prompt: Optional[str] = None
) -> Agent:
    """
    Create an agent by name.

    Args:
        agent_name: Name of agent to create
        llm: LLM provider
        tool_registry: Tool registry
        system_prompt: Optional custom system prompt

    Returns:
        Agent instance

    Raises:
        ValueError: If agent name is unknown
    """
    agents = {
        "id_mapping": IDMappingAgent,
        "drug_discovery": DrugDiscoveryAgent,
    }

    if agent_name not in agents:
        available = ", ".join(agents.keys())
        raise ValueError(f"Unknown agent: {agent_name}. Available: {available}")

    return agents[agent_name](
        llm=llm,
        tool_registry=tool_registry,
        system_prompt=system_prompt
    )


def setup_agents(
    llm: LLMProvider,
    tool_registry: ToolRegistry
) -> Dict[str, Agent]:
    """
    Create all available agents.

    Args:
        llm: LLM provider
        tool_registry: Tool registry

    Returns:
        Dictionary of agent name to agent instance
    """
    return {
        "id_mapping": IDMappingAgent(llm=llm, tool_registry=tool_registry),
        "drug_discovery": DrugDiscoveryAgent(llm=llm, tool_registry=tool_registry),
    }


def create_reasoning_engine(
    llm: Optional[LLMProvider] = None,
    tool_registry: Optional[ToolRegistry] = None
) -> ReasoningEngine:
    """
    Create a fully configured reasoning engine with all agents.

    Args:
        llm: Optional LLM provider (creates default if not provided)
        tool_registry: Optional tool registry (creates default if not provided)

    Returns:
        Configured ReasoningEngine
    """
    # Create defaults if not provided
    if llm is None:
        llm = create_llm_provider()

    if tool_registry is None:
        tool_registry = setup_tools()

    # Create all agents
    agents = setup_agents(llm, tool_registry)

    # Create reasoning engine
    engine = ReasoningEngine(
        llm=llm,
        tool_registry=tool_registry,
        agents=agents
    )

    return engine

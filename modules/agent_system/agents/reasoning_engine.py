"""Reasoning Engine for routing queries to appropriate agents."""

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel

from .base import Agent, AgentResult, AgentStatus, AgentContext
from ..llm.base import LLMProvider, Message
from ..tools.registry import ToolRegistry


class RoutingDecision(BaseModel):
    """Result of query routing."""
    agent_name: str  # "id_mapping", "direct", etc.
    confidence: float
    reasoning: Optional[str] = None


class ReasoningEngineResponse(BaseModel):
    """Response from reasoning engine."""
    answer: str
    agent_used: Optional[str] = None
    routing_decision: Optional[RoutingDecision] = None
    agent_result: Optional[AgentResult] = None


class ReasoningEngine:
    """
    Routes queries to appropriate agents and orchestrates responses.

    The reasoning engine is the main entry point for user queries.
    It decides which agent should handle a query and coordinates execution.
    """

    # Prompts directory relative to this file
    PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "reasoning_engine"

    def __init__(
        self,
        llm: LLMProvider,
        tool_registry: ToolRegistry,
        agents: Dict[str, Agent] = None
    ):
        """
        Initialize reasoning engine.

        Args:
            llm: LLM provider for routing decisions
            tool_registry: Tool registry for direct tool use
            agents: Dictionary of available agents {name: agent}
        """
        self.llm = llm
        self.tool_registry = tool_registry
        self.agents = agents or {}
        self._load_prompts()

    def _load_prompts(self):
        """Load prompt templates."""
        system_path = self.PROMPTS_DIR / "system.txt"
        routing_path = self.PROMPTS_DIR / "routing.txt"

        self.system_prompt = system_path.read_text() if system_path.exists() else self._default_system_prompt()
        self.routing_prompt = routing_path.read_text() if routing_path.exists() else self._default_routing_prompt()

    def _default_system_prompt(self) -> str:
        """Default system prompt if file not found."""
        return """You are BioYoda, an intelligent bioinformatics assistant.
You help users with biological data queries by routing them to specialized agents or answering directly."""

    def _default_routing_prompt(self) -> str:
        """Default routing prompt if file not found."""
        return """Analyze this query and decide how to handle it.
Options: "id_mapping" for identifier mapping, "direct" for general questions.
Query: {query}
Decision (one word):"""

    def register_agent(self, agent: Agent) -> None:
        """
        Register an agent with the reasoning engine.

        Args:
            agent: Agent to register
        """
        self.agents[agent.name] = agent

    async def route(self, query: str) -> RoutingDecision:
        """
        Determine which agent should handle the query.

        Uses a combination of:
        1. Agent confidence scores (can_handle method)
        2. LLM-based routing for ambiguous cases

        Args:
            query: User query

        Returns:
            Routing decision
        """
        # First, check agent confidence scores
        best_agent = None
        best_confidence = 0.0

        for name, agent in self.agents.items():
            confidence = agent.can_handle(query)
            if confidence > best_confidence:
                best_confidence = confidence
                best_agent = name

        # High confidence - use that agent
        if best_confidence >= 0.7:
            return RoutingDecision(
                agent_name=best_agent,
                confidence=best_confidence,
                reasoning=f"High confidence match for {best_agent}"
            )

        # Low confidence from agents - use LLM routing
        if best_confidence < 0.3:
            return await self._llm_route(query)

        # Medium confidence - use agent but note uncertainty
        return RoutingDecision(
            agent_name=best_agent,
            confidence=best_confidence,
            reasoning=f"Medium confidence match for {best_agent}"
        )

    async def _llm_route(self, query: str) -> RoutingDecision:
        """
        Use LLM to determine routing for ambiguous queries.

        Args:
            query: User query

        Returns:
            Routing decision
        """
        prompt = self.routing_prompt.format(query=query)

        try:
            response = await self.llm.chat(
                messages=[Message(role="user", content=prompt)],
                temperature=0.0,
                max_tokens=50
            )

            decision = response.content.strip().lower()

            # Parse decision
            if "id_mapping" in decision:
                return RoutingDecision(
                    agent_name="id_mapping",
                    confidence=0.6,
                    reasoning="LLM routing decision"
                )
            else:
                return RoutingDecision(
                    agent_name="direct",
                    confidence=0.6,
                    reasoning="LLM routing decision"
                )

        except Exception as e:
            # Default to direct response on error
            return RoutingDecision(
                agent_name="direct",
                confidence=0.5,
                reasoning=f"Routing error, defaulting to direct: {str(e)}"
            )

    async def process(
        self,
        query: str,
        context: Optional[AgentContext] = None
    ) -> ReasoningEngineResponse:
        """
        Process a user query through the appropriate agent.

        Args:
            query: User query
            context: Optional execution context

        Returns:
            Response with answer and metadata
        """
        # Route the query
        routing = await self.route(query)

        # Direct response - use LLM without tools
        if routing.agent_name == "direct":
            return await self._direct_response(query, routing)

        # Route to agent
        if routing.agent_name in self.agents:
            return await self._agent_response(query, routing, context)

        # Unknown agent - fallback to direct
        routing.reasoning = f"Unknown agent '{routing.agent_name}', falling back to direct"
        return await self._direct_response(query, routing)

    async def _direct_response(
        self,
        query: str,
        routing: RoutingDecision
    ) -> ReasoningEngineResponse:
        """
        Generate direct LLM response without agent.

        Args:
            query: User query
            routing: Routing decision

        Returns:
            Response
        """
        try:
            response = await self.llm.chat(
                messages=[
                    Message(role="system", content=self.system_prompt),
                    Message(role="user", content=query)
                ],
                temperature=0.3,
                max_tokens=1000
            )

            return ReasoningEngineResponse(
                answer=response.content,
                agent_used=None,
                routing_decision=routing
            )

        except Exception as e:
            return ReasoningEngineResponse(
                answer=f"Error generating response: {str(e)}",
                agent_used=None,
                routing_decision=routing
            )

    async def _agent_response(
        self,
        query: str,
        routing: RoutingDecision,
        context: Optional[AgentContext] = None
    ) -> ReasoningEngineResponse:
        """
        Process query through specialized agent.

        Args:
            query: User query
            routing: Routing decision
            context: Optional execution context

        Returns:
            Response
        """
        agent = self.agents[routing.agent_name]

        try:
            agent_result = await agent.run(query, context)

            return ReasoningEngineResponse(
                answer=agent_result.answer,
                agent_used=routing.agent_name,
                routing_decision=routing,
                agent_result=agent_result
            )

        except Exception as e:
            return ReasoningEngineResponse(
                answer=f"Agent error: {str(e)}",
                agent_used=routing.agent_name,
                routing_decision=routing,
                agent_result=AgentResult(
                    status=AgentStatus.ERROR,
                    answer="",
                    error=str(e)
                )
            )

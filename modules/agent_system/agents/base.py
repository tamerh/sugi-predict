"""Base agent class for the BioYoda multi-agent system."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel

from ..llm.base import LLMProvider, Message, LLMResponse
from ..tools.registry import ToolRegistry


class AgentStatus(str, Enum):
    """Agent execution status."""
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    MAX_ITERATIONS = "max_iterations"


class AgentResult(BaseModel):
    """Result from agent execution."""
    status: AgentStatus
    answer: str
    reasoning: List[str] = []  # Thought chain
    tool_calls: List[Dict[str, Any]] = []  # History of tool calls
    error: Optional[str] = None
    iterations: int = 0


class AgentContext(BaseModel):
    """Context passed to agent during execution."""
    conversation_history: List[Message] = []
    metadata: Dict[str, Any] = {}


class Agent(ABC):
    """
    Base class for all agents in the BioYoda system.

    Implements ReAct pattern: Thought → Action → Observation
    """

    def __init__(
        self,
        name: str,
        description: str,
        llm: LLMProvider,
        tool_registry: ToolRegistry,
        tools: List[str],
        max_iterations: int = 5,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize agent.

        Args:
            name: Agent identifier
            description: What this agent does
            llm: LLM provider for reasoning
            tool_registry: Registry of available tools
            tools: List of tool names this agent can use
            max_iterations: Maximum ReAct iterations
            system_prompt: System prompt for agent
        """
        self.name = name
        self.description = description
        self.llm = llm
        self.tool_registry = tool_registry
        self.tools = tools
        self.max_iterations = max_iterations
        self._system_prompt = system_prompt

    @property
    def system_prompt(self) -> str:
        """Get agent system prompt."""
        if self._system_prompt:
            return self._system_prompt
        return self._default_system_prompt()

    @abstractmethod
    def _default_system_prompt(self) -> str:
        """Return default system prompt for this agent type."""
        pass

    def get_tool_definitions(self):
        """Get tool definitions for tools this agent can use."""
        all_tools = self.tool_registry.get_tool_definitions()
        return [t for t in all_tools if t.name in self.tools]

    async def run(
        self,
        query: str,
        context: Optional[AgentContext] = None
    ) -> AgentResult:
        """
        Execute agent on a query using ReAct pattern.

        Args:
            query: User query to process
            context: Optional execution context

        Returns:
            Agent execution result
        """
        context = context or AgentContext()

        # Build initial messages
        messages = [
            Message(role="system", content=self.system_prompt),
            *context.conversation_history,
            Message(role="user", content=query)
        ]

        reasoning = []
        tool_calls = []
        iterations = 0

        while iterations < self.max_iterations:
            iterations += 1

            # Get LLM response with available tools
            try:
                response = await self.llm.chat_with_functions(
                    messages=messages,
                    tools=self.get_tool_definitions(),
                    temperature=0.0,
                    max_tokens=2000
                )
            except Exception as e:
                return AgentResult(
                    status=AgentStatus.ERROR,
                    answer="",
                    reasoning=reasoning,
                    tool_calls=tool_calls,
                    error=f"LLM error: {str(e)}",
                    iterations=iterations
                )

            # Check if LLM wants to call a tool
            if response.function_call:
                tool_name = response.function_call.name
                tool_args = response.function_call.arguments

                # Record reasoning if provided
                if response.content:
                    reasoning.append(f"Thought: {response.content}")

                reasoning.append(f"Action: {tool_name}({tool_args})")

                # Execute tool
                tool_result = await self.tool_registry.execute_tool(
                    tool_name, **tool_args
                )

                # Record tool call
                tool_calls.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": tool_result.data if tool_result.success else tool_result.error,
                    "success": tool_result.success
                })

                # Format observation
                if tool_result.success:
                    observation = self._format_observation(tool_result.data)
                else:
                    observation = f"Error: {tool_result.error}"

                reasoning.append(f"Observation: {observation[:500]}...")

                # Add tool response to messages
                # For OpenAI-style APIs, need to include tool_calls in assistant message
                import json as json_module
                tool_call_id = response.function_call.id if response.function_call.id else f"call_{tool_name}"
                messages.append(Message(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=[{
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json_module.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args)
                        }
                    }]
                ))
                messages.append(Message(
                    role="tool",
                    content=observation,
                    name=tool_name,
                    tool_call_id=tool_call_id
                ))

            else:
                # No tool call - agent is done
                final_answer = response.content
                if response.content:
                    reasoning.append(f"Final Answer: {response.content[:200]}...")

                return AgentResult(
                    status=AgentStatus.COMPLETED,
                    answer=final_answer,
                    reasoning=reasoning,
                    tool_calls=tool_calls,
                    iterations=iterations
                )

        # Max iterations reached
        return AgentResult(
            status=AgentStatus.MAX_ITERATIONS,
            answer="Unable to complete task within iteration limit.",
            reasoning=reasoning,
            tool_calls=tool_calls,
            iterations=iterations
        )

    def _format_observation(self, data: Any) -> str:
        """
        Format tool result for LLM observation.

        Override in subclasses for custom formatting.
        """
        import json
        if isinstance(data, (dict, list)):
            return json.dumps(data, indent=2)
        return str(data)

    def can_handle(self, query: str) -> float:
        """
        Return confidence (0-1) that this agent can handle the query.

        Used by reasoning engine for routing. Override in subclasses.

        Args:
            query: User query

        Returns:
            Confidence score 0-1
        """
        return 0.0

    def __repr__(self) -> str:
        return f"Agent(name='{self.name}', tools={self.tools})"

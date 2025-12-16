"""Schemas for unified query endpoint."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """
    Unified query request.

    The query is routed to the appropriate agent based on content.
    """
    query: str = Field(
        ...,
        description="Natural language query",
        min_length=1,
        max_length=2000,
        examples=[
            "What drugs are available for glioblastoma?",
            "What is the UniProt ID for TP53?",
            "Find proteins similar to P04637",
        ]
    )
    context: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional context for the query"
    )


class RoutingInfo(BaseModel):
    """Information about how the query was routed."""
    agent_name: str = Field(..., description="Name of agent that handled the query")
    confidence: float = Field(..., description="Routing confidence score (0-1)")
    reasoning: Optional[str] = Field(None, description="Explanation for routing decision")


class QueryResponse(BaseModel):
    """
    Unified query response.

    Contains the answer and metadata about how it was generated.
    """
    answer: str = Field(..., description="Generated answer")
    routing: RoutingInfo = Field(..., description="Routing information")
    agent_result: Optional[Dict[str, Any]] = Field(
        None,
        description="Raw result from the agent (for advanced users)"
    )
    execution_time_ms: float = Field(..., description="Total execution time in milliseconds")

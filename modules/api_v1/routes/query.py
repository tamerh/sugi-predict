"""Unified query endpoint - routes to appropriate agent."""

import logging
import time
from fastapi import APIRouter, Depends, HTTPException

from ..schemas.query import QueryRequest, QueryResponse, RoutingInfo
from ..dependencies import get_reasoning_engine
from ...agent_system.agents.reasoning_engine import ReasoningEngine
from ...agent_system.agents.base import AgentContext

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Unified Query",
    description="Natural language query routed to appropriate agent",
)
async def unified_query(
    request: QueryRequest,
    reasoning_engine: ReasoningEngine = Depends(get_reasoning_engine),
):
    """
    Unified query endpoint.

    Accepts natural language queries and routes them to the appropriate agent:
    - Drug discovery queries → DrugDiscoveryAgent
    - ID mapping queries → IDMappingAgent
    - General questions → Direct LLM response

    ## Examples

    Drug discovery:
    ```json
    {"query": "What drugs are available for glioblastoma?"}
    ```

    ID mapping:
    ```json
    {"query": "What is the UniProt ID for TP53?"}
    ```

    ## Response

    Returns the answer along with routing information showing which
    agent handled the query and with what confidence.
    """
    start_time = time.time()

    try:
        logger.info(f"Query received: '{request.query[:100]}...'")

        # Create context if provided
        context = None
        if request.context:
            context = AgentContext(**request.context)

        # Process through reasoning engine
        result = await reasoning_engine.process(request.query, context)

        execution_time_ms = (time.time() - start_time) * 1000

        # Build routing info
        routing = RoutingInfo(
            agent_name=result.agent_used or "direct",
            confidence=result.routing_decision.confidence if result.routing_decision else 1.0,
            reasoning=result.routing_decision.reasoning if result.routing_decision else None,
        )

        # Build response
        response = QueryResponse(
            answer=result.answer,
            routing=routing,
            agent_result=result.agent_result.model_dump() if result.agent_result else None,
            execution_time_ms=round(execution_time_ms, 2),
        )

        logger.info(
            f"Query completed: agent={routing.agent_name}, "
            f"confidence={routing.confidence:.2f}, "
            f"time={execution_time_ms:.0f}ms"
        )

        return response

    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {str(e)}"
        )

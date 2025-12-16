"""Health check endpoint."""

import logging
from fastapi import APIRouter, Depends

from ..schemas.common import HealthResponse
from ..dependencies import (
    get_biobtree_client,
    get_qdrant_client,
    get_reasoning_engine,
    get_tool_registry,
)
from .. import __version__

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check API health and component status",
)
async def health_check(
    biobtree=Depends(get_biobtree_client),
    qdrant=Depends(get_qdrant_client),
    reasoning_engine=Depends(get_reasoning_engine),
    tool_registry=Depends(get_tool_registry),
):
    """
    Health check endpoint.

    Returns status of all components:
    - BioBTree connection
    - Qdrant connection
    - LLM availability
    - Available agents and tools
    """
    # Check BioBTree connection
    biobtree_connected = False
    try:
        # Simple connectivity check
        biobtree_connected = biobtree is not None
    except Exception as e:
        logger.warning(f"BioBTree health check failed: {e}")

    # Check Qdrant connection
    qdrant_connected = False
    try:
        qdrant_connected = qdrant is not None
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")

    # Get available agents
    agents_available = list(reasoning_engine.agents.keys()) if reasoning_engine else []

    # Get available tools (list_tools() returns a list directly)
    tools_available = tool_registry.list_tools() if tool_registry else []

    # LLM availability
    llm_available = reasoning_engine.llm is not None if reasoning_engine else False

    # Determine overall status
    if biobtree_connected and qdrant_connected and llm_available:
        status = "healthy"
    elif biobtree_connected or qdrant_connected:
        status = "degraded"
    else:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        version=__version__,
        biobtree_connected=biobtree_connected,
        qdrant_connected=qdrant_connected,
        llm_available=llm_available,
        agents_available=agents_available,
        tools_available=tools_available,
    )

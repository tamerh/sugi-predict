"""Common schemas used across endpoints."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Health status: healthy, degraded, unhealthy")
    version: str = Field(..., description="API version")
    biobtree_connected: bool = Field(..., description="BioBTree gRPC connection status")
    qdrant_connected: bool = Field(..., description="Qdrant connection status")
    llm_available: bool = Field(..., description="LLM provider availability")
    agents_available: List[str] = Field(..., description="List of available agents")
    tools_available: List[str] = Field(..., description="List of available tools")


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Any] = Field(None, description="Additional error details")


class SuccessResponse(BaseModel):
    """Generic success response."""
    success: bool = True
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")

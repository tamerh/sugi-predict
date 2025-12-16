"""Pydantic schemas for API request/response models."""

from .common import HealthResponse, ErrorResponse
from .query import QueryRequest, QueryResponse
from .drug_discovery import DrugDiscoveryRequest, DrugDiscoveryResponse
from .id_mapping import IDMappingRequest, IDMappingResponse
from .similarity import (
    ProteinSimilarityRequest,
    ProteinSimilarityResponse,
    CompoundSimilarityRequest,
    CompoundSimilarityResponse,
)

__all__ = [
    # Common
    "HealthResponse",
    "ErrorResponse",
    # Query
    "QueryRequest",
    "QueryResponse",
    # Drug Discovery
    "DrugDiscoveryRequest",
    "DrugDiscoveryResponse",
    # ID Mapping
    "IDMappingRequest",
    "IDMappingResponse",
    # Similarity
    "ProteinSimilarityRequest",
    "ProteinSimilarityResponse",
    "CompoundSimilarityRequest",
    "CompoundSimilarityResponse",
]

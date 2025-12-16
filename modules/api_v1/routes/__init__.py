"""API route modules."""

from .health import router as health_router
from .query import router as query_router
from .drug_discovery import router as drug_discovery_router
from .id_mapping import router as id_mapping_router
from .protein_similarity import router as protein_similarity_router
from .compound_similarity import router as compound_similarity_router

__all__ = [
    "health_router",
    "query_router",
    "drug_discovery_router",
    "id_mapping_router",
    "protein_similarity_router",
    "compound_similarity_router",
]

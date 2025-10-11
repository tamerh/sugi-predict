"""
Pydantic models for API requests and responses
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from enum import Enum


class SearchRequest(BaseModel):
    """
    Search request model

    Example:
        {
            "query": "CRISPR gene editing",
            "collections": ["pubmed_abstracts", "clinical_trials"],
            "limit": 10,
            "filters": {"source": "pubmed"}
        }
    """
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search query (natural language or keywords)"
    )
    collections: List[str] = Field(
        default=["pubmed_abstracts", "clinical_trials"],
        description="List of collections to search"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results per collection"
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata filters (e.g., {'source': 'pubmed'})"
    )
    merge_results: bool = Field(
        default=True,
        description="Whether to merge and re-rank results across collections"
    )

    @validator('query')
    def query_not_empty(cls, v):
        """Validate query is not empty after stripping whitespace"""
        if not v.strip():
            raise ValueError('Query cannot be empty or only whitespace')
        return v.strip()

    @validator('collections')
    def collections_not_empty(cls, v):
        """Validate at least one collection specified"""
        if not v:
            raise ValueError('At least one collection must be specified')
        return v

    class Config:
        schema_extra = {
            "example": {
                "query": "Alzheimer disease treatment",
                "collections": ["pubmed_abstracts"],
                "limit": 10,
                "filters": None
            }
        }


class SearchResultItem(BaseModel):
    """
    Single search result item

    Contains the document ID, relevance score, source collection,
    and all metadata fields from the original document.
    """
    id: str = Field(..., description="Document ID")
    score: float = Field(..., ge=-1.0, le=1.0, description="Relevance score (-1 to 1, cosine similarity)")
    collection: str = Field(..., description="Source collection name")
    payload: Dict[str, Any] = Field(..., description="Document metadata and content")

    class Config:
        schema_extra = {
            "example": {
                "id": "12345",
                "score": 0.89,
                "collection": "pubmed_abstracts",
                "payload": {
                    "pmid": "12345",
                    "chunk_text": "Title: CRISPR...\nAbstract: ..."
                }
            }
        }


class SearchResponse(BaseModel):
    """
    Search response model

    Contains the original query, search results, and metadata about
    the search operation.
    """
    query: str = Field(..., description="Original search query")
    total_results: int = Field(..., ge=0, description="Total number of results returned")
    results_per_collection: Dict[str, int] = Field(
        ...,
        description="Number of results per collection"
    )
    results: List[SearchResultItem] = Field(..., description="Search results")
    search_time_ms: float = Field(..., ge=0, description="Search time in milliseconds")

    class Config:
        schema_extra = {
            "example": {
                "query": "cancer immunotherapy",
                "total_results": 15,
                "results_per_collection": {
                    "pubmed_abstracts": 10,
                    "clinical_trials": 5
                },
                "results": [
                    {
                        "id": "12345",
                        "score": 0.92,
                        "collection": "pubmed_abstracts",
                        "payload": {
                            "pmid": "12345",
                            "chunk_text": "Title: Cancer immunotherapy...\nAbstract: ..."
                        }
                    }
                ],
                "search_time_ms": 234.56
            }
        }


class CollectionInfo(BaseModel):
    """Collection information and statistics"""
    name: str = Field(..., description="Collection name")
    description: str = Field(..., description="Collection description")
    display_name: str = Field(..., description="Display name for UI")
    points_count: int = Field(..., ge=0, description="Number of vectors in collection")
    status: str = Field(..., description="Collection status (green/yellow/red)")
    vector_size: int = Field(..., description="Vector dimension")

    class Config:
        schema_extra = {
            "example": {
                "name": "pubmed_abstracts",
                "description": "PubMed abstracts - 30M+ biomedical research papers",
                "display_name": "PubMed",
                "points_count": 30000000,
                "status": "green",
                "vector_size": 768
            }
        }


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Overall API status (healthy/degraded/unhealthy)")
    qdrant_connected: bool = Field(..., description="Whether Qdrant is accessible")
    model_loaded: bool = Field(..., description="Whether embedding model is loaded")
    collections_available: List[str] = Field(..., description="Available collections")
    version: str = Field(..., description="API version")

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "qdrant_connected": True,
                "model_loaded": True,
                "collections_available": ["pubmed_abstracts", "clinical_trials"],
                "version": "0.1.0"
            }
        }


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")

    class Config:
        schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid search parameters",
                "detail": "Query cannot be empty"
            }
        }


# ============================================================================
# RAG (Retrieval-Augmented Generation) Models
# ============================================================================

class AskRequest(BaseModel):
    """
    RAG question-answering request model

    Example:
        {
            "question": "What is CRISPR gene editing?",
            "collections": ["pubmed_abstracts", "clinical_trials"],
            "top_k": 5,
            "temperature": 0.1,
            "max_tokens": 1000
        }
    """
    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Question to answer"
    )
    collections: Optional[List[str]] = Field(
        default=None,
        description="Collections to search (default: pubmed + clinical_trials)"
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of sources to retrieve"
    )
    temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="LLM temperature (0.0=factual, 1.0=creative)"
    )
    max_tokens: int = Field(
        default=1000,
        ge=100,
        le=4000,
        description="Maximum tokens in response"
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata filters"
    )

    @validator('question')
    def question_not_empty(cls, v):
        """Validate question is not empty after stripping whitespace"""
        if not v.strip():
            raise ValueError('Question cannot be empty or only whitespace')
        return v.strip()

    class Config:
        schema_extra = {
            "example": {
                "question": "What are the latest treatments for Alzheimer's disease?",
                "collections": ["pubmed_abstracts"],
                "top_k": 5,
                "temperature": 0.1,
                "max_tokens": 1000
            }
        }


class Source(BaseModel):
    """Source document from RAG retrieval"""
    id: str = Field(..., description="Source identifier (PMID or trial ID)")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score")
    collection: str = Field(..., description="Source collection name")
    title: str = Field(..., description="Document title")
    text_preview: str = Field(..., description="Text preview/snippet")
    url: Optional[str] = Field(None, description="URL to source document")

    class Config:
        schema_extra = {
            "example": {
                "id": "PMID:12345678",
                "score": 0.92,
                "collection": "pubmed_abstracts",
                "title": "CRISPR-Cas9 gene editing in human cells",
                "text_preview": "CRISPR-Cas9 is a revolutionary gene editing technology...",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
            }
        }


class Metrics(BaseModel):
    """Performance and cost metrics"""
    search_time_ms: float = Field(..., ge=0, description="Search time in milliseconds")
    llm_time_ms: float = Field(..., ge=0, description="LLM generation time in milliseconds")
    total_time_ms: float = Field(..., ge=0, description="Total time in milliseconds")
    num_sources: int = Field(..., ge=0, description="Number of sources retrieved")
    model_used: str = Field(..., description="LLM model used")
    estimated_cost_usd: float = Field(..., ge=0, description="Estimated cost in USD")

    class Config:
        schema_extra = {
            "example": {
                "search_time_ms": 234.56,
                "llm_time_ms": 1567.89,
                "total_time_ms": 1802.45,
                "num_sources": 5,
                "model_used": "claude-3-5-sonnet-20241022",
                "estimated_cost_usd": 0.0142
            }
        }


class Validation(BaseModel):
    """Citation validation results"""
    citation_coverage: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of sources cited (0.0-1.0)"
    )
    cited_count: int = Field(..., ge=0, description="Number of sources cited")
    valid_citations: List[str] = Field(..., description="Valid citations")
    invalid_citations: List[str] = Field(..., description="Hallucinated citations")
    warning: Optional[str] = Field(None, description="Warning if issues detected")

    class Config:
        schema_extra = {
            "example": {
                "citation_coverage": 0.8,
                "cited_count": 4,
                "valid_citations": ["PMID:12345678", "PMID:87654321"],
                "invalid_citations": [],
                "warning": None
            }
        }


class AskResponse(BaseModel):
    """
    RAG question-answering response model

    Contains the generated answer, sources, and validation metrics
    """
    question: str = Field(..., description="Original question")
    answer: str = Field(..., description="Generated answer with citations")
    sources: List[Source] = Field(..., description="Source documents")
    metrics: Metrics = Field(..., description="Performance metrics")
    validation: Optional[Validation] = Field(None, description="Citation validation (if enabled)")

    class Config:
        schema_extra = {
            "example": {
                "question": "What is CRISPR gene editing?",
                "answer": "CRISPR-Cas9 is a revolutionary gene editing technology... (PMID:12345678)",
                "sources": [
                    {
                        "id": "PMID:12345678",
                        "score": 0.92,
                        "collection": "pubmed_abstracts",
                        "title": "CRISPR-Cas9 gene editing",
                        "text_preview": "CRISPR-Cas9 is a revolutionary...",
                        "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
                    }
                ],
                "metrics": {
                    "search_time_ms": 234.56,
                    "llm_time_ms": 1567.89,
                    "total_time_ms": 1802.45,
                    "num_sources": 5,
                    "model_used": "claude-3-5-sonnet-20241022",
                    "estimated_cost_usd": 0.0142
                },
                "validation": {
                    "citation_coverage": 0.8,
                    "cited_count": 4,
                    "valid_citations": ["PMID:12345678"],
                    "invalid_citations": [],
                    "warning": None
                }
            }
        }

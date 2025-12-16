"""Schemas for ID mapping endpoint."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class IDMappingRequest(BaseModel):
    """
    ID mapping request.

    Maps biological identifiers between different databases.
    """
    ids: List[str] = Field(
        ...,
        description="List of identifiers to map",
        min_length=1,
        max_length=100,
        examples=[["TP53", "BRCA1", "EGFR"], ["P04637"], ["ENSG00000141510"]]
    )
    from_type: Optional[str] = Field(
        None,
        description="Source ID type (auto-detected if not specified)",
        examples=["gene_symbol", "uniprot", "ensembl", "hgnc"]
    )
    to_type: str = Field(
        ...,
        description="Target ID type",
        examples=["uniprot", "ensembl", "gene_symbol", "hgnc"]
    )


class MappingResult(BaseModel):
    """Single ID mapping result."""
    input_id: str = Field(..., description="Original input ID")
    input_type: str = Field(..., description="Detected input type")
    mapped_ids: List[str] = Field(default_factory=list, description="Mapped IDs")
    mapped_type: str = Field(..., description="Output ID type")
    success: bool = Field(..., description="Whether mapping was successful")
    error: Optional[str] = Field(None, description="Error message if failed")


class IDMappingResponse(BaseModel):
    """
    ID mapping response.

    Contains mapping results for all input IDs.
    """
    results: List[MappingResult] = Field(..., description="Mapping results")
    total_input: int = Field(..., description="Total input IDs")
    total_mapped: int = Field(..., description="Successfully mapped IDs")
    total_failed: int = Field(..., description="Failed mappings")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")

"""Schemas for similarity search endpoints."""

from typing import Optional, List
from pydantic import BaseModel, Field


# Protein Similarity
class ProteinSimilarityRequest(BaseModel):
    """
    Protein similarity search request.

    Uses ESM-2 embeddings to find similar proteins.
    """
    query: str = Field(
        ...,
        description="Query: UniProt ID, gene symbol, or protein sequence",
        examples=["P04637", "TP53", "MEEPQSDPSV..."]
    )
    limit: int = Field(
        10,
        ge=1,
        le=100,
        description="Maximum number of results"
    )
    min_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold"
    )


class ProteinMatch(BaseModel):
    """Similar protein match."""
    uniprot_id: str = Field(..., description="UniProt accession")
    gene_name: Optional[str] = Field(None, description="Gene name")
    protein_name: Optional[str] = Field(None, description="Protein name")
    organism: Optional[str] = Field(None, description="Source organism")
    score: float = Field(..., description="Similarity score (0-1)")
    sequence_length: Optional[int] = Field(None, description="Protein sequence length")


class ProteinSimilarityResponse(BaseModel):
    """
    Protein similarity search response.

    Results from ESM-2 embedding similarity search.
    """
    query: str = Field(..., description="Original query")
    query_uniprot: Optional[str] = Field(None, description="Resolved UniProt ID")
    results: List[ProteinMatch] = Field(..., description="Similar proteins")
    total_results: int = Field(..., description="Number of results")
    collection: str = Field(
        "swissprot_esm2",
        description="Qdrant collection searched"
    )
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")


# Compound Similarity
class CompoundSimilarityRequest(BaseModel):
    """
    Compound similarity search request.

    Uses Morgan fingerprints to find similar compounds.
    """
    query: str = Field(
        ...,
        description="Query: SMILES, ChEMBL ID, or compound name",
        examples=[
            "CC(=O)Oc1ccccc1C(=O)O",  # Aspirin SMILES
            "CHEMBL25",
            "aspirin"
        ]
    )
    limit: int = Field(
        10,
        ge=1,
        le=100,
        description="Maximum number of results"
    )
    min_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold"
    )


class CompoundMatch(BaseModel):
    """Similar compound match."""
    id: str = Field(..., description="Compound ID (SureChEMBL)")
    smiles: Optional[str] = Field(None, description="SMILES structure")
    score: float = Field(..., description="Similarity score (0-1)")
    molecular_weight: Optional[float] = Field(None, description="Molecular weight")
    formula: Optional[str] = Field(None, description="Molecular formula")
    source: Optional[str] = Field(None, description="Data source")


class CompoundSimilarityResponse(BaseModel):
    """
    Compound similarity search response.

    Results from Morgan fingerprint similarity search.
    """
    query: str = Field(..., description="Original query")
    query_smiles: Optional[str] = Field(None, description="Resolved SMILES")
    results: List[CompoundMatch] = Field(..., description="Similar compounds")
    total_results: int = Field(..., description="Number of results")
    collection: str = Field(
        "patents_compounds",
        description="Qdrant collection searched"
    )
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")

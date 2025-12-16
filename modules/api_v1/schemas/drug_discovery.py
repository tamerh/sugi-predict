"""Schemas for drug discovery endpoint."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Request schema
class DrugDiscoveryRequest(BaseModel):
    """
    Drug discovery request parameters.

    Finds drugs for a disease using multiple evidence paths.
    """
    disease: str = Field(
        ...,
        description="Disease name or ID (EFO/MONDO)",
        min_length=1,
        examples=["glioblastoma", "type 2 diabetes", "EFO:0000311"]
    )
    min_indication_phase: int = Field(
        3,
        ge=0,
        le=4,
        description="Minimum clinical phase for direct indications (0-4)"
    )
    include_gwas: bool = Field(True, description="Include GWAS genetic associations")
    include_clinvar: bool = Field(True, description="Include ClinVar variant associations")
    include_pubchem: bool = Field(True, description="Include PubChem FDA-approved drugs")
    include_reactome: bool = Field(True, description="Include Reactome pathways")
    include_similar_proteins: bool = Field(
        False,
        description="Find similar proteins via ESM-2 embeddings"
    )
    include_similar_compounds: bool = Field(
        False,
        description="Find similar compounds via Morgan fingerprints"
    )
    similarity_limit: int = Field(
        5,
        ge=1,
        le=20,
        description="Max similar items per query"
    )


# Response sub-schemas (matching frontend types)
class Drug(BaseModel):
    """Drug information."""
    id: str = Field(..., description="Drug ID (e.g., CHEMBL25)")
    name: str = Field(..., description="Drug name")
    phase: Optional[int] = Field(None, description="Clinical phase (0-4)")
    indication: Optional[str] = Field(None, description="Disease indication")
    source: Optional[str] = Field(None, description="Data source")


class Gene(BaseModel):
    """Gene information."""
    id: str = Field(..., description="Gene ID (e.g., ENSG00000141510)")
    symbol: str = Field(..., description="Gene symbol (e.g., TP53)")
    name: Optional[str] = Field(None, description="Full gene name")


class Pathway(BaseModel):
    """Pathway information."""
    id: str = Field(..., description="Pathway ID (e.g., R-HSA-123)")
    name: str = Field(..., description="Pathway name")
    genes: Optional[List[str]] = Field(None, description="Associated genes")


class SimilarProtein(BaseModel):
    """Similar protein from ESM-2 search."""
    uniprot_id: str = Field(..., description="UniProt accession")
    gene_name: Optional[str] = Field(None, description="Gene name")
    score: float = Field(..., description="Similarity score (0-1)")
    description: Optional[str] = Field(None, description="Protein description")


class SimilarCompound(BaseModel):
    """Similar compound from Morgan FP search."""
    id: str = Field(..., description="Compound ID")
    smiles: Optional[str] = Field(None, description="SMILES structure")
    score: float = Field(..., description="Similarity score (0-1)")
    source: Optional[str] = Field(None, description="Data source")


class DirectIndications(BaseModel):
    """Direct drug indications from ChEMBL."""
    count: int = Field(..., description="Number of drugs")
    drugs: List[Drug] = Field(default_factory=list, description="List of drugs")


class GwasTargets(BaseModel):
    """GWAS-associated targets."""
    genes: List[str] = Field(default_factory=list, description="Gene symbols")
    drug_count: int = Field(0, description="Number of drugs for these genes")
    drugs: Optional[List[Drug]] = Field(None, description="Associated drugs")


class ClinvarTargets(BaseModel):
    """ClinVar-associated targets."""
    genes: List[str] = Field(default_factory=list, description="Gene symbols")
    drug_count: int = Field(0, description="Number of drugs for these genes")
    drugs: Optional[List[Drug]] = Field(None, description="Associated drugs")


class PubchemTargets(BaseModel):
    """PubChem FDA-approved drugs."""
    genes: List[str] = Field(default_factory=list, description="Gene symbols")
    drug_count: int = Field(0, description="Number of FDA-approved drugs")
    drugs: Optional[List[Drug]] = Field(None, description="FDA-approved drugs")


class ReactomePathways(BaseModel):
    """Reactome pathway associations."""
    pathways: List[Pathway] = Field(default_factory=list, description="Pathways")
    count: int = Field(0, description="Number of pathways")


class Summary(BaseModel):
    """Result summary statistics."""
    total_drugs: int = Field(0, description="Total unique drugs found")
    total_genes: int = Field(0, description="Total unique genes found")
    total_pathways: int = Field(0, description="Total pathways found")
    evidence_paths_used: List[str] = Field(
        default_factory=list,
        description="Evidence paths that returned results"
    )


# Main response schema
class DrugDiscoveryResponse(BaseModel):
    """
    Drug discovery response.

    Contains results from all evidence paths.
    """
    disease: str = Field(..., description="Queried disease")
    disease_id: Optional[str] = Field(None, description="Resolved disease ID (EFO/MONDO)")

    # Evidence paths
    direct_indications: DirectIndications = Field(
        ..., description="PATH 1: Direct drug indications from ChEMBL"
    )
    gwas_targets: Optional[GwasTargets] = Field(
        None, description="PATH 2: GWAS genetic associations"
    )
    clinvar_targets: Optional[ClinvarTargets] = Field(
        None, description="PATH 3: ClinVar variant associations"
    )
    pubchem_targets: Optional[PubchemTargets] = Field(
        None, description="PATH 6: PubChem FDA-approved drugs"
    )
    reactome_pathways: Optional[ReactomePathways] = Field(
        None, description="PATH 7: Reactome pathway associations"
    )
    similar_proteins: Optional[List[SimilarProtein]] = Field(
        None, description="PATH 8: Similar proteins (ESM-2)"
    )
    similar_compounds: Optional[List[SimilarCompound]] = Field(
        None, description="PATH 9: Similar compounds (Morgan FP)"
    )

    # Summary
    summary: Summary = Field(..., description="Result summary statistics")

    # Metadata
    execution_time_ms: float = Field(..., description="Total execution time in milliseconds")

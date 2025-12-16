"""Drug discovery endpoint - direct access to DrugDiscoveryAgent."""

import logging
import time
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from ..schemas.drug_discovery import (
    DrugDiscoveryRequest,
    DrugDiscoveryResponse,
    DirectIndications,
    GwasTargets,
    ClinvarTargets,
    PubchemTargets,
    ReactomePathways,
    Drug,
    Pathway,
    SimilarProtein,
    SimilarCompound,
    Summary,
)
from ..dependencies import get_tool_registry
from ...agent_system.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter()


def _convert_drugs(drugs_data: List[dict]) -> List[Drug]:
    """Convert raw drug data to Drug schema."""
    return [
        Drug(
            id=d.get("chembl_id", d.get("id", "")),
            name=d.get("name", d.get("title", "")),
            phase=d.get("phase"),
            indication=d.get("indication"),
            source=d.get("source"),
        )
        for d in drugs_data[:50]  # Limit to top 50
    ]


def _convert_pathways(pathways_data: List[dict]) -> List[Pathway]:
    """Convert raw pathway data to Pathway schema."""
    return [
        Pathway(
            id=p.get("id", ""),
            name=p.get("name", ""),
            genes=p.get("genes"),
        )
        for p in pathways_data[:50]  # Limit to top 50
    ]


@router.post(
    "/drug-discovery",
    response_model=DrugDiscoveryResponse,
    summary="Drug Discovery",
    description="Find drugs for a disease using multiple evidence paths",
)
async def drug_discovery(
    request: DrugDiscoveryRequest,
    tool_registry: ToolRegistry = Depends(get_tool_registry),
):
    """
    Drug discovery endpoint.

    Finds drugs for a disease using 9 evidence paths:
    - PATH 1: Direct indications from ChEMBL
    - PATH 2: GWAS genetic associations
    - PATH 3: ClinVar variant associations
    - PATH 6: PubChem FDA-approved drugs
    - PATH 7: Reactome pathways
    - PATH 8: Similar proteins (ESM-2)
    - PATH 9: Similar compounds (Morgan FP)

    ## Example

    ```json
    {
        "disease": "glioblastoma",
        "min_indication_phase": 3,
        "include_gwas": true,
        "include_clinvar": true,
        "include_similar_proteins": true
    }
    ```

    ## Response

    Returns drugs from all enabled evidence paths with summary statistics.
    """
    start_time = time.time()

    try:
        logger.info(f"Drug discovery request: disease='{request.disease}'")

        # Get the disease_drug_discovery tool
        tool = tool_registry.get_tool("disease_drug_discovery")
        if not tool:
            raise HTTPException(
                status_code=503,
                detail="Disease drug discovery tool not available"
            )

        # Execute the tool
        result = await tool.execute(
            disease=request.disease,
            min_indication_phase=request.min_indication_phase,
            include_gwas=request.include_gwas,
            include_clinvar=request.include_clinvar,
            include_reactome=request.include_reactome,
            include_pubchem=request.include_pubchem,
            include_similar_proteins=request.include_similar_proteins,
            include_similar_compounds=request.include_similar_compounds,
            similarity_limit=request.similarity_limit,
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Drug discovery failed: {result.error}"
            )

        data = result.data
        execution_time_ms = (time.time() - start_time) * 1000

        # Build response from tool result
        # Direct indications
        direct_data = data.get("direct_indications", {})
        direct_indications = DirectIndications(
            count=direct_data.get("count", 0),
            drugs=_convert_drugs(direct_data.get("drugs", [])),
        )

        # GWAS targets
        gwas_targets = None
        if request.include_gwas and "gwas_targets" in data:
            gwas_data = data["gwas_targets"]
            gwas_targets = GwasTargets(
                genes=gwas_data.get("genes", []),
                drug_count=gwas_data.get("drug_count", 0),
                drugs=_convert_drugs(gwas_data.get("drugs", [])) if gwas_data.get("drugs") else None,
            )

        # ClinVar targets
        clinvar_targets = None
        if request.include_clinvar and "clinvar_targets" in data:
            clinvar_data = data["clinvar_targets"]
            clinvar_targets = ClinvarTargets(
                genes=clinvar_data.get("genes", []),
                drug_count=clinvar_data.get("drug_count", 0),
                drugs=_convert_drugs(clinvar_data.get("drugs", [])) if clinvar_data.get("drugs") else None,
            )

        # PubChem targets
        pubchem_targets = None
        if request.include_pubchem and "pubchem_targets" in data:
            pubchem_data = data["pubchem_targets"]
            pubchem_targets = PubchemTargets(
                genes=pubchem_data.get("genes", []),
                drug_count=pubchem_data.get("drug_count", 0),
                drugs=_convert_drugs(pubchem_data.get("drugs", [])) if pubchem_data.get("drugs") else None,
            )

        # Reactome pathways
        reactome_pathways = None
        if request.include_reactome and "reactome_pathways" in data:
            reactome_data = data["reactome_pathways"]
            reactome_pathways = ReactomePathways(
                pathways=_convert_pathways(reactome_data.get("pathways", [])),
                count=reactome_data.get("count", 0),
            )

        # Similar proteins
        similar_proteins = None
        if request.include_similar_proteins and "similar_proteins" in data:
            similar_proteins = [
                SimilarProtein(
                    uniprot_id=p.get("uniprot_id", ""),
                    gene_name=p.get("gene_name"),
                    score=p.get("score", 0.0),
                    description=p.get("description"),
                )
                for p in data["similar_proteins"]
            ]

        # Similar compounds
        similar_compounds = None
        if request.include_similar_compounds and "similar_compounds" in data:
            similar_compounds = [
                SimilarCompound(
                    id=c.get("id", ""),
                    smiles=c.get("smiles"),
                    score=c.get("score", 0.0),
                    source=c.get("source"),
                )
                for c in data["similar_compounds"]
            ]

        # Build summary
        evidence_paths = ["direct_indications"]
        if gwas_targets:
            evidence_paths.append("gwas")
        if clinvar_targets:
            evidence_paths.append("clinvar")
        if pubchem_targets:
            evidence_paths.append("pubchem")
        if reactome_pathways:
            evidence_paths.append("reactome")
        if similar_proteins:
            evidence_paths.append("similar_proteins")
        if similar_compounds:
            evidence_paths.append("similar_compounds")

        summary = Summary(
            total_drugs=data.get("summary", {}).get("total_drugs", direct_indications.count),
            total_genes=data.get("summary", {}).get("total_genes", 0),
            total_pathways=reactome_pathways.count if reactome_pathways else 0,
            evidence_paths_used=evidence_paths,
        )

        response = DrugDiscoveryResponse(
            disease=request.disease,
            disease_id=data.get("disease_id"),
            direct_indications=direct_indications,
            gwas_targets=gwas_targets,
            clinvar_targets=clinvar_targets,
            pubchem_targets=pubchem_targets,
            reactome_pathways=reactome_pathways,
            similar_proteins=similar_proteins,
            similar_compounds=similar_compounds,
            summary=summary,
            execution_time_ms=round(execution_time_ms, 2),
        )

        logger.info(
            f"Drug discovery completed: disease='{request.disease}', "
            f"drugs={summary.total_drugs}, genes={summary.total_genes}, "
            f"time={execution_time_ms:.0f}ms"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Drug discovery failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Drug discovery failed: {str(e)}"
        )

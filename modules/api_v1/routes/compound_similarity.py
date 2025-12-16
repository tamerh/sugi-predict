"""Compound similarity search endpoint."""

import logging
import time
from fastapi import APIRouter, Depends, HTTPException

from ..schemas.similarity import (
    CompoundSimilarityRequest,
    CompoundSimilarityResponse,
    CompoundMatch,
)
from ..dependencies import get_tool_registry
from ...agent_system.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/compound-similarity",
    response_model=CompoundSimilarityResponse,
    summary="Compound Similarity Search",
    description="Find similar compounds using Morgan fingerprints",
)
async def compound_similarity(
    request: CompoundSimilarityRequest,
    tool_registry: ToolRegistry = Depends(get_tool_registry),
):
    """
    Compound similarity search endpoint.

    Uses Morgan fingerprints (2048-bit) to find structurally similar compounds
    from 30.8M SureChEMBL patent compounds.

    ## Example

    ```json
    {
        "query": "CHEMBL25",
        "limit": 10,
        "min_score": 0.7
    }
    ```

    ## Query formats

    - ChEMBL ID: "CHEMBL25"
    - SMILES: "CC(=O)Oc1ccccc1C(=O)O"
    - Compound name: "aspirin"

    ## Response

    Returns similar compounds ranked by Morgan fingerprint similarity.
    """
    start_time = time.time()

    try:
        logger.info(f"Compound similarity request: query='{request.query[:50]}...', limit={request.limit}")

        # Get the compound_similarity_search tool
        tool = tool_registry.get_tool("compound_similarity_search")
        if not tool:
            raise HTTPException(
                status_code=503,
                detail="Compound similarity search tool not available"
            )

        # Execute search
        result = await tool.execute(
            query=request.query,
            limit=request.limit,
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Compound similarity search failed: {result.error}"
            )

        execution_time_ms = (time.time() - start_time) * 1000

        # Convert results
        matches = []
        for item in result.data.get("results", []):
            score = item.get("score", 0.0)
            if score >= request.min_score:
                matches.append(CompoundMatch(
                    id=item.get("id", item.get("surechembl_id", "")),
                    smiles=item.get("smiles"),
                    score=score,
                    molecular_weight=item.get("molecular_weight"),
                    formula=item.get("formula"),
                    source=item.get("source"),
                ))

        response = CompoundSimilarityResponse(
            query=request.query,
            query_smiles=result.data.get("query_smiles"),
            results=matches,
            total_results=len(matches),
            collection="patents_compounds",
            execution_time_ms=round(execution_time_ms, 2),
        )

        logger.info(
            f"Compound similarity completed: {len(matches)} results, "
            f"time={execution_time_ms:.0f}ms"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Compound similarity search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Compound similarity search failed: {str(e)}"
        )

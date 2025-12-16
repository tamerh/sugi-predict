"""Protein similarity search endpoint."""

import logging
import time
from fastapi import APIRouter, Depends, HTTPException

from ..schemas.similarity import (
    ProteinSimilarityRequest,
    ProteinSimilarityResponse,
    ProteinMatch,
)
from ..dependencies import get_tool_registry
from ...agent_system.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/protein-similarity",
    response_model=ProteinSimilarityResponse,
    summary="Protein Similarity Search",
    description="Find similar proteins using ESM-2 embeddings",
)
async def protein_similarity(
    request: ProteinSimilarityRequest,
    tool_registry: ToolRegistry = Depends(get_tool_registry),
):
    """
    Protein similarity search endpoint.

    Uses ESM-2 embeddings (1280-dim) to find structurally similar proteins
    from 573K SwissProt proteins.

    ## Example

    ```json
    {
        "query": "P04637",
        "limit": 10,
        "min_score": 0.8
    }
    ```

    ## Query formats

    - UniProt ID: "P04637"
    - Gene symbol: "TP53"
    - Protein sequence: "MEEPQSDPSVEPPLSQETFSDLWKLLPENNVLS..."

    ## Response

    Returns similar proteins ranked by ESM-2 embedding similarity.
    """
    start_time = time.time()

    try:
        logger.info(f"Protein similarity request: query='{request.query[:50]}...', limit={request.limit}")

        # Get the protein_similarity_search tool
        tool = tool_registry.get_tool("protein_similarity_search")
        if not tool:
            raise HTTPException(
                status_code=503,
                detail="Protein similarity search tool not available"
            )

        # Execute search
        result = await tool.execute(
            query=request.query,
            limit=request.limit,
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Protein similarity search failed: {result.error}"
            )

        execution_time_ms = (time.time() - start_time) * 1000

        # Convert results (tool returns similar_proteins, not results)
        matches = []
        for item in result.data.get("similar_proteins", []):
            score = item.get("score", 0.0)
            if score >= request.min_score:
                matches.append(ProteinMatch(
                    uniprot_id=item.get("protein_id", ""),
                    gene_name=item.get("gene"),
                    protein_name=item.get("name"),
                    organism=item.get("organism"),
                    score=score,
                    sequence_length=item.get("sequence_length"),
                ))

        # Extract query protein info
        query_protein = result.data.get("query_protein", {})
        query_uniprot = query_protein.get("id") if query_protein else None

        response = ProteinSimilarityResponse(
            query=request.query,
            query_uniprot=query_uniprot,
            results=matches,
            total_results=len(matches),
            collection="swissprot_esm2",
            execution_time_ms=round(execution_time_ms, 2),
        )

        logger.info(
            f"Protein similarity completed: {len(matches)} results, "
            f"time={execution_time_ms:.0f}ms"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Protein similarity search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Protein similarity search failed: {str(e)}"
        )

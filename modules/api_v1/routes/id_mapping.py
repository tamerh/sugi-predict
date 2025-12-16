"""ID mapping endpoint - direct access to ID mapping functionality."""

import logging
import time
from fastapi import APIRouter, Depends, HTTPException

from ..schemas.id_mapping import (
    IDMappingRequest,
    IDMappingResponse,
    MappingResult,
)
from ..dependencies import get_tool_registry
from ...agent_system.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/id-mapping",
    response_model=IDMappingResponse,
    summary="ID Mapping",
    description="Map biological identifiers between databases",
)
async def id_mapping(
    request: IDMappingRequest,
    tool_registry: ToolRegistry = Depends(get_tool_registry),
):
    """
    ID mapping endpoint.

    Maps biological identifiers between different databases:
    - Gene symbols ↔ UniProt
    - Gene symbols ↔ Ensembl
    - UniProt ↔ Ensembl
    - HGNC ↔ Gene symbols

    ## Example

    ```json
    {
        "ids": ["TP53", "BRCA1", "EGFR"],
        "to_type": "uniprot"
    }
    ```

    ## Response

    Returns mapping results for each input ID.
    """
    start_time = time.time()

    try:
        logger.info(f"ID mapping request: {len(request.ids)} IDs → {request.to_type}")

        # Get the biobtree_query tool
        tool = tool_registry.get_tool("biobtree_query")
        if not tool:
            raise HTTPException(
                status_code=503,
                detail="BioBTree query tool not available"
            )

        results = []
        total_mapped = 0
        total_failed = 0

        # Process each ID
        for input_id in request.ids:
            try:
                # Determine query based on target type
                # Use ensembl as intermediate step for gene symbol mappings (works better)
                if request.to_type == "uniprot":
                    # Gene symbol to UniProt via Ensembl
                    query = f"{input_id} >> ensembl >> uniprot"
                elif request.to_type == "ensembl":
                    # Gene symbol to Ensembl
                    query = f"{input_id} >> ensembl"
                elif request.to_type == "gene_symbol":
                    # UniProt to gene symbol via HGNC
                    query = f"{input_id} >> uniprot >> hgnc"
                else:
                    query = f"{input_id} >> {request.to_type}"

                # Execute query (BioBTreeQueryTool uses chain_query parameter)
                result = await tool.execute(chain_query=query)

                if result.success and result.data:
                    # Extract mapped IDs from result
                    # Result structure: {mappings: [{targets: [{id: "...", dataset: "..."}]}]}
                    mapped_ids = []
                    data = result.data

                    if isinstance(data, dict):
                        mappings = data.get("mappings", [])
                        for mapping in mappings:
                            targets = mapping.get("targets", [])
                            for target in targets:
                                target_id = target.get("id")
                                if target_id:
                                    mapped_ids.append(str(target_id))
                    elif isinstance(data, list):
                        # Fallback for list format
                        for item in data:
                            if isinstance(item, dict):
                                item_id = item.get("id") or item.get("accession") or item.get("symbol")
                                if item_id:
                                    mapped_ids.append(str(item_id))

                    if mapped_ids:
                        results.append(MappingResult(
                            input_id=input_id,
                            input_type=request.from_type or "auto",
                            mapped_ids=mapped_ids,
                            mapped_type=request.to_type,
                            success=True,
                        ))
                        total_mapped += 1
                    else:
                        results.append(MappingResult(
                            input_id=input_id,
                            input_type=request.from_type or "auto",
                            mapped_ids=[],
                            mapped_type=request.to_type,
                            success=False,
                            error="No mappings found",
                        ))
                        total_failed += 1
                else:
                    results.append(MappingResult(
                        input_id=input_id,
                        input_type=request.from_type or "auto",
                        mapped_ids=[],
                        mapped_type=request.to_type,
                        success=False,
                        error=result.error or "Query failed",
                    ))
                    total_failed += 1

            except Exception as e:
                logger.warning(f"Failed to map {input_id}: {e}")
                results.append(MappingResult(
                    input_id=input_id,
                    input_type=request.from_type or "auto",
                    mapped_ids=[],
                    mapped_type=request.to_type,
                    success=False,
                    error=str(e),
                ))
                total_failed += 1

        execution_time_ms = (time.time() - start_time) * 1000

        response = IDMappingResponse(
            results=results,
            total_input=len(request.ids),
            total_mapped=total_mapped,
            total_failed=total_failed,
            execution_time_ms=round(execution_time_ms, 2),
        )

        logger.info(
            f"ID mapping completed: {total_mapped}/{len(request.ids)} mapped, "
            f"time={execution_time_ms:.0f}ms"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ID mapping failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"ID mapping failed: {str(e)}"
        )

"""BioYoda REST API — FastAPI router for /api/*. Thin wrappers over the engine (the single source of truth)."""
from typing import Optional, List

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse, Response

from . import engine as E

router = APIRouter(prefix="/api", tags=["api"])


def _err(e):
    return JSONResponse(status_code=400, content={"error": str(e)})


@router.get("/collections")
async def api_collections():
    """The capability map: collections, their modality, and vector dim."""
    return E.collections()


@router.post("/query")
async def api_query(body: dict = Body(...)):
    """Search/filter any collection. Body: {collection, text?|smiles?|accession?, filter?, limit?, offset?}."""
    try:
        return E.query(
            collection=body["collection"], text=body.get("text"), smiles=body.get("smiles"),
            accession=body.get("accession"), text_target=body.get("text_target"), filter=body.get("filter"),
            limit=body.get("limit", 10), offset=body.get("offset"), ids=body.get("ids"),
            with_names=body.get("with_names", False), with_known=body.get("with_known", False),
        )
    except KeyError:
        return _err("'collection' is required")
    except Exception as e:
        return _err(e)


@router.post("/count")
async def api_count(body: dict = Body(...)):
    """Count points matching a filter. Body: {collection, filter?}."""
    try:
        return E.count(collection=body["collection"], filter=body.get("filter"))
    except Exception as e:
        return _err(e)


@router.get("/depict")
async def api_depict(smiles: str = Query(...), w: int = Query(240), h: int = Query(150)):
    """Render a molecule to SVG (RDKit). Run in a worker thread so concurrent renders don't block the loop."""
    import asyncio
    try:
        svg = await asyncio.to_thread(E.depict, smiles, w, h)
        if svg is None:
            return Response(status_code=404)
        return Response(content=svg, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=604800"})
    except Exception:
        return Response(status_code=404)


@router.get("/predict")
async def api_predict(smiles: str = Query(...), top: int = Query(20), human_only: bool = Query(True)):
    """Predict targets for a SMILES."""
    try:
        return E.predict(smiles, top=top, human_only=human_only)
    except Exception as e:
        return _err(e)


@router.get("/provenance")
async def api_provenance(ids: str = Query(..., description="comma-separated SureChEMBL ids"),
                         max_per: int = Query(8), epo: int = Query(1)):
    """Patent provenance for SureChEMBL id(s). With epo=1 (default) the top patents are lazily enriched with
    EPO OPS priority/filing dates and a normalized applicant; enrichment is bounded, cached per patent, run off
    the event loop, and never blocks the baked result on EPO availability."""
    try:
        prov = E.provenance([i.strip() for i in ids.split(",") if i.strip()], max_per=max_per)
        if epo:
            import asyncio
            await asyncio.to_thread(E.epo_apply, prov, 20)
        return prov
    except Exception as e:
        return _err(e)


@router.get("/patent-text-support")
async def api_patent_text_support(compound_id: int = Query(..., description="SureChEMBL int id")):
    """Does a compound's full-text patent body corroborate its chemistry-predicted target(s)? Per-prediction
    badges + the per-patent detail. Serve-time: no model load (precomputed target embeddings)."""
    try:
        return E.patent_text_support(compound_id)
    except Exception as e:
        return _err(e)


@router.get("/similar-compounds")
async def api_similar_compounds(compound_id: int = Query(..., description="SureChEMBL int id"),
                                limit: int = Query(10)):
    """Chemically nearest patent compounds (vector search on the compound's own Morgan fingerprint)."""
    try:
        return E.similar_compounds(compound_id, limit=limit)
    except Exception as e:
        return _err(e)

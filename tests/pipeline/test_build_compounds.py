#!/usr/bin/env python3
"""Tier-1 pipeline test: compounds -> patent_compounds_test.

Runs the real `bioyoda.sh build compounds ingest` in TEST MODE.  In test mode build.sh already
points the source at the work/test/ fixtures (chunks + atlas_nbrs + preds, 1000 compounds) and
targets patent_compounds_test -- no --prod, no GPU (the GPU `predict` stage is pre-computed in the
fixture as work/test/atlas_nbrs).

Asserts: the collection is created, has ~1000 points, a representative point has the expected
chemical payload (surechembl_id + smiles), and a vector search returns neighbours.

  python tests/pipeline/test_build_compounds.py

Runtime: ~2-3 min (Pass-1 Tanimoto scoring over the 1000-compound fixture dominates).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import client, drop, run_build, assert_build_ok, wait_count

COLL = "patent_compounds_test"


def test_build_compounds():
    qc = client()
    drop(qc, COLL)

    # ingest = score neighbours + align + upsert into patent_compounds_test (the core build pass).
    # (provenance/denoise need a patents.parquet + map snapshot the small fixture doesn't ship, and
    #  predict needs a GPU -- so we exercise the ingest pass, which is what populates the collection.)
    r = run_build("compounds", "ingest", timeout=900)
    assert_build_ok(r, "compounds ingest")

    n = wait_count(qc, COLL)
    assert n >= 900, f"expected ~1000 compounds, got {n}"

    # representative payload: chemical modality => surechembl_id + smiles present
    pt = qc.scroll(COLL, limit=1, with_payload=True, with_vectors=False)[0][0]
    assert "surechembl_id" in pt.payload, f"missing surechembl_id in payload: {list(pt.payload)}"
    assert "smiles" in pt.payload, f"missing smiles in payload: {list(pt.payload)}"

    # representative query: vector search by an existing point's own 2048-d Morgan FP returns itself top-1
    p = qc.retrieve(COLL, ids=[pt.id], with_vectors=True)[0]
    hits = qc.query_points(COLL, query=p.vector, limit=3, with_payload=False).points
    assert len(hits) >= 1, "vector search returned nothing"
    assert hits[0].id == pt.id, f"self-search should return the point itself top-1 (got {hits[0].id})"

    print(f"test_build_compounds: PASSED ({n} compounds in {COLL}, payload + vector search OK)")


if __name__ == "__main__":
    test_build_compounds()

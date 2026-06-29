#!/usr/bin/env python3
"""Tier-2 LIVE gate for the Sugi Predict SMILES search — the ENGINE REST API.

READ-ONLY. Hits http://localhost:8011/api (BIOYODA_API env honored). Where
test_collections_health proves the collections are present and test_known_answers
proves Qdrant gives the right answers, THIS proves the two request-time endpoints the
web SMILES box depends on still work end to end:

  /api/predict?smiles=   the FPSim2 target predictor  (drives the predicted-targets view)
  /api/query {smiles}    the Qdrant structure search   (drives direct-hit redirect + similars)

The predict check on a KNOWN drug would have caught the corrupt chembl_reference FPSim2
index that was returning an HDF5 error (predictions came back empty / 500). The query
check pins the direct-hit signal: an in-DB molecule's top hit must carry exact_match +
best_tanimoto==1.0 + a surechembl_id (what predict_page redirects on). The nonsense-SMILES
check pins graceful degradation (no 500, predictions still returned).

  /data/miniconda3/envs/bioyoda/bin/python tests/integration/test_smiles_search.py
"""
import os
import sys

import httpx

API = os.environ.get("BIOYODA_API", "http://localhost:8011/api")

# aspirin — its real curated/known mechanism targets are the COX enzymes.
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
ASPIRIN_MUST_HAVE = {"PTGS1", "PTGS2"}

# imatinib — predictions must include a real kinase target (ABL1 or KIT). Non-empty
# predictions here is exactly the signal the corrupt FPSim2 index destroyed.
IMATINIB = "Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C"
IMATINIB_KINASE_ANY = {"ABL1", "KIT", "ABL2", "PDGFRA", "PDGFRB"}

# a valid but absurd molecule that is not a real drug — must still degrade gracefully.
NONSENSE = "CCCCCCCCCCCCCCCCNCCCCCCCCCCCCCCCCCC"

ATLAS = "patent_compounds"


def _client():
    return httpx.Client(base_url=API, timeout=90)


def _genes(predictions):
    return {(p.get("gene") or "").upper() for p in (predictions or [])}


def test_predict_aspirin_known_targets():
    """/api/predict for aspirin returns the COX known targets."""
    with _client() as c:
        r = c.get("/predict", params={"smiles": ASPIRIN, "top": 20})
    assert r.status_code == 200, f"/predict aspirin HTTP {r.status_code}"
    d = r.json()
    assert not d.get("error"), f"/predict aspirin returned error: {d.get('error')!r}"
    preds = d.get("predictions") or []
    assert preds, "/predict aspirin returned NO predictions — FPSim2 predictor is broken (HDF5/index error?)"
    known = set(d.get("known") or [])
    # COX targets should be in the curated `known` set (they're the validation answer key).
    have = ASPIRIN_MUST_HAVE & (known | _genes(preds))
    assert ASPIRIN_MUST_HAVE <= (known | _genes(preds)), (
        f"aspirin lost its COX targets {ASPIRIN_MUST_HAVE} — got known={sorted(known)}, "
        f"have={sorted(have)}. The known-target answer key has regressed.")
    print(f"  predict aspirin: {len(preds)} predictions, known={sorted(known)}")


def test_predict_imatinib_kinase():
    """/api/predict for imatinib returns non-empty predictions incl. a known kinase."""
    with _client() as c:
        r = c.get("/predict", params={"smiles": IMATINIB, "top": 20})
    assert r.status_code == 200, f"/predict imatinib HTTP {r.status_code}"
    d = r.json()
    assert not d.get("error"), f"/predict imatinib returned error: {d.get('error')!r}"
    preds = d.get("predictions") or []
    assert preds, (
        "/predict imatinib returned NO predictions — this is the exact symptom of the "
        "corrupt chembl_reference FPSim2 index (HDF5 error). The predictor is broken.")
    genes = _genes(preds) | set(g.upper() for g in (d.get("known") or []))
    hit = IMATINIB_KINASE_ANY & genes
    assert hit, (
        f"imatinib predictions include NO known kinase target {sorted(IMATINIB_KINASE_ANY)} "
        f"— got {sorted(genes)[:10]}... The ligand->target prediction has regressed.")
    print(f"  predict imatinib: {len(preds)} predictions, kinase hit={sorted(hit)}")


def test_query_structure_direct_hit():
    """/api/query {smiles} for an in-DB molecule: top hit is an exact match w/ a SureChEMBL id.

    This is the signal predict_page redirects on (direct hit -> full compound page)."""
    with _client() as c:
        r = c.post("/query", json={"collection": ATLAS, "smiles": IMATINIB, "limit": 8,
                                   "with_names": True})
    assert r.status_code == 200, f"/query imatinib HTTP {r.status_code}"
    hits = r.json().get("hits") or []
    assert hits, "/query imatinib returned NO hits — Qdrant structure search is broken"
    pl = hits[0].get("payload") or {}
    assert pl.get("exact_match") is True, (
        f"in-DB imatinib top hit exact_match={pl.get('exact_match')!r}, expected True "
        f"— the direct-hit redirect would silently never fire")
    assert float(pl.get("best_tanimoto", 0)) == 1.0, (
        f"in-DB imatinib top hit best_tanimoto={pl.get('best_tanimoto')!r}, expected 1.0")
    sid = pl.get("surechembl_id") or ""
    assert sid.startswith("SCHEMBL"), f"top hit missing a SureChEMBL id (got {sid!r})"
    print(f"  query imatinib: top hit {sid} exact_match=True tanimoto=1.0 name={pl.get('name')!r}")


def test_query_structure_returns_similars():
    """/api/query {smiles} returns several neighbours (the 'Similar compounds' block)."""
    with _client() as c:
        r = c.post("/query", json={"collection": ATLAS, "smiles": ASPIRIN, "limit": 8,
                                   "with_names": True})
    assert r.status_code == 200, f"/query aspirin HTTP {r.status_code}"
    hits = r.json().get("hits") or []
    assert len(hits) >= 1, "/query aspirin returned no neighbours for the similars block"
    # every card needs a surechembl_id + smiles to render
    for h in hits:
        pl = h.get("payload") or {}
        assert pl.get("surechembl_id") and pl.get("smiles"), (
            f"a similar hit is missing surechembl_id/smiles: {pl!r}")
    print(f"  query aspirin: {len(hits)} similar hits, all renderable (sid+smiles)")


def test_nonsense_smiles_graceful():
    """A valid-but-not-a-drug SMILES still returns predictions, no 500 (graceful)."""
    with _client() as c:
        rp = c.get("/predict", params={"smiles": NONSENSE, "top": 20})
        rq = c.post("/query", json={"collection": ATLAS, "smiles": NONSENSE, "limit": 8})
    assert rp.status_code == 200, f"/predict nonsense HTTP {rp.status_code} (should degrade, not 500)"
    dp = rp.json()
    assert not dp.get("error"), f"/predict nonsense returned error: {dp.get('error')!r}"
    assert dp.get("predictions"), "/predict nonsense returned no predictions (should still produce some)"
    assert rq.status_code == 200, f"/query nonsense HTTP {rq.status_code} (should degrade, not 500)"
    # A binary-fingerprint collision can score 1.0 while NOT being an exact structure match;
    # the engine must report exact_match=False so the web does NOT wrongly redirect.
    qhits = rq.json().get("hits") or []
    if qhits:
        top = (qhits[0].get("payload") or {})
        assert top.get("exact_match") is not True, (
            "/query nonsense top hit reports exact_match=True for a molecule that is NOT in "
            "the DB — the direct-hit redirect would fire on the wrong compound")
    print(f"  nonsense SMILES: predict OK ({len(dp['predictions'])} preds), "
          f"query OK ({len(qhits)} hits, top exact_match={'n/a' if not qhits else (qhits[0].get('payload') or {}).get('exact_match')})")


TESTS = [
    test_predict_aspirin_known_targets,
    test_predict_imatinib_kinase,
    test_query_structure_direct_hit,
    test_query_structure_returns_similars,
    test_nonsense_smiles_graceful,
]


if __name__ == "__main__":
    failed = 0
    for fn in TESTS:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"  FAILED [{fn.__name__}]: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR  [{fn.__name__}]: {type(e).__name__}: {e}")
    if failed:
        print(f"test_smiles_search: FAILED ({failed}/{len(TESTS)} checks)")
        sys.exit(1)
    print("test_smiles_search: PASSED (predict aspirin/imatinib targets, query direct-hit + "
          "similars, nonsense graceful)")

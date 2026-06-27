#!/usr/bin/env python3
"""Tier-2 LIVE known-answer gate for BioYoda's production Qdrant collections.

READ-ONLY. Only count / retrieve / scroll / query_points — never writes or deletes.
Where test_collections_health.py proves the collections are present and indexed,
THIS proves they still give the right answers, so a silently-bad rebuild (vectors
shuffled, payloads dropped, a filter field unmapped) is caught.

Each assertion is a floor or a range chosen well inside the known-good values so
ordinary growth won't trip it, but a real regression (EGFR landscape collapsing to
~0, imatinib losing ABL1/KIT, HNSW returning garbage) will.

  /data/miniconda3/envs/bioyoda/bin/python tests/integration/test_known_answers.py

Field names below were read off real points on 2026-06-27 (not assumed):
  patent_compounds_v2 payload: surechembl_id, smiles, inchi_key, mol_weight,
      targets[UniProt-acc, keyword-indexed], predicted[{acc,gene,conf,support}], prov
  clinical_trials_medcpt payload: nct_id, brief_title, chunk_type, ... (nct_id NOT indexed)
  chembl payload: cid, smiles, targets[UniProt-acc], source
"""
import os
import sys
import time

from qdrant_client import QdrantClient, models

QDRANT = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")

PC = "patent_compounds_v2"   # the patent_compounds alias target
CT = "clinical_trials_medcpt"
CHEMBL = "chembl"
ESM2 = "esm2"
PTEXT = "patents_text_medcpt"

# A green in-RAM/HNSW vector search returns in well under this. Warm latencies
# observed: patent_compounds ~11ms, chembl ~4ms, esm2 ~4ms. We give a generous
# ceiling so a busy box (concurrent biobtree/build) won't flake the gate, while a
# truly wedged index (seconds) still fails.
LATENCY_CEILING_MS = 750

# imatinib (SCHEMBL3827, point id 3827) — its real primary targets. The atlas must
# keep predicting these or a rebuild has corrupted the ligand->target map.
IMATINIB_ID = 3827
IMATINIB_MUST_HAVE = {  # UniProt acc -> gene, for a readable failure
    "P00519": "ABL1",
    "P11274": "BCR",
    "P10721": "KIT",
}

# EGFR = UniProt P00533. The patent landscape for it is large (~841,765 now).
EGFR = "P00533"
EGFR_RANGE = (500_000, 1_500_000)


def _qc():
    return QdrantClient(url=QDRANT, timeout=300, check_compatibility=False)


def test_egfr_landscape():
    """count(patent_compounds where targets contains P00533) is in a sane range."""
    qc = _qc()
    flt = models.Filter(must=[models.FieldCondition(
        key="targets", match=models.MatchValue(value=EGFR))])
    t = time.time()
    n = qc.count(PC, count_filter=flt, exact=True).count
    dt = (time.time() - t) * 1000
    lo, hi = EGFR_RANGE
    assert lo <= n <= hi, (
        f"EGFR (P00533) landscape count = {n:,}, expected within {lo:,}..{hi:,}. "
        f"A collapse to ~0 means the `targets` keyword index or the bake was lost; "
        f"a blowout means the target map is corrupted.")
    print(f"  EGFR landscape: {n:,} compounds target P00533  ({dt:.0f}ms)")


def test_imatinib_targets():
    """imatinib (id 3827) still carries its real targets in both targets[] and predicted[]."""
    qc = _qc()
    rec = qc.retrieve(PC, ids=[IMATINIB_ID], with_payload=True)
    assert rec, f"imatinib point id {IMATINIB_ID} not found in {PC}"
    pl = rec[0].payload
    assert pl.get("surechembl_id") == "SCHEMBL3827", (
        f"id {IMATINIB_ID} is no longer SCHEMBL3827 (got {pl.get('surechembl_id')!r}) "
        f"— point ids were reshuffled by a rebuild")

    targets = set(pl.get("targets") or [])
    predicted_accs = {p.get("acc") for p in (pl.get("predicted") or [])}
    predicted_genes = {(p.get("gene") or "").upper() for p in (pl.get("predicted") or [])}

    for acc, gene in IMATINIB_MUST_HAVE.items():
        in_targets = acc in targets
        in_predicted = acc in predicted_accs or gene.upper() in predicted_genes
        assert in_targets or in_predicted, (
            f"imatinib lost its {gene} ({acc}) target — present in targets={in_targets}, "
            f"predicted={in_predicted}. The ligand->target prediction has regressed.")
    print(f"  imatinib (SCHEMBL3827): keeps {sorted(IMATINIB_MUST_HAVE.values())} "
          f"({len(targets)} targets, {len(predicted_accs)} predicted)")


def _self_search(qc, coll, pid, label):
    """A point's own vector must return itself at score ~1.0 within the top-k, fast.

    NOTE: BINARY-quantized fingerprint collections (patent_compounds, chembl) have
    many identical fingerprints, so the literal top-1 is often a DUPLICATE rather
    than the query point. We therefore assert the point is in the top-k AND that
    top-1 score is ~1.0 (perfect self-similarity), which is what catches a shuffled
    or garbage HNSW. int8 quant can round a cosine slightly above 1.0, so the bound
    is >= 0.99, not == 1.0.
    """
    rec = qc.retrieve(coll, ids=[pid], with_vectors=True)
    assert rec and rec[0].vector is not None, f"{label}: point {pid} has no vector"
    vec = rec[0].vector
    qc.query_points(coll, query=vec, limit=10, with_payload=False)  # warm
    t = time.time()
    res = qc.query_points(coll, query=vec, limit=20, with_payload=False).points
    dt = (time.time() - t) * 1000
    ids = [r.id for r in res]
    assert pid in ids, (
        f"{label}: self-search for point {pid} did NOT return itself in top-20 "
        f"(got {ids[:5]}...) — HNSW is returning garbage")
    assert res[0].score >= 0.99, (
        f"{label}: top-1 self-similarity score {res[0].score:.4f} < 0.99 — "
        f"distance metric or vectors are corrupted")
    assert dt < LATENCY_CEILING_MS, (
        f"{label}: warm vector search took {dt:.0f}ms (> {LATENCY_CEILING_MS}ms) "
        f"— index may be wedged or mmap is thrashing")
    rank = ids.index(pid)
    print(f"  {label}: self {pid} found at rank {rank}, top1 score={res[0].score:.4f}, {dt:.0f}ms")


def test_vector_self_search():
    """HNSW sanity on the two owned-fingerprint collections."""
    qc = _qc()
    _self_search(qc, PC, IMATINIB_ID, "patent_compounds self-search")
    _self_search(qc, CHEMBL, 6, "chembl self-search")


def test_chembl_known_ligand():
    """A known ChEMBL ligand keeps its target label (cid 6 -> P00811)."""
    qc = _qc()
    pts, _ = qc.scroll(CHEMBL, limit=1, with_payload=True,
                       scroll_filter=models.Filter(must=[models.FieldCondition(
                           key="cid", match=models.MatchValue(value=6))]))
    assert pts, "chembl cid=6 not found"
    pl = pts[0].payload
    assert "P00811" in (pl.get("targets") or []), (
        f"chembl cid=6 lost its P00811 target (got {pl.get('targets')}) "
        f"— ligand->target answer key corrupted")
    print(f"  chembl cid=6: targets={pl.get('targets')}")


def test_clinical_trials_filter():
    """clinical_trials_medcpt returns chunks for a known nct_id.

    nct_id is NOT payload-indexed, so this is a filtered scroll (full scan). We keep
    limit small and rely on the client timeout; it proves the trial is still present
    and addressable by id, which a dropped/reingested collection would break.
    """
    qc = _qc()
    nct = "NCT04131569"
    flt = models.Filter(must=[models.FieldCondition(
        key="nct_id", match=models.MatchValue(value=nct))])
    t = time.time()
    pts, _ = qc.scroll(CT, scroll_filter=flt, limit=3, with_payload=["nct_id", "brief_title"])
    dt = (time.time() - t) * 1000
    assert pts, f"clinical_trials: no chunks for {nct} — trial missing or nct_id field renamed"
    assert pts[0].payload.get("nct_id") == nct
    print(f"  clinical_trials: {nct} -> {len(pts)} chunk(s), "
          f"title={pts[0].payload.get('brief_title')!r}  ({dt:.0f}ms)")


def test_patents_text_addressable():
    """patents_text_medcpt is present and a point is retrievable by id."""
    qc = _qc()
    pts, _ = qc.scroll(PTEXT, limit=1, with_payload=["patent_id"])
    assert pts, "patents_text_medcpt is empty"
    pid = pts[0].id
    r = qc.retrieve(PTEXT, ids=[pid], with_payload=["patent_id"])
    assert r and r[0].payload.get("patent_id"), "patents_text point missing patent_id"
    print(f"  patents_text: point {pid} -> {r[0].payload.get('patent_id')}")


TESTS = [
    test_egfr_landscape,
    test_imatinib_targets,
    test_vector_self_search,
    test_chembl_known_ligand,
    test_clinical_trials_filter,
    test_patents_text_addressable,
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
        print(f"test_known_answers: FAILED ({failed}/{len(TESTS)} checks)")
        sys.exit(1)
    print("test_known_answers: PASSED (EGFR landscape, imatinib targets, self-search, "
          "chembl/CT/patents_text answers all correct)")

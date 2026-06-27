#!/usr/bin/env python3
"""Tier-1 pipeline test: proteins (esm2) -> esm2_test.

Runs the real `bioyoda.sh build proteins all --full` in TEST MODE through prepare -> embed -> insert.
The protein SOURCE does NOT auto-switch to a fixture, so we point ESM2_SOURCE_FASTA at the small
fixture (60 SwissProt sequences).  Embed runs ESM-2 650M (esm2_t33_650M_UR50D, dim 1280) on CPU --
the model is cached in torch hub and the fixture's short sequences embed in well under a minute
(no GPU/pod).  Test-mode scratch/state is isolated under work/test/ (build.sh suffix logic), so the
prod esm2 chunks/state are never touched.

Asserts: esm2_test is created, has ~60 points, the vectors are 1280-d, and a payload filter by a
known fixture accession returns the protein.

  python tests/pipeline/test_build_proteins.py

Runtime: ~1-2 min (ESM-2 model load + 60 short-sequence embeds on CPU).
"""
import os
import sys

from qdrant_client import models

sys.path.insert(0, os.path.dirname(__file__))
from _common import ROOT, client, drop, run_build, assert_build_ok, wait_count

COLL = "esm2_test"
FIXTURE_FASTA = os.path.join(ROOT, "tests/fixtures/esm2/reference_proteins.fasta")
KNOWN_ACC = "Q6GZX4"  # >sp|Q6GZX4|001R_FRG3G — first protein in the fixture; payload protein_id == accession


def test_build_proteins():
    qc = client()
    drop(qc, COLL)

    # --full so prepare splits the whole fixture (no delta filter); ESM2_SOURCE_FASTA points at the fixture.
    r = run_build("proteins", "all", env={"ESM2_SOURCE_FASTA": FIXTURE_FASTA}, extra=["--full"], timeout=900)
    assert_build_ok(r, "proteins all")

    n = wait_count(qc, COLL)
    assert n >= 50, f"expected ~60 proteins, got {n}"

    # vectors must be ESM-2 1280-d
    info = qc.get_collection(COLL)
    dim = info.config.params.vectors.size
    assert dim == 1280, f"expected 1280-d ESM-2 vectors, got {dim}"

    # representative query: a known fixture accession is present (payload protein_id == accession)
    flt = models.Filter(must=[models.FieldCondition(key="protein_id", match=models.MatchValue(value=KNOWN_ACC))])
    hits = qc.scroll(COLL, scroll_filter=flt, limit=2, with_payload=True)[0]
    assert hits, f"accession {KNOWN_ACC} not found in {COLL}"
    assert hits[0].payload.get("protein_id") == KNOWN_ACC

    print(f"test_build_proteins: PASSED ({n} proteins in {COLL}, 1280-d, accession {KNOWN_ACC} present)")


if __name__ == "__main__":
    test_build_proteins()

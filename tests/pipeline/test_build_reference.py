#!/usr/bin/env python3
"""Tier-1 pipeline test: reference (chembl) -> chembl_test.

Runs the real `bioyoda.sh build reference chembl` in TEST MODE.  The reference SOURCE is the full
1.25M-row work/chembl_reference; we point it at a tiny fixture (10 real ChEMBL cid/smiles rows +
their cid_targets) via CHEMBL_REF_DIR.  No embed model -- Morgan/ECFP4 fingerprints are computed
on CPU by RDKit, so this is the fastest collection to build.

Asserts: chembl_test is created, has 10 points, vectors are 2048-d, and a retrieve by a known cid
returns the expected chemical payload (cid + smiles + targets list).

  python tests/pipeline/test_build_reference.py

Runtime: ~20 s (RDKit fingerprints for 10 compounds + HNSW build on a tiny collection).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import ROOT, client, drop, run_build, assert_build_ok, wait_count

COLL = "chembl_test"
FIXTURE_REF = os.path.join(ROOT, "tests/fixtures/chembl")  # reference.tsv + cid_targets.json


def _first_cid():
    with open(os.path.join(FIXTURE_REF, "reference.tsv")) as f:
        return int(f.readline().split("\t", 1)[0])


def test_build_reference():
    qc = client()
    drop(qc, COLL)

    r = run_build("reference", "chembl", env={"CHEMBL_REF_DIR": FIXTURE_REF}, timeout=300)
    assert_build_ok(r, "reference chembl")

    n = wait_count(qc, COLL)
    assert n == 10, f"expected 10 ChEMBL reference compounds, got {n}"

    info = qc.get_collection(COLL)
    dim = info.config.params.vectors.size
    assert dim == 2048, f"expected 2048-d Morgan vectors, got {dim}"

    # representative query: retrieve by a known cid (point id == pubchem cid)
    cid = _first_cid()
    pts = qc.retrieve(COLL, ids=[cid], with_payload=True)
    assert pts, f"cid {cid} not found in {COLL}"
    pl = pts[0].payload
    assert pl.get("cid") == cid and "smiles" in pl and "targets" in pl, f"unexpected payload: {list(pl)}"

    print(f"test_build_reference: PASSED ({n} compounds in {COLL}, 2048-d, cid {cid} payload OK)")


if __name__ == "__main__":
    test_build_reference()

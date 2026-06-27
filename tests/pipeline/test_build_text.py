#!/usr/bin/env python3
"""Tier-1 pipeline test: text (pubmed) -> pubmed_abstracts_medcpt_test.

Runs the real `bioyoda.sh build text all` in TEST MODE through chunk -> embed -> insert.  The pubmed
SOURCE does NOT auto-switch to a fixture, so we point PUBMED_RAW_DIR at a scratch dir holding the
50-abstract fixture under baseline/ (the chunk step globs <raw>/baseline/*.xml.gz).  Embed runs
MedCPT-Article on CPU (cached model; 50 abstracts in seconds after the model load).

Asserts: pubmed_abstracts_medcpt_test is created, has ~50 points, and a retrieve by a known fixture
PMID (point id == pmid) returns the abstract with its text payload.

  python tests/pipeline/test_build_text.py

Runtime: ~1 min (MedCPT model load on CPU dominates).  No GPU/pod required.
"""
import gzip
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
from _common import ROOT, client, drop, run_build, assert_build_ok, wait_count

COLL = "pubmed_abstracts_medcpt_test"
FIXTURE_XML = os.path.join(ROOT, "tests/fixtures/pubmed/test_abstracts.xml.gz")
KNOWN_PMID = 10912848  # present in the fixture; point id == pmid (direct int)


def test_build_text():
    qc = client()
    drop(qc, COLL)

    # chunk_pubmed_to_jsonl globs <raw-dir>/baseline/*.xml.gz -> stage the fixture there.
    raw = tempfile.mkdtemp(prefix="pm_raw_")
    os.makedirs(os.path.join(raw, "baseline"))
    shutil.copy(FIXTURE_XML, os.path.join(raw, "baseline", "pubmed_test_0001.xml.gz"))
    try:
        r = run_build("text", "all", env={"PUBMED_RAW_DIR": raw}, extra=["--full"], timeout=900)
        assert_build_ok(r, "text all")

        n = wait_count(qc, COLL)
        assert n >= 40, f"expected ~50 abstracts, got {n}"

        # representative query: retrieve by a known PMID (the point id is the pmid itself)
        pts = qc.retrieve(COLL, ids=[KNOWN_PMID], with_payload=True)
        assert pts, f"PMID {KNOWN_PMID} not found in {COLL}"
        assert str(pts[0].payload.get("pmid")) == str(KNOWN_PMID)
        assert "source" in pts[0].payload, f"missing source: {list(pts[0].payload)}"

        print(f"test_build_text: PASSED ({n} points in {COLL}, retrieve PMID {KNOWN_PMID} OK)")
    finally:
        shutil.rmtree(raw, ignore_errors=True)


if __name__ == "__main__":
    test_build_text()

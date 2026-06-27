#!/usr/bin/env python3
"""Tier-1 pipeline test: trials -> clinical_trials_medcpt_test.

Runs the real `bioyoda.sh build trials all` in TEST MODE through the full chunk -> embed -> insert
chain.  The trials SOURCE does NOT auto-switch to a fixture, so we point it at the small fixture
(5 trials) via CT_TRIALS_JSON.  Embed runs MedCPT-Article on CPU (device=auto -> cpu here): the
model is cached locally and 5 trials (~35 section-chunks) embed in seconds after a ~30s model load.

Asserts: clinical_trials_medcpt_test is created, has >0 points, and a filter by a known fixture
nct_id returns the trial's section(s) with the expected payload.

  python tests/pipeline/test_build_trials.py

Runtime: ~1 min (dominated by the MedCPT model load on CPU).  No GPU/pod required.
"""
import os
import sys

from qdrant_client import models

sys.path.insert(0, os.path.dirname(__file__))
from _common import ROOT, client, drop, run_build, assert_build_ok, wait_count

COLL = "clinical_trials_medcpt_test"
FIXTURE = os.path.join(ROOT, "tests/fixtures/clinical_trials/trials_small.json")
KNOWN_NCT = "NCT01990365"  # first trial in trials_small.json


def test_build_trials():
    qc = client()
    drop(qc, COLL)

    # --full so the chunk step ignores any prior tracking DB; CT_TRIALS_JSON points the source at the fixture.
    env = {"CT_TRIALS_JSON": FIXTURE}
    r = run_build("trials", "all", env=env, extra=["--full"], timeout=900)
    assert_build_ok(r, "trials all")

    n = wait_count(qc, COLL)
    assert n > 0, f"clinical_trials_medcpt_test is empty (got {n})"

    # representative query: a known fixture nct_id must be present (its section chunks)
    flt = models.Filter(must=[models.FieldCondition(key="nct_id", match=models.MatchValue(value=KNOWN_NCT))])
    hits = qc.scroll(COLL, scroll_filter=flt, limit=10, with_payload=True)[0]
    assert hits, f"no points for known nct_id {KNOWN_NCT}"
    assert hits[0].payload.get("nct_id") == KNOWN_NCT
    assert "brief_title" in hits[0].payload, f"missing brief_title: {list(hits[0].payload)}"

    print(f"test_build_trials: PASSED ({n} points in {COLL}, nct_id filter returns {KNOWN_NCT})")


if __name__ == "__main__":
    test_build_trials()

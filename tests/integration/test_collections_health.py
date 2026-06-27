#!/usr/bin/env python3
"""Tier-2 LIVE health gate for BioYoda's production Qdrant collections.

READ-ONLY. This only calls get_aliases / get_collection — it never writes, deletes,
re-optimizes, or upserts anything. Run before and after a data update to catch a
regression: a dropped/renamed collection, a wedged or yellow (not-fully-indexed)
HNSW, or a points_count that collapsed.

Assertions per production collection:
  * status is GREEN (optimizer idle, index built),
  * indexed_vectors_count is within tolerance of points_count (fully indexed —
    Qdrant may report a few % over/under due to deleted or duplicate vectors),
  * points_count >= a floor a bit below the known-good June-2026 state. Floors only
    (updates ADD data); we do NOT assert exact equality.

The two aliases (patent_compounds -> patent_compounds_v2, patents_text ->
patents_text_medcpt) are also asserted, because the query tools resolve through them.

  /data/miniconda3/envs/bioyoda/bin/python tests/integration/test_collections_health.py
"""
import os
import sys

from qdrant_client import QdrantClient

QDRANT = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")

# Expected aliases the query layer depends on.
EXPECTED_ALIASES = {
    "patent_compounds": "patent_compounds_v2",
    "patents_text": "patents_text_medcpt",
}

# Floors set ~3-5% below the known-good June-2026 counts (DB only grows).
# (real_value_observed_2026-06-27 in the comment for sanity-checking the floor.)
EXPECTED = {
    "patent_compounds_v2":   {"floor":   29_000_000},  # ~30,937,359
    "clinical_trials_medcpt": {"floor":   4_300_000},  #  ~4,475,522
    "patents_text_medcpt":   {"floor":   38_000_000},  # ~39,614,358
    "esm2":                  {"floor":     560_000},   #    ~574,648
    "chembl":                {"floor":   1_200_000},   #  ~1,248,456
}

# How far indexed_vectors_count may drift from points_count and still count as
# "fully indexed". Deleted/duplicate vectors push this both ways (clinical_trials
# reports slightly OVER, patents_text slightly UNDER), so the band is symmetric.
INDEX_TOLERANCE = 0.02  # 2%


def test_aliases():
    qc = QdrantClient(url=QDRANT, timeout=60, check_compatibility=False)
    live = {a.alias_name: a.collection_name for a in qc.get_aliases().aliases}
    for alias, target in EXPECTED_ALIASES.items():
        assert live.get(alias) == target, (
            f"alias {alias!r} -> {live.get(alias)!r}, expected {target!r}")
    print(f"  aliases OK: {EXPECTED_ALIASES}")


def test_health():
    qc = QdrantClient(url=QDRANT, timeout=60, check_compatibility=False)
    live = {c.name for c in qc.get_collections().collections}

    for name, exp in EXPECTED.items():
        assert name in live, f"production collection {name!r} is MISSING from {sorted(live)}"
        ci = qc.get_collection(name)

        status = str(ci.status).lower()
        assert status.endswith("green") or status == "green", (
            f"{name}: status is {ci.status!r}, expected GREEN (a yellow/red index "
            f"means HNSW is still building or wedged)")

        pts = ci.points_count or 0
        idx = ci.indexed_vectors_count or 0
        assert pts >= exp["floor"], (
            f"{name}: points_count {pts:,} fell below floor {exp['floor']:,} — "
            f"a collection LOST data (or a bad rebuild dropped points)")

        # Fully indexed: indexed vectors within +/-INDEX_TOLERANCE of points.
        lo = pts * (1 - INDEX_TOLERANCE)
        hi = pts * (1 + INDEX_TOLERANCE)
        assert lo <= idx <= hi, (
            f"{name}: indexed_vectors {idx:,} not within +/-{INDEX_TOLERANCE:.0%} of "
            f"points {pts:,} — index is NOT fully built (wedged/partial HNSW)")

        # optimizer_status == ok (string 'ok' or an object that stringifies to ok)
        opt = str(ci.optimizer_status).lower()
        assert "ok" in opt, f"{name}: optimizer_status is {ci.optimizer_status!r}, expected ok"

        print(f"  {name}: GREEN  points={pts:,}  indexed={idx:,}  "
              f"(floor {exp['floor']:,})  optimizer={opt}")


if __name__ == "__main__":
    try:
        test_aliases()
        test_health()
    except AssertionError as e:
        print(f"test_collections_health: FAILED\n  {e}")
        sys.exit(1)
    print("test_collections_health: PASSED (all production collections green, fully indexed, above floor)")

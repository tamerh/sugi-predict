#!/usr/bin/env python3
"""Small-data test for the target de-noise (modules/compounds/bake_targets.py).

Builds a throwaway collection with hand-crafted `predicted` lists, runs the bake, and asserts `targets`
becomes the floored (drop support==1 & conf<0.4) + capped, conf-descending strong membership -- while
`predicted` is left untouched. Self-contained; touches only a temp collection.

  python tests/test_atlas_targets.py        (or via `bioyoda.sh test --atlas`)
"""
import os, sys, time
from qdrant_client import QdrantClient, models

QDRANT = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")
COLL = "test_targets_tmp"
BAKE = "/data/bioyoda/modules/compounds/bake_targets.py"


def _run(*args):
    import subprocess
    r = subprocess.run([sys.executable, BAKE, "--collection", COLL, *args], capture_output=True, text=True)
    assert r.returncode == 0, f"bake failed:\n{r.stderr}"


def test_targets():
    qc = QdrantClient(url=QDRANT, timeout=60)
    try:
        qc.delete_collection(COLL)
    except Exception:
        pass
    qc.create_collection(COLL, vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
    pred = [
        {"acc": "P1", "conf": 0.80, "support": 5},   # keep — strong conf + support
        {"acc": "P2", "conf": 0.35, "support": 1},   # DROP — support 1 AND conf < 0.4
        {"acc": "P3", "conf": 0.45, "support": 1},   # keep — conf >= 0.4 saves the singleton
        {"acc": "P4", "conf": 0.30, "support": 3},   # keep — support >= 2 saves low conf
    ]
    qc.upsert(COLL, points=[models.PointStruct(id=1, vector=[0.0, 0.0],
              payload={"predicted": pred, "targets": [p["acc"] for p in pred]})])

    _run("--floor", "0.4", "--cap", "50", "--ckpt", "/tmp/_tt.ckpt")
    time.sleep(1)
    pl = qc.retrieve(COLL, ids=[1], with_payload=True)[0].payload
    assert pl["targets"] == ["P1", "P3", "P4"], pl["targets"]            # P2 dropped, conf-descending
    assert len(pl["predicted"]) == 4, "predicted must be left untouched"

    _run("--floor", "0.4", "--cap", "2", "--ckpt", "/tmp/_tt2.ckpt")     # cap takes the top-2 by conf
    time.sleep(1)
    assert qc.retrieve(COLL, ids=[1], with_payload=["targets"])[0].payload["targets"] == ["P1", "P3"], "cap"

    qc.delete_collection(COLL)
    print("test_atlas_targets: PASSED (floored + capped membership, predicted untouched)")


if __name__ == "__main__":
    test_targets()

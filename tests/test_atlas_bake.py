#!/usr/bin/env python3
"""Small-data pipeline test for the provenance bake (modules/compounds/bake_provenance.py).

Builds a tiny SureChEMBL-shaped fixture (patent_compound_map + patents parquet) and a throwaway Qdrant
collection, runs the bake step end-to-end, and asserts each compound's payload gets the correct top-N
provenance span (claimed-first, foundational+recent). Self-contained; touches only a temp collection.

  python tests/test_atlas_bake.py        (or via `bioyoda.sh test --atlas`)
"""
import os, sys, time, tempfile, shutil, subprocess
import pyarrow as pa, pyarrow.parquet as pq
from qdrant_client import QdrantClient, models

QDRANT = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")
COLL = "test_bake_tmp"
BAKE = "/data/bioyoda/modules/compounds/bake_provenance.py"


def test_bake():
    tmp = tempfile.mkdtemp(); snap = os.path.join(tmp, "snap"); os.makedirs(snap)
    # patents fixture
    pq.write_table(pa.table({
        "id": [10, 11, 12, 20],
        "patent_number": ["US-1-A", "US-2-A", "US-3-A", "US-9-A"],
        "country": ["US", "US", "US", "US"],
        "publication_date": ["1995-01-01", "2010-01-01", "2020-01-01", "2001-01-01"],
        "asignee": [["Acme"], ["Beta"], ["Gamma"], ["Delta"]],
        "title": ["old", "mid", "new", "other"],
    }), os.path.join(snap, "patents.parquet"))
    # map fixture, deliberately UNSORTED (a compound's links scattered, compounds interleaved) to mirror the
    # real map -- a naive "group by consecutive compound_id" stream would mis-bake compound 1 here. field_id==2 => claimed.
    #   compound 1: patent 10 claimed (1995); 11,12 disclosed (2010,2020).  compound 2: patent 20 claimed (2001).
    pq.write_table(pa.table({
        "compound_id": [1, 2, 1, 1], "patent_id": [10, 20, 11, 12], "field_id": [2, 2, 1, 1],
    }), os.path.join(snap, "patent_compound_map.parquet"))

    qc = QdrantClient(url=QDRANT, timeout=60)
    try:
        qc.delete_collection(COLL)
    except Exception:
        pass
    qc.create_collection(COLL, vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
    qc.upsert(COLL, points=[
        models.PointStruct(id=1, vector=[0.0, 0.0], payload={"surechembl_id": "SCHEMBL1"}),
        models.PointStruct(id=2, vector=[0.0, 0.0], payload={"surechembl_id": "SCHEMBL2"}),
    ])

    r = subprocess.run([sys.executable, BAKE, "--snapshot", snap, "--collection", COLL,
                        "--top", "5", "--batch", "10", "--ckpt", os.path.join(tmp, "ckpt"),
                        "--sorted", os.path.join(tmp, "sorted.parquet"),
                        "--duck-tmp", os.path.join(tmp, "ducktmp"),
                        "--mem-limit", "2GB", "--threads", "2"],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"bake failed:\n{r.stderr}"
    time.sleep(1)

    pts = {p.id: p.payload for p in qc.retrieve(COLL, ids=[1, 2], with_payload=True)}
    p1 = pts[1]["prov"]
    assert p1["n"] == 3 and len(p1["patents"]) == 3, p1
    assert p1["patents"][0]["claimed"] is True and p1["patents"][0]["number"] == "US-1-A", "claimed must be on top"
    p2 = pts[2]["prov"]
    assert p2["n"] == 1 and p2["patents"][0]["number"] == "US-9-A", p2
    assert pts[1]["surechembl_id"] == "SCHEMBL1", "existing payload field must survive (additive)"

    qc.delete_collection(COLL)
    shutil.rmtree(tmp, ignore_errors=True)
    print("test_atlas_bake: PASSED (provenance baked correctly, claimed-first, additive)")


if __name__ == "__main__":
    test_bake()

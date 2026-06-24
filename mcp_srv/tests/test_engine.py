"""Engine unit tests — the three primitives directly against Qdrant + the chemical engine (no HTTP)."""
import sys
sys.path.insert(0, "/data/bioyoda")
import pytest
from mcp_srv import engine as E

QUINAZOLINE = "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1O"   # SCHEMBL8383-like → EGFR


def test_collections():
    c = E.collections()
    assert len(c) == 6
    assert c["patent_atlas"]["modality"] == "chemical" and c["patent_atlas"]["dim"] == 2048
    assert c["clinical_trials_medcpt"]["modality"] == "text"
    assert c["esm2"]["modality"] == "protein"


def test_query_filter_target():
    r = E.query("patent_atlas", filter={"targets": "P00533", "best_tanimoto": {"gte": 0.5}}, limit=3)
    assert len(r["hits"]) == 3
    for h in r["hits"]:
        assert "P00533" in h["payload"]["targets"]
        assert h["payload"]["best_tanimoto"] >= 0.5
        assert "vector" not in h["payload"]            # vectors stripped


def test_query_by_id():
    r = E.query("patent_atlas", ids=[8383], limit=1)
    pl = r["hits"][0]["payload"]
    assert pl["surechembl_id"] == "SCHEMBL8383"
    assert "EGFR" in [p["gene"] for p in pl["predicted"]]


def test_query_by_smiles_vector():
    r = E.query("patent_atlas", smiles=QUINAZOLINE, limit=5)
    assert len(r["hits"]) == 5
    assert all("score" in h for h in r["hits"])
    assert r["hits"][0]["score"] >= r["hits"][-1]["score"]   # ranked


def test_query_by_protein_accession():
    r = E.query("esm2", accession="P00533", limit=3)
    assert len(r["hits"]) >= 1 and all("score" in h for h in r["hits"])


def test_count_target():
    assert E.count("patent_atlas", filter={"targets": "P00533"})["count"] > 1_000_000


def test_predict_quinazoline_is_egfr():
    r = E.predict(QUINAZOLINE, top=5)
    top = r["predictions"][0]
    assert top["gene"] == "EGFR"
    assert top["confidence"] >= 0.7 and top["support"] >= 5
    assert top["band"] == "HIGH"


def test_provenance_losartan_is_dupont():
    d = E.provenance(["SCHEMBL964"])["SCHEMBL964"]
    assert d["n_patents"] >= 5 and d["noise"] is False
    assert any("PONT" in (p["assignee"] or "").upper() for p in d["patents"])


def test_query_unknown_collection_raises():
    with pytest.raises(ValueError):
        E.query("does_not_exist", limit=1)


def test_query_bad_smiles_raises():
    with pytest.raises(ValueError):
        E.query("patent_atlas", smiles="this is not a molecule", limit=1)


def test_limit_is_capped():
    r = E.query("patent_atlas", filter={"targets": "P00533"}, limit=99999)
    assert len(r["hits"]) <= E.MAX_LIMIT

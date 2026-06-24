"""API integration tests — the REST endpoints + MCP over HTTP (requires mcp_srv running on :8011)."""
import httpx
import pytest

API = "http://localhost:8011"
try:
    _UP = httpx.get(API + "/health", timeout=3).status_code == 200
except Exception:
    _UP = False
pytestmark = pytest.mark.skipif(not _UP, reason="mcp_srv not running on :8011")

C = httpx.Client(base_url=API, timeout=60)
QUINAZOLINE = "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1O"


def test_health():
    assert C.get("/health").json()["status"] == "healthy"


def test_collections():
    d = C.get("/api/collections").json()
    assert "patent_atlas" in d and len(d) == 7


def test_query_filter():
    d = C.post("/api/query", json={"collection": "patent_atlas",
               "filter": {"targets": "P00533", "best_tanimoto": {"gte": 0.5}}, "limit": 2}).json()
    assert len(d["hits"]) == 2 and "P00533" in d["hits"][0]["payload"]["targets"]


def test_query_by_id():
    d = C.post("/api/query", json={"collection": "patent_atlas", "ids": [8383], "limit": 1}).json()
    assert d["hits"][0]["payload"]["surechembl_id"] == "SCHEMBL8383"


def test_query_bad_collection_is_400():
    r = C.post("/api/query", json={"collection": "nope", "limit": 1})
    assert r.status_code == 400 and "error" in r.json()


def test_predict():
    d = C.get("/api/predict", params={"smiles": QUINAZOLINE, "top": 3}).json()
    assert d["predictions"][0]["gene"] == "EGFR" and d["predictions"][0]["support"] >= 5


def test_provenance():
    d = C.get("/api/provenance", params={"ids": "SCHEMBL964"}).json()
    assert d["SCHEMBL964"]["n_patents"] >= 5


def test_count():
    d = C.post("/api/count", json={"collection": "patent_atlas", "filter": {"targets": "P00533"}}).json()
    assert d["count"] > 1_000_000


def test_mcp_tools_list():
    d = C.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    names = {t["name"] for t in d["result"]["tools"]}
    assert names == {"bioyoda_query", "bioyoda_predict", "bioyoda_provenance"}


def test_mcp_tools_call_predict():
    d = C.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": "bioyoda_predict", "arguments": {"smiles": QUINAZOLINE, "top": 2}}}).json()
    assert "EGFR" in d["result"]["content"][0]["text"]

#!/usr/bin/env python3
"""Thin BioBTree REST client for BioYoda — DELEGATE all grounding / id-mapping /
synonym / cross-reference lookups to BioBTree instead of reimplementing them.

Architecture: BioBTree = deterministic ground truth + features (70+ DBs, ontologies w/
synonyms, id-mapping); BioYoda = predictive vector side. Every symbolic lookup goes here.

Mirrors sugi-atlas's client (atlas/biobtree/client.py): the fast "direct" Go `/ws/`
transport with mode=lite. Three primitives + row/map parsers.
  search(term, source=None)  -> /ws/        {schema, data}   (ground a name -> ids)
  entry(id, source)          -> /ws/entry/  full entry + xrefs
  bmap(ids, chain, page)     -> /ws/map/     id-mapping via chain DSL (>>ensembl>>uniprot)

Response: {"schema": "col1|col2|...", "data": ["v1|v2|...", ...]} (search) or
{"mappings": [{"input","source","targets":[...]}], ...} (map). Errors: inline {"Err":...}.
"""
import os, json, time, urllib.parse, urllib.request

BASE = os.environ.get("BIOYODA_BIOBTREE", "http://127.0.0.1:9291").rstrip("/")
_OPS = {"search": "/ws/", "map": "/ws/map/", "entry": "/ws/entry/"}


class BioBTreeError(RuntimeError):
    pass


def _get(op, params, timeout=30, retries=3):
    params = {**params, "mode": "lite"}
    url = f"{BASE}{_OPS[op]}?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                body = json.loads(r.read().decode())
            if isinstance(body, dict) and body.get("Err"):
                raise BioBTreeError(f"{op} {params}: {body['Err']}")
            return body
        except BioBTreeError:
            raise
        except Exception as e:  # noqa
            last = e
            time.sleep(0.3 * (attempt + 1))
    raise BioBTreeError(f"{op} {params} failed after {retries}: {last}")


def search(term, source=None):
    p = {"i": term}
    if source:
        p["s"] = source
    return _get("search", p)


def entry(identifier, source):
    return _get("entry", {"i": identifier, "s": source})


def bmap(ids, chain, page=None):
    p = {"i": ids, "m": chain}
    if page:
        p["p"] = page
    return _get("map", p)


def rows(resp):
    """search response -> list of dicts keyed by schema columns (e.g. id,dataset,name,xref_count)."""
    cols = (resp.get("schema") or "").split("|")
    out = []
    for r in (resp.get("data") or []):
        parts = r.split("|")
        if len(parts) == len(cols):
            out.append(dict(zip(cols, parts)))
    return out


def map_targets(resp):
    """map response -> flat deduped list of target ids."""
    seen, out = set(), []
    for m in (resp.get("mappings") or []):
        for t in (m.get("targets") or []):
            if t not in seen:
                seen.add(t); out.append(t)
    return out


# --- convenience: the grounding-as-payload primitive, delegated ---
def ground(term, source="mondo"):
    """Ground a free-text name to a canonical id in `source` (default MONDO). Returns
    (id, name) of the best (first) hit, or (None, None). Set source=None for multi-ontology."""
    try:
        rs = rows(search(term, source=source))
    except BioBTreeError:
        return (None, None)
    return (rs[0]["id"], rs[0]["name"]) if rs else (None, None)


if __name__ == "__main__":
    import sys
    src = None if (len(sys.argv) > 1 and sys.argv[1] == "--multi") else "mondo"
    terms = [a for a in sys.argv[1:] if a != "--multi"] or ["Hepatocellular Carcinoma", "Triple Negative Breast Cancer"]
    for t in terms:
        print(f"{t!r} (s={src}):")
        for r in rows(search(t, source=src))[:5]:
            print("   ", r)

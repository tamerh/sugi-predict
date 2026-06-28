#!/usr/bin/env python3
"""Mode B — exact-Tanimoto FTO / chemical-density queries over the 30.9M patent compounds (FPSim2).

What it answers that Qdrant top-k ANN cannot:
  - density(q, t)   : EXACT count of patent compounds within Tanimoto >= t  ("how crowded / how claimed")
  - neighbors(q, t) : EXHAUSTIVE list of every patent compound >= t           (FTO / what's-claimed)
Qdrant stays the fast top-k similarity layer; this is the exhaustive/threshold companion. Identical FP
definition (Morgan r2, 2048) so results are directly comparable.

CLI:  python fto.py "<smiles | SCHEMBL<id> | drug-name>" [--threshold 0.4] [--list N]
"""
import sys, os, json, glob, bisect, argparse, urllib.request, urllib.parse
from FPSim2 import FPSim2Engine
from rdkit import Chem
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

ROOT = os.environ.get("BIOYODA_ROOT", "/data/bioyoda")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from modules.paths import FPSIM2_PATENTS_H5, CHUNKED_COMPOUNDS
H5 = str(FPSIM2_PATENTS_H5)
PARQ = sorted(glob.glob(str(CHUNKED_COMPOUNDS / "compounds_chunk_*.parquet")))

_eng = None
def engine(in_memory=True):
    global _eng
    if _eng is None:
        if not os.path.exists(H5):
            sys.exit(f"FPSim2 index not found at {H5}\nbuild it first:  python {ROOT}/modules/compounds/build_fpsim2.py")
        _eng = FPSim2Engine(H5, in_memory_fps=in_memory)
    return _eng

# ---- query resolution: SMILES, SCHEMBL id, or drug name (via biobtree PubChem) ----
def smiles_for_id(scid):                       # SCHEMBL numeric id -> smiles (parquet is id-sorted)
    import pyarrow.parquet as pq
    for f in PARQ:
        tb = pq.read_table(f, columns=["id", "smiles"]); ids = tb.column("id").to_pylist()
        if ids and ids[0] <= scid <= ids[-1]:
            i = bisect.bisect_left(ids, scid)
            if i < len(ids) and ids[i] == scid: return tb.column("smiles")[i].as_py()
    return None
def name_to_smiles(name):
    try:
        url = "http://127.0.0.1:9291/ws/?" + urllib.parse.urlencode({"i": name})
        for r in json.load(urllib.request.urlopen(url, timeout=30)).get("results", []):
            for _, a in (r.get("Attributes") or {}).items():
                if isinstance(a, dict) and a.get("smiles"): return a["smiles"]
    except Exception: pass
    return None
def resolve(q):
    if Chem.MolFromSmiles(q) is not None: return q, q if len(q) <= 24 else q[:21] + "…"   # SMILES (label = the SMILES, truncated)
    if q.upper().startswith("SCHEMBL"):
        num = q[7:]
        if num.isdigit():
            s = smiles_for_id(int(num)); return (s, f"SCHEMBL{num}") if s else (None, q)
        # fall through: not a numeric SureChEMBL id -> try as a name
    return name_to_smiles(q), q                # drug name

# ---- the two Mode-B operations ----
def neighbors(smiles, threshold=0.4, n_workers=4):
    res = engine().similarity(smiles, threshold, n_workers=n_workers)   # structured (mol_id, coeff), desc
    return [(f"SCHEMBL{int(m)}", float(c)) for m, c in res]
def density(smiles, thresholds=(0.7, 0.5, 0.4, 0.3), n_workers=4):
    res = engine().similarity(smiles, min(thresholds), n_workers=n_workers)
    coeffs = [float(c) for _, c in res]
    return {t: sum(1 for c in coeffs if c >= t) for t in sorted(thresholds, reverse=True)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query"); ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--list", type=int, default=10, help="show top-N neighbors")
    a = ap.parse_args()
    sm, label = resolve(a.query)
    if not sm: sys.exit(f"could not resolve query: {a.query!r}")
    d = density(sm)
    print(f"query: {label}   (FP: Morgan r2/2048)")
    print("EXACT claimed-density (count of 30.9M patent compounds within Tanimoto):")
    for t, n in d.items(): print(f"   >= {t}:  {n:>8}")
    nb = neighbors(sm, a.threshold)
    print(f"\nexhaustive neighbors >= {a.threshold}: {len(nb)} total; top {a.list}:")
    for scid, c in nb[:a.list]: print(f"   {scid:<16} {c:.4f}")

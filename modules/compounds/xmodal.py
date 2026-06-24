#!/usr/bin/env python3
"""Mode C — cross-modal compound dossier: drug -> primary target -> ESM-2 TWILIGHT homolog
-> grounded evidence + druggability, in one query. The join no sequence/structure/federation tool makes.

Hardened from usecases/poc_xmodal.py with the two fixes that PoC found:
  (1) ORTHOLOG->HUMAN normalization — ESM-2 neighbors are all-species SwissProt, so a twilight homolog
      is often a non-human ortholog with no ChEMBL mapping (druggability falsely 0). We resolve each to
      its human ortholog (UniProt REST gene -> human reviewed accession) before counting drugs/grounding.
  (2) mechanism -> activity FALLBACK for primary-target resolution (imatinib-class ChEMBL gaps).

Twilight homolog = ESM-2 neighbor that (shares >=1 InterPro domain with the target) AND (is NOT in the
target's DIAMOND filtered_top100) = functionally related but sequence-search-invisible.

CLI:  python xmodal.py <drug>            (drug name | ChEMBL id)
"""
import sys, json, time, subprocess, urllib.request, urllib.parse
import os
ROOT = os.environ.get("BIOYODA_ROOT", "/data/bioyoda")
sys.path.insert(0, os.environ.get("SUGI_ATLAS_SRC", "/data/sugi-atlas/src")); sys.path.insert(0, ROOT)
import torch
from transformers import AutoTokenizer, AutoModel
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import atlas.biobtree as B

def _warn(msg): print(f"  [xmodal] {msg}", file=sys.stderr)   # so a 0-result is distinguishable from a failure
DIAMOND_TSV = f"{ROOT}/snapshots/diamond_latest/data/processed/diamond/merged/filtered_top100.tsv"
ESM_TOPK, MAX_TWILIGHT, NDRUG_CAP = 30, 4, 300
GROUND_THR = 0.50   # MedCPT relevance floor: below this the "nearest abstract" is not real grounding
c = QdrantClient(url="http://localhost:6333", timeout=120)
_qtok = _qm = None
def medcpt(t):
    global _qtok, _qm
    if _qm is None:
        _qtok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
        _qm = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()
    with torch.no_grad():
        e = _qtok([t], truncation=True, padding=True, max_length=64, return_tensors="pt")
        return torch.nn.functional.normalize(_qm(**e).last_hidden_state[:, 0, :], dim=1)[0].numpy().tolist()

def esm2_vec(acc):
    p, _ = c.scroll("esm2", scroll_filter=Filter(must=[FieldCondition(key="protein_id", match=MatchValue(value=acc))]), limit=1, with_vectors=True)
    return p[0].vector if p else None
_ip = {}
def interpro(acc):
    if acc in _ip: return _ip[acc]
    s = set()
    try:
        for r in B.map_all(acc, ">>uniprot>>interpro", cap=30):
            if r.get("id"): s.add(r["id"])
    except Exception: pass
    _ip[acc] = s; return s
def pname(acc):
    try:
        rs = B.rows(B.search(acc, source="uniprot"))
        if rs: return rs[0].get("name", acc) or acc
    except Exception: pass
    return acc

# ---- ortholog -> human normalization (UniProt REST = authoritative) ----
_gene = {}
def gene_org(acc):
    if acc in _gene: return _gene[acc]
    g = o = None
    try:
        url = f"https://rest.uniprot.org/uniprotkb/{acc}?" + urllib.parse.urlencode({"fields": "gene_primary,organism_name", "format": "json"})
        d = json.load(urllib.request.urlopen(url, timeout=30))
        gs = d.get("genes") or []
        if gs: g = (gs[0].get("geneName") or {}).get("value")
        o = (d.get("organism") or {}).get("scientificName")
    except Exception: pass
    _gene[acc] = (g, o); return g, o
_huacc = {}
def human_acc_for_gene(gene):
    if gene in _huacc: return _huacc[gene]
    a = None
    try:
        url = "https://rest.uniprot.org/uniprotkb/search?" + urllib.parse.urlencode(
            {"query": f"gene_exact:{gene} AND organism_id:9606 AND reviewed:true", "fields": "accession", "format": "json", "size": 1})
        rs = json.load(urllib.request.urlopen(url, timeout=30)).get("results", [])
        if rs: a = rs[0]["primaryAccession"]
    except Exception: pass
    _huacc[gene] = a; return a
def human_normalize(acc):
    """return (human_acc, gene, organism) — collapse a non-human ortholog to its human reviewed entry."""
    g, o = gene_org(acc)
    if o == "Homo sapiens" or not g: return acc, g, o
    h = human_acc_for_gene(g)
    return (h or acc), g, o

def ndrugs(acc):
    try: return len(B.map_all(acc, ">>uniprot>>chembl_target>>chembl_molecule", cap=NDRUG_CAP))
    except Exception as e: _warn(f"ndrugs({acc}) failed ({e}) -> reporting 0; may be a network blip, not 'not druggable'"); return 0
def diamond_set(acc):
    out = subprocess.run(["grep", "-F", f"sp|{acc}|", DIAMOND_TSV], capture_output=True, text=True).stdout
    s = set()
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) < 2: continue
        for col in (p[0], p[1]):
            parts = col.split("|")
            if len(parts) >= 2 and parts[1] != acc: s.add(parts[1])
    return s
def primary_target(drug):
    for chain in (">>chembl_molecule>>chembl_mechanism>>chembl_target>>uniprot",
                  ">>chembl_molecule>>chembl_activity>>chembl_target>>uniprot"):   # (2) activity fallback
        try: prim = [r.get("id") for r in B.map_all(drug, chain, cap=20) if r.get("id")]
        except Exception: prim = []
        for a in prim:
            if esm2_vec(a) is not None: return a, ("activity" if "activity" in chain else "mechanism")
        if prim: return prim[0], ("activity" if "activity" in chain else "mechanism")
    return None, None

def dossier(drug):
    tgt, via = primary_target(drug)
    if not tgt: return {"drug": drug, "error": "no target resolved"}
    v = esm2_vec(tgt)
    if v is None: return {"drug": drug, "target": tgt, "gene": pname(tgt), "error": "target not in esm2"}
    dia, qip = diamond_set(tgt), interpro(tgt)
    tws, seen = [], set()
    for h in c.query_points("esm2", query=v, limit=ESM_TOPK + 1, with_payload=["protein_id"]).points:
        a = h.payload.get("protein_id")
        if a == tgt or a in dia or not (qip & interpro(a)): continue
        hacc, gene, org = human_normalize(a)                 # (1) ortholog -> human
        key = (gene or a).upper()
        if key in seen: continue
        seen.add(key)
        tws.append({"surfaced": a, "species": org, "gene": gene or pname(a), "human_acc": hacc,
                    "sim": h.score, "nligands": ndrugs(hacc), "pmid": None, "lit": None, "gscore": 0.0})
        if len(tws) >= MAX_TWILIGHT: break
    for tw in tws:
        # grounding query ties the homolog to the SOURCE target's disease context (not a generic template);
        # store the MedCPT relevance score so "grounded" is thresholded, not "an abstract was always returned".
        L = c.query_points("pubmed_abstracts_medcpt", query=medcpt(f"{tw['gene']} {pname(tgt)} inhibitor drug target cancer"), limit=1).points
        if L:
            tw["pmid"], tw["lit"], tw["gscore"] = L[0].payload.get("pmid"), (L[0].payload.get("chunk_text") or "")[:90], float(L[0].score)
    return {"drug": drug, "target": tgt, "target_gene": gene_org(tgt)[0], "target_name": pname(tgt),
            "via": via, "n_diamond": len(dia), "twilights": tws}

if __name__ == "__main__":
    d = dossier(sys.argv[1] if len(sys.argv) > 1 else "osimertinib")
    if d.get("error"): sys.exit(f"{d['drug']}: {d['error']}")
    print(f"\n{d['drug']}  ->  primary target {d['target_gene'] or d['target_name']} ({d['target']}, via {d['via']}; {d['n_diamond']} DIAMOND homologs)")
    print("  TWILIGHT homologs (ESM-2 neighbor, shares InterPro, NOT in DIAMOND top-100):")
    print("  ligands = total ChEMBL ligands of the target (tractability proxy, popularity-biased — NOT")
    print(f"  proof of cross-reactivity); grounded = nearest abstract MedCPT-relevant (score ≥ {GROUND_THR}).")
    if not d["twilights"]: print("    none (neighbors all DIAMOND-visible or no shared InterPro)")
    for tw in d["twilights"]:
        grounded = tw["gscore"] >= GROUND_THR
        u = "  ★USABLE" if tw["nligands"] > 0 and grounded else ""
        sp = f" [{tw['species']}→human]" if tw["species"] and tw["species"] != "Homo sapiens" else ""
        g = f"PMID:{tw['pmid']}({tw['gscore']:.2f})" if grounded else f"ungrounded({tw['gscore']:.2f})"
        print(f"    {tw['gene']:12} {tw['human_acc']}{sp}  sim={tw['sim']:.3f}  ligands={tw['nligands']:>4}  {g}{u}")
        if tw["lit"] and grounded: print(f"        ↳ {tw['lit']}")

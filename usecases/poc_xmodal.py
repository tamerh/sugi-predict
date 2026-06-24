#!/usr/bin/env python3
"""PoC: does BioYoda's CROSS-MODAL compound join surface NON-OBVIOUS, GROUNDED
repurposing/target hypotheses a single-modality tool (or the drug's primary
target alone) cannot?

Pipeline, per drug (read-only; touches nothing):
  1. drug  -> primary target UniProt acc   (biobtree mechanism chain)
  2. target -> ESM-2 nearest neighbors      (esm2 collection, the target's stored vector)
  3. classify neighbor TWILIGHT =
        (shares >=1 InterPro domain with target)   # functionally related
        AND (NOT in target's DIAMOND filtered_top100 set)  # sequence-search-invisible
  4. per twilight homolog: druggability (#drugs via chembl chain) + 1 grounded PubMed hit (MedCPT)

A drug "produces a usable hypothesis" iff it has >=1 twilight homolog that is
DRUGGABLE (#drugs>0) AND grounded (a PMID returned). Validated archetype: EGFR -> NTRK/Trk.

Run: /data/miniconda3/envs/bioyoda/bin/python /data/bioyoda/usecases/poc_xmodal.py 2>&1 | grep -v -iE "warn|deprecat"
"""
import sys, time, subprocess
sys.path.insert(0, "/data/sugi-atlas/src"); sys.path.insert(0, "/data/bioyoda")
import numpy as np, torch
from transformers import AutoTokenizer, AutoModel
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import atlas.biobtree as B
from scripts.integrations import biobtree_client as bb

DIAMOND_TSV = "/data/bioyoda/snapshots/diamond_latest/data/processed/diamond/merged/filtered_top100.tsv"
DRUGS = ["osimertinib", "imatinib", "gefitinib", "sildenafil",
         "thalidomide", "crizotinib", "dasatinib", "vemurafenib"]
ESM_TOPK = 30          # neighbors to pull per target
MAX_TWILIGHT = 4       # report top-N twilights per drug
NDRUG_CAP = 200        # cap for druggability count chain

c = QdrantClient(url="http://localhost:6333", timeout=120)
print("loading MedCPT query encoder…", flush=True)
qtok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
qm = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()

def medcpt(t):
    with torch.no_grad():
        e = qtok([t], truncation=True, padding=True, max_length=64, return_tensors="pt")
        return torch.nn.functional.normalize(qm(**e).last_hidden_state[:, 0, :], dim=1)[0].numpy().tolist()

def esm2_vec(acc):
    p, _ = c.scroll("esm2", scroll_filter=Filter(must=[FieldCondition(
        key="protein_id", match=MatchValue(value=acc))]), limit=1, with_vectors=True)
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

_nm = {}
def pname(acc):
    if acc in _nm: return _nm[acc]
    nm = acc
    try:
        rs = B.rows(B.search(acc, source="uniprot"))
        if rs: nm = rs[0].get("name", acc) or acc
    except Exception: pass
    _nm[acc] = nm; return nm

def ndrugs(acc):
    try:
        return len(B.map_all(acc, ">>uniprot>>chembl_target>>chembl_molecule", cap=NDRUG_CAP))
    except Exception:
        return 0

def diamond_set(acc):
    """Union of all sequence-search-visible homolog accessions of `acc` in the
    DIAMOND filtered_top100 set (acc appearing as either query or subject)."""
    out = subprocess.run(["grep", "-F", f"sp|{acc}|", DIAMOND_TSV],
                         capture_output=True, text=True).stdout
    s = set()
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) < 2: continue
        for col in (p[0], p[1]):
            parts = col.split("|")
            if len(parts) >= 2 and parts[1] != acc:
                s.add(parts[1])
    return s

def primary_target(drug):
    """drug -> primary target UniProt acc via mechanism chain; require it be in esm2."""
    try:
        prim = bb.map_targets(bb.bmap(drug, ">>chembl_molecule>>chembl_mechanism>>chembl_target>>uniprot"))
    except Exception:
        prim = []
    for cand in prim:
        if esm2_vec(cand) is not None:
            return cand, prim
    return (prim[0] if prim else None), prim

# ---------------------------------------------------------------- per-drug
results = []
for drug in DRUGS:
    t0 = time.time()
    print(f"\n=== {drug} ===", flush=True)
    tgt, prim_all = primary_target(drug)
    if not tgt:
        print("  no mechanism target"); results.append((drug, None, "", [], "no mechanism target")); continue
    gene = pname(tgt)
    v = esm2_vec(tgt)
    if v is None:
        print(f"  target {tgt} ({gene}) not in esm2")
        results.append((drug, tgt, gene, [], "target not in esm2")); continue
    print(f"  primary target: {tgt} ({gene})", flush=True)

    dia = diamond_set(tgt)
    qip = interpro(tgt)
    print(f"  DIAMOND homologs: {len(dia)} | target InterPro domains: {len(qip)}", flush=True)

    hits = c.query_points("esm2", query=v, limit=ESM_TOPK + 1, with_payload=["protein_id"]).points
    twilights = []; seen_genes = set()
    for h in hits:
        a = h.payload.get("protein_id")
        if a == tgt or a in dia:        # self or sequence-search-visible -> not twilight
            continue
        if not (qip & interpro(a)):     # must share an InterPro domain (functional relation)
            continue
        nm = pname(a); key = nm.split()[0] if nm else a
        if key in seen_genes:           # dedupe orthologs/paralogs by leading name token
            continue
        seen_genes.add(key)
        nd = ndrugs(a)
        twilights.append({"acc": a, "name": nm, "sim": h.score, "ndrugs": nd, "pmid": None, "lit": None})
        if len(twilights) >= MAX_TWILIGHT:
            break

    # grounded PubMed hit per twilight (target-family pathway/therapy query)
    for tw in twilights:
        nm = tw["name"]
        q = f"{nm} signaling pathway targeted therapy"
        L = c.query_points("pubmed_abstracts_medcpt", query=medcpt(q), limit=1).points
        if L:
            tw["pmid"] = L[0].payload.get("pmid")
            tw["lit"] = (L[0].payload.get("chunk_text") or "")[:80]

    usable = [tw for tw in twilights if tw["ndrugs"] > 0 and tw["pmid"]]
    note = "" if twilights else "no twilight homologs (all ESM-2 neighbors either DIAMOND-visible or no shared InterPro)"
    results.append((drug, tgt, gene, twilights, note))
    for tw in twilights:
        flag = "USABLE" if (tw["ndrugs"] > 0 and tw["pmid"]) else ""
        print(f"    twilight {tw['acc']} {tw['name'][:38]:38s} sim={tw['sim']:.3f} "
              f"drugs={tw['ndrugs']:>4} pmid={tw['pmid']} {flag}", flush=True)
    print(f"  -> {len(usable)} usable hypothesis(es)  [{time.time()-t0:.1f}s]", flush=True)

# ---------------------------------------------------------------- report
print("\n\n" + "#" * 78)
print("# REPORT (markdown)")
print("#" * 78 + "\n")

n_with_twilight = 0; n_usable = 0
for drug, tgt, gene, tws, note in results:
    print(f"### {drug}")
    if tgt is None:
        print(f"- primary target: **{note}**\n"); continue
    print(f"- primary target: **{gene}** ({tgt})")
    if not tws:
        print(f"- twilight homologs: _{note}_\n"); continue
    n_with_twilight += 1
    print()
    print("| twilight acc | name | ESM-2 sim | #drugs | PMID | grounded snippet |")
    print("|---|---|---|---|---|---|")
    for tw in tws:
        snip = (tw["lit"] or "").replace("|", "/").replace("\n", " ")
        print(f"| {tw['acc']} | {tw['name'][:34]} | {tw['sim']:.3f} | "
              f"{tw['ndrugs']} | {tw['pmid'] or '—'} | {snip} |")
    usable = [tw for tw in tws if tw["ndrugs"] > 0 and tw["pmid"]]
    if usable:
        n_usable += 1
        names = ", ".join(f"{tw['name'].split()[0]}({tw['ndrugs']}d)" for tw in usable)
        print(f"\n- **usable cross-target hypothesis:** {names}")
    print()

n_total = sum(1 for _, t, *_ in results if t is not None)
print("#" * 78)
print(f"\n**SCORECARD** (drugs evaluated: {len(results)}, with resolvable in-esm2 target: {n_total})")
print(f"- drugs with >=1 twilight homolog: {n_with_twilight}/{len(results)}")
print(f"- drugs with >=1 USABLE hypothesis (twilight & druggable & grounded): {n_usable}/{len(results)} "
      f"= {100*n_usable/len(results):.0f}%")

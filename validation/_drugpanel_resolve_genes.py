#!/usr/bin/env python3
"""Re-resolve mechanism chembl_target -> uniprot -> gene with PAGINATION (the
prior bulk_map only read page 1, dropping ~40% of inputs). Patches drugpanel_large_panel.json in place."""
import sys, os, json, time
sys.path.insert(0, "/data/sugi-atlas/src")
from atlas.biobtree import bbmap

SCRATCH = "/data/bioyoda/validation/results"
REF = "/data/bioyoda/out_prod/work/chembl_reference"
GENES = json.load(open(f"{REF}/target_genes.json"))
def gene(acc): return GENES.get(acc, {}).get("gene", acc)

panel = json.load(open(f"{SCRATCH}/drugpanel_large_panel.json"))

def bulk_map_paged(ids, chain):
    """{input: [targets]} accumulating across ALL pages."""
    out = {}; page = None; seen_pages = 0
    while True:
        resp = bbmap(",".join(ids), chain, page)
        for m in (resp.get("mappings") or []):
            out.setdefault(m["input"], [])
            for t in (m.get("targets") or []):
                if t not in out[m["input"]]: out[m["input"]].append(t)
        pg = resp.get("pagination", {}) or {}
        nxt = pg.get("next_token")
        seen_pages += 1
        if not pg.get("has_next") or not nxt or seen_pages > 200: break
        page = nxt
    return out

all_tids = sorted({t for v in panel.values() for t in v["mech_target_ids"]})
print(f"{len(all_tids)} unique mechanism chembl_target ids -> uniprot (paginated)...", flush=True)
tid2uni = {}
for i in range(0, len(all_tids), 40):
    batch = all_tids[i:i+40]
    for tries in range(3):
        try: mp = bulk_map_paged(batch, ">>chembl_target>>uniprot"); break
        except Exception as e: print("retry", e, file=sys.stderr); time.sleep(1)
    else: mp = {}
    tid2uni.update(mp)
resolved = sum(1 for t in all_tids if tid2uni.get(t))
print(f"  resolved {resolved}/{len(all_tids)} target ids to >=1 uniprot", flush=True)

for d, v in panel.items():
    genes = set()
    for tid in v["mech_target_ids"]:
        for uni in tid2uni.get(tid, ()):
            genes.add(gene(uni))
    v["genes"] = sorted(genes)
json.dump(panel, open(f"{SCRATCH}/drugpanel_large_panel.json", "w"))
n_gene = sum(1 for v in panel.values() if v["genes"])
n_tid_nogene = sum(1 for v in panel.values() if v["mech_target_ids"] and not v["genes"])
print(f"drugs with smiles: {len(panel)} | with >=1 mechanism gene: {n_gene} | tid-but-no-gene: {n_tid_nogene}", flush=True)

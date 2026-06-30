#!/usr/bin/env python3
"""Gather, for each approved drug ChEMBL ID:
   (a) SMILES + PubChem CID via >>chembl_molecule>>pubchem
   (b) MECHANISM target genes via the chembl_mechanism table (molecule_id->target_id),
       with parent<->child bridging for IDs whose mechanism is keyed on a salt/parent form.
   target_id (chembl_target) -> uniprot -> gene.
Writes a single JSON: drugpanel_large_panel.json  {chembl_id: {smiles, cid, mech_targets:[chembl_target], genes:[...] }}
"""
import sys, os, json, time
sys.path.insert(0, "/data/sugi-atlas/src")
import atlas.biobtree as B   # client module
from atlas.biobtree import bbmap, map_targets

SCRATCH = "/data/bioyoda/validation/results"
REF = "/data/bioyoda/out_prod/work/chembl_reference"
MECH = "/data/biobtree/raw_data/chembl/extracted/chembl_mechanisms.jsonl"

drugs = [l.strip() for l in open("/data/sugi-atlas/data/corpus/seeds/drugs_chembl_approved.txt") if l.strip()]
GENES = json.load(open(f"{REF}/target_genes.json"))
def gene(acc): return GENES.get(acc, {}).get("gene", acc)

# --- mechanism table: molecule_id -> set(chembl_target_id) ---
mech = {}            # molecule_id -> set(target chembl ids)
for l in open(MECH):
    d = json.loads(l)
    tid = d.get("target_id")
    if tid:
        mech.setdefault(d["molecule_id"], set()).add(tid)
print(f"mechanism table: {len(mech)} molecules", flush=True)

def batched(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i+n]

def bulk_map(ids, chain, parse="targets"):
    """Return {input_id: [target strings]} for a batch. Handles pagination minimally (chains here are 1:few)."""
    out = {}
    resp = bbmap(",".join(ids), chain)
    for m in (resp.get("mappings") or []):
        out[m["input"]] = list(m.get("targets") or [])
    return out

# 1) SMILES + CID for all drugs  (chembl_molecule>>pubchem)
print("step 1: SMILES+CID via chembl_molecule>>pubchem ...", flush=True)
smiles = {}; cid = {}
t0 = time.time()
for bi, batch in enumerate(batched(drugs, 50)):
    for tries in range(3):
        try:
            mp = bulk_map(batch, ">>chembl_molecule>>pubchem"); break
        except Exception as e:
            print("  retry", e, file=sys.stderr); time.sleep(1)
    else:
        mp = {}
    for q, tgts in mp.items():
        # take first pubchem row: "cid|title|formula|smiles|approved|type|mesh"
        for t in tgts:
            p = t.split("|")
            if len(p) >= 4 and p[3]:
                cid[q] = p[0]; smiles[q] = p[3]; break
    if (bi+1) % 10 == 0:
        print(f"  {(bi+1)*50}/{len(drugs)} drugs, {len(smiles)} smiles, {time.time()-t0:.0f}s", flush=True)
print(f"  SMILES resolved: {len(smiles)}/{len(drugs)} ({time.time()-t0:.0f}s)", flush=True)

# 2) mechanism bridging: for drugs with no direct mech row, gather parent+child molecule ids
print("step 2: parent/child bridging for missing mechanism ...", flush=True)
missing = [d for d in drugs if d not in mech]
print(f"  {len(missing)} drugs have no DIRECT mechanism row; bridging via parent/child", flush=True)
bridge = {}   # drug -> set(alt molecule ids found via child/parent)
for chain in (">>chembl_molecule>>chembl_moleculechild", ">>chembl_molecule>>chembl_moleculeparent"):
    for batch in batched(missing, 50):
        try: mp = bulk_map(batch, chain)
        except Exception as e: print("  bridge retry", e, file=sys.stderr); continue
        for q, tgts in mp.items():
            for t in tgts:
                alt = t.split("|")[0]
                if alt: bridge.setdefault(q, set()).add(alt)

# 3) resolve mech target ids per drug (direct + bridged)
drug_mech_targets = {}   # drug -> set(chembl_target ids)
for d in drugs:
    tids = set(mech.get(d, set()))
    for alt in bridge.get(d, ()):
        tids |= mech.get(alt, set())
    if tids: drug_mech_targets[d] = tids
print(f"  drugs with a mechanism target (after bridging): {len(drug_mech_targets)}", flush=True)

# 4) map all unique chembl_target ids -> uniprot, then -> gene
all_tids = sorted({t for ts in drug_mech_targets.values() for t in ts})
print(f"step 3: {len(all_tids)} unique mechanism chembl_target ids -> uniprot ...", flush=True)
tid2uni = {}
for batch in batched(all_tids, 80):
    for tries in range(3):
        try: mp = bulk_map(batch, ">>chembl_target>>uniprot"); break
        except Exception as e: print("  uni retry", e, file=sys.stderr); time.sleep(1)
    else: mp = {}
    for q, tgts in mp.items():
        tid2uni[q] = [t for t in tgts]   # uniprot accessions

# 5) assemble panel
panel = {}
for d in drugs:
    if d not in smiles: continue
    genes = set()
    for tid in drug_mech_targets.get(d, ()):
        for uni in tid2uni.get(tid, ()):
            genes.add(gene(uni))
    panel[d] = {"smiles": smiles[d], "cid": cid.get(d), "genes": sorted(genes),
                "mech_target_ids": sorted(drug_mech_targets.get(d, ()))}
json.dump(panel, open(f"{SCRATCH}/drugpanel_large_panel.json", "w"))
n_sm = sum(1 for v in panel.values() if v["smiles"])
n_gene = sum(1 for v in panel.values() if v["genes"])
print(f"\nDONE: {len(panel)} drugs with smiles; {n_gene} also have >=1 mechanism gene", flush=True)
print(f" -> {SCRATCH}/drugpanel_large_panel.json", flush=True)

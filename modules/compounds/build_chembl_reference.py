#!/usr/bin/env python3
"""Assemble the ChEMBL ligand→target REFERENCE for the patent target-atlas.

Pure biobtree-API (localhost:9291). Per target:
    >>uniprot>>chembl_target>>chembl_molecule>>pubchem   → (pubchem cid, SMILES, compound_type) inline
(SMILES is now emitted on the pubchem node). Targets = the biobtree-KG ChEMBL target list
(work/chembl_reference/targets.txt, from qual_chembl.tsv). Reproducible; filtering knobs (compound_type,
later activity/pChembl) adjustable. Resumable: checkpoints every CKPT targets, skips done on restart.

Output (work/chembl_reference/):
    reference.tsv   cid \\t smiles            (unique molecules → feed to the FPSim2 reference index)
    cid_targets.json   {cid: [uniprot,...]}   (the labels: each molecule's target set)
    _state.json     {done:[...], n_edges:int} (checkpoint)

Usage: python build_chembl_reference.py [LIMIT_TARGETS]   # LIMIT for a test slice; omit for all 8146
"""
import sys, os, json, time
sys.path.insert(0, "/data/sugi-atlas/src")
import atlas.biobtree as B

OUT = "/data/bioyoda/work/chembl_reference"
CHAIN = ">>uniprot>>chembl_target>>chembl_molecule>>pubchem"
CAP = 2000          # effectively UNCAPPED: pagination terminates naturally (new==0/no next_token);
                    # this is just a runaway ceiling. (Was 12 ≈ 1,300 ligands/target — truncated popular
                    # targets like EGFR to 1,299 of ~5,000+, dropping canonical pairs. Complete now.)
CKPT = 200          # checkpoint every N targets
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else None

targets = [l.strip() for l in open(f"{OUT}/targets.txt") if l.strip()]
if LIMIT: targets = targets[:LIMIT]

# resume
cid_smiles, cid_targets, done = {}, {}, set()
sp, tp = f"{OUT}/_cid_smiles.json", f"{OUT}/cid_targets.json"
if os.path.exists(f"{OUT}/_state.json") and not LIMIT:
    done = set(json.load(open(f"{OUT}/_state.json")).get("done", []))
    if os.path.exists(sp): cid_smiles = json.load(open(sp))
    if os.path.exists(tp): cid_targets = {k: set(v) for k, v in json.load(open(tp)).items()}
    print(f"resumed: {len(done)} targets done, {len(cid_smiles)} cids so far", flush=True)

def save():
    json.dump(cid_smiles, open(sp, "w"))
    json.dump({k: sorted(v) for k, v in cid_targets.items()}, open(tp, "w"))
    json.dump({"done": sorted(done), "n_cids": len(cid_smiles)}, open(f"{OUT}/_state.json", "w"))

t0 = time.time(); n_edges = 0
for i, tgt in enumerate(targets):
    if tgt in done: continue
    try:
        rows = B.map_all(tgt, CHAIN, cap=CAP)
    except Exception as e:
        print(f"  [skip {tgt}] {e}", file=sys.stderr); done.add(tgt); continue
    for r in rows:
        cid, sm = r.get("id"), r.get("smiles")
        if not cid or not sm: continue
        # filter: keep small-molecule-ish (skip explicit biologics); cheap, refine later
        if r.get("compound_type") in ("biologic", "protein"): continue
        cid_smiles[cid] = sm
        cid_targets.setdefault(cid, set()).add(tgt)
        n_edges += 1
    done.add(tgt)
    if (i + 1) % CKPT == 0:
        save()
        print(f"  {i+1}/{len(targets)} targets · {len(cid_smiles)} cids · {n_edges} edges · {time.time()-t0:.0f}s", flush=True)
save()

# write the unique-molecule reference table
with open(f"{OUT}/reference.tsv", "w") as f:
    for cid, sm in cid_smiles.items():
        f.write(f"{cid}\t{sm}\n")
print(f"\nDONE: {len(done)} targets · {len(cid_smiles)} unique molecules · {n_edges} compound-target edges "
      f"in {time.time()-t0:.0f}s\n  -> {OUT}/reference.tsv + cid_targets.json", flush=True)

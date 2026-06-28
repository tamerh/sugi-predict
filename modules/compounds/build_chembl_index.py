#!/usr/bin/env python3
"""Build the FPSim2 index for the ChEMBL ligand→target reference (the answer key the atlas searches).
reference.tsv (cid \\t smiles)  ->  reference_fpsim2.smi (smiles \\t cid)  ->  FPSim2 .h5 (Morgan r2/2048).
Run after build_chembl_reference.py. The .h5 is what target.py uses locally AND what we push to the GPU box.
Usage: python build_chembl_index.py
"""
import time, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from FPSim2.io import create_db_file
from modules.paths import CHEMBL_REF
REF = str(CHEMBL_REF)
SMI, H5 = f"{REF}/reference_fpsim2.smi", f"{REF}/chembl_reference_morgan_r2_2048.h5"
t = time.time(); n = 0
with open(SMI, "w") as out:
    for line in open(f"{REF}/reference.tsv"):
        cid, sm = line.rstrip("\n").split("\t", 1)
        if cid.isdigit() and sm:
            out.write(f"{sm}\t{cid}\n"); n += 1
print(f"wrote {n:,} smiles -> {SMI} in {time.time()-t:.0f}s", flush=True)
if os.path.exists(H5): os.remove(H5)
t = time.time()
create_db_file(SMI, H5, "smiles", "Morgan", {"radius": 2, "fpSize": 2048})
from FPSim2 import FPSim2Engine
indexed = FPSim2Engine(H5).fps.shape[0]
print(f"built {H5} ({os.path.getsize(H5)//1024//1024} MB) · {indexed:,} indexed "
      f"({n-indexed} unparseable dropped) in {time.time()-t:.0f}s", flush=True)

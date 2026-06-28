#!/usr/bin/env python3
"""Build the exact-Tanimoto FTO engine (FPSim2) over the patent-compound Morgan fingerprints.

Mode B of the compound substrate: Qdrant ANN serves fast top-k similarity; THIS serves EXHAUSTIVE
threshold / FTO / "what's-claimed-within-T" / chemical-density queries that top-k ANN structurally cannot.

Source : raw_data/patents/chunked_compounds/*.parquet  (id = SureChEMBL numeric -> SCHEMBL{id}; smiles)
FP     : Morgan radius 2, 2048 bits  (identical definition to patents_compounds; verified vs RDKit exact)
Output : work/fpsim2/patents_compounds_morgan_r2_2048.h5  (FPSim2, popcount-sorted; ~4 GB)

Usage: python build_fpsim2.py [LIMIT]   # LIMIT rows for a validation build; omit for full 30.9M
"""
import glob, time, os, sys
import pyarrow.parquet as pq
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from FPSim2.io import create_db_file
from modules.paths import CHUNKED_COMPOUNDS, FPSIM2

SRC = sorted(glob.glob(str(CHUNKED_COMPOUNDS / 'compounds_chunk_*.parquet')))
OUTDIR = str(FPSIM2)
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else None
tag = f"_test{LIMIT}" if LIMIT else ""
SMI = f"{OUTDIR}/compounds{tag}.smi"
H5  = f"{OUTDIR}/patents_compounds_morgan_r2_2048{tag}.h5"

t = time.time(); n = 0
with open(SMI, 'w') as out:
    for f in SRC:
        tb = pq.read_table(f, columns=['id', 'smiles'])
        for i, s in zip(tb.column('id').to_pylist(), tb.column('smiles').to_pylist()):
            if s:
                out.write(f"{s}\t{i}\n"); n += 1
                if LIMIT and n >= LIMIT: break
        if LIMIT and n >= LIMIT: break
print(f"wrote {n} smiles -> {SMI} in {time.time()-t:.0f}s", flush=True)

t = time.time()
create_db_file(SMI, H5, 'smiles', 'Morgan', {'radius': 2, 'fpSize': 2048})
print(f"built FPSim2 db {H5} ({os.path.getsize(H5)//1024//1024} MB) in {time.time()-t:.0f}s", flush=True)

# reconciliation — make the silent RDKit drops visible (don't pretend full coverage)
from FPSim2 import FPSim2Engine
indexed = FPSim2Engine(H5).fps.shape[0]
print(f"reconciliation: smi_lines={n}  indexed={indexed}  dropped={n-indexed} "
      f"({(n-indexed)/max(n,1)*100:.3f}% unparseable, excluded from FTO results)", flush=True)
try:
    from qdrant_client import QdrantClient
    qn = QdrantClient(url="http://localhost:6333", timeout=30).get_collection("patents_compounds").points_count
    print(f"  vs Qdrant patents_compounds={qn}  delta={qn-indexed} "
          f"({(qn-indexed)/max(qn,1)*100:.3f}% — FTO under-reports 'what's claimed' by this much)", flush=True)
except Exception as e:
    print(f"  (Qdrant cross-check skipped: {e})", flush=True)

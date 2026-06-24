#!/usr/bin/env python3
"""GPU patent target-atlas prediction — runs on a rented A100 (RunPod).

EXACT Tanimoto (identical math to the CPU path), accelerated by FPSim2's CUDA engine. For each of the 30.9M
patent compounds: search the UNCAPPED ChEMBL reference, take the top-K neighbours, aggregate to the top-20
protein targets with a Tanimoto confidence (max similarity to a known ligand of that target) — exactly like
modules/compounds/target.py:predict(), just on GPU. Writes a compact predictions file to pull back home and
ingest into the `patent_atlas` Qdrant collection locally.

This is NOT a workaround: same fingerprints (Morgan r=2, 2048 bits), same Tanimoto, same top-K aggregation,
same novel<0.3 rule. Only the hardware changes.

Inputs (pushed to the box):
  --ref       chembl_reference_morgan_r2_2048.h5   (FPSim2 index of the UNCAPPED reference)
  --targets   cid_targets.json                     ({cid: [uniprot,...]})
  --patents   DIR of compounds_chunk_*.parquet     (id, smiles)
Output (one parquet per input chunk, so the local ingest can parallelise per-chunk):
  --outdir    DIR of preds_<chunk>.parquet   (pid, best_tanimoto, novel, targets[list], confs[list])

Usage (validate first, then full):
  python gpu_atlas_predict.py --ref ref.h5 --targets cid_targets.json --patents patents/ --outdir preds/ --limit 100000
  python gpu_atlas_predict.py --ref ref.h5 --targets cid_targets.json --patents patents/ --outdir preds/
"""
import sys, os, glob, json, time, argparse, collections
import numpy as np, pyarrow as pa, pyarrow.parquet as pq
from rdkit import Chem
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

KNN, MIN_TAN, MIN_HEAVY = 20, 0.30, 10   # KNN = k in k-NN (validated model param, NOT a data cap);
                                         # store ALL targets from the k-NN (no top-N count cap — see predict_one)

def get_engine(ref):
    """FPSim2 CUDA engine if available; fall back to CPU engine (for a no-GPU smoke test)."""
    try:
        from FPSim2 import FPSim2CudaEngine
        eng = FPSim2CudaEngine(ref)
        print("using FPSim2CudaEngine (GPU)", flush=True); return eng, "gpu"
    except Exception as e:
        from FPSim2 import FPSim2Engine
        print(f"CUDA engine unavailable ({e}); using CPU FPSim2Engine", flush=True)
        return FPSim2Engine(ref, in_memory_fps=True), "cpu"

def predict_one(eng, ct, smiles):
    """→ (ALL [(target, conf)] from the k-NN, ranked; best_tanimoto). Mirrors target.py:predict exactly.
    No top-N count cap — every target supported by a known ligand ≥0.3 within the top-KNN neighbours is kept."""
    try:
        res = eng.similarity(smiles, MIN_TAN)            # [(cid, tanimoto)] desc
    except Exception:
        return [], 0.0
    if not len(res): return [], 0.0
    supp = collections.defaultdict(float); vote = collections.defaultdict(float)
    for i, (cid, co) in enumerate(res):
        if i >= KNN: break
        co = float(co)
        for t in ct.get(int(cid), ()):
            vote[t] += co; supp[t] = max(supp[t], co)
    ranked = sorted(supp, key=lambda t: (-supp[t], -vote[t]))    # ALL, no cap
    return [(t, supp[t]) for t in ranked], float(res[0][1])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True); ap.add_argument("--targets", required=True)
    ap.add_argument("--patents", required=True); ap.add_argument("--outdir", required=True)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    eng, mode = get_engine(a.ref)
    ct = {int(k): v for k, v in json.load(open(a.targets)).items()}
    print(f"reference targets-map: {len(ct):,} cids", flush=True)
    chunks = sorted(glob.glob(f"{a.patents}/compounds_chunk_*.parquet"))
    n = 0; t0 = time.time()
    for f in chunks:
        outp = f"{a.outdir}/preds_{os.path.basename(f)}"
        if os.path.exists(outp):                          # resumable: skip finished chunks
            print(f"  skip (done) {os.path.basename(f)}", flush=True); continue
        tb = pq.read_table(f, columns=["id", "smiles"])
        pids, bests, novels, tgts, confs = [], [], [], [], []
        for pid, sm in zip(tb.column("id").to_pylist(), tb.column("smiles").to_pylist()):
            if a.limit and n >= a.limit: break
            if not sm: continue
            m = Chem.MolFromSmiles(sm)
            if m is None or m.GetNumHeavyAtoms() < MIN_HEAVY: continue
            top, best = predict_one(eng, ct, sm)
            pids.append(int(pid)); bests.append(round(best, 3)); novels.append(bool(best < MIN_TAN))
            tgts.append([t for t, _ in top]); confs.append([round(s, 3) for _, s in top])
            n += 1
            if n % 100000 == 0:
                r = n / (time.time() - t0)
                print(f"  {n:,} done · {r:.0f}/s · eta_full {30.9e6/r/3600:.1f}h · {time.time()-t0:.0f}s", flush=True)
        pq.write_table(pa.table({"pid": pids, "best_tanimoto": bests, "novel": novels, "targets": tgts, "confs": confs}),
                       outp, compression="zstd")
        print(f"  wrote {os.path.basename(outp)} ({len(pids):,} rows)", flush=True)
        if a.limit and n >= a.limit: break
    dt = time.time() - t0
    print(f"\nDONE [{mode}]: {n:,} compounds in {dt:.0f}s ({n/max(dt,1):.0f}/s) → {a.outdir}/", flush=True)

if __name__ == "__main__":
    main()

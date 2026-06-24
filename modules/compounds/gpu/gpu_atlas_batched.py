#!/usr/bin/env python3
"""Batched GPU Tanimoto — the real A100 path for the patent target-atlas.

Per-query FPSim2-CUDA was overhead-bound (~425/s). This batches thousands of patents per GPU launch: a packed
popcount-Tanimoto kernel scores each patent vs ALL reference ligands, top-20 neighbours on GPU (iterative argmax),
target aggregation PARALLELISED across CPU workers. EXACT Morgan r=2/2048 Tanimoto — same math as target.py:predict.
Reference AND patent FPs are both computed on THIS box's RDKit (consistent — no cross-version FP drift).

Usage:
  python gpu_atlas_batched.py --refsmi ref/reference.tsv --targets ref/cid_targets.json \
      --patents patents --outdir preds [--limit N] [--batch 4096] [--procs 24]
"""
import sys, os, glob, json, time, argparse
import numpy as np, cupy as cp, pyarrow as pa, pyarrow.parquet as pq
import multiprocessing as mp
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

KNN, MIN_TAN, MIN_HEAVY, NWORDS = 20, 0.30, 10, 32
_CT = None; _REFCIDS = None
def _init(ct_path, refcids):
    global _CT, _REFCIDS
    _CT = {int(k): v for k, v in json.load(open(ct_path)).items()}
    _REFCIDS = refcids

def _pack(smi):
    m = Chem.MolFromSmiles(smi) if smi else None
    if m is None or m.GetNumHeavyAtoms() < MIN_HEAVY: return None
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    a = np.zeros(2048, dtype=np.uint8); DataStructs.ConvertToNumpyArray(bv, a)
    return np.packbits(a).view(np.uint64), int(a.sum())

def _fp_batch(items):
    ids, packed, pc = [], [], []
    for i, s in items:
        r = _pack(s)
        if r is None: continue
        ids.append(int(i)); packed.append(r[0]); pc.append(r[1])
    if not ids: return np.empty(0, np.int64), np.empty((0, NWORDS), np.uint64), np.empty(0, np.int32)
    return np.array(ids, np.int64), np.vstack(packed), np.array(pc, np.int32)

def fps_parallel(items, pool, shard=20000):
    res = pool.map(_fp_batch, [items[i:i+shard] for i in range(0, len(items), shard)])
    if not res: return np.empty(0, np.int64), np.empty((0, NWORDS), np.uint64), np.empty(0, np.int32)
    return (np.concatenate([r[0] for r in res]), np.vstack([r[1] for r in res]), np.concatenate([r[2] for r in res]))

def _aggregate(args):
    """(pids, idx[n,k], sims[n,k]) → [(pid, best, novel, targets, confs)] using _CT/_REFCIDS globals."""
    pids, idx, sims = args; out = []
    for j in range(len(pids)):
        best = float(sims[j, 0]); supp = {}; vote = {}
        for kk in range(idx.shape[1]):
            s = float(sims[j, kk])
            if s < MIN_TAN: break
            for t in _CT.get(int(_REFCIDS[idx[j, kk]]), ()):
                vote[t] = vote.get(t, 0.0) + s
                if s > supp.get(t, 0.0): supp[t] = s
        ranked = sorted(supp, key=lambda t: (-supp[t], -vote[t]))
        out.append((int(pids[j]), round(best, 3), bool(best < MIN_TAN), ranked, [round(supp[t], 3) for t in ranked]))
    return out

_KERNEL = cp.RawKernel(r'''
extern "C" __global__
void tanimoto(const unsigned long long* P, const unsigned long long* R,
              const int* pcb, const int* pct, float* out, int B, int T) {
    long long idx = blockIdx.x * (long long)blockDim.x + threadIdx.x;
    if (idx >= (long long)B * T) return;
    int b = (int)(idx / T), t = (int)(idx % T);
    const unsigned long long* pb = P + (long long)b * 32;
    const unsigned long long* rt = R + (long long)t * 32;
    int inter = 0;
    #pragma unroll
    for (int w = 0; w < 32; w++) inter += __popcll(pb[w] & rt[w]);
    int uni = pcb[b] + pct[t] - inter;
    out[idx] = uni > 0 ? (float)inter / (float)uni : 0.0f;
}
''', 'tanimoto')

def topk_gpu(Pb_d, pcb_d, R_d, pct_d, T, k, B):
    out = cp.empty((B, T), dtype=cp.float32)
    total = B * T; threads = 256; blocks = (total + threads - 1) // threads
    _KERNEL((blocks,), (threads,), (Pb_d, R_d, pcb_d, pct_d, out, np.int32(B), np.int32(T)))
    rows = cp.arange(B)
    idx = cp.empty((B, k), dtype=cp.int32); sims = cp.empty((B, k), dtype=cp.float32)
    for kk in range(k):
        am = cp.argmax(out, axis=1)
        idx[:, kk] = am.astype(cp.int32); sims[:, kk] = out[rows, am]
        out[rows, am] = -1.0
    del out
    return cp.asnumpy(idx), cp.asnumpy(sims)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refsmi", required=True); ap.add_argument("--targets", required=True)
    ap.add_argument("--patents", required=True); ap.add_argument("--outdir", required=True)
    ap.add_argument("--limit", type=int, default=None); ap.add_argument("--batch", type=int, default=4096)
    ap.add_argument("--procs", type=int, default=24)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    # reference FPs (recomputed here = consistent RDKit), to GPU
    t0 = time.time()
    ref_items = [(int(c), s) for c, s in (ln.rstrip("\n").split("\t", 1) for ln in open(a.refsmi)) if c.isdigit() and s]
    with mp.Pool(a.procs) as pf:
        ref_cids, ref_packed, ref_pc = fps_parallel(ref_items, pf)
    R = ref_cids.shape[0]
    R_d = cp.asarray(ref_packed.reshape(-1)); pct_d = cp.asarray(ref_pc)
    print(f"reference: {R:,} FPs on GPU ({R_d.nbytes/1e9:.2f} GB) in {time.time()-t0:.0f}s", flush=True)

    pool = mp.Pool(a.procs, initializer=_init, initargs=(a.targets, ref_cids))   # FP + aggregation workers
    chunks = sorted(glob.glob(f"{a.patents}/compounds_chunk_*.parquet"))
    n = 0; t0 = time.time()
    for f in chunks:
        outp = f"{a.outdir}/preds_{os.path.basename(f)}"
        if os.path.exists(outp): print(f"  skip {os.path.basename(f)}", flush=True); continue
        tb = pq.read_table(f, columns=["id", "smiles"])
        items = list(zip(tb.column("id").to_pylist(), tb.column("smiles").to_pylist()))
        if a.limit: items = items[:max(0, a.limit - n)]
        pids, packed, pc = fps_parallel(items, pool)
        all_idx, all_sims = [], []
        for i in range(0, len(pids), a.batch):
            Pb = packed[i:i+a.batch]
            Pb_d = cp.asarray(Pb.reshape(-1)); pcb_d = cp.asarray(pc[i:i+a.batch])
            idx, sims = topk_gpu(Pb_d, pcb_d, R_d, pct_d, R, KNN, Pb.shape[0])
            all_idx.append(idx); all_sims.append(sims); del Pb_d, pcb_d
        cp.get_default_memory_pool().free_all_blocks()
        idx = np.vstack(all_idx) if all_idx else np.empty((0, KNN), np.int32)
        sims = np.vstack(all_sims) if all_sims else np.empty((0, KNN), np.float32)
        # parallel aggregation
        sh = 8000
        shards = [(pids[i:i+sh], idx[i:i+sh], sims[i:i+sh]) for i in range(0, len(pids), sh)]
        rows = [r for part in pool.map(_aggregate, shards) for r in part]
        pq.write_table(pa.table({"pid": [r[0] for r in rows], "best_tanimoto": [r[1] for r in rows],
                                 "novel": [r[2] for r in rows], "targets": [r[3] for r in rows],
                                 "confs": [r[4] for r in rows]}), outp, compression="zstd")
        n += len(pids); r = n / (time.time() - t0)
        print(f"  {os.path.basename(f)}: {len(pids):,} → total {n:,} · {r:.0f}/s · eta {30.9e6/r/3600:.2f}h · {time.time()-t0:.0f}s", flush=True)
        if a.limit and n >= a.limit: break
    pool.close()
    print(f"\nDONE: {n:,} in {time.time()-t0:.0f}s → {a.outdir}/", flush=True)

if __name__ == "__main__":
    main()

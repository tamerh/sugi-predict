#!/usr/bin/env python3
"""Patent target-atlas — FUSED-kernel GPU k-NN (one pass, no score matrix).

Each block handles one query compound: its threads cooperatively scan ALL reference ligands, compute exact
Morgan-r2/2048 Tanimoto on the fly, and maintain the top-K nearest neighbours inline (per-thread local top-K +
a block merge). No (B×T) score matrix, no argmax passes.

OUTPUT = RAW NEIGHBOURS: per compound, the top-K (neighbour pubchem cid, Tanimoto) + best + novel. Target
scoring/ranking is then a cheap, iterable LOCAL post-step. K is generous (default 150) so weak-but-real targets
(whose ligands sit at neighbour ranks ~20-150) can be recovered by the scoring — NOT capped at the prediction's k.

Usage:
  python gpu_atlas_fused.py --refsmi ref/reference.tsv --patents patents --outdir nbrs [--knn 150] [--limit N] [--procs 24]
"""
import sys, os, glob, time, argparse
import numpy as np, cupy as cp, pyarrow as pa, pyarrow.parquet as pq
import multiprocessing as mp
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

MIN_TAN, MIN_HEAVY, NWORDS = 0.30, 10, 32

def _pack(smi, mh):
    """Morgan r2/2048 packed FP + popcount. mh = min heavy atoms (0 for REFERENCE — keep every ligand,
    matching FPSim2; MIN_HEAVY for patent QUERIES — skip solvent/fragment junk)."""
    m = Chem.MolFromSmiles(smi) if smi else None
    if m is None or m.GetNumHeavyAtoms() < mh: return None
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    a = np.zeros(2048, dtype=np.uint8); DataStructs.ConvertToNumpyArray(bv, a)
    return np.packbits(a).view(np.uint64), int(a.sum())

def _fp_batch(arg):
    items, mh = arg
    ids, packed, pc = [], [], []
    for i, s in items:
        r = _pack(s, mh)
        if r is None: continue
        ids.append(int(i)); packed.append(r[0]); pc.append(r[1])
    if not ids: return np.empty(0, np.int64), np.empty((0, NWORDS), np.uint64), np.empty(0, np.int32)
    return np.array(ids, np.int64), np.vstack(packed), np.array(pc, np.int32)

def fps_parallel(items, pool, mh, shard=20000):
    res = pool.map(_fp_batch, [(items[i:i+shard], mh) for i in range(0, len(items), shard)])
    if not res: return np.empty(0, np.int64), np.empty((0, NWORDS), np.uint64), np.empty(0, np.int32)
    return (np.concatenate([r[0] for r in res]), np.vstack([r[1] for r in res]), np.concatenate([r[2] for r in res]))

def build_kernel(maxk):
    """Compile the fused k-NN kernel with the per-thread top-K arrays sized for this K."""
    src = r'''
extern "C" __global__
void fused_knn(const unsigned long long* P, const unsigned long long* R,
               const int* pcb, const int* pct, int* out_idx, float* out_sim, int B, int T, int K) {
    int b = blockIdx.x;
    if (b >= B) return;
    int tid = threadIdx.x, nth = blockDim.x;
    __shared__ unsigned long long qfp[32];
    __shared__ int qpc;
    for (int i = tid; i < 32; i += nth) qfp[i] = P[(long long)b * 32 + i];
    if (tid == 0) qpc = pcb[b];
    __syncthreads();
    float ls[MAXK]; int li[MAXK];                          // per-thread top-K, ascending (worst at 0)
    for (int i = 0; i < K; i++) { ls[i] = -1.0f; li[i] = -1; }
    for (int t = tid; t < T; t += nth) {
        const unsigned long long* rt = R + (long long)t * 32;
        int inter = 0;
        #pragma unroll
        for (int w = 0; w < 32; w++) inter += __popcll(qfp[w] & rt[w]);
        int uni = qpc + pct[t] - inter;
        float tan = uni > 0 ? (float)inter / (float)uni : 0.0f;
        if (tan > ls[0]) {
            int p = 0;
            while (p < K - 1 && tan > ls[p + 1]) { ls[p] = ls[p + 1]; li[p] = li[p + 1]; p++; }
            ls[p] = tan; li[p] = t;
        }
    }
    extern __shared__ float smem[];
    float* ssim = smem; int* sidx = (int*)(smem + nth * K);
    for (int i = 0; i < K; i++) { ssim[tid * K + i] = ls[i]; sidx[tid * K + i] = li[i]; }
    __syncthreads();
    if (tid == 0) {
        float fs[MAXK]; int fi[MAXK];
        for (int i = 0; i < K; i++) { fs[i] = -1.0f; fi[i] = -1; }
        for (int e = 0; e < nth * K; e++) {
            float tan = ssim[e];
            if (tan > fs[0]) {
                int idx = sidx[e]; int p = 0;
                while (p < K - 1 && tan > fs[p + 1]) { fs[p] = fs[p + 1]; fi[p] = fi[p + 1]; p++; }
                fs[p] = tan; fi[p] = idx;
            }
        }
        for (int i = 0; i < K; i++) {                      // write descending (best first)
            out_sim[(long long)b * K + i] = fs[K - 1 - i];
            out_idx[(long long)b * K + i] = fi[K - 1 - i];
        }
    }
}'''.replace("MAXK", str(maxk))
    return cp.RawKernel(src, 'fused_knn')

def fused_topk(KERNEL, Pb_d, pcb_d, R_d, pct_d, T, k, B, nth):
    out_idx = cp.empty((B, k), dtype=cp.int32); out_sim = cp.empty((B, k), dtype=cp.float32)
    KERNEL((B,), (nth,), (Pb_d, R_d, pcb_d, pct_d, out_idx, out_sim, np.int32(B), np.int32(T), np.int32(k)),
           shared_mem=nth * k * 8)
    return cp.asnumpy(out_idx), cp.asnumpy(out_sim)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refsmi", required=True); ap.add_argument("--patents", required=True)
    ap.add_argument("--outdir", required=True); ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--knn", type=int, default=150); ap.add_argument("--batch", type=int, default=131072)
    ap.add_argument("--procs", type=int, default=24)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    K = a.knn
    nth = max(32, min(128, (48000 // (K * 8)) // 32 * 32))    # fit nth*K*8 bytes of shared mem under 48KB
    KERNEL = build_kernel(K)
    print(f"K={K}, block={nth} threads, shared={nth*K*8} bytes", flush=True)
    pool = mp.Pool(a.procs)

    t0 = time.time()
    ref_items = [(int(c), s) for c, s in (ln.rstrip("\n").split("\t", 1) for ln in open(a.refsmi)) if c.isdigit() and s]
    ref_cids, ref_packed, ref_pc = fps_parallel(ref_items, pool, mh=0)        # REFERENCE: keep every ligand
    R = ref_cids.shape[0]
    R_d = cp.asarray(ref_packed.reshape(-1)); pct_d = cp.asarray(ref_pc)
    print(f"reference: {R:,} FPs on GPU ({R_d.nbytes/1e9:.2f} GB) in {time.time()-t0:.0f}s", flush=True)

    chunks = sorted(glob.glob(f"{a.patents}/compounds_chunk_*.parquet"))
    n = 0; t0 = time.time()
    for f in chunks:
        outp = f"{a.outdir}/nbrs_{os.path.basename(f)}"
        if os.path.exists(outp): print(f"  skip {os.path.basename(f)}", flush=True); continue
        tb = pq.read_table(f, columns=["id", "smiles"])
        items = list(zip(tb.column("id").to_pylist(), tb.column("smiles").to_pylist()))
        if a.limit: items = items[:max(0, a.limit - n)]
        pids, packed, pc = fps_parallel(items, pool, mh=MIN_HEAVY)            # patent QUERIES: skip <10-heavy junk
        idxs, sims = [], []
        for i in range(0, len(pids), a.batch):
            Pb = packed[i:i+a.batch]
            Pb_d = cp.asarray(Pb.reshape(-1)); pcb_d = cp.asarray(pc[i:i+a.batch])
            ix, sm = fused_topk(KERNEL, Pb_d, pcb_d, R_d, pct_d, R, K, Pb.shape[0], nth)
            idxs.append(ix); sims.append(sm); del Pb_d, pcb_d
        cp.get_default_memory_pool().free_all_blocks()
        idx = np.vstack(idxs) if idxs else np.empty((0, K), np.int32)
        sim = np.vstack(sims) if sims else np.empty((0, K), np.float32)
        nbr_cids = ref_cids[idx] if len(idx) else np.empty((0, K), np.int64)
        best = sim[:, 0] if len(sim) else np.empty(0, np.float32)
        pq.write_table(pa.table({"pid": pids.tolist(),
                                 "best_tanimoto": [round(float(x), 3) for x in best],
                                 "novel": [bool(x < MIN_TAN) for x in best],
                                 "nbr_cids": nbr_cids.tolist(),
                                 "nbr_sims": [[round(float(s), 3) for s in row] for row in sim]}),
                       outp, compression="zstd")
        n += len(pids); r = n / (time.time() - t0)
        print(f"  {os.path.basename(f)}: {len(pids):,} → total {n:,} · {r:.0f}/s · eta {30.9e6/r/3600:.2f}h · {time.time()-t0:.0f}s", flush=True)
        if a.limit and n >= a.limit: break
    pool.close()
    print(f"\nDONE: {n:,} in {time.time()-t0:.0f}s → {a.outdir}/", flush=True)

if __name__ == "__main__":
    main()

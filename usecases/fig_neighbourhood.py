#!/usr/bin/env python3
"""Publication figure for the chemical-NEIGHBOURHOOD argument behind the target atlas.

The atlas predicts targets by a nearest-neighbour argument over Morgan-FP Tanimoto, but no page SHOWS the
neighbourhood. This makes it visible for two example compounds (a KNOWN drug, gefitinib, and a NOVEL patent
compound in chemical whitespace):

  (A) Tanimoto-vs-neighbour-rank decay — how fast similarity to the query falls off, with the 0.3 "novel"
      threshold marked. A known drug sits on a plateau of close neighbours; a novel compound falls off a cliff
      below 0.3 (no close known ligand → nothing to transfer a target from).
  (B) 2D MDS layout of the query + its nearest ChEMBL neighbours, embedded from the full pairwise Tanimoto
      DISTANCE matrix, coloured by each neighbour's dominant target gene. A known drug lands inside a tight,
      single-target cluster (e.g. EGFR); a novel compound floats alone, far from any known cluster.

Output: PNG + SVG to /data/bioyoda-preprint/figures/ (or /data/demos/bioyoda/ as fallback).
Run: python usecases/fig_neighbourhood.py
"""
import sys, os, collections
sys.path.insert(0, "/data/bioyoda/modules/compounds"); sys.path.insert(0, "/data/bioyoda")
import numpy as np
import target, fto
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
from sklearn.manifold import MDS
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

OUT = "/data/bioyoda-preprint/figures" if os.path.isdir("/data/bioyoda-preprint/figures") else "/data/demos/bioyoda"
os.makedirs(OUT, exist_ok=True)
eng, ct = target.engine()
NOVEL = target.MIN_TAN                                                  # 0.30 — the whitespace threshold

# load the ChEMBL cid->smiles map for fingerprinting the neighbours (for the true pairwise distance matrix)
csm = {}
for _l in open("/data/bioyoda/work/chembl_reference/reference.tsv"):
    _c, _s = _l.rstrip("\n").split("\t", 1)
    if _c.isdigit(): csm[int(_c)] = _s

def fp(sm):
    m = Chem.MolFromSmiles(sm)
    return AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048) if m else None

def dom_target(cid):
    """dominant (alphabetically-first human) target gene symbol of a ChEMBL ligand, for colouring."""
    ts = [t for t in ct.get(int(cid), ()) if target.is_human(t)]
    if not ts: return None
    return target.gene_sym(sorted(ts)[0])

def neighbourhood(query_smiles, k=60):
    """→ (ranks, sims, neighbour_records). neighbour_records = [(cid, sim, smiles, gene)] for the top-k that we
    can fingerprint, excluding the query's own exact self-match so the layout shows the *neighbours*."""
    res = eng.similarity(query_smiles, 0.05, n_workers=4)               # (cid, tanimoto) desc, wide net
    sims = np.array([float(c) for _, c in res], dtype=float)
    recs = []
    for cid, co in res:
        co = float(co)
        if co >= 0.999:                                                # skip the query's own copy in ChEMBL
            continue
        sm = csm.get(int(cid))
        if not sm: continue
        recs.append((int(cid), co, sm, dom_target(cid)))
        if len(recs) >= k: break
    return np.arange(1, len(sims) + 1), sims, recs

def mds_layout(query_smiles, recs):
    """embed query + neighbours via metric MDS on the full pairwise Tanimoto-DISTANCE matrix (1 - similarity)."""
    fps = [fp(query_smiles)] + [fp(sm) for _, _, sm, _ in recs]
    n = len(fps)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            t = DataStructs.TanimotoSimilarity(fps[i], fps[j])
            D[i, j] = D[j, i] = 1.0 - t
    xy = MDS(n_components=2, dissimilarity="precomputed", random_state=0, normalized_stress="auto",
             init="random", n_init=4, max_iter=400).fit_transform(D)
    return xy                                                          # row 0 = query, rest = neighbours

def palette(genes):
    cmap = plt.get_cmap("tab10")
    uniq = [g for g in dict.fromkeys(genes) if g]
    col = {g: cmap(i % 10) for i, g in enumerate(uniq)}
    return col

def figure(examples):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": "#444",
                         "figure.facecolor": "white", "axes.facecolor": "white"})
    nrow = len(examples)
    fig, axes = plt.subplots(nrow, 2, figsize=(11.5, 4.4 * nrow))
    if nrow == 1: axes = axes.reshape(1, 2)

    for r, (name, query, kind) in enumerate(examples):
        sm, label = fto.resolve(query)
        ranks, sims, recs = neighbourhood(sm)
        best = sims[0] if len(sims) else 0.0
        known = best >= 0.999
        # neighbour best-Tanimoto for the headline = top non-self neighbour
        nbest = recs[0][1] if recs else 0.0

        # --- (A) decay curve (only the visible window — keeps the SVG small) ---
        axA = axes[r, 0]
        W = min(60, len(sims))
        axA.plot(ranks[:W], sims[:W], "-", lw=1.6, color="#2b6cb0")
        axA.scatter(ranks[:W], sims[:W], s=14, color="#2b6cb0", zorder=3)
        axA.axhline(NOVEL, ls="--", lw=1.2, color="#c0392b")
        axA.text(W * 0.42, NOVEL + 0.02, f"novel threshold (Tanimoto {NOVEL:.1f})",
                 color="#c0392b", fontsize=8.5)
        axA.fill_between(ranks[:W], 0, NOVEL, color="#c0392b", alpha=0.05)
        axA.set_xlim(1, W)
        axA.set_ylim(0, 1.02)
        axA.set_xlabel("neighbour rank (k-th nearest known ChEMBL ligand)")
        axA.set_ylabel("Tanimoto similarity to query")
        tag = "KNOWN — itself in ChEMBL" if known else f"novel (nearest neighbour {nbest:.2f})"
        axA.set_title(f"{name}  ·  {tag}", fontsize=11, loc="left", fontweight="bold")
        axA.grid(True, alpha=0.25, lw=0.6)

        # --- (B) MDS layout ---
        axB = axes[r, 1]
        xy = mds_layout(sm, recs)
        genes = [g for _, _, _, g in recs]
        col = palette(genes)
        # neighbours
        for i, (cid, co, smi, g) in enumerate(recs, start=1):
            c = col.get(g, "#9aa4b2")
            axB.scatter(xy[i, 0], xy[i, 1], s=24 + 90 * co, color=c, alpha=0.8,
                        edgecolor="white", linewidth=0.4, zorder=2)
        # query as a black star
        axB.scatter(xy[0, 0], xy[0, 1], s=240, marker="*", color="black", edgecolor="white",
                    linewidth=1.0, zorder=5)
        axB.annotate("query", (xy[0, 0], xy[0, 1]), textcoords="offset points", xytext=(8, 6),
                     fontsize=9, fontweight="bold")
        # legend: top targets by neighbour count
        cnt = collections.Counter(g for g in genes if g)
        top = [g for g, _ in cnt.most_common(6)]
        handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor=col[g], markersize=8,
                          label=f"{g} (×{cnt[g]})") for g in top]
        handles.append(Line2D([0], [0], marker="*", color="w", markerfacecolor="black", markersize=12,
                              label="query compound"))
        axB.legend(handles=handles, fontsize=8, loc="best", framealpha=0.9, title="dominant target",
                   title_fontsize=8.5)
        axB.set_title("chemical neighbourhood (MDS on Tanimoto distance)", fontsize=11, loc="left",
                      fontweight="bold")
        # robust limits: pad the point cloud so a single far outlier can't blow up the autoscaled canvas
        mx = float(np.median(np.abs(xy[:, 0] - np.median(xy[:, 0]))) + xy[:, 0].std())
        my = float(np.median(np.abs(xy[:, 1] - np.median(xy[:, 1]))) + xy[:, 1].std())
        cx, cy = float(np.median(xy[:, 0])), float(np.median(xy[:, 1]))
        rx = max(mx * 3 + 0.05, abs(xy[0, 0] - cx) * 1.15)
        ry = max(my * 3 + 0.05, abs(xy[0, 1] - cy) * 1.15)
        axB.set_xlim(cx - rx, cx + rx); axB.set_ylim(cy - ry, cy + ry)
        axB.set_xticks([]); axB.set_yticks([])
        axB.set_xlabel("marker size ∝ similarity to query")

    fig.suptitle("The chemical-neighbourhood argument behind the target atlas", fontsize=13.5,
                 fontweight="bold", y=0.997)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    png = f"{OUT}/fig_neighbourhood.png"; svg = f"{OUT}/fig_neighbourhood.svg"
    fig.savefig(png, dpi=200)
    fig.savefig(svg)
    print("wrote", png)
    print("wrote", svg)

def find_novel_patent():
    """a NOVEL patent compound (nearest known ChEMBL ligand 0.2–0.29) for the whitespace example."""
    import glob, random, pyarrow.parquet as pq
    rng = random.Random(7)
    for f in sorted(glob.glob("/data/bioyoda/raw_data/patents/chunked_compounds/compounds_chunk_*.parquet"))[::13]:
        tab = pq.read_table(f, columns=["id", "smiles"])
        ids, smis = tab.column("id").to_pylist(), tab.column("smiles").to_pylist()
        for i in rng.sample(range(len(smis)), min(400, len(smis))):
            s = smis[i]
            if not s: continue
            rr = eng.similarity(s, 0.10, n_workers=4)
            b = float(rr[0][1]) if len(rr) else 0.0
            if 0.20 <= b < 0.29 and Chem.MolFromSmiles(s) and 15 <= len(s) <= 60:
                return f"SCHEMBL{ids[i]} (patent)", s
    return None, None

if __name__ == "__main__":
    examples = [("Gefitinib", "gefitinib", "known")]
    nid, nsm = find_novel_patent()
    if nsm:
        examples.append((nid, nsm, "novel"))
        print("novel patent example:", nid)
    else:
        print("no novel patent example found — figure shows the known drug only")
    figure(examples)

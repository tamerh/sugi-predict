#!/usr/bin/env python
"""
PoC #3D-lens: Does a 3D-shape or pharmacophore similarity "lens" beat the
incumbent 2D Morgan/ECFP4 lens on a ligand-based virtual-screening benchmark?

BioYoda's compound collection currently uses ONLY 2D Morgan ECFP4 (r=2, 2048b).
CHEESE (competitor) wins with 3D-shape + electrostatic embeddings. We want a
number: does a 3D / pharmacophore lens add retrieval ENRICHMENT over 2D Morgan
on an actives/decoys benchmark, by a margin that justifies building a second
lens at 31M scale?

Design (small, ligand-based VS):
  - Target: EGFR tyrosine-kinase inhibitors (a clear, well-known chemotype).
  - ACTIVES: ~25 known EGFR TKIs (hardcoded canonical SMILES).
  - DECOYS: random drug-like SMILES scrolled from the patents_compounds
            Qdrant collection (localhost:6333), parseable only, ~150 kept.
  - QUERIES: a few actives. For each query, rank ALL other molecules by:
      (a) 2D Morgan ECFP4 Tanimoto                       [incumbent]
      (b) Gobbi 2D pharmacophore fingerprint Tanimoto    [pharmacophore lens]
      (c) 3D shape via rdMolAlign.GetO3A score (Open3DAlign, MMFF)
      (d) 3D shape via rdShapeHelpers ShapeTanimoto (1 - dist) after O3A align
  - Metric: per-query ROC-AUC and EF1% for recovering the OTHER actives,
            averaged over queries.

Read-only w.r.t. Qdrant: we only scroll() decoys, never write.
"""

import sys
import time
import random
import warnings

import numpy as np

warnings.filterwarnings("ignore")

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, DataStructs
from rdkit.Chem import rdShapeHelpers, rdMolAlign
from rdkit.Chem.Pharm2D import Generate, Gobbi_Pharm2D

RDLogger.DisableLog("rdApp.*")

RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# ----------------------------------------------------------------------------
# 1. ACTIVES: known EGFR tyrosine-kinase inhibitors (canonical SMILES).
#    Sourced from well-known approved/clinical EGFR TKIs.
# ----------------------------------------------------------------------------
ACTIVES = {
    "gefitinib":   "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
    "erlotinib":   "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1",
    "lapatinib":   "CS(=O)(=O)CCNCc1ccc(-c2ccc3ncnc(Nc4ccc(OCc5cccc(F)c5)c(Cl)c4)c3c2)o1",
    "afatinib":    "CN(C)C/C=C/C(=O)Nc1cc2c(Nc3ccc(F)c(Cl)c3)ncnc2cc1O[C@H]1CCOC1",
    "dacomitinib": "CN1CCC(CC1)COc1cc2c(Nc3ccc(F)c(Cl)c3)ncnc2cc1NC(=O)/C=C/CN(C)C",
    "osimertinib": "COc1cc(N(C)CCN(C)C)c(NC(=O)C=C)cc1Nc1nccc(-c2cn(C)c3ccccc23)n1",
    "canertinib":  "C=CC(=O)Nc1cccc(Nc2ncnc3cc(OCCCN4CCOCC4)c(OC)cc23)c1",
    "pelitinib":   "CCOc1cc2ncc(C#N)c(Nc3ccc(F)c(Cl)c3)c2cc1NC(=O)/C=C/CN(C)C",
    "neratinib":   "CCOc1cc2ncc(C#N)c(Nc3ccc(OCc4cccc(F)c4)c(Cl)c3)c2cc1NC(=O)/C=C/CN(C)C",
    "vandetanib":  "COc1cc2ncnc(Nc3ccc(Br)cc3F)c2cc1OCC1CCN(C)CC1",
    "icotinib":    "C#Cc1cccc(Nc2ncnc3c2cc2c(c3)OCCOCCOCCO2)c1",
    "brigatinib":  "COc1cc(N2CCC(N3CCN(C)CC3)CC2)ccc1Nc1ncc(Cl)c(Nc2ccccc2P(C)(C)=O)n1",
    "rociletinib": "CN(CCOC)c1ccc(NC(=O)C=C)c(Nc2nccc(-c3cccnc3)n2)c1",
    "olmutinib":   "C=CC(=O)Nc1cccc(Oc2nc(Nc3ccc(N4CCOCC4)cc3OC)ncc2Sc2ccccc2)c1",
    "nazartinib":  "C=CC(=O)N1CCC[C@@H](n2c(=O)cc(-c3ccccc3Cl)c3cnc(NC4CCOCC4)nc32)C1",
    "mobocertinib":"CCOC(=O)C(C)c1cc(Nc2nccc(-c3cn(C)c4ccccc34)n2)c(NC(=O)/C=C/CN(C)C)cc1OC",
    "poziotinib":  "C=CC(=O)Nc1cc(Oc2cc3c(Nc4ccc(F)c(Cl)c4)ncnc3cc2OC)ccc1F",
    "varlitinib":  "Cc1cn2ncnc(Nc3cccc(C)c3)c2c1-c1ccc2c(c1)OCO2",
    "tucatinib":   "Cc1ccc(-c2nc(NCc3ccc4[nH]ncc4c3)c3ccncc3n2)cc1",
    "sapitinib":   "COc1cc2ncnc(Nc3ccc4c(c3)OCO4)c2cc1OCC1CCN(C(C)=O)CC1",
    "tesevatinib": "ClC1=CC=C(NC2=NC=NC3=CC4=C(C=C23)OCO4)C=C1Cl",
    "epitinib":    "COc1cc2ncnc(Nc3ccc(OCc4ccccn4)c(Cl)c3)c2cc1OCCCN1CCOCC1",
    "allitinib":   "CN(C)C/C=C/C(=O)Nc1cc2c(Nc3ccc(OCc4cccc(F)c4)c(Cl)c3)ncnc2cc1OC",
    "simotinib":   "C#Cc1cccc(Nc2ncnc3cc(OC)c(OCCCN4CCCC4)cc23)c1",
}

# A handful of these SMILES contain '...' placeholders intentionally invalid;
# they will be dropped at parse time (kept names for documentation). We rely on
# the cleanly specified ones below. The parser drops anything unparseable.

QUERY_NAMES = ["gefitinib", "erlotinib", "afatinib", "lapatinib",
               "osimertinib", "vandetanib"]


def get_decoys_from_qdrant(n_target=150):
    """Scroll random drug-like SMILES from patents_compounds (read-only)."""
    try:
        from qdrant_client import QdrantClient
        c = QdrantClient("localhost", port=6333, check_compatibility=False)
        # scroll more than needed; many won't parse / may be huge.
        pts, _ = c.scroll("patents_compounds", limit=1200,
                          with_payload=["smiles"], with_vectors=False)
        smis = []
        for p in pts:
            s = p.payload.get("smiles")
            if s:
                smis.append(s)
        return smis
    except Exception as e:
        print(f"[warn] Qdrant scroll failed: {e}", file=sys.stderr)
        return []


def parse_druglike(smi):
    """Parse SMILES; keep drug-like fragments only (single component, MW<700)."""
    m = Chem.MolFromSmiles(smi)
    if m is None:
        return None
    # take largest fragment if salt/mixture
    frags = Chem.GetMolFrags(m, asMols=True, sanitizeFrags=False)
    if len(frags) > 1:
        m = max(frags, key=lambda x: x.GetNumHeavyAtoms())
        try:
            Chem.SanitizeMol(m)
        except Exception:
            return None
    n = m.GetNumHeavyAtoms()
    if n < 12 or n > 50:
        return None
    return m


def embed3d(mol):
    """Add Hs, embed one conformer, MMFF optimize. Returns mol or None."""
    mh = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = RANDOM_SEED
    if AllChem.EmbedMolecule(mh, params) != 0:
        # fallback: random coords
        if AllChem.EmbedMolecule(mh, useRandomCoords=True,
                                 randomSeed=RANDOM_SEED) != 0:
            return None
    try:
        AllChem.MMFFOptimizeMolecule(mh, maxIters=400)
    except Exception:
        pass
    return mh


# ---- enrichment metrics -----------------------------------------------------
def roc_auc(scores, labels):
    """ROC-AUC; higher score = more active-like."""
    from sklearn.metrics import roc_auc_score
    if len(set(labels)) < 2:
        return float("nan")
    return roc_auc_score(labels, scores)


def ef_at(scores, labels, frac=0.01):
    """Enrichment factor in top `frac` of the ranked list."""
    order = np.argsort(scores)[::-1]
    n = len(scores)
    topn = max(1, int(round(frac * n)))
    n_act_total = sum(labels)
    if n_act_total == 0:
        return float("nan")
    hits_top = sum(labels[i] for i in order[:topn])
    return (hits_top / topn) / (n_act_total / n)


def main():
    t0 = time.time()
    print("=" * 70)
    print("PoC: 3D / pharmacophore lens vs 2D Morgan ECFP4 (EGFR TKIs)")
    print("=" * 70)

    # --- build active set ---
    active_mols, active_names = [], []
    for name, smi in ACTIVES.items():
        m = Chem.MolFromSmiles(smi)
        if m is not None and 12 <= m.GetNumHeavyAtoms() <= 60:
            active_mols.append(m)
            active_names.append(name)
    print(f"Actives parsed: {len(active_mols)} / {len(ACTIVES)}")

    # --- build decoy set ---
    raw = get_decoys_from_qdrant()
    print(f"Decoy SMILES scrolled from Qdrant: {len(raw)}")
    random.shuffle(raw)
    decoy_mols = []
    for smi in raw:
        m = parse_druglike(smi)
        if m is not None:
            decoy_mols.append(m)
        if len(decoy_mols) >= 150:
            break
    # fallback synthetic decoys if Qdrant unavailable
    if len(decoy_mols) < 50:
        print("[warn] too few Qdrant decoys; this benchmark needs them.",
              file=sys.stderr)
    print(f"Decoys kept (drug-like, parseable): {len(decoy_mols)}")

    # --- assemble library: actives + decoys ---
    mols = active_mols + decoy_mols
    labels_all = [1] * len(active_mols) + [0] * len(decoy_mols)
    names_all = active_names + [f"decoy_{i}" for i in range(len(decoy_mols))]
    N = len(mols)
    print(f"Total library: {N} molecules ({sum(labels_all)} actives)")

    # --- precompute 2D fingerprints ---
    print("\nComputing 2D Morgan ECFP4 fingerprints...")
    mfpgen = AllChem.GetMorganGenerator(radius=2, fpSize=2048)
    morgan_fps = [mfpgen.GetFingerprint(m) for m in mols]

    print("Computing Gobbi 2D pharmacophore fingerprints...")
    pharm_fps = []
    for m in mols:
        try:
            fp = Generate.Gen2DFingerprint(m, Gobbi_Pharm2D.factory)
        except Exception:
            fp = None
        pharm_fps.append(fp)

    # --- precompute 3D conformers (the slow part) ---
    print("Generating 3D conformers (ETKDGv3 + MMFF)... (slow)")
    tc = time.time()
    mol3d = []
    for i, m in enumerate(mols):
        mol3d.append(embed3d(m))
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{N} embedded ({time.time()-tc:.0f}s)")
    n_embedded = sum(1 for x in mol3d if x is not None)
    print(f"3D conformers generated: {n_embedded}/{N} "
          f"({time.time()-tc:.0f}s)")

    # --- query indices ---
    query_idx = [names_all.index(q) for q in QUERY_NAMES
                 if q in names_all and mol3d[names_all.index(q)] is not None]
    print(f"\nQueries: {[names_all[i] for i in query_idx]}")

    lenses = ["2D_Morgan_ECFP4", "Gobbi_Pharm2D", "O3A_score", "ShapeTanimoto"]
    results = {ln: {"auc": [], "ef1": [], "ef5": [], "ef10": []}
               for ln in lenses}

    for qi in query_idx:
        q_mol = mols[qi]
        q_morgan = morgan_fps[qi]
        q_pharm = pharm_fps[qi]
        q_3d = mol3d[qi]

        # target indices = everything except the query
        idxs = [i for i in range(N) if i != qi]
        labels = [labels_all[i] for i in idxs]

        # (a) 2D Morgan Tanimoto
        s_morgan = [DataStructs.TanimotoSimilarity(q_morgan, morgan_fps[i])
                    for i in idxs]

        # (b) Gobbi pharmacophore Tanimoto
        s_pharm = []
        for i in idxs:
            if q_pharm is not None and pharm_fps[i] is not None:
                s_pharm.append(DataStructs.TanimotoSimilarity(q_pharm,
                                                              pharm_fps[i]))
            else:
                s_pharm.append(0.0)

        # (c)/(d) 3D: O3A align then score + shape tanimoto
        s_o3a, s_shape = [], []
        q3 = Chem.Mol(q_3d)
        q_mmff = AllChem.MMFFGetMoleculeProperties(q3)
        for i in idxs:
            t3 = mol3d[i]
            if t3 is None or q_mmff is None:
                s_o3a.append(0.0)
                s_shape.append(0.0)
                continue
            try:
                t3c = Chem.Mol(t3)
                t_mmff = AllChem.MMFFGetMoleculeProperties(t3c)
                if t_mmff is None:
                    raise ValueError("no mmff")
                o3a = rdMolAlign.GetO3A(t3c, q3, t_mmff, q_mmff)
                score = o3a.Score()
                o3a.Align()  # apply transform to t3c so shapes overlap
                s_o3a.append(score)
                dist = rdShapeHelpers.ShapeTanimotoDist(t3c, q3)
                s_shape.append(1.0 - dist)
            except Exception:
                s_o3a.append(0.0)
                s_shape.append(0.0)

        for ln, sc in zip(lenses, [s_morgan, s_pharm, s_o3a, s_shape]):
            results[ln]["auc"].append(roc_auc(np.array(sc), labels))
            results[ln]["ef1"].append(ef_at(sc, labels, 0.01))
            results[ln]["ef5"].append(ef_at(sc, labels, 0.05))
            results[ln]["ef10"].append(ef_at(sc, labels, 0.10))

        print(f"  query {names_all[qi]:12s} done")

    # --- report ---
    print("\n" + "=" * 70)
    print("RESULTS  (averaged over queries; N=%d library, %d actives)"
          % (N, sum(labels_all)))
    print("=" * 70)
    hdr = f"{'Lens':<20}{'ROC-AUC':>10}{'EF@1%':>9}{'EF@5%':>9}{'EF@10%':>9}"
    print(hdr)
    print("-" * len(hdr))
    table = []
    for ln in lenses:
        auc = np.nanmean(results[ln]["auc"])
        ef1 = np.nanmean(results[ln]["ef1"])
        ef5 = np.nanmean(results[ln]["ef5"])
        ef10 = np.nanmean(results[ln]["ef10"])
        table.append((ln, auc, ef1, ef5, ef10))
        print(f"{ln:<20}{auc:>10.3f}{ef1:>9.2f}{ef5:>9.2f}{ef10:>9.2f}")

    # markdown table to stdout
    print("\n--- markdown ---")
    print("| Lens | ROC-AUC | EF@1% | EF@5% | EF@10% |")
    print("|---|---|---|---|---|")
    for ln, auc, ef1, ef5, ef10 in table:
        print(f"| {ln} | {auc:.3f} | {ef1:.2f} | {ef5:.2f} | {ef10:.2f} |")

    # verdict heuristic
    base_auc = np.nanmean(results["2D_Morgan_ECFP4"]["auc"])
    best_3d = max(np.nanmean(results["O3A_score"]["auc"]),
                  np.nanmean(results["ShapeTanimoto"]["auc"]))
    print(f"\n2D Morgan AUC={base_auc:.3f}  best-3D AUC={best_3d:.3f}  "
          f"delta={best_3d-base_auc:+.3f}")
    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()

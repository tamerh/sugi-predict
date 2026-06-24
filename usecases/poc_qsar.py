#!/usr/bin/env python
"""
poc_qsar.py — "Modeller"-style retrieval->prediction PoC for BioYoda.

Question: can a FAST classifier trained on the SAME frozen molecular
representation BioYoda already stores (Morgan ECFP4, radius 2, 2048 bits)
predict bioactivity/ADMET well enough to ship as a feature for non-ML users?

Datasets: MoleculeNet BACE (binding/classification) and BBBP (blood-brain
barrier penetration). Both small, public, with known ECFP+RF baselines.

Featurization: Morgan ECFP4 (radius 2, nBits=2048) — identical to BioYoda's
stored fingerprints, so this measures the predictive ceiling of the frozen rep.

Models: LogisticRegression, RandomForest, small MLP.
Splits: scaffold (honest QSAR test) + random (optimistic comparison).
Metrics: ROC-AUC, PR-AUC on held-out test.

Self-contained: downloads CSVs to a temp dir, trains, prints a markdown report.
Does NOT touch any Qdrant collection or production config.
"""
import io
import sys
import time
import urllib.request
import warnings
from collections import defaultdict

import numpy as np

warnings.filterwarnings("ignore")

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.DataStructs import ConvertToNumpyArray

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import roc_auc_score, average_precision_score

RDLogger.DisableLog("rdApp.*")

RADIUS = 2
NBITS = 2048
SEED = 42
rng = np.random.RandomState(SEED)

DATASETS = {
    "BACE": {
        "url": "https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/bace.csv",
        "smiles_col": "mol",
        "label_col": "Class",
        # MoleculeNet leaderboard ECFP/RF scaffold-split ballpark
        "baseline": "ECFP+RF scaffold ~0.78-0.84 ROC-AUC (MoleculeNet)",
    },
    "BBBP": {
        "url": "https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/BBBP.csv",
        "smiles_col": "smiles",
        "label_col": "p_np",
        "baseline": "ECFP+RF scaffold ~0.89-0.92 ROC-AUC (MoleculeNet)",
    },
}


def fetch_csv(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        raw = r.read().decode("utf-8", errors="replace")
    lines = raw.splitlines()
    header = lines[0].split(",")
    rows = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        # naive split is fine: SMILES has no commas in these files
        rows.append(ln.split(","))
    return header, rows


def featurize(smiles):
    """SMILES -> (2048,) ECFP4 numpy array, or None if RDKit can't parse."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    fp = AllChem.GetMorganFingerprintAsBitVect(mol, RADIUS, nBits=NBITS)
    arr = np.zeros((NBITS,), dtype=np.int8)
    ConvertToNumpyArray(fp, arr)
    return arr


def scaffold_of(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        return MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=False)
    except Exception:
        return None


def scaffold_split(smiles_list, frac_train=0.8):
    """Deterministic scaffold split (DeepChem-style): bin by Bemis-Murcko
    scaffold, sort bins largest-first, fill train then test. Ensures test
    scaffolds are unseen in train -> honest generalization estimate."""
    buckets = defaultdict(list)
    for i, smi in enumerate(smiles_list):
        scaf = scaffold_of(smi)
        buckets[scaf if scaf is not None else f"__none_{i}"].append(i)
    bins = sorted(buckets.values(), key=lambda x: (len(x), x[0]), reverse=True)
    n_total = len(smiles_list)
    cutoff = frac_train * n_total
    train_idx, test_idx = [], []
    for b in bins:
        if len(train_idx) + len(b) <= cutoff:
            train_idx += b
        else:
            test_idx += b
    return np.array(train_idx), np.array(test_idx)


def random_split(n, frac_train=0.8):
    idx = rng.permutation(n)
    cut = int(frac_train * n)
    return idx[:cut], idx[cut:]


def build_models():
    return {
        "LogReg": LogisticRegression(max_iter=1000, C=1.0, solver="liblinear"),
        "RandomForest": RandomForestClassifier(
            n_estimators=500, n_jobs=-1, random_state=SEED
        ),
        "MLP": MLPClassifier(
            hidden_layer_sizes=(256,), max_iter=200, random_state=SEED,
            early_stopping=True,
        ),
    }


def evaluate(X, y, train_idx, test_idx):
    Xtr, Xte = X[train_idx], X[test_idx]
    ytr, yte = y[train_idx], y[test_idx]
    out = {}
    for name, model in build_models().items():
        model.fit(Xtr, ytr)
        if hasattr(model, "predict_proba"):
            p = model.predict_proba(Xte)[:, 1]
        else:
            p = model.decision_function(Xte)
        # guard against a test fold with a single class
        if len(np.unique(yte)) < 2:
            out[name] = (float("nan"), float("nan"))
        else:
            out[name] = (roc_auc_score(yte, p), average_precision_score(yte, p))
    return out


def load_dataset(name, cfg):
    header, rows = fetch_csv(cfg["url"])
    si = header.index(cfg["smiles_col"])
    li = header.index(cfg["label_col"])
    smiles, X, y = [], [], []
    bad = 0
    for r in rows:
        if len(r) <= max(si, li):
            bad += 1
            continue
        smi = r[si].strip()
        try:
            lab = int(float(r[li].strip()))
        except ValueError:
            bad += 1
            continue
        fp = featurize(smi)
        if fp is None:
            bad += 1
            continue
        smiles.append(smi)
        X.append(fp)
        y.append(lab)
    return smiles, np.array(X), np.array(y), bad


def main():
    t0 = time.time()
    report = []
    report.append("# BioYoda PoC: frozen-fingerprint QSAR/ADMET predictor\n")
    report.append(
        f"Representation: Morgan ECFP4 (radius={RADIUS}, nBits={NBITS}) — "
        "identical to BioYoda's stored fingerprints.\n"
    )

    all_rows = []
    for name, cfg in DATASETS.items():
        try:
            smiles, X, y, bad = load_dataset(name, cfg)
        except Exception as e:
            report.append(f"## {name}\nFAILED to load: {e}\n")
            continue

        pos = int(y.sum())
        report.append(
            f"## {name}\n"
            f"- n_compounds (parsed): {len(y)}  (dropped {bad})\n"
            f"- positives: {pos} ({pos/len(y):.1%})\n"
            f"- baseline: {cfg['baseline']}\n"
        )

        for split_name, (tr, te) in {
            "scaffold": scaffold_split(smiles),
            "random": random_split(len(y)),
        }.items():
            # check class balance in test
            res = evaluate(X, y, tr, te)
            report.append(
                f"\n**{split_name} split** "
                f"(train={len(tr)}, test={len(te)}, "
                f"test_pos={int(y[te].sum())}/{len(te)})\n"
            )
            report.append("| Model | ROC-AUC | PR-AUC |")
            report.append("|---|---|---|")
            for m, (roc, pr) in res.items():
                report.append(f"| {m} | {roc:.3f} | {pr:.3f} |")
                all_rows.append((name, split_name, m, roc, pr))
        report.append("")

    report.append(f"\n_Total runtime: {time.time()-t0:.1f}s_\n")
    print("\n".join(report))

    # compact machine-readable summary at the end
    print("\n### Summary (dataset, split, model, ROC-AUC, PR-AUC)")
    for row in all_rows:
        print(f"  {row[0]:5s} {row[1]:8s} {row[2]:12s} "
              f"ROC={row[3]:.3f} PR={row[4]:.3f}")


if __name__ == "__main__":
    sys.exit(main())

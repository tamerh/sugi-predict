#!/usr/bin/env python3
"""Mode D — "Modeller": train a fast predictor on FROZEN Morgan fingerprints (the exact ECFP4 the
compound substrate already stores), then score new molecules. Retrieval -> prediction for non-ML users.

Validated by usecases/poc_qsar.py: frozen ECFP4 + sklearn = MoleculeNet baselines (BACE 0.78 / BBBP 0.85
scaffold ROC-AUC), seconds, no GPU, LogReg ~= RF. We report the SCAFFOLD-split metric (honest for novel
chemistry) and gate on minimum labels / class balance.

CLI:
  python qsar.py train <labeled.csv> [--smiles-col smiles --label-col label --model logreg|rf --out M.pkl]
  python qsar.py score <model.pkl> <input>   # input = a .csv (--smiles-col) OR SMILES|SCHEMBL<id>|drug-name
"""
import sys, os, argparse, warnings, time
from collections import defaultdict
warnings.filterwarnings("ignore")
ROOT = os.environ.get("BIOYODA_ROOT", "/data/bioyoda")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # so `import fto` works regardless of cwd
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from modules.paths import QSAR_MODELS
import numpy as np, joblib
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.DataStructs import ConvertToNumpyArray
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
RDLogger.DisableLog("rdApp.*")

RADIUS, NBITS, SEED, MIN_LABELS = 2, 2048, 42, 200
MODELDIR = str(QSAR_MODELS)

def featurize(smiles):
    m = Chem.MolFromSmiles(smiles)
    if m is None: return None
    fp = AllChem.GetMorganFingerprintAsBitVect(m, RADIUS, nBits=NBITS)
    a = np.zeros((NBITS,), dtype=np.int8); ConvertToNumpyArray(fp, a); return a
def scaffold_of(smiles):
    m = Chem.MolFromSmiles(smiles)
    try: return MurckoScaffold.MurckoScaffoldSmiles(mol=m, includeChirality=False) if m else None
    except Exception: return None
def scaffold_split(smiles, frac_train=0.8):
    buckets = defaultdict(list)
    for i, s in enumerate(smiles): buckets[scaffold_of(s) or f"__none_{i}"].append(i)
    cutoff, tr, te = frac_train * len(smiles), [], []
    for b in sorted(buckets.values(), key=lambda x: (len(x), x[0]), reverse=True):
        (tr if len(tr) + len(b) <= cutoff else te).extend(b)
    return np.array(tr), np.array(te)
def make_model(kind):
    return (LogisticRegression(max_iter=1000, solver="liblinear") if kind == "logreg"
            else RandomForestClassifier(n_estimators=500, n_jobs=-1, random_state=SEED))

def load_labeled(path, smiles_col, label_col):
    import csv
    smiles, X, y, bad = [], [], [], 0
    with open(path) as f:
        for row in csv.DictReader(f):
            s = (row.get(smiles_col) or "").strip()
            try: lab = int(float(row.get(label_col)))
            except (TypeError, ValueError): bad += 1; continue
            fp = featurize(s)
            if fp is None: bad += 1; continue
            smiles.append(s); X.append(fp); y.append(lab)
    return smiles, np.array(X), np.array(y), bad

def train(path, smiles_col, label_col, kind, out):
    smiles, X, y, bad = load_labeled(path, smiles_col, label_col)
    n, pos = len(y), int(y.sum())
    if n < MIN_LABELS: sys.exit(f"only {n} usable labeled rows (need >= {MIN_LABELS}); dropped {bad}")
    if pos == 0 or pos == n: sys.exit(f"need both classes present (got {pos} positives / {n})")
    if min(pos, n - pos) / n < 0.05: print(f"  ⚠ class imbalance: {pos} pos / {n} ({pos/n:.1%}) — AUC ok, but watch calibration")
    tr, te = scaffold_split(smiles)
    mdl = make_model(kind); mdl.fit(X[tr], y[tr])
    p = mdl.predict_proba(X[te])[:, 1]
    roc = roc_auc_score(y[te], p) if len(np.unique(y[te])) > 1 else float("nan")
    pr = average_precision_score(y[te], p) if len(np.unique(y[te])) > 1 else float("nan")
    final = make_model(kind); final.fit(X, y)            # deploy model = trained on ALL labels
    os.makedirs(MODELDIR, exist_ok=True)
    out = out or f"{MODELDIR}/{os.path.splitext(os.path.basename(path))[0]}.pkl"
    joblib.dump({"model": final, "radius": RADIUS, "nbits": NBITS, "kind": kind,
                 "n": n, "pos": pos, "cv_scaffold_roc": roc, "cv_scaffold_pr": pr}, out)
    print(f"trained {kind} on {n} mols ({pos} pos, dropped {bad})")
    print(f"  honest SCAFFOLD-split:  ROC-AUC {roc:.3f}   PR-AUC {pr:.3f}")
    print(f"  deploy model (all data) -> {out}")

def score(model_path, inp, smiles_col):
    d = joblib.load(model_path); mdl = d["model"]
    print(f"model: {model_path}  (trained on {d['n']} mols, scaffold ROC-AUC {d['cv_scaffold_roc']:.3f})")
    items = []   # (label, smiles)
    if inp.endswith(".csv"):
        import csv
        with open(inp) as f:
            reader = csv.DictReader(f)
            if reader.fieldnames and smiles_col not in reader.fieldnames:
                sys.exit(f"column {smiles_col!r} not in {inp} (columns: {reader.fieldnames}); pass --smiles-col")
            for row in reader:
                s = (row.get(smiles_col) or "").strip()
                if s: items.append((s, s))
        if not items: sys.exit(f"no usable SMILES read from {inp} (column {smiles_col!r} empty?)")
    else:
        import fto  # reuse SMILES|SCHEMBL<id>|drug-name resolver (no FPSim2 engine load)
        sm, label = fto.resolve(inp)
        if not sm: sys.exit(f"could not resolve query: {inp!r}")
        items.append((label, sm))
    print(f"{'query':28} {'P(active)':>9}")
    for label, s in items:
        fp = featurize(s)
        if fp is None: print(f"{label[:28]:28} {'unparseable':>9}"); continue
        print(f"{label[:28]:28} {mdl.predict_proba(fp.reshape(1, -1))[0, 1]:>9.3f}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="action", required=True)
    t = sub.add_parser("train"); t.add_argument("csv"); t.add_argument("--smiles-col", default="smiles")
    t.add_argument("--label-col", default="label"); t.add_argument("--model", default="logreg", choices=["logreg", "rf"])
    t.add_argument("--out", default=None)
    s = sub.add_parser("score"); s.add_argument("model"); s.add_argument("input"); s.add_argument("--smiles-col", default="smiles")
    a = ap.parse_args()
    if a.action == "train": train(a.csv, a.smiles_col, a.label_col, a.model, a.out)
    else: score(a.model, a.input, a.smiles_col)

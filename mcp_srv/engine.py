"""BioYoda substrate engine — the three primitives behind both the REST API and the MCP tools.

Read-only against Qdrant (search / scroll / count only). Embedders load lazily on first use. The engine is the
single source of truth: api.py and mcp_handlers.py both call it, so REST / MCP / the web all behave identically.
"""
import os
import sys

sys.path.insert(0, "/data/bioyoda/modules/compounds")
sys.path.insert(0, "/data/bioyoda")

from modules.paths import (TEXT_SUPPORT_QUERY_EMB, CHEMBL_NAMES_JSON,
                           CHEMBL_MECHANISMS_JSON)
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, Range

QDRANT_URL = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")
MAX_LIMIT = 100

# collection -> (modality, dim). modality decides how a free-text/smiles/accession query is embedded.
COLLECTIONS = {
    "patent_compounds":        ("chemical", 2048),   # unified: all compounds + structure + predictions + provenance (alias -> patent_compounds_v2)
    "chembl":                  ("chemical", 2048),   # ChEMBL reference ligands
    "clinical_trials_medcpt":  ("text", 768),        # clinical trials (MedCPT)
    "patents_text":            ("text", 768),        # patent text (MedCPT; Qdrant alias -> patents_text_medcpt)
    "esm2":                    ("protein", 1280),     # SwissProt ESM-2 protein embeddings
}

_qc = None
def qc():
    global _qc
    if _qc is None:
        _qc = QdrantClient(url=QDRANT_URL, timeout=120)
    return _qc


# --------------------------------------------------------------------------- embedders (lazy)
_medcpt = None
def embed_text(text):
    """MedCPT query encoder (768-d) for the text collections."""
    global _medcpt
    if _medcpt is None:
        import torch
        from transformers import AutoTokenizer, AutoModel
        tok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
        m = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()
        _medcpt = (torch, tok, m)
    torch, tok, m = _medcpt
    with torch.no_grad():
        e = tok([text], truncation=True, padding=True, max_length=64, return_tensors="pt")
        return torch.nn.functional.normalize(m(**e).last_hidden_state[:, 0, :], dim=1)[0].numpy().tolist()


def embed_smiles(smiles):
    """Morgan ECFP4 (r=2, 2048-bit), L2-normalised — the chemical collections' vector."""
    from rdkit import Chem
    from rdkit.Chem import AllChem, DataStructs
    from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
    import numpy as np
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return None
    bv = AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)
    a = np.zeros(2048, dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, a)
    n = np.linalg.norm(a)
    return (a / n).tolist() if n > 0 else None


def embed_protein(accession):
    """ESM-2 vector for a protein, retrieved by stored protein_id (sequence->ESM-2 is a later add)."""
    p, _ = qc().scroll("esm2", scroll_filter=Filter(must=[FieldCondition(key="protein_id", match=MatchValue(value=accession))]),
                       limit=1, with_vectors=True)
    return p[0].vector if p else None


# --------------------------------------------------------------------------- filters
def _build_filter(filt):
    """filt: {field: scalar | [scalars] | {gte,lte}} -> a read-only Qdrant payload Filter (AND of conditions)."""
    if not filt:
        return None
    must = []
    for k, v in filt.items():
        if isinstance(v, dict) and ("gte" in v or "lte" in v):
            must.append(FieldCondition(key=k, range=Range(gte=v.get("gte"), lte=v.get("lte"))))
        elif isinstance(v, list):
            must.append(FieldCondition(key=k, match=MatchAny(any=v)))
        else:
            must.append(FieldCondition(key=k, match=MatchValue(value=v)))
    return Filter(must=must)


# --------------------------------------------------------------------------- primitive 1: query
def query(collection, text=None, smiles=None, accession=None, filter=None, limit=10, offset=None, ids=None,
          with_names=False, with_known=False):
    """Retrieve from any collection: by point id(s) if `ids` given; else vector search if a query input
    (text/smiles/accession) is given; else a pure payload filter (scroll). Returns
    {"hits": [...], "next": <pagination token or null>}. Vectors stripped."""
    if collection not in COLLECTIONS:
        raise ValueError(f"unknown collection '{collection}'. available: {sorted(COLLECTIONS)}")
    modality, _ = COLLECTIONS[collection]
    limit = max(1, min(int(limit), MAX_LIMIT))

    def _enrich(hits):
        if (with_names or with_known) and modality == "chemical":
            for h in hits:
                sm = h.get("payload", {}).get("smiles")
                if not sm:
                    continue
                if with_names:
                    h["payload"]["name"] = name(sm)
                if with_known:
                    h["payload"]["known"] = known_targets(sm)
        return hits

    if ids:
        pts = qc().retrieve(collection, ids=[int(i) if str(i).isdigit() else i for i in ids], with_payload=True)
        return {"hits": _enrich([{"id": p.id, "payload": p.payload} for p in pts]), "next": None}

    qf = _build_filter(filter)

    qvec = None
    if text is not None:
        qvec = embed_text(text)        # all text collections now MedCPT (patents_text aliases patents_text_medcpt)
    elif smiles is not None:
        qvec = embed_smiles(smiles)
        if qvec is None:
            raise ValueError("could not parse SMILES")
    elif accession is not None:
        qvec = embed_protein(accession)
        if qvec is None:
            raise ValueError(f"no stored vector for accession '{accession}' in esm2")

    if qvec is not None:
        pts = qc().query_points(collection, query=qvec, query_filter=qf, limit=limit,
                                offset=int(offset) if offset else 0, with_payload=True).points
        return {"hits": _enrich([{"id": p.id, "score": round(p.score, 4), "payload": p.payload} for p in pts]), "next": None}

    pts, nxt = qc().scroll(collection, scroll_filter=qf, limit=limit, offset=offset, with_payload=True)
    return {"hits": _enrich([{"id": p.id, "payload": p.payload} for p in pts]), "next": nxt}


def count(collection, filter=None):
    """Count points matching a payload filter (cheap; for the broad-vs-confident sliders)."""
    if collection not in COLLECTIONS:
        raise ValueError(f"unknown collection '{collection}'")
    return {"collection": collection, "count": qc().count(collection, count_filter=_build_filter(filter)).count}


# --------------------------------------------------------------------------- primitive 2: predict
def predict(smiles, top=20, human_only=True, floor=0.3):
    """Chemical target prediction for an arbitrary molecule (the FPSim2 k-NN engine; not a Qdrant op).
    Predictions below `floor` (the calibrated novel-chemistry threshold, accuracy ~26% at 0.3--0.5 and
    worse below) are dropped as noise; experimentally known targets are always kept regardless."""
    import target
    preds, _, supp = target.predict(smiles, human_only=human_only, with_support=True)
    kn = set(known_targets(smiles))
    kept = [(acc, conf) for acc, conf in preds if conf >= floor or target.gene_sym(acc) in kn]
    out = [{"accession": acc, "gene": target.gene_sym(acc), "name": target.full_name(acc),
            "confidence": round(float(conf), 3), "support": supp.get(acc, 0), "band": target.band(conf),
            "known": target.gene_sym(acc) in kn}
           for acc, conf in kept[:top]]
    return {"smiles": smiles, "name": name(smiles), "n_targets": len(preds),
            "known": sorted(kn), "predictions": out}


# --------------------------------------------------------------------------- primitive 3: provenance
def provenance(ids, max_per=8):
    """SureChEMBL compound id(s) -> patent number / assignee / publication date / claimed flag.
    Fast path: the foundational + current-frontier span is baked into the patent_compounds payload
    (`prov` = {n, noise, patents}) by modules/compounds/bake_provenance.py, so read it straight from
    the payload (no 1.5B-row parquet scan). Falls back to the live parquet join for any id absent from
    the atlas or not yet baked. NB the baked span is currently top-20; max_per only caps it (raise via
    a re-bake at higher --top to serve more)."""
    cids = [int(str(i).replace("SCHEMBL", "")) for i in ids]
    out = {}
    try:
        for p in qc().retrieve("patent_compounds", ids=cids, with_payload=["prov"]):
            pv = (p.payload or {}).get("prov")
            if pv:
                out[int(p.id)] = {"n_patents": pv["n"], "noise": pv["noise"], "patents": pv["patents"][:max_per]}
    except Exception:
        pass
    missing = [c for c in cids if c not in out]
    if missing:
        import patent_provenance
        out.update(patent_provenance.compound_patents(missing, max_per=max_per))
    import assignee                                    # canonicalize messy raw assignees for display
    for v in out.values():
        for pt in v.get("patents", []):
            pt["assignee"] = assignee.canon(pt.get("assignee", ""))
    return {f"SCHEMBL{k}": v for k, v in out.items()}


def epo_apply(prov, max_per=20):
    """Lazily enrich the top patents of each compound's provenance with EPO OPS priority/filing dates and a
    normalized applicant (per-patent cache; bounded; never raises). Sets per-compound 'epo_pending'=True when a
    transient failure (quota/network) leaves some patents unresolved, so a caller can avoid caching a partial
    result. Blocking on cache misses; call off the event loop."""
    try:
        from modules.patents import epo_enrich
    except Exception:
        try:
            import sys, pathlib
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
            from modules.patents import epo_enrich
        except Exception:
            return prov
    import concurrent.futures
    try: epo_enrich._token()        # pre-warm the OAuth token so parallel workers reuse it (no fetch stampede)
    except Exception: pass
    def _one(pt):
        num = pt.get("number")
        if not num: return (None, True)
        try: return epo_enrich.enrich_state(num)
        except Exception: return (None, False)
    for v in prov.values():
        pats = v.get("patents", [])[:max_per]
        pending = False
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            results = list(ex.map(_one, pats))
        for pt, (data, resolved) in zip(pats, results):
            if data:
                if data.get("priority_date"): pt["priority_date"] = data["priority_date"]
                if data.get("filing_date"):   pt["filing_date"] = data["filing_date"]
                if data.get("applicants"):    pt["applicant_norm"] = data["applicants"][0]
            if not resolved:
                pending = True
        v["epo_pending"] = pending
    return prov


# --------------------------------------------------------------------------- patent-text support (the badge)
# Serve-time corroboration: does a compound's full-text patent BODY independently rank its chemistry-predicted
# target high? Validated in the pilot (recall@10 ~0.19 overall, ~0.40 at conf>=0.8; collapses to ~0.02 under a
# patent<->target null shuffle). NO model at request time: we dot the precomputed MedCPT-Query target embeddings
# (build_patent_text_support.py) against the patent's already-stored MedCPT-Article vector. Both are L2-norm so
# dot == cosine. Ranking is restricted to HUMAN targets (matches the predictor's human_only default; the full
# vocab's text top-hits are dominated by non-human orthologs).
_TGT_EMB = None
def _target_emb():
    """Lazy-load the precomputed (emb, bg, acc, gene) human target-query matrix. Loaded once per process.
    `bg` is each target's background affinity to the average patent — subtracted at rank time to kill the
    generic-attractor bias (see build_patent_text_support.py). Restricted to human targets."""
    global _TGT_EMB
    if _TGT_EMB is None:
        import numpy as np
        p = os.environ.get("PATENT_TEXT_SUPPORT_NPZ", str(TEXT_SUPPORT_QUERY_EMB))
        d = np.load(p, allow_pickle=True)
        hmask = d["human"].astype(bool)
        emb = d["emb"][hmask]
        bg = d["bg"][hmask] if "bg" in d else np.zeros(emb.shape[0], dtype="float32")
        acc = [str(a) for a in d["acc"][hmask]]
        gene = [str(g) for g in d["gene"][hmask]]
        _TGT_EMB = (emb, bg, acc, gene, {a: i for i, a in enumerate(acc)})
    return _TGT_EMB


# a predicted target counts as "patent-corroborated" when the body text ranks it within this many human targets.
TEXT_RANK_HIT = 10


def patent_text_support(compound_id):
    """For a compound id: among its provenance patents that have full text, rank ALL human targets by how much
    the patent BODY is 'about' each (cosine of the patent's MedCPT-Article vector to the precomputed target-query
    embeddings), and report where each chemistry-predicted target lands.

    Returns {compound_id, n_full_text_patents, patents:[{number, title, text_top:[{gene,acc,score}]x3,
    predicted_ranks:{acc: rank}}], badges:{acc: {verdict, rank, n_targets, top_gene, top_acc, patent}}}.
    `badges` is the per-prediction summary the compound page renders inline: verdict 'confirms' (predicted target
    in the text's top-TEXT_RANK_HIT), 'suggests_other' (a DIFFERENT target tops the text), or 'weak'. NO model load."""
    import numpy as np
    emb, bg, accs, genes, acc2i = _target_emb()
    N = len(accs)

    pts = qc().retrieve("patent_compounds", ids=[int(compound_id)], with_payload=True)
    if not pts:
        return {"compound_id": compound_id, "n_full_text_patents": 0, "patents": [], "badges": {}}
    pl = pts[0].payload or {}
    if (pl.get("prov") or {}).get("noise"):   # ubiquitous tool compounds (e.g. imatinib: 124k patents) appear in
        return {"compound_id": compound_id, "n_full_text_patents": 0,   # those patents only INCIDENTALLY — the body
                "patents": [], "badges": {}}   # text is about other things, so it can't speak to this compound's target. Suppress entirely.
    preds = pl.get("predicted") or []
    pred_accs = [p["acc"] for p in preds if p.get("acc") in acc2i]
    conf_of = {p["acc"]: float(p.get("conf", 0.0)) for p in preds}   # for the conf>=0.5 gate on the "suggests" flag
    pat_nums = [p["number"] for p in ((pl.get("prov") or {}).get("patents") or []) if p.get("number")]
    if not pat_nums or not pred_accs:
        return {"compound_id": compound_id, "n_full_text_patents": 0, "patents": [], "badges": {}}

    # full-text patents among this compound's provenance (uses the patent_id + has_full_text indexes)
    ftpts, _ = qc().scroll(
        "patents_text_medcpt",
        scroll_filter=Filter(must=[FieldCondition(key="patent_id", match=MatchAny(any=pat_nums)),
                                   FieldCondition(key="has_full_text", match=MatchValue(value=True))]),
        limit=50, with_payload=["patent_id", "title"], with_vectors=True)

    patents = []
    # best (lowest) text-rank per predicted target across this compound's full-text patents -> drives the badge
    best = {a: None for a in pred_accs}   # acc -> (rank, score, patent_number)
    for fp in ftpts:
        v = np.asarray(fp.vector, dtype="float32")
        scores = (emb @ v) - bg                            # (N_human,) debiased cosine (attractors removed)
        order = np.argsort(-scores)
        rank_of = np.empty(N, dtype=int); rank_of[order] = np.arange(1, N + 1)
        top = [{"gene": genes[order[r]], "acc": accs[order[r]], "score": round(float(scores[order[r]]), 3)}
               for r in range(3)]
        pranks = {}
        for a in pred_accs:
            i = acc2i[a]; rk = int(rank_of[i])
            pranks[a] = rk
            if best[a] is None or rk < best[a][0]:
                best[a] = (rk, round(float(scores[i]), 3), fp.payload["patent_id"])
        patents.append({"number": fp.payload["patent_id"], "title": fp.payload.get("title", ""),
                        "text_top": top, "predicted_ranks": pranks, "n_targets": N})

    # targets this compound ALREADY confirms (predicted target the text ranks high) — used to suppress a
    # misleading "suggests {X}" when X is itself one of this compound's own confirmed predictions.
    confirmed_accs = {a for a in pred_accs if best[a] and best[a][0] <= TEXT_RANK_HIT}

    # per-prediction badge:
    #  'confirms'       — the predicted target is in the patent text's top-TEXT_RANK_HIT (corroborated).
    #  'suggests_other' — this prediction ranks poorly AND a DIFFERENT target clearly tops the text that is
    #                     NOT itself a confirmed prediction of this same compound (a genuine false-positive flag).
    #  'weak'           — neither: the text just isn't strongly about this target.
    badges = {}
    for a in pred_accs:
        if best[a] is None:
            continue
        rk, sc, pnum = best[a]
        top_for_patent = next((p["text_top"][0] for p in patents if p["number"] == pnum), None)
        is_confirm = rk <= TEXT_RANK_HIT
        is_other = bool(top_for_patent) and top_for_patent["acc"] != a and rk > 50 \
            and top_for_patent["acc"] not in confirmed_accs and conf_of.get(a, 0.0) >= 0.5   # don't flag weak preds
        verdict = "confirms" if is_confirm else "suggests_other" if is_other else "weak"
        badges[a] = {"verdict": verdict, "rank": rk, "score": sc, "n_targets": N, "patent": pnum,
                     "top_gene": top_for_patent["gene"] if top_for_patent else None,
                     "top_acc": top_for_patent["acc"] if top_for_patent else None}

    return {"compound_id": compound_id, "n_full_text_patents": len(patents),
            "patents": patents, "badges": badges}


def similar_compounds(compound_id, limit=10):
    """Chemically nearest patent compounds to this one — vector search in patent_compounds on the compound's OWN
    Morgan vector (cosine == Tanimoto-like). Each neighbour: id, name, smiles, cosine, its top predicted target,
    and the predicted-target genes SHARED with the query. Surfaces the raw vector-similarity capability. No model."""
    pts = qc().retrieve("patent_compounds", ids=[int(compound_id)], with_payload=True, with_vectors=True)
    if not pts:
        return {"compound_id": compound_id, "neighbours": []}
    qpl = pts[0].payload or {}
    qvec = pts[0].vector
    # query's predicted genes, kept in confidence order so shared-target lists lead with the strong ones
    q_pred = qpl.get("predicted") or []
    q_genes_ranked = [p["gene"] for p in q_pred]
    q_genes = set(q_genes_ranked)

    res = qc().query_points("patent_compounds", query=qvec, limit=int(limit) + 1, with_payload=True).points
    out = []
    for h in res:
        if int(h.id) == int(compound_id):                  # the query itself (cosine 1.0)
            continue
        pl = h.payload or {}
        preds = pl.get("predicted") or []
        top = preds[0] if preds else None
        nb_genes = {p["gene"] for p in preds}
        shared = [g for g in q_genes_ranked if g in nb_genes]   # query-confidence order, strongest first
        out.append({"id": pl.get("surechembl_id"), "name": name(pl.get("smiles")), "smiles": pl.get("smiles"),
                    "cosine": round(float(h.score), 3),
                    "top_gene": top["gene"] if top else None, "top_acc": top["acc"] if top else None,
                    "top_conf": top["conf"] if top else None, "shared_targets": shared})
        if len(out) >= int(limit):
            break
    return {"compound_id": compound_id, "neighbours": out}


_NAMES = None
def name(smiles):
    """Common name (ChEMBL pref_name by InChIKey) if the molecule is a known named compound, else None.
    ChEMBL pref_names are upper-case; returned title-cased for display."""
    global _NAMES
    if _NAMES is None:
        import json
        try:
            _NAMES = json.load(open(CHEMBL_NAMES_JSON))
        except Exception:
            _NAMES = {}
    from rdkit import Chem
    from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
    m = Chem.MolFromSmiles(smiles) if smiles else None
    if m is None:
        return None
    cands = [m]
    if "." in smiles:                          # salt / co-crystal / aggregate: try each fragment (largest first)
        frags = sorted(Chem.GetMolFrags(m, asMols=True, sanitizeFrags=False), key=lambda x: -x.GetNumAtoms())
        cands = frags + [m]
    for mol in cands:
        ik = Chem.MolToInchiKey(mol)
        nm = _NAMES.get(ik) or _NAMES.get(ik.split("-", 1)[0])   # exact, then tautomer/salt-insensitive skeleton
        if nm:
            return nm.title()
    return None


_MECH = None
def known_targets(smiles):
    """Curated KNOWN target genes (ChEMBL drug_mechanism) if the molecule is a known drug, else []."""
    global _MECH
    if _MECH is None:
        import json
        try:
            _MECH = json.load(open(CHEMBL_MECHANISMS_JSON))
        except Exception:
            _MECH = {}
    from rdkit import Chem
    from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
    m = Chem.MolFromSmiles(smiles) if smiles else None
    if m is None:
        return []
    cands = [m]
    if "." in smiles:
        cands = sorted(Chem.GetMolFrags(m, asMols=True, sanitizeFrags=False), key=lambda x: -x.GetNumAtoms()) + [m]
    for mol in cands:
        ik = Chem.MolToInchiKey(mol)
        g = _MECH.get(ik) or _MECH.get(ik.split("-", 1)[0])
        if g:
            return g
    return []


def depict(smiles, w=240, h=150):
    """Render a molecule to an SVG string (RDKit). None if the SMILES does not parse."""
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D
    from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return None
    d = rdMolDraw2D.MolDraw2DSVG(int(w), int(h)); d.drawOptions().padding = 0.1
    rdMolDraw2D.PrepareAndDrawMolecule(d, m); d.FinishDrawing()
    return d.GetDrawingText().replace("<?xml version='1.0' encoding='iso-8859-1'?>", "")


def collections():
    """The capability map clients read instead of querying Qdrant blind."""
    return {name: {"modality": mod, "dim": dim} for name, (mod, dim) in COLLECTIONS.items()}

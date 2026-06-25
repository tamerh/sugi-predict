"""BioYoda substrate engine — the three primitives behind both the REST API and the MCP tools.

Read-only against Qdrant (search / scroll / count only). Embedders load lazily on first use. The engine is the
single source of truth: api.py and mcp_handlers.py both call it, so REST / MCP / the web all behave identically.
"""
import os
import sys

sys.path.insert(0, "/data/bioyoda/modules/compounds")
sys.path.insert(0, "/data/bioyoda")

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, Range

QDRANT_URL = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")
MAX_LIMIT = 100

# collection -> (modality, dim). modality decides how a free-text/smiles/accession query is embedded.
COLLECTIONS = {
    "patent_atlas":            ("chemical", 2048),   # 30M patent compounds, predicted targets + provenance
    "chembl":                  ("chemical", 2048),   # ChEMBL reference ligands
    "patents_compounds":       ("chemical", 2048),   # SureChEMBL compound fingerprints
    "clinical_trials_medcpt":  ("text", 768),        # clinical trials (MedCPT)
    "patents_text":            ("text", 768),        # patent text (S-BioBERT — see embed_text_sbiobert)
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


_sbiobert = None
def embed_text_sbiobert(text):
    """S-BioBERT query encoder (768-d) for patents_text, which was embedded with this exact model
    (modules/patents/scripts/process_patents.py). MedCPT is the wrong embedding space for it -- querying
    patents_text with MedCPT returns near-random hits; with S-BioBERT it returns the right patents."""
    global _sbiobert
    if _sbiobert is None:
        import os
        os.environ.setdefault("HF_HUB_OFFLINE", "1"); os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer
        _sbiobert = SentenceTransformer("pritamdeka/S-BioBERT-snli-multinli-stsb")
    return _sbiobert.encode(text).tolist()


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
        qvec = embed_text_sbiobert(text) if collection == "patents_text" else embed_text(text)
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
    Fast path: the foundational + current-frontier span is baked into the patent_atlas payload
    (`prov` = {n, noise, patents}) by modules/compounds/bake_provenance.py, so read it straight from
    the payload (no 1.5B-row parquet scan). Falls back to the live parquet join for any id absent from
    the atlas or not yet baked. NB the baked span is currently top-20; max_per only caps it (raise via
    a re-bake at higher --top to serve more)."""
    cids = [int(str(i).replace("SCHEMBL", "")) for i in ids]
    out = {}
    try:
        for p in qc().retrieve("patent_atlas", ids=cids, with_payload=["prov"]):
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


_NAMES = None
def name(smiles):
    """Common name (ChEMBL pref_name by InChIKey) if the molecule is a known named compound, else None.
    ChEMBL pref_names are upper-case; returned title-cased for display."""
    global _NAMES
    if _NAMES is None:
        import json
        try:
            _NAMES = json.load(open("/data/bioyoda/work/chembl_names.json"))
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
            _MECH = json.load(open("/data/bioyoda/work/chembl_mechanisms.json"))
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

#!/usr/bin/env python3
"""Build the 'bioyoda atlas' demo — static, grounded, capability-reflecting pages.
Iterating prototype (not production): concretely shows the compound substrate's modes + the cross-modal moat.
Renders from the SAME hardened modules the CLI uses (modules/compounds/{xmodal,fto}) so it reflects real behavior.
Output: /data/demos/bioyoda/*.html (auto-served at https://dev.sugi.bio/demos/bioyoda/)."""
import sys, os, time, html, subprocess, collections, json as _json, urllib.request, urllib.parse
sys.path.insert(0, "/data/sugi-atlas/src"); sys.path.insert(0, "/data/bioyoda")
import numpy as np, torch
from transformers import AutoTokenizer, AutoModel
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import atlas.biobtree as B
from scripts.integrations import biobtree_client as bb
from modules.compounds import xmodal, fto      # the hardened Mode-C / Mode-B engines

OUT = "/data/demos/bioyoda"; os.makedirs(OUT, exist_ok=True)
c = QdrantClient(url="http://localhost:6333", timeout=120)
print("loading MedCPT…", flush=True)
qtok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder"); qm = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()
def medcpt(t):
    with torch.no_grad():
        e = qtok([t], truncation=True, padding=True, max_length=64, return_tensors="pt")
        return torch.nn.functional.normalize(qm(**e).last_hidden_state[:, 0, :], dim=1)[0].numpy().tolist()
def esm2_vec(a):
    p,_=c.scroll("esm2",scroll_filter=Filter(must=[FieldCondition(key="protein_id",match=MatchValue(value=a))]),limit=1,with_vectors=True); return p[0].vector if p else None
_ip={}
def interpro(a):
    if a in _ip: return _ip[a]
    s=set()
    try:
        for r in B.map_all(a,">>uniprot>>interpro",cap=30):
            if r.get("id"): s.add(r["id"])
    except Exception: pass
    _ip[a]=s; return s
def pname(a):
    try:
        for r in B.rows(B.search(a,source="uniprot"))[:1]: return r.get("name","")
    except Exception: pass
    return a
def nligands(a):
    try: return len(B.map_all(a,">>uniprot>>chembl_target>>chembl_molecule",cap=300))
    except Exception: return 0
def diamond_homologs(acc):
    f="/data/bioyoda/snapshots/diamond_latest/data/processed/diamond/merged/filtered_top100.tsv"
    out=subprocess.run(["grep","-F",f"sp|{acc}|",f],capture_output=True,text=True).stdout
    s=set()
    for line in out.splitlines():
        p=line.split("\t")
        if len(p)>1 and "|" in p[1]: s.add(p[1].split("|")[1])
    return s
def smiles_cid(drug):
    try:
        url="http://127.0.0.1:9291/ws/?"+urllib.parse.urlencode({"i":drug})
        for res in _json.load(urllib.request.urlopen(url,timeout=30)).get("results",[]):
            for src,a in (res.get("Attributes") or {}).items():
                if isinstance(a,dict) and a.get("smiles"): return a["smiles"], a.get("cid")
    except Exception: pass
    return None,None
def _uxref(acc):
    try:
        for r in (B.search(acc,source="uniprot").get("data") or []):
            p=r.split("|")
            if p and p[0]==acc: return int(p[-1]) if p[-1].isdigit() else 0
    except Exception: pass
    return 0
def hgnc_uniprot(gene):
    try:
        cand=[r.get("id") for r in B.map_all(gene,">>hgnc>>uniprot",cap=10) if r.get("id")]
        cand=[a for a in cand if esm2_vec(a) is not None]; cand.sort(key=_uxref, reverse=True)
        if cand: return cand[0]
    except Exception: pass

# ---------------- HTML ----------------
CSS = """
*{box-sizing:border-box} body{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e7eaf0}
.wrap{max-width:900px;margin:0 auto;padding:28px}
a{color:#7cc4ff;text-decoration:none} a:hover{text-decoration:underline}
.top{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;border-bottom:1px solid #232733;padding-bottom:14px;margin-bottom:8px}
.kind{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#9aa4b2;background:#1a1f2b;padding:3px 9px;border-radius:20px}
h1{font-size:26px;margin:0}
.curie{font-size:13px;color:#9aa4b2}
.sub{color:#9aa4b2;margin:6px 0 20px}
.card{background:#161a22;border:1px solid #232733;border-radius:12px;padding:16px 18px;margin:14px 0;position:relative}
.card h2{font-size:14px;margin:0 0 12px;color:#cdd5e0;text-transform:uppercase;letter-spacing:.06em}
.pred{border-left:3px solid #6ee7a8} .ground{border-left:3px solid #7cc4ff}
.moat{border-left:3px solid #f0c674;background:#1b1814}
table{width:100%;border-collapse:collapse;font-size:14px} td,th{text-align:left;padding:6px 8px;border-bottom:1px solid #20242f}
th{color:#9aa4b2;font-weight:600;font-size:12px}
.pill{display:inline-block;font-size:11px;padding:2px 7px;border-radius:6px;background:#1c2230;color:#9fb0c6;margin-right:4px}
.pill.tw{background:#2b2614;color:#f0c674}
.score{font-variant-numeric:tabular-nums;color:#9aa4b2}
.badge{font-size:11px;background:#11202e;color:#7cc4ff;padding:2px 8px;border-radius:6px;margin-right:4px}
.note{font-size:12px;color:#7b8696;margin-top:8px}
.warn{color:#c89b6b}
.mode{position:absolute;top:14px;right:16px;font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:#7b8696;background:#10141c;border:1px solid #232733;padding:2px 8px;border-radius:5px}
.foot{color:#5b6472;font-size:12px;border-top:1px solid #232733;margin-top:26px;padding-top:14px}
.li{margin:7px 0} .li .s{color:#7cc4ff;font-variant-numeric:tabular-nums;margin-right:8px}
.stat{display:inline-block;margin:4px 22px 4px 0} .stat .big{font-size:22px;font-weight:600;color:#e7eaf0;font-variant-numeric:tabular-nums} .stat .l{font-size:11px;color:#9aa4b2;display:block}
.cap{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0} .cap .m{flex:1;min-width:175px;background:#12161e;border:1px solid #232733;border-radius:10px;padding:11px 13px;font-size:12px;color:#9aa4b2} .cap .m b{color:#cdd5e0;font-size:13px;display:block;margin-bottom:3px}
.tag{display:inline-block;font-size:10px;color:#6ee7a8;border:1px solid #2a4030;border-radius:4px;padding:1px 5px;margin-left:6px}
"""
def esc(x): return html.escape(str(x))
def page(title, kind, name, curie_html, subtitle, body):
    return f"""<!doctype html><html><head><meta charset=utf-8><title>{esc(title)}</title>
<meta name=viewport content="width=device-width,initial-scale=1"><style>{CSS}</style></head>
<body><div class=wrap>
<div class=top><span class=kind>{esc(kind)}</span><h1>{esc(name)}</h1><span class=curie>{curie_html}</span></div>
<div class=sub>{subtitle}</div>{body}
<div class=foot>bioyoda atlas · iterating prototype · predictions are <b>grounded hypotheses</b> (not curated facts),
from a 103M-vector cross-modal substrate + biobtree grounding · {time.strftime('%Y-%m-%d')}</div>
</div></body></html>"""
def card(mode, title, inner, cls="pred"):
    return f'<div class="card {cls}"><span class=mode>{mode}</span><h2>{title}</h2>{inner}</div>'
def uni(a): return f'<a href="https://www.uniprot.org/uniprotkb/{a}">UniProt:{a}</a>'
def cidlink(cid): return f'<a href="https://pubchem.ncbi.nlm.nih.gov/compound/{cid}">PubChem:{cid}</a>' if cid else "?"
def pmidlink(p): return f'<a href="https://pubmed.ncbi.nlm.nih.gov/{p}">PMID:{p}</a>'
def nctlink(n): return f'<a href="https://clinicaltrials.gov/study/{n}">{n}</a>'
def mondolink(m): return f'<a href="https://monarchinitiative.org/{m}">{m}</a>'
def litrow(h): return f"<div class=li><span class=s>{h.score:.2f}</span>{esc((h.payload.get('chunk_text') or '')[:96])} · {pmidlink(h.payload.get('pmid'))}</div>"

# ---------------- PROTEIN PAGE (the moat showcase) ----------------
def build_protein(acc, label):
    print(f"protein {label}…", flush=True)
    dia=diamond_homologs(acc); qip=interpro(acc)
    hits=c.query_points("esm2",query=esm2_vec(acc),limit=80,with_payload=["protein_id"]).points
    rows=[]; seen=set()
    for h in hits:
        a=h.payload.get("protein_id")
        if a==acc or a in dia or not (qip & interpro(a)): continue
        nm=pname(a); key=nm.split()[0]
        if key in seen: continue
        seen.add(key); rows.append((a,nm,h.score,nligands(a)))
        if len(rows)>=8: break
    tbody="".join(
        f"<tr><td><span class='pill tw'>twilight</span>{uni(a)}</td><td>{esc(nm[:44])}</td>"
        f"<td class=score>{s:.3f}</td><td class=score>{d if d else '—'}</td></tr>" for a,nm,s,d in rows)
    lit=""
    for a,nm,s,d in rows[:3]:
        L=c.query_points("pubmed_abstracts_medcpt",query=medcpt(f"{nm} {label} inhibitor cancer drug target"),limit=1).points
        if L and L[0].score>=0.50:
            lit+=f"<div class=li><span class=s>{a} · {L[0].score:.2f}</span>{esc((L[0].payload.get('chunk_text') or '')[:90])} · {pmidlink(L[0].payload.get('pmid'))}</div>"
    moat=card("Mode C · remote homology","Twilight-zone homologs — functional relatives sequence search misses",
        f"<table><tr><th>protein</th><th>name</th><th>ESM-2 sim</th><th>ligands*</th></tr>{tbody}</table>"
        f"<div class=note>Shared InterPro domain, but <b>NOT</b> in DIAMOND's {len(dia)} sequence homologs of {label} — "
        f"reachable only via the ESM-2 embedding. <span class=warn>*ligands = ChEMBL ligands of that target "
        f"(tractability proxy, popularity-biased — these are structural relatives, NOT validated repurposing targets).</span></div>","pred")
    evid=card("evidence · reproducible","ESM-2 reaches remote homologs sequence search misses",
        "<span class=stat><span class=big>71%</span><span class=l>ESM-2 neighbors functionally coherent</span></span>"
        "<span class=stat><span class=big>2%</span><span class=l>random-pairs null (base rate)</span></span>"
        "<span class=stat><span class=big>16%</span><span class=l>strict twilight (&lt;30% identity)</span></span>"
        "<div class=note>40 random human proteins, seed-fixed, strict &lt;30%-identity (Smith-Waterman), random-pairs "
        "null — <b>35× above chance</b>. Reproducible: <code>usecases/poc_twilight_coherence.py</code>. "
        "<span class=warn>This is remote-homology detection (real, but a known protein-LM capability) — it does NOT, on a held-out "
        "test, predict a drug's off-targets. Hypothesis generation, not validated repurposing.</span></div>","ground")
    grnd=card("grounded","Related literature for these homologs", lit or '<div class=note>—</div>',"ground")
    h=page(f"{label} — bioyoda atlas","protein",label,uni(acc),
           "ESM-2 k-NN reaches a protein's functional relatives that BLAST/DIAMOND miss — grounded, exploratory hypotheses.",
           moat+evid+grnd)
    open(f"{OUT}/protein_{label}.html","w").write(h); return f"protein_{label}.html"

# ---------------- COMPOUND PAGE (all four modes for one drug) ----------------
def build_compound(drug):
    print(f"compound {drug}…", flush=True)
    name=drug.capitalize(); sm,cid=smiles_cid(drug)
    # Mode C — cross-modal twilight repurposing (the moat), from the hardened engine
    dos=xmodal.dossier(drug); twr=""
    for tw in dos.get("twilights",[]):
        grounded=tw["gscore"]>=xmodal.GROUND_THR
        sp=f" <span class=warn>[{tw['species']}→human]</span>" if tw['species'] and tw['species']!='Homo sapiens' else ""
        g=f"{pmidlink(tw['pmid'])} <span class=score>({tw['gscore']:.2f})</span>" if grounded else "<span class=warn>ungrounded</span>"
        twr+=(f"<tr><td><span class='pill tw'>twilight</span>{esc(tw['gene'])}{sp}</td><td>{uni(tw['human_acc'])}</td>"
              f"<td class=score>{tw['sim']:.3f}</td><td class=score>{tw['nligands']}</td><td>{g}</td></tr>")
    modec=card("Mode C · cross-modal hypotheses",f"Structural twilight homologs of {esc(dos.get('target_gene') or '?')} — exploratory, not predictions",
        f"<table><tr><th>twilight homolog</th><th>UniProt</th><th>ESM-2 sim</th><th>ligands*</th><th>related lit</th></tr>{twr}</table>"
        f"<div class=note>{name} → primary target <b>{esc(dos.get('target_gene') or '?')}</b> ({dos.get('via','?')}-grounded) → "
        f"ESM-2 neighbors sharing a domain but <b>NOT</b> in DIAMOND's {dos.get('n_diamond','?')} sequence homologs. "
        f"<span class=warn>⚠ These are functional structural relatives, <b>NOT</b> validated targets of {name} — a held-out "
        f"polypharmacology test showed the twilight hop does not predict a drug's real off-targets. Use as hypotheses only. "
        f"*ligands = popularity-biased tractability proxy; lit = MedCPT-related abstract (score ≥ {xmodal.GROUND_THR}).</span></div>","pred")
    # Mode B — exact claimed-chemical-density over 30.9M (FPSim2)
    modeb=""
    if sm:
        dens=fto.density(sm); nb=fto.neighbors(sm,0.5)[:6]
        stats="".join(f'<span class=stat><span class=big>{n:,}</span><span class=l>≥ {t} Tanimoto</span></span>' for t,n in dens.items())
        nbr="".join(f"<tr><td>{esc(sid)}</td><td class=score>{tt:.3f}</td></tr>" for sid,tt in nb)
        modeb=card("Mode B · claimed-chemical-density",f"Exact patent-chemical density around {name} (30.9M compounds)",
            f"<div>{stats}</div><div class=note>EXACT count of patent compounds within each Tanimoto cutoff (FPSim2, ~250&nbsp;ms) — "
            f"the exhaustive 'how-crowded / what's-claimed' signal top-k similarity can't give.</div>"
            f"<table style='margin-top:8px'><tr><th>nearest claimed compound</th><th>Tanimoto</th></tr>{nbr}</table>","pred")
    # Mode D — prediction (BYO-labels, frozen FPs)
    moded=""
    try:
        import joblib; mp="/data/bioyoda/work/qsar_models/bace.pkl"
        if sm and os.path.exists(mp):
            mdl=joblib.load(mp); m=Chem.MolFromSmiles(sm)
            bv=AllChem.GetMorganFingerprintAsBitVect(m,2,nBits=2048); arr=np.zeros((2048,),dtype=np.int8); DataStructs.ConvertToNumpyArray(bv,arr)
            p=mdl["model"].predict_proba(arr.reshape(1,-1))[0,1]
            moded=card("Mode D · prediction","BYO-labels predictor on frozen fingerprints",
                f"<span class=stat><span class=big>{p:.2f}</span><span class=l>P(active), demo model</span></span>"
                f"<div class=note>Illustrative only: predictor trained on the stored ECFP4 with a public label set "
                f"(BACE β-secretase binding, scaffold ROC-AUC {mdl['cv_scaffold_roc']:.2f}). "
                f"<span class=warn>Upload your own labels → instant predictor on the same 30.9M fingerprints.</span></div>","pred")
    except Exception: pass
    # grounded literature + trials
    gene=dos.get("target_gene") or ""
    lit=[h for h in c.query_points("pubmed_abstracts_medcpt",query=medcpt(f"{drug} {gene} resistance mechanism"),limit=3).points]
    tr=[]; seen=set()
    for h in c.query_points("clinical_trials_medcpt",query=medcpt(f"{drug} {gene}"),limit=20).points:
        n=h.payload.get("nct_id")
        if n in seen: continue
        seen.add(n); tr.append(h)
        if len(tr)>=3: break
    litc=card("Mode A · literature","Grounded literature","".join(litrow(h) for h in lit),"ground")
    trc=card("grounded","Clinical trials","".join(f"<div class=li>{nctlink(h.payload.get('nct_id'))} · {esc(str(h.payload.get('brief_title'))[:62])}</div>" for h in tr),"ground")
    h=page(f"{name} — bioyoda atlas","compound",name,cidlink(cid),
           "One molecule, four modes over an owned + grounded substrate — cross-modal repurposing, exact chemical density, prediction, literature.",
           modec+(modeb)+(moded)+litc+trc)
    fn=f"compound_{drug}.html"; open(f"{OUT}/{fn}","w").write(h); return fn

# ---------------- DISEASE PAGE ----------------
def build_disease(term):
    print(f"disease {term}…", flush=True)
    mid,_=bb.ground(term,"mondo")
    kids=[r.get("name") for r in B.map_all(term,">>mondo>>mondochild",cap=20) if r.get("name")][:5]
    par=[r.get("name") for r in B.map_all(term,">>mondo>>mondoparent",cap=10) if r.get("name")][:2]
    genes=[]
    for r in B.map_all(mid,">>mondo>>gencc",cap=30):
        g=r.get("gene_symbol")
        if g and g not in genes: genes.append(g)
    civ=collections.Counter()
    for r in B.map_all(mid,">>mondo>>civic_evidence",cap=300):
        mp=(r.get("molecular_profile") or "").split()
        if mp and mp[0][:1].isalpha() and mp[0].upper()==mp[0] and mp[0].replace("-","").isalnum(): civ[mp[0]]+=1
    for g,_ in civ.most_common(10):
        if g not in genes: genes.append(g)
    genes=genes[:8]; grows=""
    for g in genes:
        u=hgnc_uniprot(g); fam=[]
        if u:
            seen=set()
            for h in c.query_points("esm2",query=esm2_vec(u),limit=8,with_payload=["protein_id"]).points:
                a=h.payload.get("protein_id")
                if a==u: continue
                nm=pname(a).split()[0]
                if nm in seen: continue
                seen.add(nm); fam.append(nm)
                if len(fam)>=3: break
        grows+=f"<tr><td><b>{esc(g)}</b></td><td>{uni(u) if u else '—'}</td><td>{esc(', '.join(fam))}</td></tr>"
    qv=medcpt(f"{term} targeted therapy")
    flt=Filter(must=[FieldCondition(key="disease_curie",match=MatchValue(value=mid))]) if mid else None
    tr=[];seen=set()
    for h in (c.query_points("clinical_trials_medcpt",query=qv,query_filter=flt,limit=20).points if flt else []):
        n=h.payload.get("nct_id")
        if n in seen: continue
        seen.add(n); tr.append(h)
        if len(tr)>=4: break
    lit=c.query_points("pubmed_abstracts_medcpt",query=medcpt(f"{term} driver oncogene targeted therapy"),limit=3).points
    body=(card("grounding · hierarchy-aware","MONDO grounding",
            f"<span class=badge>{mondolink(mid)}</span><div class=note>parent: {esc(', '.join(par))} · children: {esc(', '.join(kids))}</div>","ground")
        + card("Mode C · cohort→families","Driver gene cohort → predicted protein families",
            f"<table><tr><th>gene</th><th>UniProt</th><th>ESM-2 family</th></tr>{grows}</table>"
            "<div class=note>Cohort from biobtree GenCC (curated) + CIViC (somatic drivers); each → its ESM-2 neighborhood.</div>","pred")
        + card("grounded","Trials (vector + disease_curie filter)",
            "".join(f"<div class=li>{nctlink(h.payload.get('nct_id'))} · {esc(str(h.payload.get('brief_title'))[:62])}</div>" for h in tr),"ground")
        + card("Mode A · literature","Literature","".join(litrow(h) for h in lit),"ground"))
    name=term.title()
    h=page(f"{name} — bioyoda atlas","disease",name,mondolink(mid),
           "Hierarchy-aware grounding + driver cohort → predicted families + grounded trials/literature.",body)
    fn="disease_"+term.split()[0].lower()+".html"; open(f"{OUT}/{fn}","w").write(h); return fn

# ---------------- INDEX ----------------
def build_index(pages):
    modes=("<div class=cap>"
        "<div class=m><b>Mode B · claimed-density</b>exact count of the 30.9M patent compounds within any Tanimoto of a molecule (~250&nbsp;ms) — open programmatic patent-chemical-space intelligence.</div>"
        "<div class=m><b>Mode A · similarity</b>millisecond top-k analogs / literature / trials over 103M owned vectors, CURIE-grounded.</div>"
        "<div class=m><b>Mode D · prediction</b>upload labels → instant QSAR/ADMET predictor on the stored fingerprints.</div>"
        "<div class=m><b>Mode C · remote homology</b>ESM-2 finds a target's structural relatives sequence search misses → exploratory hypotheses (not validated repurposing).</div>"
        "</div>")
    scale=("<div style='margin:6px 0'>"
        "<span class=stat><span class=big>103M</span><span class=l>owned vectors, 5 modalities</span></span>"
        "<span class=stat><span class=big>30.9M</span><span class=l>patent compounds (exact + ANN)</span></span>"
        "<span class=stat><span class=big>574K</span><span class=l>proteins (ESM-2)</span></span>"
        "<span class=stat><span class=big>4–9 ms</span><span class=l>warm query, no GPU</span></span></div>")
    links="".join(f'<div class=li><a href="{fn}">{esc(t)}</a></div>' for t,fn in pages)
    body=(card("substrate","103M-vector grounded substrate",scale,"ground")
        + card("capabilities","Four modes over one owned compound substrate",modes,"pred")
        + card("pages","Example dossiers",f"<div class=card style='background:transparent;border:none;padding:0;margin:0'>{links}</div>","ground"))
    idx=page("bioyoda atlas — prototype","atlas","bioyoda atlas","",
        "An open, efficient, grounded multi-modal vector substrate over owned biomedical data — 103M vectors, "
        "millisecond queries, no GPU. Exploratory, traceable hypotheses across chemistry, proteins, literature and trials.",body)
    open(f"{OUT}/index.html","w").write(idx)

if __name__=="__main__":
    pages=[]
    pages.append(("Compound · Osimertinib  — all four modes", build_compound("osimertinib")))
    pages.append(("Protein · EGFR  — the twilight moat", build_protein("P00533","EGFR")))
    pages.append(("Disease · Non-small cell lung carcinoma", build_disease("non-small cell lung carcinoma")))
    build_index(pages)
    subprocess.run(["chmod","-R","a+rX",OUT])
    print("\nwrote:", OUT, "->", [fn for _,fn in pages]+["index.html"])

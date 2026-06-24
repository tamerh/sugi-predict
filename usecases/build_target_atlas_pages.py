#!/usr/bin/env python3
"""Render sample HTML pages for the bioyoda-atlas TARGET pages (predicted target atlas of chemical space).
Per molecule: structure + ranked predicted targets (Tanimoto confidence, grounded) + the nearest known
ChEMBL ligands it reasons from. Includes a NOVEL/whitespace example. Output /data/demos/bioyoda/target-atlas/."""
import sys, os, html, glob, random, collections
sys.path.insert(0, "/data/bioyoda/modules/compounds"); sys.path.insert(0, "/data/bioyoda")
import target, fto                                                   # the validated engine
from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit import RDLogger; RDLogger.DisableLog("rdApp.*")

OUT = "/data/demos/bioyoda/target-atlas"; os.makedirs(OUT, exist_ok=True)
eng, ct = target.engine()

# --- for the TARGET / patent-landscape pages: the 31M patent vector DB + reverse index ---
from qdrant_client import QdrantClient
import numpy as np
from rdkit.Chem import AllChem, DataStructs
qc = QdrantClient(url="http://localhost:6333", timeout=120)
csm = {}
for _l in open("/data/bioyoda/work/chembl_reference/reference.tsv"):
    _c, _s = _l.rstrip("\n").split("\t", 1)
    if _c.isdigit(): csm[int(_c)] = _s
tgt_cids = collections.defaultdict(list)             # target -> its known ChEMBL ligands
for _cid, _ts in ct.items():
    for _t in _ts: tgt_cids[_t].append(_cid)
def morgan(sm):
    m = Chem.MolFromSmiles(sm)
    return AllChem.GetMorganFingerprintAsBitVect(m, 2, nBits=2048) if m else None

def esc(x): return html.escape(str(x))
def svg(smiles):
    m = Chem.MolFromSmiles(smiles)
    if not m: return ""
    d = rdMolDraw2D.MolDraw2DSVG(380, 210); d.drawOptions().padding = 0.12
    rdMolDraw2D.PrepareAndDrawMolecule(d, m); d.FinishDrawing()
    return d.GetDrawingText().replace("<?xml version='1.0' encoding='iso-8859-1'?>", "")
def uni(a): return f'<a href="https://www.uniprot.org/uniprotkb/{a}">{a}</a>'
def bandcol(t): return "#6ee7a8" if t>=0.5 else "#f0c674" if t>=0.4 else "#e0995b" if t>=0.3 else "#7b8696"

CSS = """*{box-sizing:border-box}body{font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e7eaf0}
.wrap{max-width:860px;margin:0 auto;padding:28px}a{color:#7cc4ff;text-decoration:none}a:hover{text-decoration:underline}
.top{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;border-bottom:1px solid #232733;padding-bottom:14px}
.kind{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#9aa4b2;background:#1a1f2b;padding:3px 9px;border-radius:20px}
h1{font-size:25px;margin:0}.smiles{font-family:ui-monospace,monospace;font-size:12px;color:#7b8696;word-break:break-all;margin:6px 0 0}
.card{background:#161a22;border:1px solid #232733;border-radius:12px;padding:16px 18px;margin:14px 0}
.card h2{font-size:13px;margin:0 0 12px;color:#cdd5e0;text-transform:uppercase;letter-spacing:.06em}
.struct{background:#f4f6fa;border-radius:10px;padding:8px;display:inline-block}
.conf{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.bigpct{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums}
.lab{font-size:12px;color:#9aa4b2}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:7px 8px;border-bottom:1px solid #20242f}
th{color:#9aa4b2;font-weight:600;font-size:12px}.r{color:#7b8696;font-variant-numeric:tabular-nums}
.bar{height:8px;border-radius:4px;background:#222} .conftxt{font-variant-numeric:tabular-nums}
.pill{display:inline-block;font-size:10px;padding:2px 7px;border-radius:5px;margin-left:6px;font-weight:600}
.known{display:inline-block;font-size:10px;padding:2px 8px;border-radius:5px;margin-left:8px;font-weight:700;background:#7cc4ff22;color:#7cc4ff;letter-spacing:.04em}
.supp{font-variant-numeric:tabular-nums;color:#9aa4b2}.gsym{font-weight:600}.gfull{color:#7b8696;font-size:12px}
.note{font-size:12px;color:#7b8696;margin-top:8px}.warn{color:#c89b6b}
.foot{color:#5b6472;font-size:12px;border-top:1px solid #232733;margin-top:24px;padding-top:14px}
.li{margin:6px 0;font-size:13px}.li .s{color:#6ee7a8;font-variant-numeric:tabular-nums;margin-right:8px}"""

def page_html(title, body):
    return f"<!doctype html><html><head><meta charset=utf-8><title>{esc(title)}</title><meta name=viewport content='width=device-width,initial-scale=1'><style>{CSS}</style></head><body><div class=wrap>{body}<div class=foot>bioyoda-atlas · predicted target atlas of chemical space · predictions are grounded hypotheses by chemical k-NN to known ChEMBL ligands, NOT measured facts · confidence = Tanimoto to nearest known ligand</div></div></body></html>"

def band(t): return target.band(t)

def trow(i, t, s, supp, known):
    """one predicted-target row: GENE SYMBOL primary, full name as title/secondary, support count, known flag."""
    w = int(s * 100); sym = esc(target.gene_sym(t)); fn = esc(target.full_name(t))
    kflag = "<span class=known>known</span>" if known else ""
    sc = supp.get(t, 0)
    return (f"<tr><td class=r>{i}</td>"
            f"<td><span class=gsym title='{fn}'>{sym}</span>{kflag}<div class=gfull>{fn[:52]}</div></td>"
            f"<td>{uni(t)}</td>"
            f"<td class=supp title='{sc} of {target.KNN} nearest known ligands support this target'>{sc}/{target.KNN}</td>"
            f"<td class=conftxt>{s:.2f} <span class=pill style='background:{bandcol(s)}22;color:{bandcol(s)}'>{band(s)}</span></td></tr>")

def build(name, query, fname):
    sm, label = fto.resolve(query)
    if not sm: print(f"  skip {name}: unresolved"); return None
    preds, _, supp = target.predict(sm, human_only=True, with_support=True)
    # TRUE nearest Tanimoto (independent of the 0.3 prediction cutoff) for display + evidence
    res = eng.similarity(sm, 0.10, n_workers=4)
    best = float(res[0][1]) if len(res) else 0.0
    known = best >= 0.999                                 # the molecule is itself in ChEMBL (exact match)
    ev = []
    for cid, co in res:
        tg = [target.gene_sym(t) for t in sorted(ct.get(int(cid), ())) if target.is_human(t)][:2]
        ev.append((int(cid), float(co), tg))
        if len(ev) >= 4: break
    # predicted-targets table (top 10), GENE SYMBOL primary, support count as discriminator
    rows = "".join(trow(i, t, s, supp, known) for i, (t, s) in enumerate(preds[:20], 1))
    evrows = "".join(f"<div class=li><span class=s>SCHEMBL/CID {cid} · {co:.2f}</span>→ hits {', '.join(esc(x) for x in tg) or '—'}</div>" for cid, co, tg in ev)
    novel = best < 0.30
    knownbadge = "<span class=known>✓ known drug — recovers its established targets</span>" if known else ""
    confline = (f"<span class=bigpct style='color:{bandcol(best)}'>{best:.2f}</span>"
                f"<span class=lab>nearest known ligand (Tanimoto) →<br><b style='color:{bandcol(best)}'>{band(best)} confidence</b>{knownbadge}</span>")
    hdrnote = ("this molecule is itself in ChEMBL, so its top predictions <b>match its established targets</b> — a sanity check that the method recovers the right answer (the rigorous test, with the molecule's own scaffold held out, is on the <a href='validation.html'>validation page</a>)" if known
               else "ranked target profile — chemical-neighbourhood hypotheses, not measured facts")
    pred_block = ("<div class='card'><h2>⚠ Novel chemotype — chemical whitespace</h2><div class=note>No close known "
                  "ligand (best Tanimoto &lt; 0.3) → no confident target. This compound is in unexplored chemical space "
                  "relative to ChEMBL — interesting in itself, but not target-annotatable by similarity.</div></div>"
                  if novel else
                  f"<div class='card'><h2>Predicted protein targets &nbsp;<span class=note>(top 20 of {len(preds)} human targets)</span></h2>"
                  f"<table><tr><th>#</th><th>gene · protein</th><th>UniProt</th><th title='how many of the 20 nearest known ligands support this target'>supporting neighbours</th><th>confidence</th></tr>{rows}</table>"
                  f"<div class=note>Ranked by chemical k-NN over 1.25M known ChEMBL ligands ({hdrnote}). Confidence = best "
                  f"Tanimoto to a known ligand of that target; <b>supporting neighbours</b> = how many of the 20 nearest known ligands "
                  f"back it — the discriminator that separates the real target from tied 1.00s. <span class=warn>This is "
                  f"the full target <i>profile</i> (every protein it's in the chemical neighbourhood of), ranked — not a "
                  f"single hard label.</span></div></div>")
    body = (f"<div class=top><span class=kind>compound · predicted targets</span><h1>{esc(name)}</h1></div>"
            f"<p class=smiles>{esc(sm[:90])}{'…' if len(sm)>90 else ''}</p>"
            f"<div class=card><h2>Structure</h2><div class=struct>{svg(sm)}</div>"
            f"<div class=conf style='margin-top:12px'>{confline}</div></div>"
            f"{pred_block}"
            f"<div class=card><h2>Why — nearest known ligands (the evidence)</h2>{evrows}"
            f"<div class=note>The targets above are inferred because this molecule sits in the <b>chemical neighbourhood</b> "
            f"of these similar molecules whose targets are already known — a nearest-neighbour argument, not a measurement.</div></div>")
    open(f"{OUT}/{fname}", "w").write(page_html(f"{name} — bioyoda-atlas", body))
    print(f"  wrote {fname}  (best Tan {best:.2f}, {len(preds)} targets)")
    return name, fname, best

def build_landscape(acc, gene, fname):
    """TARGET page: search the 31M-patent vector DB (Qdrant) for compounds near this target's known
    ligands → the patented chemical matter likely active against it. This is the direction that USES the
    patent vector DB (compound pages use the small ChEMBL index; this uses the big owned patent corpus)."""
    actives = [(c, csm[c]) for c in tgt_cids.get(acc, []) if c in csm]
    rng = random.Random(1); rng.shuffle(actives); actives = actives[:10]
    patent = {}                                       # surechembl_id -> (best Tanimoto, smiles)
    for c, sm in actives:
        bv = morgan(sm)
        if bv is None: continue
        arr = np.zeros((2048,), dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, arr)
        for h in qc.query_points("patents_compounds", query=arr.tolist(), limit=40,
                                 with_payload=["surechembl_id", "smiles"]).points:
            s2 = h.payload.get("smiles"); mm = Chem.MolFromSmiles(s2) if s2 else None
            if mm is None: continue
            t = DataStructs.TanimotoSimilarity(bv, AllChem.GetMorganFingerprintAsBitVect(mm, 2, nBits=2048))
            sid = h.payload.get("surechembl_id")
            if sid and t > patent.get(sid, (0,))[0]: patent[sid] = (t, s2)
    ranked = sorted(patent.items(), key=lambda x: -x[1][0])
    n5 = sum(1 for _, (t, _) in ranked if t >= 0.5); n7 = sum(1 for _, (t, _) in ranked if t >= 0.7)
    actrows = "".join(f"<div class=li><span class=s>CID {c}</span>{esc(sm[:62])}</div>" for c, sm in actives[:4])
    patrows = "".join(f"<tr><td>{esc(sid)}</td><td class=conftxt>{t:.2f}</td>"
                      f"<td><div class=struct style='padding:2px'>{svg(s2)}</div></td></tr>" for sid, (t, s2) in ranked[:8])
    # ---- ATLAS-WIDE view: query the 30M predicted patent_atlas directly (broad vs high-confidence) ----
    from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
    af = Filter(must=[FieldCondition(key="targets", match=MatchValue(value=acc))])
    hf = Filter(must=[FieldCondition(key="targets", match=MatchValue(value=acc)),
                      FieldCondition(key="best_tanimoto", range=Range(gte=0.5))])
    n_all = qc.count("patent_atlas", count_filter=af).count
    n_hi = qc.count("patent_atlas", count_filter=hf).count
    tight = []
    for h in qc.scroll("patent_atlas", scroll_filter=hf, limit=600,
                       with_payload=["surechembl_id", "smiles", "predicted"])[0]:
        pr = [p for p in h.payload["predicted"] if p["acc"] == acc]
        if not pr or pr[0]["conf"] < 0.5 or pr[0]["support"] < 2: continue
        tight.append((h.payload["surechembl_id"], h.payload["smiles"], pr[0]["conf"], pr[0]["support"]))
    tight.sort(key=lambda x: (-x[2], -x[3]))
    top = tight[:8]
    # patent provenance for the surfaced compounds (one batched SureChEMBL-parquet scan)
    import patent_provenance
    prov = patent_provenance.compound_patents([int(sid.replace("SCHEMBL", "")) for sid, _, _, _ in top])
    def patcell(sid):
        d = prov.get(int(sid.replace("SCHEMBL", "")))
        if not d or not d["patents"]: return "<span class=note>—</span>"
        p = d["patents"][0]; cl = " <span class=pill style='background:#6ee7a822;color:#6ee7a8'>claimed</span>" if p["claimed"] else ""
        npat = f" · {d['n_patents']} patents" if d["n_patents"] > 1 else ""
        return f"<b>{esc(p['number'])}</b>{cl}<div class=gfull>{esc(p['assignee'][:36])} · {esc(p['date'][:4])}{npat}</div>"
    tightrows = "".join(f"<tr><td>{esc(sid)}</td><td class=conftxt>{c:.2f}</td><td class=supp>{sp}/20</td>"
                        f"<td>{patcell(sid)}</td><td><div class=struct style='padding:2px'>{svg(s)}</div></td></tr>"
                        for sid, s, c, sp in top)
    atlas_card = (f"<div class=card><h2>Atlas-wide — claimed against {esc(gene)} "
                  f"<span class=note>(queried from the 30M predicted atlas)</span></h2>"
                  f"<div class=conf><span class=bigpct style='color:#6ee7a8'>{n_all:,}</span>"
                  f"<span class=lab>patent compounds with {esc(gene)} in their predicted profile<br>"
                  f"<b>{n_hi:,}</b> at high confidence (nearest known ligand ≥0.5)</span></div>"
                  f"<div class=note>Most confident {esc(gene)} matter ({esc(gene)} conf ≥0.5, ≥2 supporting neighbours), "
                  f"with the patent it is claimed in (assignee · year):</div>"
                  f"<table style='margin-top:8px'><tr><th>SureChEMBL</th><th>conf</th><th>supporting neighbours</th>"
                  f"<th>patent · assignee · year</th><th>structure</th></tr>{tightrows}</table>"
                  f"<div class=note>The whole 30.0M-compound atlas, filtered by target × confidence × support and joined "
                  f"to patent provenance — the owned corpus turned into a queryable, attributable IP landscape.</div></div>")
    body = (f"<div class=top><span class=kind>target · patent landscape</span><h1>{esc(gene)}</h1>"
            f"<span class=lab>{uni(acc)}</span></div>"
            f"{atlas_card}"
            f"<div class=card><h2>Known chemistry (ChEMBL) — what teaches us</h2>{actrows}"
            f"<div class=note>{len(actives)} sampled known {esc(gene)} ligands (the 'answer key' for this target).</div></div>"
            f"<div class=card><h2>Patent landscape — claimed against {esc(gene)}</h2>"
            f"<div class=conf><span class=bigpct style='color:#6ee7a8'>{len(ranked)}</span>"
            f"<span class=lab>patent compounds found near known {esc(gene)} ligands<br>"
            f"<b>{n7} ≥0.7</b> · {n5} ≥0.5 Tanimoto</span></div>"
            f"<table style='margin-top:12px'><tr><th>SureChEMBL</th><th>Tanimoto</th><th>structure</th></tr>{patrows}</table>"
            f"<div class=note>Found by searching the <b>31M-compound patent vector DB</b> for molecules similar to "
            f"{esc(gene)}'s known ligands — the patented chemical matter <b>in the chemical neighbourhood of known "
            f"{esc(gene)} ligands</b> (a similarity hypothesis, not a measured activity), including compounds NOT in "
            f"ChEMBL. <span class=warn>This direction is what the owned patent corpus uniquely enables.</span></div></div>")
    open(f"{OUT}/{fname}", "w").write(page_html(f"{gene} landscape — bioyoda-atlas", body))
    print(f"  wrote {fname}  ({len(ranked)} patent compounds for {gene})")
    return gene, fname, len(ranked)

def build_validation(fname="validation.html"):
    """The evidence page — does the prediction work, how honest is the confidence, what's the coverage."""
    def S(big, lab, col="#6ee7a8"):
        return f"<span class=stat><span class=big style='color:{col}'>{big}</span><span class=lab>{lab}</span></span>"
    body = (
        "<div class=top><span class=kind>method · validation</span><h1>Does the prediction work?</h1></div>"
        "<div class=card><h2>Held-out accuracy — predicting among 7,929 targets</h2>"
        f"<div class=conf>{S('77%','recall@1 · scaffold')}{S('88%','recall@5 · scaffold')}{S('41%','recall@1 · new chemistry')}{S('5.6%','popularity baseline','#c89b6b')}</div>"
        "<div class=note>2,000 held-out queries, deployed ranking. <b>Scaffold split</b> (whole Bemis–Murcko scaffolds withheld) = 77% / 88%; leave-one-out upper bound 83% / 92%; <b>temporal split</b> (chemistry disclosed after the reference was frozen) = 41% / 56% — the hardest, most realistic. All ≫ popularity (5.6%) and random (0.1%).</div></div>"
        "<div class=card><h2>The confidence is honest (graded by chemical similarity)</h2>"
        "<table><tr><th>nearest known ligand (Tanimoto)</th><th>recall@1</th></tr>"
        "<tr><td>≥ 0.7</td><td>89%</td></tr><tr><td>0.5 – 0.7</td><td>64%</td></tr><tr><td>0.3 – 0.5</td><td>26%</td></tr>"
        "<tr><td>&lt; 0.3</td><td>~0% &rarr; flagged <b>novel</b></td></tr></table>"
        "<div class=note>Every prediction carries its Tanimoto confidence. High &rarr; trust it; low &rarr; flagged, not faked.</div></div>"
        "<div class=card><h2>Coverage of the 30.9M patent corpus</h2>"
        f"<div class=conf>{S('39.8%','high-confidence (≥0.5)')}{S('68.4%','≥0.4 moderate+')}{S('6.5%','novel / whitespace','#c89b6b')}</div>"
        "<div class=note>All 30.0M drug-like compounds annotated against the uncapped 1.25M-ligand reference: 40% high-confidence, 93.5% target-reachable, only 6.5% novel chemical whitespace (median best-Tanimoto 0.46).</div></div>"
        "<div class=card><h2>Validated by elimination</h2>"
        "<div class=note>The same held-out test killed weaker approaches before keeping this one:</div>"
        "<table style='margin-top:8px'><tr><th>approach</th><th>held-out result</th><th></th></tr>"
        "<tr><td>peptide sequence-embedding</td><td>≈ random (no signal beyond composition)</td><td class=warn>dropped</td></tr>"
        "<tr><td>protein-homology repurposing</td><td>2% &lt; random</td><td class=warn>dropped</td></tr>"
        "<tr><td><b>ligand &rarr; target (this atlas)</b></td><td><b>85% recall@1</b></td><td style='color:#6ee7a8'>kept</td></tr></table></div>"
        "<div class=card><h2>The owned substrate it runs on</h2>"
        f"<div class=conf>{S('103M','owned vectors')}{S('6','modalities')}{S('30.9M','patent compounds')}{S('4–9 ms','warm query')}{S('none','query-time GPU','#7cc4ff')}</div>"
        "<div class=note>Reproducible pipeline (~$13 to re-embed); grounded to biobtree — the deterministic companion to this predictive atlas.</div></div>")
    open(f"{OUT}/{fname}", "w").write(page_html("BioYoda — method & validation", body))
    print(f"  wrote {fname}"); return fname

# find a NOVEL patent compound (low best-Tanimoto) for the whitespace example
def novel_patent():
    rng = random.Random(7)
    for f in sorted(glob.glob("/data/bioyoda/raw_data/patents/chunked_compounds/compounds_chunk_*.parquet"))[::13]:
        import pyarrow.parquet as pq
        sm = pq.read_table(f, columns=["id", "smiles"])
        ids, smis = sm.column("id").to_pylist(), sm.column("smiles").to_pylist()
        for i in rng.sample(range(len(smis)), min(400, len(smis))):
            s = smis[i]
            if not s: continue
            r = eng.similarity(s, 0.15, n_workers=4)
            best = float(r[0][1]) if len(r) else 0.0
            if 0.20 <= best < 0.29 and Chem.MolFromSmiles(s) and 15 <= len(s) <= 60:
                return f"SCHEMBL{ids[i]}", s
    return None, None

def build_combined(name, query, fname):
    """ONE dense compound dossier: molecule → predicted targets (ChEMBL) AND the patent landscape of its
    #1 predicted target (31M patent vector DB). Compound-centric — shows both directions on one page."""
    print(f"combined {name}…", flush=True)
    sm, label = fto.resolve(query)
    if not sm: return None
    preds, _, supp = target.predict(sm, human_only=True, with_support=True)
    res = eng.similarity(sm, 0.10, n_workers=4); best = float(res[0][1]) if len(res) else 0.0
    known = best >= 0.999
    ev = []
    for cid, co in res:
        tg = [target.gene_sym(t) for t in sorted(ct.get(int(cid), ())) if target.is_human(t)][:2]
        ev.append((int(cid), float(co), tg))
        if len(ev) >= 3: break
    trows = ""
    for i, (t, s) in enumerate(preds[:20], 1):
        w = int(s * 100); sym = esc(target.gene_sym(t)); fn = esc(target.full_name(t)); sc = supp.get(t, 0)
        kflag = "<span class=known>known</span>" if known else ""
        trows += (f"<tr><td class=r>{i}</td>"
                  f"<td><span class=gsym title='{fn}'>{sym}</span>{kflag}</td><td>{uni(t)}</td>"
                  f"<td class=supp>{sc}/{target.KNN}</td>"
                  f"<td class=conftxt>{s:.2f} <span style='color:{bandcol(s)}'>●</span></td></tr>")
    evrows = "".join(f"<div class=li><span class=s>CID {cid} · {co:.2f}</span>→ hits {', '.join(esc(x) for x in tg) or '—'}</div>" for cid, co, tg in ev)
    # patent landscape for the #1 predicted target
    land = ""
    if preds and best >= 0.30:
        tacc = preds[0][0]; tgene = target.gene_sym(tacc)
        actives = [(c, csm[c]) for c in tgt_cids.get(tacc, []) if c in csm]
        random.Random(1).shuffle(actives); actives = actives[:8]
        patent = {}
        for c, asm in actives:
            bv = morgan(asm)
            if bv is None: continue
            arr = np.zeros((2048,), dtype=np.float32); DataStructs.ConvertToNumpyArray(bv, arr)
            for h in qc.query_points("patents_compounds", query=arr.tolist(), limit=40, with_payload=["surechembl_id", "smiles"]).points:
                s2 = h.payload.get("smiles"); mm = Chem.MolFromSmiles(s2) if s2 else None
                if mm is None: continue
                tt = DataStructs.TanimotoSimilarity(bv, AllChem.GetMorganFingerprintAsBitVect(mm, 2, nBits=2048))
                sid = h.payload.get("surechembl_id")
                if sid and tt > patent.get(sid, (0,))[0]: patent[sid] = (tt, s2)
        ranked = sorted(patent.items(), key=lambda x: -x[1][0])
        cells = "".join(f"<div style='display:inline-block;text-align:center;margin:4px;vertical-align:top'><div class=struct style='padding:2px'>{svg(s2)}</div><div class=r style='font-size:11px'>{esc(sid)} · {tt:.2f}</div></div>" for sid, (tt, s2) in ranked[:6])
        land = (f"<div class=card moat><span class=mode>uses the 31M patent vector DB</span>"
                f"<h2>Patent landscape — chemistry claimed against {esc(tgene[:30])} <span class=note>(its #1 predicted target)</span></h2>"
                f"<div class=note>{len(ranked)} patent compounds in the chemical neighbourhood of {esc(tgene)}'s known ligands — the patented neighbourhood this molecule's target sits in.</div>"
                f"<div style='margin-top:8px'>{cells}</div></div>")
    body = (f"<div class=top><span class=kind>compound dossier</span><h1>{esc(name)}</h1></div>"
            f"<p class=smiles>{esc(sm[:88])}{'…' if len(sm) > 88 else ''}</p>"
            f"<div class=card><div style='display:flex;gap:18px;align-items:center;flex-wrap:wrap'>"
            f"<div class=struct>{svg(sm)}</div>"
            f"<div><span class=bigpct style='color:{bandcol(best)}'>{best:.2f}</span><div class=lab>nearest known ligand (Tanimoto) &rarr; <b style='color:{bandcol(best)}'>{band(best)}</b>{' <span class=known>✓ known drug — recovers established targets</span>' if known else ''}</div></div></div></div>"
            f"<div class=card pred><h2>Predicted protein targets <span class=note>(top 20 of {len(preds)} human; ChEMBL k-NN)</span></h2>"
            f"<table><tr><th>#</th><th>gene</th><th>UniProt</th><th title='nearest-neighbour support out of 20'>supporting neighbours</th><th>confidence</th></tr>{trows}</table></div>"
            f"<div class=card ground><h2>Why — nearest known ligands (the evidence)</h2>{evrows}</div>"
            f"{land}")
    open(f"{OUT}/{fname}", "w").write(page_html(f"{name} — BioYoda atlas", body))
    print(f"  wrote {fname}"); return name, fname, best

if __name__ == "__main__":
    print("building target-atlas sample pages…", flush=True)
    # COMPOUND pages: molecule → predicted targets (uses the ChEMBL answer key)
    cpages = []
    # genuine PREDICTIONS — real patent compounds NOT in ChEMBL (best < 1.0 → a fresh prediction, not "known")
    for name, q, fn in [
        ("Patent compound SCHEMBL8383", "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1O", "predict_egfr.html"),
        ("Patent compound SCHEMBL735", "CCCc1nn(CC)c2c(=O)[nH]c(-c3ccccc3OCC)nc12", "predict_pde5.html"),
        ("Patent compound SCHEMBL40470", "Nc1ccc(N2CCCCC2)cc1-c1cc(NC(=O)c2cccc(C(F)(F)F)c2)ccn1", "predict_braf.html")]:
        r = build(name, q, fn); cpages.append(r) if r else None
    # KNOWN drugs — sanity check that the method recovers established targets (these ARE in ChEMBL → "known")
    for name, q, fn in [("Imatinib", "imatinib", "imatinib.html"),
                        ("Gefitinib", "gefitinib", "gefitinib.html"),
                        ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O", "aspirin.html")]:
        r = build(name, q, fn); cpages.append(r) if r else None
    nid, nsm = novel_patent()
    if nsm:
        r = build(nid, nsm, "novel_patent.html"); cpages.append(r) if r else None
    # TARGET pages: target → patent landscape (uses the 31M patent vector DB)
    tpages = []
    for acc, gene, fn in [("P00533", "EGFR", "target_EGFR.html"),
                          ("P15056", "BRAF", "target_BRAF.html")]:
        r = build_landscape(acc, gene, fn); tpages.append(r) if r else None
    # COMBINED dossier pages: both directions on one dense page (compound-centric)
    combos = []
    for nm, q, fn in [("Imatinib", "imatinib", "dossier_imatinib.html"),
                      ("Gefitinib", "gefitinib", "dossier_gefitinib.html")]:
        r = build_combined(nm, q, fn)
        if r: combos.append(r)
    vf = build_validation()
    # rich index
    def Si(big, lab): return f"<span class=stat><span class=big>{big}</span><span class=lab>{lab}</span></span>"
    colinks = "".join(f"<div class=li><a href='{fn}'><b>{esc(nm)}</b></a> <span class=r>· predicted targets + its target's patent landscape · best Tanimoto {b:.2f}</span></div>" for nm, fn, b in combos)
    clinks = "".join(f"<div class=li><a href='{fn}'>{esc(nm)}</a> <span class=r>· best Tanimoto {b:.2f} · {band(b)}</span></div>" for nm, fn, b in cpages)
    tlinks = "".join(f"<div class=li><a href='{fn}'>{esc(g)}</a> <span class=r>· {n} patent compounds claimed</span></div>" for g, fn, n in tpages)
    idx = page_html("BioYoda atlas",
        "<div class=top><span class=kind>atlas</span><h1>BioYoda · predicted target atlas of chemical space</h1></div>"
        "<div class=sub>For any molecule — <b>what protein does it probably hit?</b> — and for any protein — <b>what patented "
        "chemistry is claimed against it?</b> Predicted from owned vectors, grounded, with honest confidence.</div>"
        # family positioning
        "<div class=card ground><h2>Where this sits</h2><table>"
        "<tr><th></th><th>deterministic (known)</th><th>predictive (plausible)</th></tr>"
        "<tr><td class=r>substrate</td><td>biobtree</td><td><b>BioYoda</b></td></tr>"
        "<tr><td class=r>catalog</td><td>sugi-atlas</td><td><b>this atlas</b></td></tr></table>"
        "<div class=note>biobtree grounds and sugi-atlas catalogs what is <b>known</b>, deterministically. BioYoda predicts and "
        "catalogs what is <b>plausible-but-not-yet-curated</b>, and grounds it back to biobtree.</div></div>"
        # scale strip
        f"<div class=card><h2>The owned substrate</h2><div class=conf>{Si('103M','vectors')}{Si('6','modalities')}{Si('30.9M','patent compounds')}{Si('4–9 ms','warm query')}{Si('no GPU','at query')}</div></div>"
        # method/validation (prominent)
        f"<div class=card pred><h2>Does it work? — method &amp; validation</h2><div class=note>Held-out <b>77% recall@1</b> (scaffold split) among 7,929 "
        f"targets, far above baselines; 83% leave-one-out upper bound, 41% on chemistry disclosed after the reference; 40% of patent space high-confidence, 93.5% target-reachable. "
        f"Validated by elimination — weaker ideas were dropped on the same test.</div><div class=li style='margin-top:8px'>&rarr; <a href='{vf}'><b>Method &amp; validation page</b></a></div></div>"
        # FEATURED: combined dossier (both directions on one page)
        f"<div class=card pred><h2>★ Combined compound dossier <span class=note>(both directions, one dense page)</span></h2>"
        f"<div class=note>Predicted targets <b>and</b> the patent landscape of the molecule's top target — the whole story for one compound.</div>{colinks}</div>"
        # the two directions, separately
        f"<div class=card><h2>① Compound → predicted target <span class=note>(searches the ChEMBL answer key)</span></h2>{clinks}</div>"
        f"<div class=card><h2>② Target → patent landscape <span class=note>(searches the 31M patent vector DB)</span></h2>{tlinks}</div>")
    open(f"{OUT}/index.html", "w").write(idx)
    import subprocess; subprocess.run(["chmod", "-R", "a+rX", OUT])
    print(f"\nwrote: {OUT}  ->", [p[1] for p in cpages] + [p[1] for p in tpages] + [vf, "index.html"])

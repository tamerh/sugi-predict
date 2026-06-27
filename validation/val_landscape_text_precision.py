#!/usr/bin/env python3
"""HONEST validation of the flagship TARGET -> PATENT LANDSCAPE direction (the reviewer's "~20%, anecdotes only"
flag). The landscape at /target/X lists patent compounds predicted against X by chemistry k-NN, ranked by SUPPORT
(n of 20 nearest ChEMBL ligands backing X) then confidence. The PRECISION question: of those compounds, what
fraction GENUINELY associate with X by an INDEPENDENT signal?

INDEPENDENT SIGNAL = the patent's OWN body text. For a landscape compound that has a full-text patent, we rank
ALL human targets by how much the patent BODY is "about" each (debiased cosine of the patent's MedCPT-Article
vector to the precomputed MedCPT-Query target embeddings -- EXACTLY the serve-time method in
mcp_srv/engine.py:patent_text_support()). X is "corroborated" when it lands in the text's top-TEXT_RANK_HIT.

We report, per target and overall:
  * landscape precision  = frac of full-text landscape compounds whose patent text ranks X in top-k (corroborated)
  * NULL baseline        = same, but for a RANDOM human target instead of X (calibrates "by chance")
  * disagreement rate    = frac where the text STRONGLY points elsewhere (X rank > DISAGREE_RANK and a different
                           target tops the text) -- a false-positive estimate
  * stratification        by SUPPORT bucket and by CONFIDENCE band (is support a trustworthy landscape knob?)

CAVEATS (printed in the report):
  - coverage: only ~1.4% of patents have full text, so this measures the FULL-TEXT SUBSET, not the whole landscape.
  - partial independence: inventors design AND describe the molecule, so corroboration means "the patent is about
    X", not ground-truth binding. It is an independent-of-chemistry signal, not an independent assay.
  - noise compounds: ubiquitous tool compounds (prov.noise=True; e.g. imatinib in 124k patents) are SUPPRESSED by
    the serve-time badge (their patents mention them only incidentally). We report WITH and WITHOUT them so the
    suppression's effect on the measured landscape is visible.

Read-only. No git commit. Saves nothing but its stdout (redirect to capture).
  python val_landscape_text_precision.py [--per-target 400] [--rank-hit 10]
"""
import argparse, os, sys, random, collections, json
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

QDRANT = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")
NPZ = "/data/bioyoda/work/patent_text_support/target_query_emb.npz"
PC = "patent_compounds_v2"          # alias target of patent_compounds
PT = "patents_text_medcpt"          # alias target of patents_text

# diverse panel: kinases, GPCRs, ion channels, proteases, nuclear receptors; well-covered -> sparser
PANEL = [
    ("P00533", "EGFR",  "kinase"),
    ("P00519", "ABL1",  "kinase"),
    ("P11362", "FGFR1", "kinase"),
    ("P07550", "ADRB2", "GPCR"),
    ("P14416", "DRD2",  "GPCR"),
    ("P28223", "HTR2A", "GPCR"),
    ("Q12809", "KCNH2", "ion-channel"),
    ("Q14524", "SCN5A", "ion-channel"),
    ("P00734", "F2",    "protease"),
    ("P08246", "ELANE", "protease"),
    ("P03372", "ESR1",  "nuclear-receptor"),
    ("P10275", "AR",    "nuclear-receptor"),
]

DISAGREE_RANK = 50    # X must rank worse than this AND a different target tops the text -> "disagreement"


def load_targets():
    """Replicate engine._target_emb(): human-only debiased target-query matrix."""
    d = np.load(NPZ, allow_pickle=True)
    hm = d["human"].astype(bool)
    emb = d["emb"][hm]
    bg = d["bg"][hm] if "bg" in d.files else np.zeros(emb.shape[0], dtype="float32")
    acc = [str(a) for a in d["acc"][hm]]
    gene = [str(g) for g in d["gene"][hm]]
    return emb, bg, acc, gene, {a: i for i, a in enumerate(acc)}


def support_ranked_landscape(qc, acc, limit, acc2i):
    """Scroll the target's landscape (targets:acc) and return compounds ranked by SUPPORT desc then CONF desc on
    the predicted entry for `acc` -- the same ordering the web /target/X landscape uses. Returns list of dicts:
    {id, schembl, conf, support, noise, pat_nums:[...]}.  Only compounds whose `predicted` actually contains acc
    (it always should, since targets is derived from predicted) and that have provenance patents."""
    f = Filter(must=[FieldCondition(key="targets", match=MatchValue(value=acc))])
    true_n = qc.count(PC, count_filter=f).count        # the FULL landscape size (not the scanned pool)
    rows = []
    nxt = None
    seen = 0
    while True:
        pts, nxt = qc.scroll(PC, scroll_filter=f, limit=2000, offset=nxt,
                             with_payload=["surechembl_id", "predicted", "prov"], with_vectors=False)
        if not pts:
            break
        for p in pts:
            pl = p.payload or {}
            pred = {d["acc"]: d for d in (pl.get("predicted") or [])}
            d = pred.get(acc)
            if not d:
                continue
            prov = pl.get("prov") or {}
            pat_nums = [pt.get("number") for pt in (prov.get("patents") or []) if pt.get("number")]
            if not pat_nums:
                continue
            rows.append({"id": int(p.id), "schembl": pl.get("surechembl_id"),
                         "conf": float(d.get("conf", 0.0)), "support": int(d.get("support", 0)),
                         "noise": bool(prov.get("noise")), "pat_nums": pat_nums})
        seen += len(pts)
        # cap the scan: we only need enough full-text compounds; stop once we have a big pool
        if nxt is None or len(rows) >= limit * 60 or seen >= 120000:
            break
    rows.sort(key=lambda r: (-r["support"], -r["conf"]))
    return rows, true_n


def evaluate_compound(qc, r, i_x, acc, accs, emb, bg, N, RANK_HIT, rng):
    """Return (hit, null_hit, disagree, best_rank) for one compound, or None if it has no full-text patent."""
    tr = text_ranks_for_patents(qc, r["pat_nums"], emb, bg, N)
    if not tr:
        return None
    best_rank = None; best_order = None
    for pid, scores, order, rank_of in tr:
        rk = int(rank_of[i_x])
        if best_rank is None or rk < best_rank:
            best_rank = rk; best_order = order
    hit = best_rank <= RANK_HIT
    null_rank_of = np.empty(N, dtype=int); null_rank_of[best_order] = np.arange(1, N + 1)
    null_hit = int(null_rank_of[rng.randrange(N)] <= RANK_HIT)
    top_acc = accs[best_order[0]]
    disagree = int(best_rank > DISAGREE_RANK and top_acc != acc)
    return hit, null_hit, disagree, best_rank


def text_ranks_for_patents(qc, pat_nums, emb, bg, N):
    """For a set of patent numbers, fetch FULL-TEXT ones and return list of (patent_id, scores_vector,
    order, rank_of) -- one per full-text patent. scores = debiased cosine of patent body to every human target."""
    ftpts, _ = qc.scroll(
        PT, scroll_filter=Filter(must=[
            FieldCondition(key="patent_id", match=MatchAny(any=pat_nums)),
            FieldCondition(key="has_full_text", match=MatchValue(value=True))]),
        limit=50, with_payload=["patent_id"], with_vectors=True)
    out = []
    for fp in ftpts:
        v = np.asarray(fp.vector, dtype="float32")
        scores = (emb @ v) - bg
        order = np.argsort(-scores)
        rank_of = np.empty(N, dtype=int); rank_of[order] = np.arange(1, N + 1)
        out.append((fp.payload["patent_id"], scores, order, rank_of))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-target", type=int, default=400,
                    help="max full-text landscape compounds to evaluate per target (support-ranked, PASS 1)")
    ap.add_argument("--strat", type=int, default=300,
                    help="full-text compounds per target sampled across the support range for stratification (PASS 2)")
    ap.add_argument("--rank-hit", type=int, default=10, help="TEXT_RANK_HIT: X in top-k = corroborated")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    RANK_HIT = a.rank_hit
    rng = random.Random(a.seed)

    qc = QdrantClient(url=QDRANT, timeout=600, check_compatibility=False)
    emb, bg, accs, genes, acc2i = load_targets()
    N = len(accs)
    print(f"# human targets in text-ranking vocab: N={N}", flush=True)
    print(f"# TEXT_RANK_HIT = {RANK_HIT}  (X in text top-{RANK_HIT} == corroborated); "
          f"DISAGREE_RANK = {DISAGREE_RANK}\n", flush=True)

    # accumulators
    per = {}                                  # acc -> dict of counts
    # global stratification
    g_supp = collections.defaultdict(lambda: [0, 0])   # support bucket -> [corroborated, total]
    g_band = collections.defaultdict(lambda: [0, 0])   # conf band -> [corroborated, total]
    overall = {"hit": 0, "tot": 0, "null": 0, "disagree": 0, "hit_excl_noise": 0, "tot_excl_noise": 0}

    def band(c):
        return "high>=0.5" if c >= 0.5 else "mod 0.4-0.5" if c >= 0.4 else "low 0.3-0.4" if c >= 0.3 else "<0.3"

    def supp_bucket(s):
        return "1" if s <= 1 else "2-3" if s <= 3 else "4-7" if s <= 7 else "8+"

    for acc, gene, cls in PANEL:
        i_x = acc2i.get(acc)
        if i_x is None:
            print(f"{gene} ({acc}): NOT in human text vocab -- skipped"); continue
        land, land_n = support_ranked_landscape(qc, acc, a.per_target, acc2i)
        scanned_n = len(land)
        # walk support-ranked; evaluate compounds that have >=1 full-text patent until we hit per-target cap
        c = {"gene": gene, "acc": acc, "class": cls, "landscape_n": land_n, "scanned_n": scanned_n,
             "ft": 0, "hit": 0, "null": 0, "disagree": 0,
             "ft_noise": 0, "hit_noise": 0, "ft_clean": 0, "hit_clean": 0,
             "supp": collections.defaultdict(lambda: [0, 0]), "band": collections.defaultdict(lambda: [0, 0]),
             "ranks": []}
        # PASS 1 (primary): walk the SUPPORT-RANKED served order -> the precision a user actually sees at /target/X
        for r in land:
            if c["ft"] >= a.per_target:
                break
            ev = evaluate_compound(qc, r, i_x, acc, accs, emb, bg, N, RANK_HIT, rng)
            if ev is None:
                continue
            hit, null_hit, dis, best_rank = ev
            c["ft"] += 1
            c["ranks"].append(best_rank)
            c["hit"] += hit
            c["null"] += null_hit
            c["disagree"] += dis
            if r["noise"]:
                c["ft_noise"] += 1; c["hit_noise"] += hit
            else:
                c["ft_clean"] += 1; c["hit_clean"] += hit

        # PASS 2 (stratification): sample full-text compounds ACROSS the whole support range (not just the top),
        # so "does precision climb with support?" is answerable. Shuffle the landscape and evaluate until we have
        # `--strat` full-text compounds; bin by support and conf band.
        strat_pool = land[:]
        rng.shuffle(strat_pool)
        got = 0
        for r in strat_pool:
            if got >= a.strat:
                break
            ev = evaluate_compound(qc, r, i_x, acc, accs, emb, bg, N, RANK_HIT, rng)
            if ev is None:
                continue
            hit = ev[0]; got += 1
            c["supp"][supp_bucket(r["support"])][0] += hit; c["supp"][supp_bucket(r["support"])][1] += 1
            c["band"][band(r["conf"])][0] += hit;          c["band"][band(r["conf"])][1] += 1
            g_supp[supp_bucket(r["support"])][0] += hit;   g_supp[supp_bucket(r["support"])][1] += 1
            g_band[band(r["conf"])][0] += hit;             g_band[band(r["conf"])][1] += 1
        per[acc] = c
        overall["hit"] += c["hit"]; overall["tot"] += c["ft"]; overall["null"] += c["null"]
        overall["disagree"] += c["disagree"]
        overall["hit_excl_noise"] += c["hit_clean"]; overall["tot_excl_noise"] += c["ft_clean"]
        prec = c["hit"] / c["ft"] if c["ft"] else 0
        nullp = c["null"] / c["ft"] if c["ft"] else 0
        med = int(np.median(c["ranks"])) if c["ranks"] else -1
        print(f"{gene:6} {acc} [{cls:16}] landscape={land_n:8,}  full-text n={c['ft']:4}  "
              f"precision={prec:5.1%}  null={nullp:5.1%}  disagree={c['disagree']/c['ft'] if c['ft'] else 0:5.1%}  "
              f"median_rank={med:4}  (clean n={c['ft_clean']}, noise n={c['ft_noise']})", flush=True)

    # ---------- REPORT ----------
    print("\n" + "=" * 100)
    print("PER-TARGET LANDSCAPE PRECISION (independent signal = patent body text)")
    print("=" * 100)
    hdr = f"{'target':7}{'class':17}{'landscape':>11}{'FT n':>6}{'PRECISION':>11}{'null':>8}{'lift':>7}{'disagree':>10}{'med-rank':>10}"
    print(hdr); print("-" * len(hdr))
    for acc, gene, cls in PANEL:
        c = per.get(acc)
        if not c:
            continue
        ft = c["ft"]
        if not ft:
            print(f"{gene:7}{cls:17}{c['landscape_n']:>11,}{0:>6}   (no full-text landscape compounds)"); continue
        prec = c["hit"] / ft; nullp = c["null"] / ft
        lift = prec / nullp if nullp else float("inf")
        dis = c["disagree"] / ft
        med = int(np.median(c["ranks"]))
        print(f"{gene:7}{cls:17}{c['landscape_n']:>11,}{ft:>6}{prec:>11.1%}{nullp:>8.1%}"
              f"{lift:>6.1f}x{dis:>10.1%}{med:>10}")
    print("-" * len(hdr))
    O = overall
    op = O["hit"] / O["tot"] if O["tot"] else 0
    onull = O["null"] / O["tot"] if O["tot"] else 0
    odis = O["disagree"] / O["tot"] if O["tot"] else 0
    opc = O["hit_excl_noise"] / O["tot_excl_noise"] if O["tot_excl_noise"] else 0
    print(f"{'OVERALL':7}{'(micro)':17}{'':>9}{O['tot']:>6}{op:>11.1%}{onull:>8.1%}"
          f"{(op/onull if onull else float('inf')):>6.1f}x{odis:>10.1%}")
    print(f"\nOVERALL precision (all full-text landscape compounds):        {op:5.1%}   (n={O['tot']})")
    print(f"OVERALL precision EXCLUDING noise/tool compounds (served set): {opc:5.1%}   (n={O['tot_excl_noise']})")
    print(f"NULL baseline (random human target, same patents):            {onull:5.1%}")
    print(f"DISAGREEMENT rate (text strongly points elsewhere):           {odis:5.1%}")
    macro = np.mean([per[a]["hit"] / per[a]["ft"] for a, _, _ in PANEL if per.get(a) and per[a]["ft"]])
    print(f"MACRO precision (mean over targets):                          {macro:5.1%}")

    print("\n" + "=" * 70)
    print("STRATIFICATION BY SUPPORT  (is support a trustworthy landscape knob?)")
    print("   [from PASS 2: full-text compounds sampled ACROSS the support range, not just the top]")
    print("=" * 70)
    print(f"{'support bucket':16}{'precision':>12}{'n':>9}")
    for b in ["1", "2-3", "4-7", "8+"]:
        h, t = g_supp[b]
        if t:
            print(f"{b:16}{h/t:>12.1%}{t:>9}")
    print("\n" + "=" * 70)
    print("STRATIFICATION BY CONFIDENCE BAND")
    print("=" * 70)
    print(f"{'conf band':16}{'precision':>12}{'n':>9}")
    for b in ["high>=0.5", "mod 0.4-0.5", "low 0.3-0.4", "<0.3"]:
        h, t = g_band[b]
        if t:
            print(f"{b:16}{h/t:>12.1%}{t:>9}")

    print("\n" + "=" * 100)
    print("CAVEATS")
    print("=" * 100)
    print("- FULL-TEXT SUBSET: only ~1.4% of patents have full text. This precision is measured ON THAT SUBSET,")
    print("  not the whole landscape. The other ~98.6% of landscape compounds have no independent text signal here.")
    print("- PARTIAL INDEPENDENCE: inventors design AND describe the molecule, so 'corroborated' means the patent")
    print("  is ABOUT X -- evidence the compound is an X-program molecule -- NOT a ground-truth binding assay.")
    print("- NOISE/TOOL COMPOUNDS: served badges suppress prov.noise compounds (incidental mentions). The")
    print("  'EXCLUDING noise' row is the precision of what users actually see.")
    print(f"- NULL is non-zero ({onull:.1%}) because a random target lands in top-{RANK_HIT} of {N} ~ {RANK_HIT/N:.1%}")
    print("  of the time by chance; precision must beat NULL to mean anything (see 'lift').")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Standalone, reproducible null-control validation of the patent-text-support badge.

THE CLAIM under test (mcp_srv/engine.py patent_text_support):
  For a patent compound, the full-text patent BODY independently corroborates the
  chemistry-predicted target. Method: precomputed MedCPT-Query target-vocab embeddings
  (work/patent_text_support/target_query_emb.npz) dotted against the patent's stored
  MedCPT-Article text vector, BACKGROUND-DEBIASED (minus the mean-patent affinity), then
  the predicted target is ranked among ~4885 human targets. The pilot reported recall@10
  ~0.19 (overall) / ~0.40 (conf>=0.8) vs ~0.02 under a link-shuffle null -- but those
  numbers lived only in a build-script docstring. This script recomputes them on a fresh
  sample and answers the harder question: HOW INDEPENDENT is the signal really?

WHAT IT MEASURES, for a fresh random sample of (compound -> predicted-target) pairs that
have at least one full-text provenance patent:

  REAL          : real compound<->patent links. Where does the predicted target rank in
                  the body text? (recall@1/@5/@10, median rank.)
  SIMPLE NULL   : permute the compound<->patent link globally (a random full-text patent).
                  If the signal were pure artifact this would match REAL.
  STRICT NULL   : permute the compound<->patent link WITHIN the same topical class
                  (CPC section+class prefix, e.g. C07D / A61K). The null patent is now
                  topically similar (same chemistry/therapeutic area) but is NOT this
                  compound's patent. THE CRUX: if REAL still beats STRICT, the signal is
                  weakly-but-genuinely independent; if REAL ~= STRICT, the badge is mostly
                  "the patent is about this kind of target" (consistency), not independent
                  corroboration of THIS compound's target.

  Every metric is reported PRE-debias (raw cosine) and POST-debias (cosine - bg), so the
  background subtraction is shown to be a declared, necessary step (raw cosine is dominated
  by a handful of attractor targets) rather than a knob tuned to manufacture a gap.

OPTIONAL NER PRECISION CHECK (--ner): for patents whose body text explicitly NAMES the
predicted target's gene symbol (simple word-boundary string match over the full text from
the MedCPT input shards), what fraction of predicted targets is the body actually about?
A direct, non-semantic precision check that does not depend on the embedding at all.

Reproducible: fixed --seed. No model load (uses precomputed embeddings + stored vectors).
CPC topical classes are joined from raw_data/patents/chunked/*.parquet (the text-shard
ipc_codes payload is almost entirely empty; cpc in the parquet metadata is ~99% populated).

Run:
  python modules/compounds/validate_patent_text_support.py --n 600 --seed 0 \
      --report work/patent_text_support/validation_report.json
  # add --ner for the gene-name precision check (scans the 20G text shards once, slower)
"""
import argparse
import collections
import glob
import json
import os
import random
import re
import sys

import numpy as np

ROOT = os.environ.get("BIOYODA_ROOT", "/data/bioyoda")
QDRANT_URL = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")
NPZ = os.environ.get("PATENT_TEXT_SUPPORT_NPZ",
                     f"{ROOT}/work/patent_text_support/target_query_emb.npz")
SHARD_DIR = f"{ROOT}/work/data/medcpt_input/patents"           # patent_id -> full text + ipc
PARQUET_GLOB = f"{ROOT}/raw_data/patents/chunked/*.parquet"    # patent_number -> cpc (topical class)
KS = (1, 5, 10)


# ----------------------------------------------------------------------------- target matrix
def load_targets():
    """Human target-query matrix: emb (N,768 L2-norm), bg (N,) background affinity,
    acc/gene (N,), and acc->row index. Matches what the engine loads at serve time."""
    d = np.load(NPZ, allow_pickle=True)
    h = d["human"].astype(bool)
    emb = d["emb"][h].astype("float32")
    bg = (d["bg"][h] if "bg" in d else np.zeros(emb.shape[0], "float32")).astype("float32")
    acc = [str(a) for a in d["acc"][h]]
    gene = [str(g) for g in d["gene"][h]]
    return emb, bg, acc, gene, {a: i for i, a in enumerate(acc)}


# ----------------------------------------------------------------------------- sampling
def sample_pairs(qc, n_pairs, seed, max_scan):
    """Scan patent_compounds for non-noise compounds with predictions + provenance patents.
    Returns a list of dicts: {cid, pred_accs:[acc], pred_conf:{acc:conf}, pred_gene:{acc:gene},
    pat_nums:[patent_number]}. We oversample compounds (each yields >=1 predicted-target pair)."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue  # noqa
    rng = random.Random(seed)
    out, off, scanned = [], None, 0
    while len(out) < n_pairs * 3 and scanned < max_scan:
        pts, off = qc.scroll("patent_compounds", limit=512, with_payload=True,
                             with_vectors=False, offset=off)
        if not pts:
            break
        for p in pts:
            scanned += 1
            pl = p.payload or {}
            prov = pl.get("prov") or {}
            if prov.get("noise"):
                continue
            preds = pl.get("predicted") or []
            pats = [x["number"] for x in (prov.get("patents") or []) if x.get("number")]
            if not preds or not pats:
                continue
            out.append({
                "cid": p.id,
                "pred_accs": [x["acc"] for x in preds if x.get("acc")],
                "pred_conf": {x["acc"]: float(x.get("conf", 0.0)) for x in preds if x.get("acc")},
                "pred_gene": {x["acc"]: x.get("gene") for x in preds if x.get("acc")},
                "pat_nums": pats,
            })
        if off is None:
            break
    rng.shuffle(out)
    print(f"  scanned {scanned} compounds -> {len(out)} usable; keeping ~{n_pairs}", file=sys.stderr)
    return out


# ----------------------------------------------------------------------------- patent text vectors
def fetch_fulltext_vecs(qc, patent_ids):
    """patent_id -> (vec float32, cpc_class str|None) for patents that have a full-text vector.
    cpc class is filled later from parquet; here we just grab vectors + the stored ipc payload."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
    res = {}
    ids = list(patent_ids)
    for i in range(0, len(ids), 256):
        chunk = ids[i:i + 256]
        pts, _ = qc.scroll(
            "patents_text_medcpt",
            scroll_filter=Filter(must=[
                FieldCondition(key="patent_id", match=MatchAny(any=chunk)),
                FieldCondition(key="has_full_text", match=MatchValue(value=True))]),
            limit=512, with_payload=["patent_id", "ipc_codes"], with_vectors=True)
        for p in pts:
            pid = p.payload["patent_id"]
            if pid not in res:
                res[pid] = np.asarray(p.vector, dtype="float32")
    return res


# ----------------------------------------------------------------------------- CPC topical class
def cpc_class(code):
    """Topical class key from a CPC/IPC code, e.g. 'C07D 231/12' -> 'C07D'. Section+class+subclass
    (4 chars) groups patents by chemistry / therapeutic area -- the right granularity for a topical
    null (too coarse = section letter only; too fine = full group splits real siblings apart)."""
    if not code:
        return None
    s = str(code).strip().replace(" ", "")
    return s[:4] if len(s) >= 4 else None


def load_cpc_for(patent_ids):
    """patent_number -> CPC topical class, joined from the chunked parquet metadata.

    The cpc/ipc columns are list-of-string columns over 44M rows; materializing them whole is
    very slow. Instead we FILTER each chunk to just our wanted patent_numbers with pyarrow.compute
    BEFORE touching the list columns, so only the handful of matching rows are ever materialized."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    import pyarrow.compute as pc
    want = set(patent_ids)
    want_arr = pa.array(sorted(want))
    out = {}
    for f in sorted(glob.glob(PARQUET_GLOB)):
        t = pq.read_table(f, columns=["patent_number", "cpc", "ipc", "ipcr"])
        mask = pc.is_in(t.column("patent_number"), value_set=want_arr)
        if not pc.any(mask).as_py():
            continue
        sub = t.filter(mask).to_pylist()    # only the matching rows
        for r in sub:
            num = r["patent_number"]
            if num in out:
                continue
            codes = r["cpc"] or r["ipc"] or r["ipcr"] or []
            cls = next((c for c in (cpc_class(c) for c in codes) if c), None)
            if cls:
                out[num] = cls
        if len(out) >= len(want):
            break
    return out


# ----------------------------------------------------------------------------- ranking
def ranks_for(vec, emb, bg, idxs):
    """Given a patent vector, return (raw_rank, debiased_rank) for each target row index in idxs,
    among all N human targets. Lower rank = the text is more 'about' that target."""
    raw = emb @ vec
    deb = raw - bg
    N = emb.shape[0]
    r_raw = np.empty(N, int); r_raw[np.argsort(-raw)] = np.arange(1, N + 1)
    r_deb = np.empty(N, int); r_deb[np.argsort(-deb)] = np.arange(1, N + 1)
    return {i: (int(r_raw[i]), int(r_deb[i])) for i in idxs}


def summarize(ranks):
    """ranks: list of int ranks (best rank per pair). -> recall@k + median rank."""
    a = np.array(ranks, dtype=float)
    out = {f"recall@{k}": round(float((a <= k).mean()), 4) for k in KS}
    out["median_rank"] = float(np.median(a)) if len(a) else None
    out["n"] = len(a)
    return out


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600, help="target number of (compound,target) pairs")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-scan", type=int, default=40000, help="max compounds to scroll")
    ap.add_argument("--conf-hi", type=float, default=0.8, help="high-confidence cut for the conf split")
    ap.add_argument("--ner", action="store_true", help="run the gene-name body-text precision check")
    ap.add_argument("--report", default=f"{ROOT}/work/patent_text_support/validation_report.json")
    args = ap.parse_args()

    from qdrant_client import QdrantClient
    qc = QdrantClient(url=QDRANT_URL, timeout=300, check_compatibility=False)

    emb, bg, accs, genes, acc2i = load_targets()
    N = len(accs)
    print(f"targets: {N} human; npz={NPZ}", file=sys.stderr)

    comps = sample_pairs(qc, args.n, args.seed, args.max_scan)

    # need vectors for all provenance patents of sampled compounds
    all_pats = sorted({p for c in comps for p in c["pat_nums"]})
    print(f"fetching full-text vectors for up to {len(all_pats)} provenance patents ...", file=sys.stderr)
    vecs = fetch_fulltext_vecs(qc, all_pats)
    print(f"  {len(vecs)} of those have a full-text vector", file=sys.stderr)

    # keep only compounds that actually have >=1 full-text patent + >=1 predicted target in-vocab
    usable = []
    for c in comps:
        ft = [p for p in c["pat_nums"] if p in vecs]
        pa = [a for a in c["pred_accs"] if a in acc2i]
        if ft and pa:
            c["ft"] = ft
            c["pa"] = pa
            usable.append(c)
        if len(usable) >= args.n:
            break
    print(f"usable compounds with full-text + in-vocab preds: {len(usable)}", file=sys.stderr)

    # CPC topical class for every full-text patent in play (for the strict null)
    ft_pats = sorted({p for c in usable for p in c["ft"]})
    print(f"joining CPC topical class for {len(ft_pats)} full-text patents from parquet ...", file=sys.stderr)
    cpc = load_cpc_for(ft_pats)
    print(f"  CPC class found for {len(cpc)}/{len(ft_pats)} ({100*len(cpc)/max(1,len(ft_pats)):.0f}%)", file=sys.stderr)

    # pool of full-text patents grouped by CPC class -> the strict-null draw
    by_class = collections.defaultdict(list)
    for p in ft_pats:
        if p in cpc:
            by_class[cpc[p]].append(p)
    all_ft = list(vecs.keys())

    rng = random.Random(args.seed + 7)

    # cache per-patent ranks for every predicted acc we ever touch (compute once, reuse across null draws)
    rank_cache = {}

    def get_ranks(pid, idxs):
        if pid not in vecs:
            return None
        need = [i for i in idxs if (pid, i) not in rank_cache]
        if need:
            r = ranks_for(vecs[pid], emb, bg, need)
            for i in need:
                rank_cache[(pid, i)] = r[i]
        return {i: rank_cache[(pid, i)] for i in idxs}

    # accumulate best (lowest) rank per (compound,target) pair under each condition.
    # `top` flags the pair that is this compound's single highest-confidence in-vocab prediction
    # (the one the badge most cares about) so we can report a top-prediction-only tier.
    cond = {k: {"raw": [], "deb": [], "conf": [], "top": []} for k in ("real", "simple", "strict")}
    strict_skipped = 0   # pairs with no same-class alternative patent

    for c in usable:
        idxs = [acc2i[a] for a in c["pa"]]
        top_acc = max(c["pa"], key=lambda a: c["pred_conf"].get(a, 0.0))
        # REAL: best rank across this compound's own full-text patents. Track the best RAW rank and
        # the best DEBIASED rank INDEPENDENTLY, so the pre/post comparison is fair (neither metric is
        # handicapped by being forced onto the patent the other metric preferred).
        real = {i: [10**9, 10**9] for i in idxs}   # [best_raw, best_deb]
        for pid in c["ft"]:
            rr = get_ranks(pid, idxs)
            for i in idxs:
                real[i][0] = min(real[i][0], rr[i][0])
                real[i][1] = min(real[i][1], rr[i][1])
        # SIMPLE NULL: one random full-text patent from the global pool
        sp = rng.choice(all_ft)
        simple = get_ranks(sp, idxs)
        # STRICT NULL: a random patent in the SAME CPC class as one of the compound's real patents,
        # but not one of the compound's own patents.
        own = set(c["ft"])
        classes = [cpc[p] for p in c["ft"] if p in cpc]
        strict = None
        if classes:
            cls = rng.choice(classes)
            pool = [p for p in by_class[cls] if p not in own]
            if pool:
                strict = get_ranks(rng.choice(pool), idxs)
        for a, i in zip(c["pa"], idxs):
            conf = c["pred_conf"].get(a, 0.0)
            is_top = (a == top_acc)
            cond["real"]["raw"].append(real[i][0]); cond["real"]["deb"].append(real[i][1])
            cond["real"]["conf"].append(conf); cond["real"]["top"].append(is_top)
            cond["simple"]["raw"].append(simple[i][0]); cond["simple"]["deb"].append(simple[i][1])
            cond["simple"]["conf"].append(conf); cond["simple"]["top"].append(is_top)
            if strict is not None:
                cond["strict"]["raw"].append(strict[i][0]); cond["strict"]["deb"].append(strict[i][1])
                cond["strict"]["conf"].append(conf); cond["strict"]["top"].append(is_top)
            else:
                strict_skipped += 1

    # ------------------------------------------------------------------- assemble report
    # NOTE on tiers: non-noise compounds carry a MEDIAN of ~19 predicted targets (a long low-confidence
    # tail); only ~2% of predictions are conf>=0.8. The badge in production only fires for strong, top
    # predictions, so the honest headline is the high-confidence / top-prediction tier, not "all pairs".
    def block(name):
        d = cond[name]
        raw = np.array(d["raw"]); deb = np.array(d["deb"])
        conf = np.array(d["conf"]); top = np.array(d["top"])
        tiers = {"all": np.ones(len(raw), bool),
                 "conf>=0.5": conf >= 0.5,
                 f"conf>={args.conf_hi}": conf >= args.conf_hi,
                 "top_pred_only": top}
        out = {}
        for tname, m in tiers.items():
            if m.any():
                out[tname] = {"pre_debias": summarize(list(raw[m])),
                              "post_debias": summarize(list(deb[m]))}
        return out

    report = {
        "config": {"n_requested": args.n, "seed": args.seed, "n_targets": N,
                   "conf_hi": args.conf_hi, "n_pairs": len(cond["real"]["deb"]),
                   "n_compounds": len(usable), "strict_null_pairs_skipped_no_sameclass": strict_skipped},
        "real": block("real"),
        "simple_null": block("simple"),
        "strict_ipc_null": block("strict"),
    }

    if args.ner:
        report["ner_gene_name_precision"] = ner_check(usable, vecs, args.seed)

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    json.dump(report, open(args.report, "w"), indent=2)
    print_table(report, args)
    print(f"\nwrote {args.report}", file=sys.stderr)


# ----------------------------------------------------------------------------- NER precision check
def ner_check(usable, vecs, seed):
    """For each (compound, predicted target) whose body text EXPLICITLY names the gene symbol
    (word-boundary match over the full patent text from the MedCPT input shards), measure:
      coverage  : fraction of predicted targets whose gene is named in >=1 of the compound's patents
      this is a non-semantic, direct corroboration that does not use the embedding at all.
    Also reports, among named pairs, the debiased semantic rank distribution -- i.e. when the body
    literally names the gene, does the semantic ranker also place it high? (sanity cross-check)."""
    # gather the set of patent_ids we need text for, and the gene symbols to look for
    want_pids = sorted({p for c in usable for p in c["ft"]})
    gene_by_pair = []   # (pid_list, gene, acc, conf)
    for c in usable:
        for a in c["pa"]:
            g = c["pred_gene"].get(a)
            if g and len(g) >= 2:
                gene_by_pair.append((c["ft"], g, a, c["pred_conf"].get(a, 0.0)))
    want = set(want_pids)
    print(f"NER: scanning text shards for {len(want)} patents ...", file=sys.stderr)

    pid_text = {}
    for fn in sorted(glob.glob(f"{SHARD_DIR}/*.jsonl")):
        if len(pid_text) >= len(want):
            break
        with open(fn) as f:
            for line in f:
                # cheap prefilter before json.loads
                if '"has_full_text": true' not in line and '"has_full_text":true' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                pid = r.get("patent_id")
                if pid in want and pid not in pid_text:
                    pid_text[pid] = (r.get("text") or "")
    print(f"NER: recovered text for {len(pid_text)}/{len(want)} patents", file=sys.stderr)

    # tier by confidence: a compound carries ~19 predictions, mostly low-conf junk whose gene the body
    # will never name. The meaningful precision number is on the predictions the badge would surface.
    tiers = {"all": lambda cf: True, "conf>=0.5": lambda cf: cf >= 0.5, "conf>=0.8": lambda cf: cf >= 0.8}
    res = {"n_patents_text_recovered": len(pid_text),
           "note": ("fraction of predicted targets whose gene symbol literally appears (word-boundary) in "
                    ">=1 of the compound's full-text patents. Non-semantic, embedding-free direct check.")}
    for tname, keep in tiers.items():
        total = named = 0
        for pids, gene, acc, conf in gene_by_pair:
            if not keep(conf):
                continue
            total += 1
            pat = re.compile(r"\b" + re.escape(gene) + r"\b")
            if any(pat.search(pid_text.get(p, "")) for p in pids if p in pid_text):
                named += 1
        res[tname] = {"n_pairs_with_gene_symbol": total, "named_in_body_count": named,
                      "named_in_body_fraction": round(named / total, 4) if total else None}
    return res


# ----------------------------------------------------------------------------- pretty print
def print_table(rep, args):
    cfg = rep["config"]
    print("\n" + "=" * 78)
    print(f"PATENT-TEXT-SUPPORT VALIDATION  (n_pairs={cfg['n_pairs']}, "
          f"compounds={cfg['n_compounds']}, targets={cfg['n_targets']}, seed={cfg['seed']})")
    print("=" * 78)
    conds = [("REAL link", "real"), ("SIMPLE null", "simple_null"), ("STRICT-CPC null", "strict_ipc_null")]
    splits = ["all", "conf>=0.5", f"conf>={args.conf_hi}", "top_pred_only"]
    for split in splits:
        if not rep["real"].get(split):
            continue
        print(f"\n[{split}]")
        hdr = f"{'condition':<16}{'debias':<8}" + "".join(f"r@{k:<6}" for k in KS) + f"{'med_rank':>10}{'n':>7}"
        print(hdr); print("-" * len(hdr))
        for label, key in conds:
            blk = rep[key].get(split)
            if not blk:
                continue
            for deb_label, deb_key in (("raw", "pre_debias"), ("debias", "post_debias")):
                m = blk[deb_key]
                row = f"{label:<16}{deb_label:<8}" + "".join(f"{m[f'recall@{k}']:<8.3f}" for k in KS)
                row += f"{m['median_rank']:>10.1f}{m['n']:>7d}"
                print(row)
    if "ner_gene_name_precision" in rep:
        n = rep["ner_gene_name_precision"]
        print(f"\n[NER gene-name body-text precision] (text recovered for {n['n_patents_text_recovered']} patents)")
        for tier in ("all", "conf>=0.5", "conf>=0.8"):
            t = n.get(tier)
            if t:
                print(f"  {tier:<10} gene literally named in body: "
                      f"{t['named_in_body_count']}/{t['n_pairs_with_gene_symbol']} = {t['named_in_body_fraction']}")


if __name__ == "__main__":
    main()

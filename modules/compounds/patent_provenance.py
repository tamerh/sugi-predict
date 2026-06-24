#!/usr/bin/env python3
"""Patent provenance for SureChEMBL compounds — SCHEMBL id -> {patent number, assignee, date, claimed-flag}.

Self-contained parquet join over the owned SureChEMBL snapshot (no biobtree round-trips, reproducible).
The SCHEMBL number IS compounds.id. patent_compound_map is sorted by compound_id with row-group stats, so a
filtered read skips non-overlapping row groups (no 1.5B-row scan). Batch many compound ids in ONE scan.

  compound_patents([8383, 964, ...]) -> {cid: {"n_patents": int, "noise": bool, "patents": [
        {"number","date","country","assignee","claimed"}, ... ]}}

claimed = the compound appears in the patent's CLAIMS (field_id 2) — the strongest IP signal.
noise   = n_patents above NOISE_CAP (generic fragment / excipient claimed everywhere — down-weight).
Honest gaps (see docs/internal/PATENT_PROVENANCE.md): only publication_date (no priority/filing date); assignee
is the raw, un-normalized SureChEMBL list; no inventors.
"""
import pyarrow.parquet as pq
from collections import defaultdict

DIR = "/data/bioyoda/raw_data/patents/surechembl/2025-12-15"
MAP = f"{DIR}/patent_compound_map.parquet"
PATENTS = f"{DIR}/patents.parquet"
NOISE_CAP = 2000        # n_patents above this = generic/excipient noise, not IP-informative

def _span(lst, k):
    """Earliest + latest k of a date-ascending list: foundational/priority patents plus the current frontier
    (rather than the k oldest). Returns all if there are <= k."""
    if len(lst) <= k:
        return lst
    return lst[:k - k // 2] + lst[-(k // 2):]


def compound_patents(compound_ids, max_per=8):
    ids = sorted({int(c) for c in compound_ids})
    if not ids: return {}
    m = pq.read_table(MAP, filters=[("compound_id", "in", ids)], columns=["compound_id", "patent_id", "field_id"])
    links = defaultdict(list)                                  # cid -> [(patent_id, field_id)]
    for cid, pid, fid in zip(m.column("compound_id").to_pylist(), m.column("patent_id").to_pylist(),
                             m.column("field_id").to_pylist()):
        links[int(cid)].append((int(pid), int(fid)))
    all_pids = list({pid for v in links.values() for pid, _ in v})
    pm = {}
    if all_pids:
        p = pq.read_table(PATENTS, filters=[("id", "in", all_pids)],
                          columns=["id", "patent_number", "country", "publication_date", "asignee", "title"])
        pm = {int(r["id"]): r for r in p.to_pylist()}
    out = {}
    for cid, lk in links.items():
        n = len(lk)
        pats = []
        for pid, fid in lk:
            r = pm.get(pid)
            if not r: continue
            pats.append({"number": r["patent_number"], "date": str(r["publication_date"]),
                         "country": r["country"], "assignee": (r["asignee"][0] if r["asignee"] else ""),
                         "title": (r["title"] or ""), "claimed": fid == 2})
        # select a foundational + current-frontier span (earliest + latest dates), preferring claimed patents
        claimed = sorted((p for p in pats if p["claimed"]), key=lambda x: x["date"])
        disclosed = sorted((p for p in pats if not p["claimed"]), key=lambda x: x["date"])
        chosen = _span(claimed, max_per) if len(claimed) >= max_per \
            else claimed + _span(disclosed, max_per - len(claimed))
        chosen.sort(key=lambda x: x["date"], reverse=True)   # newest first,
        chosen.sort(key=lambda x: not x["claimed"])          # claimed group on top (stable sort keeps date order)
        out[cid] = {"n_patents": n, "noise": n > NOISE_CAP, "patents": chosen}
    return out

if __name__ == "__main__":
    import sys, json
    ids = [int(a.replace("SCHEMBL", "")) for a in sys.argv[1:]] or [964, 8383, 553]
    print(json.dumps(compound_patents(ids), indent=2, default=str)[:1500])

#!/usr/bin/env python3
"""Pipeline step: bake patent provenance into the Qdrant patent_atlas payload.

Streams the SureChEMBL patent_compound_map (sorted by compound_id) ONCE, groups by compound, selects each
compound's top-N patent span (claimed-first, foundational + current-frontier — same logic the web serves),
and writes it to that compound's Qdrant payload as `prov` = {n, noise, patents:[...]}. Additive (set_payload
only — vectors and existing payload fields untouched), resumable (checkpoint), idempotent (re-running overwrites
`prov`). Reuses patent_provenance._span so the baked provenance matches the live web exactly.

  python bake_provenance.py [--snapshot DIR] [--collection patent_atlas] [--top 20]
                            [--batch 1000] [--limit N] [--dry-run] [--resume]

Reproducible: run as `bioyoda.sh atlas bake`. Small-data test: tests/fixtures/atlas/ → a throwaway collection.
No GPU — CPU + I/O. Needs ~16 GB RAM (patent metadata) + ~N-dependent payload disk (top-20 ≈ 87 GB over 30M).
"""
import argparse, json, os, sys, time
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patent_provenance import _span, NOISE_CAP


def load_patent_meta(patents_parquet):
    """id -> (number, date, country, assignee, title). ~16 GB for the full 43.8M-row table."""
    t = pq.read_table(patents_parquet,
                      columns=["id", "patent_number", "country", "publication_date", "asignee", "title"])
    ids = t.column("id").to_pylist()
    num = t.column("patent_number").to_pylist(); cty = t.column("country").to_pylist()
    dat = t.column("publication_date").to_pylist(); asg = t.column("asignee").to_pylist()
    ttl = t.column("title").to_pylist()
    return {pid: (num[i], str(dat[i]), cty[i], (asg[i][0] if asg[i] else ""), (ttl[i] or ""))
            for i, pid in enumerate(ids)}


def build_prov(links, pm, max_per):
    """links: [(patent_id, field_id)] for one compound -> {n, noise, patents:[top-N span]} (web-identical)."""
    n = len(links)
    pats = []
    for pid, fid in links:
        r = pm.get(pid)
        if not r:
            continue
        num, dat, cty, asg, ttl = r
        pats.append({"number": num, "date": dat, "country": cty, "assignee": asg, "title": ttl, "claimed": fid == 2})
    claimed = sorted((p for p in pats if p["claimed"]), key=lambda x: x["date"])
    disclosed = sorted((p for p in pats if not p["claimed"]), key=lambda x: x["date"])
    chosen = _span(claimed, max_per) if len(claimed) >= max_per else claimed + _span(disclosed, max_per - len(claimed))
    chosen.sort(key=lambda x: x["date"], reverse=True)     # newest first,
    chosen.sort(key=lambda x: not x["claimed"])            # claimed group on top (stable)
    return {"n": n, "noise": n > NOISE_CAP, "patents": chosen}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="/data/bioyoda/raw_data/patents/surechembl/2025-12-15")
    ap.add_argument("--collection", default="patent_atlas")
    ap.add_argument("--qdrant", default="http://localhost:6333")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--batch", type=int, default=1000)      # compounds per set_payload batch
    ap.add_argument("--limit", type=int, default=0)         # 0 = all (else process first N compounds, for tests)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--ckpt", default="/data/bioyoda/work/bake_provenance.ckpt")
    a = ap.parse_args()
    MAP = f"{a.snapshot}/patent_compound_map.parquet"

    start_after = -1
    if a.resume and os.path.exists(a.ckpt):
        start_after = int(open(a.ckpt).read().strip())
        print(f"resuming after compound_id {start_after}", flush=True)

    print("loading patent metadata…", flush=True)
    pm = load_patent_meta(f"{a.snapshot}/patents.parquet")
    print(f"  {len(pm):,} patents", flush=True)

    qc = None
    if not a.dry_run:
        from qdrant_client import QdrantClient
        qc = QdrantClient(url=a.qdrant, timeout=600)

    pf = pq.ParquetFile(MAP)
    cur_cid, cur_links = None, []
    ops, done, t0 = [], 0, time.time()

    def flush():
        if ops and not a.dry_run:
            from qdrant_client import models
            qc.batch_update_points(collection_name=a.collection, update_operations=ops, wait=False)
        ops.clear()

    def finalize(cid, links):
        nonlocal done
        if cid <= start_after:
            return
        prov = build_prov(links, pm, a.top)
        if not a.dry_run:
            from qdrant_client import models
            ops.append(models.SetPayloadOperation(set_payload=models.SetPayload(payload={"prov": prov}, points=[cid])))
            if len(ops) >= a.batch:
                flush()
        done += 1
        if done % 100000 == 0:
            with open(a.ckpt, "w") as f:
                f.write(str(cid))
            print(f"  {done:,} compounds  ({done / (time.time() - t0):.0f}/s)", flush=True)

    stop = False
    for rb in pf.iter_batches(columns=["compound_id", "patent_id", "field_id"], batch_size=1_000_000):
        cids = rb.column("compound_id").to_pylist()
        pids = rb.column("patent_id").to_pylist()
        fids = rb.column("field_id").to_pylist()
        for i in range(len(cids)):
            cid = cids[i]
            if cid != cur_cid:
                if cur_cid is not None:
                    finalize(cur_cid, cur_links)
                    if a.limit and done >= a.limit:
                        stop = True; break
                cur_cid, cur_links = cid, []
            cur_links.append((pids[i], fids[i]))
        if stop:
            break
    if not stop and cur_cid is not None:
        finalize(cur_cid, cur_links)
    flush()
    if cur_cid is not None and not a.dry_run:
        with open(a.ckpt, "w") as f:
            f.write(str(cur_cid))
    print(f"done: baked {done:,} compounds in {time.time() - t0:.0f}s "
          f"({'DRY RUN' if a.dry_run else 'written to ' + a.collection})", flush=True)


if __name__ == "__main__":
    main()

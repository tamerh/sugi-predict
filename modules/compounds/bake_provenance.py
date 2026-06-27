#!/usr/bin/env python3
"""Pipeline step: bake patent provenance into the Qdrant patent_compounds payload.

Two stages, both reproducible and resumable:

  1. SORT (one-time per snapshot, cached): the raw SureChEMBL patent_compound_map has every parquet
     row group spanning the full compound_id range (the ids are shuffled), so a windowed read cannot
     skip any row group -- it rescans all 1.5 B rows per window and OOMs. We sort it once by compound_id
     with DuckDB (out-of-core, spills to disk) into a sorted parquet whose row groups cover narrow id
     ranges. Skipped if the sorted file already exists and is newer than the source.

  2. BAKE (streaming): read the sorted map once with bounded memory. Because a compound's rows are now
     contiguous, we accumulate one compound at a time, select its top-N patent span (claimed-first,
     foundational + current-frontier -- same logic the web serves via patent_provenance._span), and write
     it to that compound's Qdrant payload as `prov` = {n, noise, patents:[...]}. Additive (set_payload
     only), resumable (checkpoint = last completed compound_id), idempotent (re-running overwrites `prov`).

  python bake_provenance.py [--snapshot DIR] [--collection patent_compounds] [--top 20]
                            [--batch 1000] [--limit N] [--dry-run] [--resume] [--resort]

Reproducible: run as `bioyoda.sh atlas bake`. Small-data test: tests/test_atlas_bake.py -> throwaway collection.
No GPU -- CPU + I/O. Needs ~16 GB RAM (patent metadata) + sort scratch on disk + payload disk (top-20 ~87 GB).
"""
import argparse, os, sys, time
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


def build_prov(links, pm, max_per, n=None):
    """links: (capped) sample of [(patent_id, field_id)] for one compound; n: true link count
    (defaults to len(links)) -> {n, noise, patents:[top-N span]} (web-identical for n below the cap)."""
    if n is None:
        n = len(links)
    # Sort only the patent ids by date (cheap), pick the span, then build full records for the <=max_per
    # patents we actually show. Stable sort on pm[p][1] (the date) == the original dict sort, so output is
    # identical -- but a fragment with 300k links costs two id passes, not 300k dict builds.
    claimed = sorted((pid for pid, fid in links if fid == 2 and pid in pm), key=lambda p: pm[p][1])
    disclosed = sorted((pid for pid, fid in links if fid != 2 and pid in pm), key=lambda p: pm[p][1])
    if len(claimed) >= max_per:
        chosen = [(p, True) for p in _span(claimed, max_per)]
    else:
        chosen = [(p, True) for p in claimed] + [(p, False) for p in _span(disclosed, max_per - len(claimed))]
    pats = []
    for pid, claimed_flag in chosen:
        num, dat, cty, asg, ttl = pm[pid]
        pats.append({"number": num, "date": dat, "country": cty, "assignee": asg, "title": ttl, "claimed": claimed_flag})
    pats.sort(key=lambda x: x["date"], reverse=True)       # newest first,
    pats.sort(key=lambda x: not x["claimed"])              # claimed group on top (stable)
    return {"n": n, "noise": n > NOISE_CAP, "patents": pats}


def sort_map(map_path, sorted_path, tmp_dir, mem_limit, threads, force=False):
    """Sort the map by compound_id once (DuckDB, out-of-core) so a compound's rows are contiguous.
    Cached: skipped when sorted_path exists and is newer than map_path, unless force."""
    if (not force and os.path.exists(sorted_path)
            and os.path.getmtime(sorted_path) >= os.path.getmtime(map_path)):
        print(f"sorted map cached: {sorted_path}", flush=True)
        return
    import duckdb
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_out = sorted_path + ".tmp"
    print(f"sorting map by compound_id (DuckDB, mem={mem_limit}, threads={threads}) -> {sorted_path}", flush=True)
    t0 = time.time()
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{mem_limit}'")
    con.execute(f"PRAGMA threads={threads}")
    con.execute(f"PRAGMA temp_directory='{tmp_dir}'")
    con.execute(f"""
        COPY (SELECT compound_id, patent_id, field_id FROM read_parquet('{map_path}')
              ORDER BY compound_id)
        TO '{tmp_out}' (FORMAT parquet, ROW_GROUP_SIZE 500000)
    """)
    con.close()
    os.replace(tmp_out, sorted_path)
    print(f"  sorted in {time.time() - t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="/data/bioyoda/raw_data/patents/surechembl/2025-12-15")
    ap.add_argument("--collection", default="patent_compounds")
    ap.add_argument("--qdrant", default="http://localhost:6333")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--batch", type=int, default=1000)      # compounds per set_payload batch (and checkpoint)
    ap.add_argument("--limit", type=int, default=0)         # 0 = all (else first N compounds, for tests)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--resort", action="store_true")        # force rebuild of the sorted map
    ap.add_argument("--ckpt", default="/data/bioyoda/work/bake_provenance.ckpt")
    ap.add_argument("--sorted", dest="sorted_path", default="/data/bioyoda/work/patent_compound_map.sorted.parquet")
    ap.add_argument("--duck-tmp", default="/data/bioyoda/work/duckdb_tmp")
    ap.add_argument("--mem-limit", default="20GB")
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    MAP = f"{a.snapshot}/patent_compound_map.parquet"

    # stage 1: sort once (cached)
    sort_map(MAP, a.sorted_path, a.duck_tmp, a.mem_limit, a.threads, force=a.resort)

    # resume point: last fully-baked compound_id (we skip cid <= start_after)
    start_after = -1
    if a.resume and os.path.exists(a.ckpt):
        start_after = int(open(a.ckpt).read().strip())
        print(f"resuming after compound_id {start_after:,}", flush=True)

    print("loading patent metadata…", flush=True)
    pm = load_patent_meta(f"{a.snapshot}/patents.parquet")
    print(f"  {len(pm):,} patents", flush=True)

    qc = models = None
    if not a.dry_run:
        from qdrant_client import QdrantClient, models
        qc = QdrantClient(url=a.qdrant, timeout=600)

    def write_ckpt(cid):
        if not a.dry_run:
            with open(a.ckpt, "w") as f:
                f.write(str(cid))

    # stage 2: stream the sorted map; a compound's rows are contiguous, so flush on id change.
    # cap per-compound accumulation: a few generic fragments appear in millions of patents -- holding
    # all their links would OOM. 300k covers every real drug (imatinib ~122k) exactly; beyond it we keep
    # counting the true n but stop storing links (those compounds are noise, n >> NOISE_CAP, anyway).
    LINK_CAP = 300_000
    pf = pq.ParquetFile(a.sorted_path)
    cid_col = pf.schema_arrow.names.index("compound_id")
    nrg = pf.metadata.num_row_groups
    # resume efficiently: the map is sorted, so skip whole row groups already fully baked
    # instead of rescanning the 1.5B rows from the start.
    start_rg = 0
    if start_after >= 0:
        start_rg = nrg
        for rg in range(nrg):
            st = pf.metadata.row_group(rg).column(cid_col).statistics
            if st is not None and st.max is not None and st.max > start_after:
                start_rg = rg
                break
        print(f"resume: start at row group {start_rg:,}/{nrg:,}", flush=True)

    cur_cid, cur_links, cur_n = None, [], 0
    ops, done, t0 = [], 0, time.time()

    def commit(ops_to_write):
        # tolerate a transient Qdrant error (e.g. a WAL/disk spike) with a short backoff
        for attempt in range(4):
            try:
                qc.batch_update_points(collection_name=a.collection, update_operations=ops_to_write, wait=False)
                return
            except Exception as e:
                if attempt == 3:
                    raise
                print(f"  write retry {attempt + 1}/3 after: {str(e)[:90]}", flush=True)
                time.sleep(15)

    def flush(cid, links, n):
        nonlocal done, ops
        prov = build_prov(links, pm, a.top, n=n)
        done += 1
        if a.dry_run:
            return
        ops.append(models.SetPayloadOperation(set_payload=models.SetPayload(payload={"prov": prov}, points=[cid])))
        if len(ops) >= a.batch:
            commit(ops)
            ops = []
            write_ckpt(cid)

    stop = False
    for rg in range(start_rg, nrg):
        t = pf.read_row_group(rg, columns=["compound_id", "patent_id", "field_id"])
        cids = t.column(0).to_pylist()
        pids = t.column(1).to_pylist()
        fids = t.column(2).to_pylist()
        for i in range(len(cids)):
            cid = cids[i]
            if cid <= start_after:
                continue
            if cid != cur_cid:
                if cur_cid is not None:
                    flush(cur_cid, cur_links, cur_n)
                    if a.limit and done >= a.limit:
                        stop = True; break
                cur_cid, cur_links, cur_n = cid, [], 0
            cur_n += 1
            if cur_n <= LINK_CAP:
                cur_links.append((pids[i], fids[i]))
        if stop:
            break
        loc = f"{cur_cid:,}" if cur_cid is not None else "—"
        print(f"  …{done:,} compounds baked ({done / max(time.time() - t0, 1):.0f}/s, at cid {loc})", flush=True)

    if not stop and cur_cid is not None:          # final compound
        flush(cur_cid, cur_links, cur_n)
    if ops and not a.dry_run:                      # final partial batch
        commit(ops)
        if cur_cid is not None:
            write_ckpt(cur_cid)
    print(f"done: baked {done:,} compounds in {time.time() - t0:.0f}s "
          f"({'DRY RUN' if a.dry_run else 'written to ' + a.collection})", flush=True)


if __name__ == "__main__":
    main()

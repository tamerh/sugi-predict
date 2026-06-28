#!/usr/bin/env python3
"""Prepare MedCPT input shards for the patents_text re-embed (#6 MedCPT + #7 June-2026 refresh).

Streams the June-2026 SureChEMBL patents, overlays existing USPTO full-text (historical + the 2026 gap),
applies the SAME text construction + min_text_length filter as process_patents.py, and writes JSONL shards
(patent_id + combined searchable text + payload) ready for modules/text/embed_text_medcpt_gpu.py on GPU.

Title-only text is the title DOUBLED (process_patents weighting); full-text adds abstract/claims/description.
Kept iff the combined text is >= min-text-length (50). point ids are computed at insert time from patent_id
(insert_from_faiss.get_point_id_from_metadata), so we only carry patent_id. Bounded memory: the 44.7M
patents stream; only the ~0.7M-entry full-text dict is held in RAM.

  python prepare_medcpt_shards.py \
    --patents raw_data/patents/surechembl/2026-06-01/patents.parquet \
    --uspto   raw_data/patents/historical_uspto/uspto_historical.parquet \
              work/data/processed/patents/uspto_gap_enriched.parquet \
    --out-dir work/data/medcpt_input/patents --shard-size 50000
"""
import argparse, json, os, re
import pyarrow.parquet as pq

_URL = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")
def clean_text(t):
    if t is None:
        return ""
    t = str(t)
    t = re.sub(r"\s+", " ", t.strip())
    t = re.sub(r"\r\n|\r|\n", " ", t)
    t = re.sub(r"\t+", " ", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = _URL.sub("", t)
    return t.strip()


def load_fulltext(paths):
    """patent_number -> (abstract, claims, description); later paths win (gap over historical)."""
    ft = {}
    for p in paths:
        t = pq.read_table(p)
        cols = set(t.column_names)
        pn = t.column("patent_number").to_pylist()
        ab = t.column("abstract").to_pylist() if "abstract" in cols else [None] * len(pn)
        cl = t.column("claims").to_pylist() if "claims" in cols else [None] * len(pn)
        de = t.column("description").to_pylist() if "description" in cols else [None] * len(pn)
        for i, k in enumerate(pn):
            if k:
                ft[k] = (ab[i], cl[i], de[i])
        print(f"  + {len(pn):,} from {os.path.basename(p)} (running distinct {len(ft):,})", flush=True)
    return ft


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patents", required=True)
    ap.add_argument("--uspto", nargs="*", default=[])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--shard-size", type=int, default=50000)
    ap.add_argument("--min-text-length", type=int, default=50)
    ap.add_argument("--limit", type=int, default=0)          # 0 = all (else stop after N rows scanned, for tests)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    print("loading USPTO full-text…", flush=True)
    ft = load_fulltext(a.uspto)
    print(f"  full-text patents: {len(ft):,}", flush=True)

    pf = pq.ParquetFile(a.patents)
    total = kept = ftkept = shard_i = 0
    buf = []

    def flush():
        nonlocal shard_i, buf
        if not buf:
            return
        with open(os.path.join(a.out_dir, f"patents_{shard_i:04d}.jsonl"), "w") as f:
            for r in buf:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        shard_i += 1
        buf = []

    cols = ["patent_number", "title", "family_id", "ipc", "asignee", "publication_date"]
    for batch in pf.iter_batches(columns=cols, batch_size=100000):
        d = batch.to_pydict()
        for i in range(len(d["patent_number"])):
            total += 1
            pid = d["patent_number"][i]
            if not pid:
                continue
            title = clean_text(d["title"][i])
            parts = [title, title] if title else []
            f = ft.get(pid)
            if f is not None:
                ab, cl, de = f
                for x in (ab, cl, de):
                    if x:
                        parts.append(clean_text(x))
            text = " ".join(parts)
            if not text or len(text) < a.min_text_length:
                continue
            kept += 1
            ftkept += f is not None
            buf.append({
                "patent_id": pid,
                "text": text,
                "title": title,
                "has_full_text": f is not None,
                "text_source": "surechembl+uspto" if f is not None else "surechembl_only",
                "family_id": d["family_id"][i],
                "pub_date": str(d["publication_date"][i] or ""),
                "ipc_codes": d["ipc"][i] or [],
                "assignees": d["asignee"][i] or [],
                "source": "patents",
            })
            if len(buf) >= a.shard_size:
                flush()
        print(f"  scanned {total:,} | kept {kept:,} (full-text {ftkept:,}) | shards {shard_i}", flush=True)
        if a.limit and total >= a.limit:
            break
    flush()
    print(f"done: kept {kept:,} of {total:,} ({ftkept:,} full-text) -> {shard_i} shards in {a.out_dir}", flush=True)


if __name__ == "__main__":
    main()

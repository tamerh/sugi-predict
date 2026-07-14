#!/usr/bin/env python3
"""
SaProt Stage 1 -- fetch AlphaFold DB structures.

Reads isoform_list.csv (columns: id,txt), downloads the AlphaFold mmCIF for each
UniProt accession (canonical + isoform) into --out-dir/<acc>.cif, and writes a
coverage manifest (_coverage.tsv). Isoforms without an AFDB model are recorded as
'missing' -- they fall back to AlphaMissense downstream. Resumable: existing
non-empty files are skipped.

  python fetch_afdb_structures.py \
    --list /data/biobtree/raw_data/esm1b/isoform_list.csv \
    --out-dir /data/bioyoda/raw_data/saprot/structures \
    --workers 24 [--limit N]
"""
import os, sys, csv, argparse, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request, urllib.error

URL = "https://alphafold.ebi.ac.uk/files/AF-{acc}-F1-model_v{ver}.cif"
VERSIONS = (6, 5, 4)  # newest first; most of AFDB-2025 is v6


def read_accessions(path):
    out = []
    with open(path, newline="") as f:
        r = csv.reader(f)
        next(r, None)  # header: id,txt
        for row in r:
            if row and row[0].strip():
                out.append(row[0].strip())
    return out


def fetch_one(acc, out_dir):
    dst = os.path.join(out_dir, acc + ".cif")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return acc, "exists"
    for ver in VERSIONS:
        try:
            req = urllib.request.Request(URL.format(acc=acc, ver=ver),
                                         headers={"User-Agent": "bioyoda-saprot/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            tmp = dst + ".tmp"
            with open(tmp, "wb") as g:
                g.write(data)
            os.replace(tmp, dst)
            return acc, "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue  # try an older version, else fall through to 'missing'
            return acc, "http%d" % e.code
        except Exception as e:
            return acc, "err:" + type(e).__name__
    return acc, "missing"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    accs = read_accessions(a.list)
    if a.limit:
        accs = accs[:a.limit]
    print("[fetch] %d accessions -> %s" % (len(accs), a.out_dir), flush=True)

    man = open(os.path.join(a.out_dir, "_coverage.tsv"), "w")
    counts, done, t0 = {}, 0, time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_one, acc, a.out_dir): acc for acc in accs}
        for fut in as_completed(futs):
            acc, status = fut.result()
            key = status if status in ("exists", "ok", "missing") else "error"
            counts[key] = counts.get(key, 0) + 1
            man.write("%s\t%s\n" % (acc, status)); man.flush()
            done += 1
            if done % 500 == 0:
                print("[fetch] %d/%d (%.0f/s) %s"
                      % (done, len(accs), done / (time.time() - t0), counts), flush=True)
    man.close()
    dt = time.time() - t0
    cov = counts.get("ok", 0) + counts.get("exists", 0)
    print("[fetch] DONE %d in %.0fs %s" % (done, dt, counts), flush=True)
    print("[fetch] structures present: %d/%d (%.1f%%); missing: %d; errors: %d"
          % (cov, len(accs), 100 * cov / max(1, len(accs)),
             counts.get("missing", 0), counts.get("error", 0)), flush=True)


if __name__ == "__main__":
    sys.exit(main())

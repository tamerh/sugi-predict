#!/usr/bin/env python3
"""
SaProt Stage 2 -- convert AFDB structures to SaProt AA+3Di combined sequences.

Reads --struct-dir/*.cif, runs Foldseek (via SaProt's get_struc_seq) with pLDDT
masking, and writes one JSONL line per protein: {"acc", "aa", "combined"}. The
combined AA+3Di string is what SaProt tokenizes in Stage 3 (GPU scoring).
Resumable: skips accessions already present in --out.

Run with the bioyoda conda python (needs numpy + biopython):
  /data/miniconda3/envs/bioyoda/bin/python batch_3di.py \
    --struct-dir /data/bioyoda/raw_data/saprot/structures \
    --foldseek   /data/bioyoda/raw_data/saprot/tools/foldseek/bin/foldseek \
    --saprot     /data/bioyoda/raw_data/saprot/tools/SaProt \
    --out        /data/bioyoda/out_prod/work/saprot/combined_seqs.jsonl \
    --workers 16
"""
import os, sys, json, glob, argparse, time
from concurrent.futures import ProcessPoolExecutor, as_completed


def convert_one(args):
    cif, foldseek, saprot_dir = args
    acc = os.path.splitext(os.path.basename(cif))[0]
    try:
        if saprot_dir not in sys.path:
            sys.path.insert(0, saprot_dir)
        from utils.foldseek_util import get_struc_seq
        aa, fs, comb = get_struc_seq(foldseek, cif, ["A"], plddt_mask=True)["A"]
        return acc, aa, comb, None
    except Exception as e:
        return acc, None, None, "%s: %s" % (type(e).__name__, e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--struct-dir", required=True)
    ap.add_argument("--foldseek", required=True)
    ap.add_argument("--saprot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    cifs = sorted(glob.glob(os.path.join(a.struct_dir, "*.cif")))
    if a.limit:
        cifs = cifs[:a.limit]

    done = set()
    if os.path.exists(a.out):
        with open(a.out) as f:
            for line in f:
                try:
                    done.add(json.loads(line)["acc"])
                except Exception:
                    pass
    cifs = [c for c in cifs if os.path.splitext(os.path.basename(c))[0] not in done]
    print("[3di] %d to convert (%d already done) -> %s" % (len(cifs), len(done), a.out), flush=True)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    ok, err, errs_sample, t0 = 0, 0, [], time.time()
    tasks = [(c, a.foldseek, a.saprot) for c in cifs]
    with open(a.out, "a") as out, ProcessPoolExecutor(max_workers=a.workers) as ex:
        for fut in as_completed([ex.submit(convert_one, t) for t in tasks]):
            acc, aa, comb, e = fut.result()
            if e is None:
                out.write(json.dumps({"acc": acc, "aa": aa, "combined": comb}) + "\n")
                out.flush()
                ok += 1
            else:
                err += 1
                if len(errs_sample) < 5:
                    errs_sample.append("%s: %s" % (acc, e))
            n = ok + err
            if n % 500 == 0:
                print("[3di] %d/%d (%.0f/s) ok=%d err=%d" % (n, len(cifs), n / (time.time() - t0), ok, err), flush=True)
    print("[3di] DONE ok=%d err=%d in %.0fs" % (ok, err, time.time() - t0), flush=True)
    for e in errs_sample:
        print("  err: " + e, flush=True)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Split a SureChEMBL compounds.parquet into N fixed chunks (id + smiles + ...) for the atlas k-NN + ingest.

Reproducible chunking step so the patent_atlas can be rebuilt on any snapshot from the orchestrator:
`bioyoda.sh build compounds chunk`. Streams the parquet (bounded memory), writes compounds_chunk_NNNN.parquet.

  python chunk_compounds.py --input <compounds.parquet> --out-dir <dir> --chunks 62
"""
import argparse, math, os, glob
import pyarrow as pa
import pyarrow.parquet as pq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--chunks", type=int, default=62)
    ap.add_argument("--delta", action="store_true",
                    help="incremental: write only compounds NOT already in --nbrs (the proven June pattern)")
    ap.add_argument("--nbrs", default="",
                    help="atlas_nbrs dir to diff against in --delta mode (its pids = already-computed compounds)")
    ap.add_argument("--chunk-size", type=int, default=500_000, help="rows/chunk in --delta mode")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(a.out_dir, "compounds_chunk_*.parquet")):   # clean stale chunks
        os.remove(old)

    done = set()
    if a.delta:                                  # load the pids already in atlas_nbrs -> skip them
        import numpy as np
        for f in sorted(glob.glob(os.path.join(a.nbrs, "nbrs_*.parquet"))):
            done.update(pq.read_table(f, columns=["pid"]).column("pid").to_numpy())
        print(f"  --delta: {len(done):,} compounds already computed; selecting only NEW ones", flush=True)

    pf = pq.ParquetFile(a.input)
    total = pf.metadata.num_rows
    per = a.chunk_size if a.delta else math.ceil(total / a.chunks)
    print(f"{total:,} input compounds -> {'delta' if a.delta else str(a.chunks)+' fixed'} chunks (~{per:,} each)", flush=True)

    ci, rows, writer, kept = 1, 0, None, 0
    def _open(i):
        return pq.ParquetWriter(os.path.join(a.out_dir, f"compounds_chunk_{i:04d}.parquet"), pf.schema_arrow)
    writer = _open(ci)
    for batch in pf.iter_batches(batch_size=100_000):
        t = pa.Table.from_batches([batch])
        if a.delta and done:                     # keep only ids not already computed
            mask = [i not in done for i in t.column("id").to_pylist()]
            t = t.filter(pa.array(mask))
            if t.num_rows == 0:
                continue
        kept += t.num_rows
        off = 0
        while off < t.num_rows:
            take = min(per - rows, t.num_rows - off)
            writer.write_table(t.slice(off, take))
            rows += take; off += take
            if rows >= per and (a.delta or ci < a.chunks):   # delta: fixed-size, no chunk cap
                writer.close(); ci += 1; rows = 0; writer = _open(ci)
    writer.close()
    print(f"done: {ci} chunks ({kept:,} compounds{' [delta]' if a.delta else ''}) -> {a.out_dir}", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Split a SureChEMBL compounds.parquet into N fixed chunks (id + smiles + ...) for the atlas k-NN + ingest.

Reproducible chunking step so the patent_atlas can be rebuilt on any snapshot from the orchestrator:
`bioyoda.sh atlas compounds chunk`. Streams the parquet (bounded memory), writes compounds_chunk_NNNN.parquet.

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
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(a.out_dir, "compounds_chunk_*.parquet")):   # clean stale chunks
        os.remove(old)

    pf = pq.ParquetFile(a.input)
    total = pf.metadata.num_rows
    per = math.ceil(total / a.chunks)
    print(f"{total:,} compounds -> {a.chunks} chunks (~{per:,} each) in {a.out_dir}", flush=True)

    ci, rows, writer = 1, 0, None
    def _open(i):
        return pq.ParquetWriter(os.path.join(a.out_dir, f"compounds_chunk_{i:04d}.parquet"), pf.schema_arrow)
    writer = _open(ci)
    for batch in pf.iter_batches(batch_size=100_000):
        t = pa.Table.from_batches([batch])
        off = 0
        while off < t.num_rows:
            take = min(per - rows, t.num_rows - off)
            writer.write_table(t.slice(off, take))
            rows += take; off += take
            if rows >= per and ci < a.chunks:
                writer.close(); ci += 1; rows = 0; writer = _open(ci)
    writer.close()
    print(f"done: {ci} chunks written", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Prepare the ESM-2 embed INPUT: split a source UniProt FASTA into chunk_*.fasta shards.

Two modes (mirrors the pubmed/trials chunk step — delta by default):

  --full   : split the WHOLE source fasta (e.g. uniprot_swissprot.fasta) into N chunks.
             The one-time bootstrap / full re-embed of the collection.

  default  : DELTA. Keep only proteins whose UniProt accession is NOT already embedded
             (read from --existing-proteins, the gzipped accession set built by
             build_existing_proteins.py from the live `esm2` collection / prior sidecars).
             Writes the delta to <out-dir>/new_proteins.fasta first (the June 2026
             new_proteins.fasta flow), then splits it into chunk_*.fasta shards sized so
             each holds ~--per-chunk sequences. Embeds ONLY new proteins -> insert keyed
             by protein_id is idempotent & additive (never recomputes the ~574K already in).

FASTA header accession is parsed like h5_to_faiss.py: `sp|Q6GZX4|001R_FRG3G` -> Q6GZX4.

Usage:
  # delta (default): only proteins not in the existing set
  prepare_delta.py --source raw_data/esm2/uniprot_swissprot.fasta \
      --out-dir raw_data/esm2/chunks --existing-proteins work/state/esm2/existing_proteins.txt.gz \
      --new-fasta raw_data/esm2/new_proteins.fasta --per-chunk 5000
  # full: split the whole source into N chunks
  prepare_delta.py --source raw_data/esm2/uniprot_swissprot.fasta \
      --out-dir raw_data/esm2/chunks --full --num-chunks 62
"""
import argparse
import gzip
import os
import sys
from datetime import datetime


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def accession_of(header):
    # header is the FASTA '>' line WITHOUT the leading '>'. e.g. "sp|Q6GZX4|001R_FRG3G ..."
    first = header.split()[0] if header else header
    parts = first.split('|')
    return parts[1] if len(parts) >= 2 else first


def iter_fasta(path):
    """Yield (header_line_without_gt, [sequence_lines]) records."""
    opener = gzip.open if path.endswith('.gz') else open
    header, seq = None, []
    with opener(path, 'rt') as f:
        for line in f:
            if line.startswith('>'):
                if header is not None:
                    yield header, seq
                header, seq = line[1:].rstrip('\n'), []
            else:
                seq.append(line.rstrip('\n'))
        if header is not None:
            yield header, seq


def load_existing(path):
    if not path or not os.path.exists(path):
        log(f"existing-proteins set not found ({path}) -> treating ALL source proteins as new")
        return set()
    opener = gzip.open if path.endswith('.gz') else open
    acc = set()
    with opener(path, 'rt') as f:
        for line in f:
            a = line.strip()
            if a:
                acc.add(a)
    log(f"loaded {len(acc):,} already-embedded accessions from {path}")
    return acc


def write_chunks(records, out_dir, per_chunk):
    """records: iterable of (header, seq_lines). Write chunk_001.fasta, chunk_002.fasta ..."""
    os.makedirs(out_dir, exist_ok=True)
    # clear stale chunks so a smaller delta can't leave a prior run's chunks behind
    for old in os.listdir(out_dir):
        if old.startswith('chunk_') and old.endswith('.fasta'):
            os.remove(os.path.join(out_dir, old))
    n_chunk, n_seq, handle = 0, 0, None
    written = 0
    for header, seq in records:
        if handle is None or n_seq >= per_chunk:
            if handle is not None:
                handle.close()
            n_chunk += 1
            n_seq = 0
            handle = open(os.path.join(out_dir, f"chunk_{n_chunk:03d}.fasta"), 'w')
        handle.write(f">{header}\n")
        handle.write('\n'.join(seq) + '\n')
        n_seq += 1
        written += 1
    if handle is not None:
        handle.close()
    log(f"wrote {written:,} sequences into {n_chunk} chunk(s) under {out_dir}")
    return written, n_chunk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True, help='Source UniProt FASTA (swissprot)')
    ap.add_argument('--out-dir', required=True, help='Output dir for chunk_*.fasta')
    ap.add_argument('--full', action='store_true', help='Split the whole source (no delta filter)')
    ap.add_argument('--existing-proteins', help='Gzipped accession set already embedded (delta filter)')
    ap.add_argument('--new-fasta', help='Where to also write the delta fasta (default: <out-dir>/new_proteins.fasta)')
    ap.add_argument('--per-chunk', type=int, default=5000, help='Sequences per chunk (delta mode; default 5000)')
    ap.add_argument('--num-chunks', type=int, default=62, help='Number of chunks (full mode; default 62)')
    args = ap.parse_args()

    if not os.path.exists(args.source):
        log(f"ERROR: source not found: {args.source}")
        return 1

    if args.full:
        log(f"FULL: splitting {args.source} into {args.num_chunks} chunks")
        total = sum(1 for _ in iter_fasta(args.source))
        per = max(1, -(-total // args.num_chunks))  # ceil
        log(f"{total:,} proteins -> ~{per:,} per chunk")
        write_chunks(iter_fasta(args.source), args.out_dir, per)
        return 0

    # DELTA
    existing = load_existing(args.existing_proteins)
    new_fasta = args.new_fasta or os.path.join(args.out_dir, 'new_proteins.fasta')
    os.makedirs(os.path.dirname(os.path.abspath(new_fasta)), exist_ok=True)

    seen = 0
    new = 0
    new_records = []
    with open(new_fasta, 'w') as out:
        for header, seq in iter_fasta(args.source):
            seen += 1
            acc = accession_of(header)
            if acc in existing:
                continue
            out.write(f">{header}\n")
            out.write('\n'.join(seq) + '\n')
            new_records.append((header, seq))
            new += 1
    log(f"scanned {seen:,} source proteins -> {new:,} NEW (delta) -> {new_fasta}")
    if new == 0:
        log("no new proteins; nothing to embed. (delta is empty — collection is up to date)")
        # still clear stale chunks so a downstream embed/insert finds nothing to do
        write_chunks(iter(()), args.out_dir, args.per_chunk)
        return 0
    write_chunks(iter(new_records), args.out_dir, args.per_chunk)
    return 0


if __name__ == '__main__':
    sys.exit(main())

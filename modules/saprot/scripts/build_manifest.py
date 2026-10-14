#!/usr/bin/env python3
"""SaProt Stage 4a -- build the per-accession sequence manifest.

Emits, for every scored protein, the identity of the exact sequence SaProt was
numbered against. These columns are release-independent (facts about what was
scored) and let a consumer validate an accession+position join instead of reading
a key-miss as "no prediction" or a coincidental same-letter hit as a result.

  python build_manifest.py \
    --combined /path/to/combined_seqs.jsonl \
    --out      /path/to/saprot_sequence_manifest.tsv

Input is the Stage 2 JSONL (one {"acc","aa","combined"} per line). Output columns:
  uniprot_acc  length  crc64  md5
where crc64 is the UniProt/SWISS-PROT (Jones) variant, verified against the SIB
test vector crc64("IHATEMATH") == E3DCADD69B01ADD1, so it joins to UniProt's own
CRC64 field. Resolve isoform ids against a specific UniProt release with the
companion resolve_isoform.py.
"""
import os, sys, json, hashlib, argparse

# UniProt / SWISS-PROT CRC64 (Jones variant).
_POLY = 0xd800000000000000
_T = []
for _i in range(256):
    _p = _i
    for _ in range(8):
        _p = (_p >> 1) ^ _POLY if _p & 1 else _p >> 1
    _T.append(_p)


def crc64(s):
    crc = 0
    for ch in s.encode():
        crc = (crc >> 8) ^ _T[(crc ^ ch) & 0xFF]
    return "%016X" % crc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--combined", required=True, help="Stage 2 combined_seqs.jsonl")
    ap.add_argument("--out", required=True, help="output manifest TSV")
    a = ap.parse_args()

    out_dir = os.path.dirname(a.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    n = 0
    with open(a.combined) as f, open(a.out, "w") as g:
        g.write("uniprot_acc\tlength\tcrc64\tmd5\n")
        for line in f:
            r = json.loads(line)
            acc, aa = r["acc"], r["aa"]
            g.write("%s\t%d\t%s\t%s\n" % (acc, len(aa), crc64(aa),
                                          hashlib.md5(aa.encode()).hexdigest()))
            n += 1
    print("[manifest] %d accessions -> %s" % (n, a.out), flush=True)


if __name__ == "__main__":
    sys.exit(main())

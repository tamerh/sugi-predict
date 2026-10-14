#!/usr/bin/env python3
"""SaProt Stage 4b -- resolve isoform ids against a UniProt release.

Adds an `isoform` column and a `verified` flag to the sequence manifest by matching
each scored sequence's CRC64 against a UniProt release's canonical + varsplic FASTA.
These two columns are release-COUPLED: re-run against the release your consumer's
accession/position source (and biobtree) is indexed on, and re-resolve on a bump.

  python resolve_isoform.py \
    --manifest  /path/to/saprot_sequence_manifest.tsv \
    --canonical /path/to/uniprot_sprot.fasta.gz \
    --varsplic  /path/to/uniprot_sprot_varsplic.fasta.gz \
    [--out /path/to/out.tsv]          # default: overwrite --manifest in place

Both FASTA are from the same UniProt release, e.g. previous_releases/release-2026_01
(canonical = base-accession sequence; varsplic = isoform-id ACC-N sequence).

Output columns: uniprot_acc  length  crc64  md5  isoform  verified
  isoform : suffixed key -> the isoform id itself; bare key equal to the canonical
            -> "canonical"; otherwise -> "unresolved".
  verified: yes   = scored sequence is identical to the release's sequence for that
                    isoform (join valid, use the score);
            drift = id exists in the release but the sequence differs (abstain);
            absent = id/accession not in the release's SwissProt (abstain).
"""
import sys, gzip, argparse
from collections import Counter

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


def load_fasta_crc(path):
    """Return {accession-or-isoform-id: crc64}. Key is the second |-field of the
    FASTA header, i.e. ACC for canonical and ACC-N for varsplic entries."""
    d = {}
    key = None
    buf = []
    opn = gzip.open if path.endswith(".gz") else open
    with opn(path, "rt") as f:
        for line in f:
            if line.startswith(">"):
                if key is not None:
                    d[key] = crc64("".join(buf))
                key = line[1:].split("|", 2)[1]
                buf = []
            else:
                buf.append(line.strip())
        if key is not None:
            d[key] = crc64("".join(buf))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="manifest TSV from build_manifest.py")
    ap.add_argument("--canonical", required=True, help="uniprot_sprot.fasta(.gz) for the release")
    ap.add_argument("--varsplic", required=True, help="uniprot_sprot_varsplic.fasta(.gz) for the release")
    ap.add_argument("--out", default=None, help="output TSV (default: overwrite --manifest)")
    ap.add_argument("--release", default=None,
                    help="UniProt release label (e.g. 2026_03); stamped as a leading "
                         "'# uniprot_release=<release>' comment, since isoform/verified are "
                         "release-coupled")
    a = ap.parse_args()
    out = a.out or a.manifest

    print("[resolve] loading canonical ...", flush=True)
    canon = load_fasta_crc(a.canonical)
    print("[resolve]   canonical entries: %d" % len(canon), flush=True)
    print("[resolve] loading varsplic ...", flush=True)
    varsp = load_fasta_crc(a.varsplic)
    print("[resolve]   isoform entries:   %d" % len(varsp), flush=True)

    rows = []
    with open(a.manifest) as f:
        for line in f:
            if line.startswith("#"):          # tolerate a stamped comment line
                continue
            if line.startswith("uniprot_acc\t"):  # header
                continue
            acc, length, c, m = line.rstrip("\n").split("\t")[:4]
            base = acc.split("-", 1)[0]
            if "-" in acc:                              # suffixed key: isoform id is the key
                ref = varsp.get(acc)
                if ref is None:                         # suffix may be the displayed/canonical isoform
                    ref = canon.get(base)
                isoform = acc
            else:                                       # bare key: scored = canonical
                ref = canon.get(base)
                isoform = "canonical" if ref == c else "unresolved"
            verified = "yes" if ref == c else ("drift" if ref is not None else "absent")
            rows.append((acc, length, c, m, isoform, verified))

    with open(out, "w") as g:
        if a.release:
            g.write("# uniprot_release=%s\n" % a.release)
        g.write("uniprot_acc\tlength\tcrc64\tmd5\tisoform\tverified\n")
        for r in rows:
            g.write("\t".join(r) + "\n")

    sv = Counter(r[5] for r in rows)
    print("[resolve] rows=%d  verified=%d  drift=%d  absent=%d -> %s"
          % (len(rows), sv.get("yes", 0), sv.get("drift", 0), sv.get("absent", 0), out), flush=True)


if __name__ == "__main__":
    sys.exit(main())

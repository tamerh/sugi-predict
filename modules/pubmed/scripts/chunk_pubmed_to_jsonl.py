#!/usr/bin/env python3
"""Chunk downloaded PubMed XML (baseline/ + updatefiles/) into MedCPT-input JSONL shards.

The MedCPT pubmed_abstracts_medcpt collection is fed the same way clinical_trials_medcpt is: a
`chunk` step emits the JSONL shards embed_text_medcpt_gpu.py expects (one record/line with a `text`
field), then a shared GPU `embed` step (MedCPT-Article-Encoder) and an `insert` step (insert_from_faiss)
take over. This replaces the legacy modules/pubmed/Snakefile, where index.py parsed XML AND embedded with
S-BioBERT in one CPU step — wrong encoder, no JSONL intermediate, no shared GPU path.

Text extraction matches index.py EXACTLY so the MedCPT corpus is the same abstracts the S-BioBERT one was:
  text = "Title: {ArticleTitle}\nAbstract: {AbstractText}"   (PMID + non-empty abstract required)

INCREMENTAL (PMID-delta), mirroring index.py --existing-pmids and the trials chunker's tracking skip:
  * --deleted-pmids  : NCBI's deleted.pmids.sorted.gz — those PMIDs are dropped (retractions/dedup).
  * --existing-pmids : the already-embedded PMID set (work/state/pubmed/existing_pmids.txt.gz, built by
    build_existing_pmids.py). By default those PMIDs are skipped, so a routine refresh re-embeds only NEW
    abstracts (~2M new vs ~30M full). --full ignores the existing set and chunks every abstract (bootstrap
    / a model change). The `insert` step keys points by pmid, so re-running a PMID is idempotent.

Each record = {text, chunk_text (== text), pmid}. The embed step preserves all non-text keys into its
sidecar; insert_from_faiss derives the Qdrant point id directly from `pmid` (int).

  python chunk_pubmed_to_jsonl.py --raw-dir work/raw_data/pubmed \
      --out-dir work/data/medcpt_input/pubmed \
      --deleted-pmids work/raw_data/pubmed/deleted.pmids.sorted.gz \
      --existing-pmids work/state/pubmed/existing_pmids.txt.gz   # omit (or --full) for a full chunk
"""
import os, sys, gzip, json, glob, argparse
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from modules.paths import PUBMED_RAW, MEDCPT_IN_PUBMED


def load_pmid_set(path, label):
    s = set()
    if not path or not os.path.exists(path):
        print(f"  {label}: {path or '(none)'} not found -> empty set", file=sys.stderr)
        return s
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt") as f:
        for line in f:
            p = line.strip()
            if p:
                s.add(p)
    print(f"  {label}: {len(s):,} PMIDs from {path}", file=sys.stderr)
    return s


def iter_abstracts(xml_gz, deleted, existing):
    """Yield (pmid, text) for each PubmedArticle with a PMID + non-empty abstract.

    Matches index.py's parse exactly (streaming iterparse, same field selection, same skips).
    Returns counts via the StopIteration value is awkward; caller tracks via the generator.
    """
    with gzip.open(xml_gz, "rb") as f:
        context = ET.iterparse(f, events=("end",))
        for _ev, elem in context:
            if elem.tag != "PubmedArticle":
                continue
            try:
                pe = elem.find(".//PMID")
                pmid = pe.text if pe is not None else None
                if not pmid:
                    elem.clear(); continue
                if pmid in deleted:
                    elem.clear(); yield ("__deleted__", None); continue
                if pmid in existing:
                    elem.clear(); yield ("__existing__", None); continue
                te = elem.find(".//ArticleTitle")
                title = "".join(te.itertext()) if te is not None else ""
                ae = elem.find(".//AbstractText")
                abstract = "".join(ae.itertext()) if ae is not None else ""
                if abstract:
                    yield (pmid, f"Title: {title}\nAbstract: {abstract}")
            except Exception:
                pass
            finally:
                elem.clear()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=str(PUBMED_RAW),
                    help="dir with baseline/ and updatefiles/ of *.xml.gz (the download checkpoint output)")
    ap.add_argument("--out-dir", default=str(MEDCPT_IN_PUBMED))
    ap.add_argument("--deleted-pmids", default=None,
                    help="NCBI deleted.pmids.sorted.gz (default: <raw-dir>/deleted.pmids.sorted.gz if present)")
    ap.add_argument("--existing-pmids", default=None,
                    help="already-embedded PMID list (one/line, .gz ok). Skipped unless --full.")
    ap.add_argument("--full", action="store_true",
                    help="chunk ALL abstracts (ignore --existing-pmids; bootstrap / model change)")
    ap.add_argument("--shard-size", type=int, default=50000)
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(a.out_dir, "shard_*.jsonl")):   # clean stale shards (delta names must not collide)
        os.remove(old)

    deleted_path = a.deleted_pmids or os.path.join(a.raw_dir, "deleted.pmids.sorted.gz")
    deleted = load_pmid_set(deleted_path, "deleted")
    existing = set() if a.full else load_pmid_set(a.existing_pmids, "existing")

    xml_files = sorted(glob.glob(os.path.join(a.raw_dir, "baseline", "*.xml.gz"))) + \
                sorted(glob.glob(os.path.join(a.raw_dir, "updatefiles", "*.xml.gz")))
    mode = "full" if a.full else "delta"
    print(f"[{mode}] {len(xml_files)} XML file(s) under {a.raw_dir}", file=sys.stderr)

    shard, n, total_seen, kept, n_del, n_exist = 0, 0, 0, 0, 0, 0
    fh = open(os.path.join(a.out_dir, f"shard_{shard:05d}.jsonl"), "w")
    for xf in xml_files:
        for pmid, text in iter_abstracts(xf, deleted, existing):
            total_seen += 1
            if pmid == "__deleted__":
                n_del += 1; continue
            if pmid == "__existing__":
                n_exist += 1; continue
            fh.write(json.dumps({"text": text, "chunk_text": text, "pmid": pmid}, ensure_ascii=False) + "\n")
            kept += 1; n += 1
            if n % a.shard_size == 0:
                fh.close(); shard += 1
                fh = open(os.path.join(a.out_dir, f"shard_{shard:05d}.jsonl"), "w")
    fh.close()

    print(f"done [{mode}]: {kept:,} abstracts -> {shard+1} shard(s) in {a.out_dir} "
          f"(skipped {n_del:,} deleted, {n_exist:,} already-embedded)", file=sys.stderr)


if __name__ == "__main__":
    main()

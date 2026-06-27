#!/usr/bin/env python3
"""Chunk biobtree's clinical_trials trials.json into MedCPT-input JSONL shards — INCREMENTAL by default.

The MedCPT clinical_trials_medcpt collection used to be fed by exporting an intermediate S-BioBERT
`clinical_trials` Qdrant collection. That coupling is gone: we chunk straight from biobtree's source
(/data/biobtree/raw_data/clinical_trials/trials.json, ~5GB) using the same TrialTextProcessor and emit the
JSONL shards embed_text_medcpt_gpu.py expects. No S-BioBERT, no GPU here.

INCREMENTAL: by default, only trials whose content hash CHANGED (or are NEW) vs the tracking DB
(work/state/clinical_trials/trials_tracking.db) are chunked — so a routine refresh re-embeds only the delta
(e.g. ~weeks of CT.gov changes), not all ~500K trials. The insert step (insert_from_faiss --update-mode)
replaces those trials' chunks by nct_id. --full chunks everything (the bootstrap / a model change).

Each output record = {text (MedCPT-embedded), chunk_text, nct_id, chunk_type, chunk_id, global_chunk_id,
+ trial-level payload fields}. Streamed with ijson so the file never loads into RAM.

  python chunk_trials_to_jsonl.py [--full]   # default: incremental vs the tracking DB
"""
import sys, os, json, glob, argparse
sys.path.insert(0, "/data/bioyoda")
import ijson
from modules.clinical_trials.scripts.process_trials import TrialTextProcessor
from modules.clinical_trials.scripts.tracking_db import TrialsTracker, compute_trial_hash

# trial-level fields carried onto every chunk's payload (matches the live collection's payload schema)
TRIAL_FIELDS = ["brief_title", "overall_status", "phase", "study_type", "conditions", "interventions",
                "sponsors", "facilities", "study_arms", "publications", "adverse_events_summary"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials-json", default="/data/biobtree/raw_data/clinical_trials/trials.json")
    ap.add_argument("--out-dir", default="/data/bioyoda/work/data/medcpt_input/clinical_trials")
    ap.add_argument("--tracking-db", default="/data/bioyoda/work/state/clinical_trials/trials_tracking.db")
    ap.add_argument("--full", action="store_true",
                    help="chunk ALL trials (default: incremental — only new/changed vs the tracking DB)")
    ap.add_argument("--shard-size", type=int, default=50000)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(a.out_dir, "shard_*.jsonl")):   # clean stale shards
        os.remove(old)

    tracker = None if a.full else TrialsTracker(a.tracking_db)   # None => full rebuild
    chunker = TrialTextProcessor()
    shard, n, gid, total, kept, updates = 0, 0, 0, 0, 0, []
    fh = open(os.path.join(a.out_dir, f"shard_{shard:05d}.jsonl"), "w")
    with open(a.trials_json, "rb") as f:
        for trial in ijson.items(f, "trials.item"):
            total += 1
            nct = trial.get("nct_id")
            if tracker is not None:                       # incremental: skip unchanged trials
                h = compute_trial_hash(trial)
                prev = tracker.get_trial(nct) if nct else None
                if prev and prev.get("content_hash") == h:
                    continue
                updates.append({"nct_id": nct, "last_update_date": str(trial.get("last_update_date", "")),
                                "content_hash": h})
            kept += 1
            base = {k: trial.get(k) for k in TRIAL_FIELDS}
            for ch in chunker.process_trial_to_chunks(trial):
                rec = {**base, **ch}
                rec["chunk_text"] = ch.get("text", "")
                rec["global_chunk_id"] = gid
                fh.write(json.dumps(rec) + "\n")
                gid += 1; n += 1
                if n % a.shard_size == 0:
                    fh.close(); shard += 1
                    fh = open(os.path.join(a.out_dir, f"shard_{shard:05d}.jsonl"), "w")
            if total % 100000 == 0:
                print(f"  scanned {total:,} trials, {kept:,} to (re)embed -> {n:,} chunks", flush=True)
    fh.close()
    if tracker is not None and updates:                   # record the new hashes for next time
        tracker.add_or_update_batch(updates)
    mode = "FULL" if a.full else "delta"
    print(f"done [{mode}]: {kept:,}/{total:,} trials (re)chunked -> {n:,} chunks in {shard+1} shards -> {a.out_dir}",
          flush=True)
    if n == 0:
        print("  (no changed trials — nothing to embed)", flush=True)


if __name__ == "__main__":
    main()

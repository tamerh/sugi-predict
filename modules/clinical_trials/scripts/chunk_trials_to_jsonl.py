#!/usr/bin/env python3
"""Chunk biobtree's clinical_trials trials.json DIRECTLY into MedCPT-input JSONL shards.

The MedCPT clinical_trials_medcpt collection used to be fed by exporting an intermediate S-BioBERT
`clinical_trials` Qdrant collection (export_text_for_embed.py). That coupling is gone here: we chunk
straight from biobtree's source (/data/biobtree/raw_data/clinical_trials/trials.json, ~4.6GB) using the
same TrialTextProcessor, and emit the JSONL shards embed_text_medcpt_gpu.py expects. No S-BioBERT, no GPU.

Each output record = {text (the field MedCPT embeds), chunk_text (full text for payload), nct_id,
chunk_type, chunk_id, global_chunk_id, + the trial-level payload fields}. Streamed with ijson so the
4.6GB file never loads into RAM.

  python chunk_trials_to_jsonl.py [--trials-json ...] [--out-dir work/data/medcpt_input/clinical_trials]
"""
import sys, os, json, glob, argparse
sys.path.insert(0, "/data/bioyoda")
import ijson
from modules.clinical_trials.scripts.process_trials import TrialTextProcessor

# trial-level fields carried onto every chunk's payload (matches the live collection's payload schema)
TRIAL_FIELDS = ["brief_title", "overall_status", "phase", "study_type", "conditions", "interventions",
                "sponsors", "facilities", "study_arms", "publications", "adverse_events_summary"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials-json", default="/data/biobtree/raw_data/clinical_trials/trials.json")
    ap.add_argument("--out-dir", default="/data/bioyoda/work/data/medcpt_input/clinical_trials")
    ap.add_argument("--shard-size", type=int, default=50000)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(a.out_dir, "shard_*.jsonl")):   # clean stale shards
        os.remove(old)

    chunker = TrialTextProcessor()
    shard, n, gid, trials = 0, 0, 0, 0
    fh = open(os.path.join(a.out_dir, f"shard_{shard:05d}.jsonl"), "w")
    with open(a.trials_json, "rb") as f:
        for trial in ijson.items(f, "trials.item"):
            trials += 1
            base = {k: trial.get(k) for k in TRIAL_FIELDS}
            for ch in chunker.process_trial_to_chunks(trial):
                rec = {**base, **ch}                 # ch (nct_id/chunk_type/chunk_id/text/...) wins over base
                rec["chunk_text"] = ch.get("text", "")
                rec["global_chunk_id"] = gid
                fh.write(json.dumps(rec) + "\n")
                gid += 1; n += 1
                if n % a.shard_size == 0:
                    fh.close(); shard += 1
                    fh = open(os.path.join(a.out_dir, f"shard_{shard:05d}.jsonl"), "w")
            if trials % 100000 == 0:
                print(f"  {trials:,} trials -> {n:,} chunks", flush=True)
    fh.close()
    print(f"done: {trials:,} trials -> {n:,} chunks in {shard+1} shards -> {a.out_dir}", flush=True)


if __name__ == "__main__":
    main()

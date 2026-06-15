#!/usr/bin/env python3
"""#G1 — enrich CT chunk sidecars with `disease_curie` (grounding DELEGATED to BioBTree)
BEFORE insert, so the new multi-chunk clinical_trials collection ships grounded from the
start. More efficient than post-insert payload writes: ground each trial's conditions once
(cached), every chunk of that trial inherits it; insert_from_faiss carries the field into
the payload.

Usage: python scripts/grounding/enrich_ct_sidecars.py work/data/processed/clinical_trials/full
"""
import sys, os, glob, json, time
sys.path.insert(0, '/data/bioyoda')
from scripts.integrations import biobtree_client as bb

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def main():
    d = sys.argv[1] if len(sys.argv) > 1 else 'work/data/processed/clinical_trials/full'
    sidecars = sorted(glob.glob(os.path.join(d, 'trials_chunk_*_meta.json')))
    log(f"{len(sidecars)} sidecars to enrich")
    cache = {}  # condition string -> MONDO id (None if ungrounded)
    def ground_many(cs):
        out = []
        for t in (cs or []):
            if t not in cache:
                mid, _ = bb.ground(t, source='mondo')
                cache[t] = mid
            if cache[t] and cache[t] not in out:
                out.append(cache[t])
        return out

    n_chunks = n_grounded = 0
    for i, sc in enumerate(sidecars, 1):
        m = json.load(open(sc))
        changed = False
        # ground per distinct nct_id in this file (chunks of a trial share conditions)
        per_nct = {}
        for rec in m.values():
            nct = rec.get('nct_id')
            if nct and nct not in per_nct:
                cs = rec.get('conditions')
                per_nct[nct] = ground_many(cs if isinstance(cs, list) else [cs] if cs else [])
        for rec in m.values():
            n_chunks += 1
            cur = per_nct.get(rec.get('nct_id')) or []
            if cur:
                rec['disease_curie'] = cur
                n_grounded += 1
                changed = True
        if changed:
            json.dump(m, open(sc, 'w'), ensure_ascii=False)
        if i % 500 == 0 or i == len(sidecars):
            log(f"  {i}/{len(sidecars)} files | {n_chunks:,} chunks, {n_grounded:,} grounded "
                f"({100*n_grounded/max(1,n_chunks):.0f}%) | {len(cache):,} distinct conditions cached")
    log(f"DONE: {n_grounded:,}/{n_chunks:,} chunks grounded; {len(cache):,} distinct conditions")

if __name__ == '__main__':
    main()

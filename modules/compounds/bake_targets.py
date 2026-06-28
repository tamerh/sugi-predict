#!/usr/bin/env python3
"""Pipeline step: de-noise the reverse target landscape.

Recompute each patent_compounds compound's `targets` membership from its `predicted` list: drop single-weak
predictions (support == 1 AND conf < FLOOR) and cap to the top-N by confidence. This shrinks a target's
landscape to the compounds genuinely predicted against it -- a promiscuous compound no longer pads hundreds
of landscapes as a single-neighbour afterthought. `predicted` is left untouched (it keeps the full per-target
conf/support for the compound page, and `targets` is always == its accs), so this is non-destructive,
idempotent, and re-runnable with different thresholds.

Validated (usecases/val_floor.py, leave-one-out over the 1.25M ChEMBL reference): the dropped bucket is
~0.4% correct (vs ~16% kept) and only ~0.17% of correctly-recovered targets are lost.

  python bake_targets.py [--floor 0.4] [--cap 50] [--collection patent_compounds] [--resume] [--dry-run]

Reproducible: `bioyoda.sh build compounds denoise`. Small-data test: tests/test_atlas_targets.py. No GPU -- payload only.
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from modules.paths import BAKE_TARGETS_CKPT


def strong_targets(predicted, floor, cap):
    """predicted: [{acc, conf, support}] -> [acc], dropping support==1 & conf<floor, conf-desc, capped."""
    keep = [p for p in predicted if not (p.get("support", 0) == 1 and p.get("conf", 0.0) < floor)]
    keep.sort(key=lambda p: p.get("conf", 0.0), reverse=True)
    return [p["acc"] for p in keep[:cap]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", default="patent_compounds")
    ap.add_argument("--qdrant", default="http://localhost:6333")
    ap.add_argument("--floor", type=float, default=0.4)
    ap.add_argument("--cap", type=int, default=50)
    ap.add_argument("--batch", type=int, default=2000)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--ckpt", default=str(BAKE_TARGETS_CKPT))
    a = ap.parse_args()
    from qdrant_client import QdrantClient, models
    qc = QdrantClient(url=a.qdrant, timeout=600)

    offset = None
    if a.resume and os.path.exists(a.ckpt):
        v = open(a.ckpt).read().strip()
        offset = int(v) if v.isdigit() else (v or None)
        print(f"resuming from offset {offset}", flush=True)

    def commit(ops):
        for attempt in range(4):
            try:
                qc.batch_update_points(collection_name=a.collection, update_operations=ops, wait=False); return
            except Exception as e:
                if attempt == 3:
                    raise
                print(f"  write retry {attempt + 1}/3: {str(e)[:80]}", flush=True); time.sleep(15)

    done, dropped, t0, last = 0, 0, time.time(), 0
    while True:
        pts, nxt = qc.scroll(a.collection, limit=a.batch, offset=offset,
                             with_payload=["predicted", "targets"], with_vectors=False)
        if not pts:
            break
        ops = []
        for p in pts:
            pred = (p.payload or {}).get("predicted") or []
            tg = strong_targets(pred, a.floor, a.cap)
            dropped += len((p.payload or {}).get("targets") or []) - len(tg)
            done += 1
            if not a.dry_run:
                ops.append(models.SetPayloadOperation(
                    set_payload=models.SetPayload(payload={"targets": tg}, points=[p.id])))
        if ops:
            commit(ops)
        offset = nxt
        if not a.dry_run:
            open(a.ckpt, "w").write(str(nxt) if nxt is not None else "")
        if done - last >= 200_000 or nxt is None:
            last = done
            print(f"  {done:,} compounds ({done / max(time.time() - t0, 1):.0f}/s); "
                  f"weak memberships dropped: {dropped:,}", flush=True)
        if nxt is None or (a.limit and done >= a.limit):
            break
    print(f"done: {done:,} compounds in {time.time() - t0:.0f}s "
          f"({'DRY RUN' if a.dry_run else 'targets rewritten'}); {dropped:,} weak memberships dropped", flush=True)


if __name__ == "__main__":
    main()

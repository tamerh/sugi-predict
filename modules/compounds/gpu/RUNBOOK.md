# Patent target-atlas — GPU run (RunPod A100)

Exact Tanimoto on GPU (FPSim2 CUDA). Same fingerprints / Tanimoto / top-20 aggregation as the CPU path —
only the hardware changes. End-to-end ≈ half a day; the GPU search itself ≈ 1–3 h.

Fill in the SSH endpoint RunPod gives you:
```
HOST=root@<pod-ip>      PORT=<pod-port>      KEY=~/.ssh/id_ed25519     # as before
SSH="ssh -p $PORT $HOST"     SCP="scp -P $PORT"
```

## 0. Local prerequisites (already prepared)
- `work/chembl_reference/chembl_reference_morgan_r2_2048.h5`  ← UNCAPPED FPSim2 index (rebuilt)
- `work/chembl_reference/cid_targets.json`                    ← {cid:[uniprot]} (uncapped)
- `raw_data/patents/chunked_compounds/` (3.8 GB, 62 chunks)   ← patent SMILES
- `modules/compounds/gpu/gpu_atlas_predict.py`                ← the GPU script

## 1. PUSH (~4 GB, minutes)
```
$SSH 'mkdir -p /workspace/atlas/{ref,patents,preds}'
$SCP modules/compounds/gpu/gpu_atlas_predict.py            $HOST:/workspace/atlas/
$SCP work/chembl_reference/chembl_reference_morgan_r2_2048.h5  $HOST:/workspace/atlas/ref/
$SCP work/chembl_reference/cid_targets.json               $HOST:/workspace/atlas/ref/
$SCP raw_data/patents/chunked_compounds/compounds_chunk_*.parquet  $HOST:/workspace/atlas/patents/
```

## 2. SETUP (on the pod)
```
pip install -q FPSim2 cupy-cuda12x rdkit pyarrow        # cupy matched to the pod's CUDA
python -c "import cupy; print('GPU:', cupy.cuda.runtime.getDeviceProperties(0)['name'])"
```

## 3. VALIDATE first (5 min) — confirm GPU == CPU exact, and measure the rate
```
cd /workspace/atlas
python gpu_atlas_predict.py --ref ref/chembl_reference_morgan_r2_2048.h5 \
    --targets ref/cid_targets.json --patents patents --outdir preds --limit 100000
# read the printed rate + eta_full; spot-check a few preds against `bioyoda.sh compounds target` at home.
```

## 4. FULL run (~1–3 h; resumable — re-running skips finished chunks)
```
nohup python gpu_atlas_predict.py --ref ref/chembl_reference_morgan_r2_2048.h5 \
    --targets ref/cid_targets.json --patents patents --outdir preds > preds.log 2>&1 &
```

## 5. PULL (~3–6 GB, minutes)
```
mkdir -p work/atlas_preds
$SCP "$HOST:/workspace/atlas/preds/preds_*.parquet" work/atlas_preds/
```

## 6. INGEST locally → `patent_atlas` Qdrant collection (~1–2 h)
```
python modules/compounds/build_atlas_from_predictions.py \
    --preds work/atlas_preds --patents raw_data/patents/chunked_compounds --workers 16
```
Then regenerate the demo (`usecases/build_target_atlas_pages.py`) — gefitinib should now headline EGFR.

## Notes
- The GPU script auto-falls back to the CPU FPSim2 engine if CUDA isn't present, so `--limit` works as a
  no-GPU smoke test too.
- Predictions are written **per chunk** (`preds_compounds_chunk_*.parquet`) → resumable, and the ingest
  parallelises per chunk without a giant shared dict.
- If FPSim2-CUDA per-query overhead caps the rate too low in step 3, switch to the batched cupy popcount
  path (same math) — decide from the measured rate, not a guess.

# June-2026 refresh + reorg plan  (working note, not committed)

## Where things stand (live now)
- **Everything in Qdrant is Dec-2025** except patents_text (Dec base + June USPTO full-text).
- The June-2026 SureChEMBL snapshot is consolidated into `raw_data/patents/surechembl/2026-06-01/`
  (patents 5.9G, compounds 4.2G, patent_compound_map 4.96G = **1.53B rows**).
- **RunPod A100 80GB** up (container disk 400G, on-demand). SSH: `root@38.128.233.200 -p 22996`, key `~/.ssh/runpod_medcpt`.
  - patents_text **MedCPT embed RUNNING** on the pod (~5k vec/s → ~2.5h, 793 shards, output ~146G).
  - atlas k-NN queued next (gpu_atlas_predict, ~1–3h after the embed).

## The June refresh (what we run)
patents_text → MedCPT:   prepare(done) → embed(GPU, running) → insert → switch engine routing to MedCPT
patent_atlas → June:     chunk(done) → predict(GPU) → ingest → provenance → de-noise
- Validated: MedCPT > S-BioBERT on patents (0.93 vs 0.75 P@10) — justifies the GPU re-embed.
- Validated: de-noise floor (support==1 & conf<0.4, cap 50) drops ~0.4%-correct noise, loses ~0.17% real.

## DECISION 1 — one compound collection  (do at INGEST, no need to wait for the reorg)
Collapse `patents_compounds` (raw) + `patent_atlas` (predictions) into **one** general collection
**`patent_compounds`**:
  - vector: Morgan FP (stored once — saves ~245G of duplicated vectors)
  - payload: structure (smiles/inchi/formula/mw/id) for ALL compounds
           + predictions (predicted/targets/best_tanimoto/exact_match/novel) on the drug-like (≥10 heavy)
           + provenance (prov)
  - "atlas" becomes a FILTERED VIEW (where predicted exists / by target / novel / conf) — not a separate collection
  - NOTHING dropped: fragments/solvents stay (valid for structure search), they just carry no predictions
  - Build at ingest: ingest ALL compounds (struct+FP) → enrich drug-like (predictions) → provenance → de-noise
  - Implement: adapt build_atlas_from_predictions to enrich `patent_compounds` in place (not create patent_atlas);
    point engine/web at `patent_compounds` with a predicted/targets filter (the landscape query already filters targets).

## DECISION 2 — orchestration is fragmented; unify onto Enju  (SEPARATE PROJECT, AFTER June)
Three systems today:
  1. Snakemake  (bioyoda.sh run <module>)  → base collections: patents_compounds, patents_text, clinical_trials, esm2, diamond
  2. Bash atlas (bioyoda.sh atlas <stage>) → atlas layer + MedCPT refresh (recent; not in Snakemake)
  3. Enju       (workflows/*.yaml)         → migration target (Snakemake→Enju proven via the CT PoC; new Enju release out)
- Plan: after June, fold Snakemake rules + bash-atlas stages into **Enju workflows**, `bioyoda.sh` as the single entry.
- Do NOT migrate orchestration mid-refresh. Finish June on the current bash flow first.

## Target command shape (post-Enju-reorg)
```
bioyoda.sh build <collection> <stage>            (* = GPU stage; device-agnostic: pod GPU or CPU)
  build compounds  chunk → ingest → predict* → enrich → provenance → denoise   → patent_compounds
  build text       prepare → embed* → insert                                   → patents_text
  build reference  make → fpsim2                                               → chembl (1.25M)
  build proteins   fetch → embed* → insert                                     → esm2
  build trials     fetch → embed* → insert                                     → clinical_trials
  build grounding | indexes                                                     (supporting)
  --full   = rebuild from snapshot (the GPU bootstrap = this June run)
  --delta  = only NEW items vs the collection, upsert by hash(id)  (CPU for small, GPU if large)
bioyoda.sh serve up|down|status ; test ; snapshot|push|pull|qdrant
```

## After June = incremental
This June run is the one-time GPU **bootstrap**. Next SureChEMBL/UniProt/CT release → `--delta`
(only the new items, mostly CPU; GPU only when a delta is big or the encoder/method changes).

## Lessons from the June GPU run → fold into the reorg (the `bioyoda.sh build` wiring)
The manual debugging this run is exactly what the orchestrator should make a one-liner. Concrete fixes:
- **GPU stages MUST run under tmux on the pod.** cupy/FPSim2-CUDA fails its CUDA init when detached
  (nohup/setsid) WITHOUT a TTY (torch tolerated it; cupy does not). And launch the tmux via SSH with clean
  fd redirect (`</dev/null >/dev/null 2>&1`) or the tmux server holds the SSH channel open → the launch hangs
  and the session dies (looked like a "crash after reference load").
- **`compounds predict` must wire to `gpu_atlas_fused.py`, NOT `gpu_atlas_predict.py`.** Per-query FPSim2-CUDA
  is ~425/s (overhead-bound, ~17h). batched (gpu_atlas_batched.py) = ~1,600/s (B×R matrix + 20 argmax) → 5.4h.
  fused = one-pass top-150 neighbours, much faster once warm (slow FIRST chunk = CUDA-kernel JIT, not slowness).
  Input is `reference.tsv` (cid\tsmiles), NOT the .h5. `ingest` → `build_atlas_from_neighbours.py` (reads knn/nbrs/).
- The whole GPU hop (push → tmux-launch → monitor shards/chunks → pull → insert/ingest) should be ONE
  reproducible `bioyoda.sh` step (CPU stages local, GPU stage via the pod runbook), not hand-run.
- The current `atlas compounds {predict,ingest}` wiring in atlas.sh is WRONG (points at the slow per-query
  script + predictions ingest). Fix it as part of the reorg (or a quick correction before the next incremental run).

## Incremental is the DEFAULT for the atlas (proven this run)
The June atlas k-NN should NOT be a full 30.9M re-run. June-23 already produced work/atlas_nbrs/
(30,046,844 neighbours). For June: reuse ALL of them (every compound still present), compute the fused
k-NN ONLY on the delta = June compounds whose id is not in atlas_nbrs = **897,606 (2.9%)** → ~17 min vs ~10h.
Merge atlas_nbrs (reused) + delta_nbrs → full set → ingest. This is exactly `build compounds --delta`:
diff snapshot ids vs the collection/nbrs, process only new ids, upsert. Wire it so the orchestrator does
this automatically (never a blind full re-run when prior nbrs exist).

## Single env for CPU + GPU → "clone anywhere + bioyoda.sh" (reproducibility target, post-June)
Goal: a fresh GPU pod = `git clone` + recreate the `bioyoda` env + `bioyoda.sh <step>` + sync — with NO manual
pip installs (this run needed hand `pip install --break-system-packages cupy-cuda12x FPSim2 faiss transformers rdkit`).
Changes:
- **environment.yml = single source of truth.** Add the GPU deps (cupy-cuda12x, FPSim2, faiss, transformers,
  torch+cuda, rdkit) pinned, alongside the existing snakemake/CPU deps. ONE env serves snakemake AND the GPU runs.
- **bioyoda.sh must resolve the env python PORTABLY** (`conda run -n bioyoda` / activate), NOT the hardcoded
  `/data/miniconda3/envs/bioyoda/bin/python` in atlas.sh — so it works on any clone/host (pod included).
- **GPU steps run under tmux** inside the bioyoda.sh step (the cupy-needs-a-TTY + clean-fd-redirect lesson above).
- **push/pull a snapshot to the destination (pod)** as bioyoda.sh commands; sync results back.
- Caveats: cupy-cuda12x must match the pod CUDA (12.x ok); the pod base image needs conda/mamba (or a conda
  image); env-create pulls GBs (torch/cupy) but is fully reproducible. Use mamba for speed.
- End state: GPU run = clone → `mamba env create -f environment.yml` → `bioyoda.sh build <step>` (tmux on pod) → `bioyoda.sh pull`.

## Defer indexing across ALL payload passes -> one optimization, not three (reorg efficiency)
Qdrant set_payload VERSIONS each point (old deleted, new written), so a pass over 30M churns segments ->
the optimizer vacuums/merges -> which REBUILDS the HNSW vector index (~245GB), even though vectors never changed.
The June build did this 3x: ingest(predictions) -> optimize, provenance bake -> optimize, denoise -> optimize.
Fix: run ingest + enrich + provenance + denoise ALL with indexing_threshold DEFERRED, then trigger the HNSW
build ONCE at the very end. The build script defers during ingest but bake/denoise are separate scripts that
re-trigger. Wire the whole compound pipeline to share one deferred window + a single final BUILD. 3 -> 1.

## Tier-1/2 still open (not June-blocking)
- #3 unify served `chembl` 683K → 1.25M (CPU)  · target_genes full-name fix · grounding/index builders to commit
- patents_text engine routing: currently S-BioBERT stopgap; flip to MedCPT after the new collection is in + verified

## bake_targets: write only CHANGED memberships (not all 30M) — denoise optimization fix
The denoise rewrote `targets` on ALL 30,937,359 compounds (even unchanged ones), so its single deferred-index
optimization became a FULL-collection re-merge (disk 294G->549G churn, ~hours). Fix: bake_targets should
set_payload only where the de-noised `targets` differs from the stored one (~6% touched), so the optimization
is proportional. Same theme as the deferred-index window — minimize what each pass actually rewrites.

# compounds

The prediction + chemistry engine of Sugi Predict. Not a single collection: it assembles the
served `patent_compounds` payload (predicted targets + provenance over the Morgan-FP substrate)
and powers the `predict`/query tools.

## What it does

- **Target prediction** — chemical k-NN from each SureChEMBL compound to the ~1.25M ChEMBL
  ligand→target reference (Morgan ECFP4). `confidence` = best Tanimoto to a backing ligand,
  `support` = agreeing neighbours; below ~0.3 Tanimoto is novel/whitespace.
- **Provenance** — bakes the patent span (which patents claim each compound — assignee, dates,
  claimed-vs-disclosed) into the payload.
- **Denoise** — cleans the reverse (target → compounds) landscape.
- **Query modes** — exact-Tanimoto FTO (FPSim2), QSAR, and the cross-modal dossier
  (`xmodal`: drug → primary target → ESM-2 twilight homolog → grounded evidence).

## Key files

- `build_patent_compounds.py` — assemble the served `patent_compounds` (FPs + predictions + provenance).
- `build_atlas_from_neighbours.py`, `score_atlas.py` — predictions + confidence/support from the k-NN.
- `bake_provenance.py`, `bake_targets.py`, `patent_provenance.py` — patent-span provenance bake.
- `build_chembl_reference.py`, `build_fpsim2.py` — the ChEMBL answer-key + the FPSim2 exact-Tanimoto index.
- `fto.py`, `qsar.py`, `xmodal.py`, `target.py`, `assignee.py` — the query/analysis modes.
- `gpu/gpu_atlas_fused.py` — the fused one-pass k-NN kernel (GPU; run by `build compounds predict`).

Built via `./bioyoda.sh build compounds <stage>` (`chunk | predict | ingest | provenance | denoise | all`,
incremental with `--delta`). See [docs/how-it-works.md](../../docs/how-it-works.md) and
[docs/cli.md](../../docs/cli.md).

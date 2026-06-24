# BioYoda use-cases & experiments

Contained, end-to-end demonstrations that exercise the *whole* pipeline (all 5 collections +
biobtree grounding) on small, checkable biological scopes — to prove the substrate is **solid +
unique + omnidirectional**, and to surface concrete adjustments. Each runs in seconds.

Run with the bioyoda conda env: `/data/miniconda3/envs/bioyoda/bin/python usecases/<script>.py`

| script | what it demonstrates |
|---|---|
| `dossier.py <drug…>` | **Compound-first** grounded dossier: drug → PubChem CID + SMILES → primary target (biobtree mechanism, with activity/binding fallbacks, source-labeled) → ESM-2 protein family → Tanimoto analogs → literature → trials → disease grounding. |
| `dossier_disease.py <disease…>` | **Disease-first** grounded dossier: disease → MONDO node **+ parent/children tree** (deliberate grounding) → grounded trials (vector + `disease_curie` filter) → literature → drugs(from trials) → targets → ESM-2 family. |
| `usecase_osimertinib.py` | The original single-drug walkthrough (osimertinib) — the first contained use-case. |
| `exp_target_ranking.py` | Experiment: mechanism vs binding-target selection; confirmed the cross-modal join is correct once pivoted on the primary target. |

## Notes / known refinements
- **disease→gene is available** via biobtree `>>mondo>>gwas`, `>>mondo>>gencc`, `>>mondo>>civic_evidence`
  (union-of-routes cohort, per sugi-atlas). bioyoda's thin `biobtree_client.map_targets()` currently
  mis-parses these multi-attribute rows — adopt sugi-atlas's `atlas.biobtree` client / row parsing to
  use the proper disease gene cohort instead of the trials→drugs workaround in `dossier_disease.py`.
- Reference for biobtree usage: **/data/sugi-atlas** (`src/atlas/biobtree`, `src/atlas/disease/anchors.py`).
- These mature into the serving cross-modal-join MCP tool later.

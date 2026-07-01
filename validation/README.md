# Validation harnesses

Held-out validation and baseline scripts behind the numbers reported in the Sugi
Predict preprint (Methods, "Validation"). Each script reads the ChEMBL reference and
queries the served collections. Run from the repository root with the project Python
environment, e.g.:

```
python validation/poc_atlas_temporal_headtohead.py
```

Captured run logs are in `results/`.

## Accuracy on unseen chemistry (forward: compound → target)

| Script | What it measures |
|---|---|
| `redo_scaffold_loo.py` | Leave-one-out and scaffold-split recall@k, plus the confidence calibration by nearest-neighbour Tanimoto band. |
| `poc_atlas_temporal_validate.py` | Temporal split: train on ligands disclosed up to a cutoff, test on later chemistry (the prospective, patent-like regime). |
| `poc_atlas_drugpanel_large.py` | Approved-drug panel: recovery of each drug's mechanism-of-action gene, with the drug's own scaffold withheld. |
| `poc_atlas_drugpanel_byclass.py` | The drug-panel recovery broken down by target class. |
| `build_drugpanel_large.py` | Assembles the approved-drug panel (SMILES + mechanism gene). Helpers: `_drugpanel_resolve_genes.py`, `_drugpanel_target_classes.py`. |
| `poc_atlas_coverage.py` | Fraction of the patent compounds close enough to a known ligand for a confident prediction. |
| `val_floor.py` | Sets the nearest-neighbour Tanimoto floor below which a query is treated as out of domain. |

## Comparison with established methods

| Script | What it measures |
|---|---|
| `poc_atlas_temporal_headtohead.py` | Temporal-split head-to-head: the deployed confidence+support ranking vs single-nearest-neighbour, a SEA-style set-size correction, naive-Bayes over fingerprint bits, and the popularity floor. |
| `poc_atlas_sea_compare.py` | The deployed max-Tanimoto ranking vs a SEA-style set-size-corrected ranking, on the scaffold split. |

## Reverse direction (target → patented chemistry) and its independent check

| Script | What it measures |
|---|---|
| `poc_atlas_landscape_validate.py` | Precision of a target's predicted landscape against known annotations, by confidence cut. |
| `val_landscape_text_precision.py` | An independent check: whether a landscape compound's own patent text concerns the predicted target, stratified by neighbour support and target class. |
| `validate_patent_text_support.py` | Null-control for the patent-text check (real vs shuffled-link vs same-classification baselines). |

## Routes that did not validate (and were dropped)

| Script | What it measures |
|---|---|
| `poc_peptides_moat.py` | Peptide sequence-embedding similarity as a predictor (did not beat baseline). |
| `poc_polypharm_validate.py` | Protein-homology repurposing as a predictor (did not beat baseline). |

Three earlier one-off scripts (`poc_atlas_scaffold_validate.py`,
`poc_atlas_fullscale_validate.py`, `poc_atlas_drugpanel_validate.py`) are retained as the
protocol origin the current scripts descend from; they are superseded for the reported
numbers by `redo_scaffold_loo.py` and `poc_atlas_drugpanel_large.py`.

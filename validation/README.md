# Validation harnesses

The held-out validation and baseline scripts behind the numbers reported in the preprint
(*A Predicted Target Atlas of Patent Chemical Space* / **Sugi Predict**). They read
`work/chembl_reference/` and query the live Qdrant collections; run from the repo root
with the project env, e.g.:

```
/data/miniconda3/envs/bioyoda/bin/python validation/poc_atlas_temporal_headtohead.py
```

| Script | What it measures |
|---|---|
| `poc_atlas_temporal_headtohead.py` | Temporal-split head-to-head: the deployed confidence+support ranking vs single-NN, a SEA-style set-size correction, naive-Bayes over Morgan bits, and the popularity floor (recall@1/@5/@10, no leakage). Captured run in `poc_atlas_temporal_headtohead_result.txt`. |
| `val_landscape_text_precision.py` | Landscape (target→compounds) precision via an **independent** signal — the patents' own body text: corroboration rate, stratified by neighbour support and by target class. |
| `validate_patent_text_support.py` | Null-control for the patent-text corroboration feature: real vs shuffled-link vs same-classification null; recall pre/post background debias. `--ner` adds a literal gene-name cross-check. |

The older per-condition validation harnesses (leave-one-out, scaffold, drug-panel) live with
the prediction code in `modules/compounds/` and the historical PoCs under `docs/internal/usecases/`.

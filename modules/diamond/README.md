# diamond

DIAMOND all-vs-all BLASTP over UniProt/SwissProt — protein-sequence similarity used by the
cross-modal / twilight join and consumed by biobtree's `diamond_similarity` source. This is
**compute, not a served Qdrant collection**, so there is no `bioyoda.sh build` key for it.

## Run

It runs as the `diamond-update` Enju workflow (`workflows/diamond-update/`):

```
prepare  download UniProt SwissProt FASTA, makedb, split into chunks
search   diamond blastp per chunk vs the db (CPU, fanned out per chunk)
merge    concatenate the per-chunk hit TSVs -> merged_results.tsv
filter   top-K per query protein -> filtered_top{K}.tsv
```

CPU-only (the diamond binary is a sequence aligner, not GPU); the search is the heavy,
parallel step. Output lands at `work/data/processed/diamond/merged/filtered_top{K}.tsv` and is
promoted to `snapshots/diamond_latest/.../filtered_top100.tsv`, the path biobtree reads.

## Key scripts (`scripts/`)

- `download_uniprot.py` — fetch the SwissProt FASTA.
- `split_fasta.py` — split the query FASTA into chunks for the search fan-out.
- `filter_top_k.py` — reduce merged hits to top-K per query protein.

The workflow task scripts call these plus the `diamond` binary directly.

See [docs/how-it-works.md](../../docs/how-it-works.md) for how this feeds the substrate.

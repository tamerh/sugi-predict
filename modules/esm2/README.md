# esm2

Builds the `esm2` collection — UniProt/SwissProt proteins embedded with ESM-2 650M
(`esm2_t33_650M_UR50D`, 1280-d), served as protein context (e.g. sequence neighbours of a
predicted target).

## Build

```bash
./bioyoda.sh build proteins <stage>   # prepare | embed | insert | all
```

`prepare` splits the UniProt FASTA into chunks, incremental by default (only accessions not
already in the collection; `--full` for the whole set); `embed` runs ESM-2 650M (GPU via the
pod, very slow on CPU); `insert` upserts the 1280-d vectors into Qdrant, keyed by hashed
`protein_id`. Incremental refresh: `./bioyoda.sh build proteins all --delta` (bash; the Enju DAG was retired).

## Key scripts (`scripts/`)

- `download_uniprot.py`, `split_fasta.py`, `prepare_delta.py` — source + delta chunking.
- `batch_esm2_gpu.py` — ESM-2 650M embedding (writes FAISS + sidecar under `embeddings/`).
- `build_existing_proteins.py` — already-embedded accession set for incremental runs.
- `merge_embeddings.py`, `h5_to_faiss.py`, `create_faiss_index.py` — embedding assembly helpers.

See [docs/how-it-works.md](../../docs/how-it-works.md) for how proteins are used and
[docs/cli.md](../../docs/cli.md) for the full build reference.

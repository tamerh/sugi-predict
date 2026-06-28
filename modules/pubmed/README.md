# pubmed

Builds a `pubmed_abstracts_medcpt` collection — PubMed abstracts embedded with MedCPT-Article
(768-d). The build pipeline is maintained, but PubMed is **not currently served** as a prod
collection of Sugi Predict (literature is commodity context; the engine is focused on patent
chemistry + targets).

## Build

```bash
./bioyoda.sh build text <stage>       # chunk | embed | insert | all
```

`chunk` parses the NCBI PubMed XML (baseline + updatefiles) into MedCPT input shards,
incremental by PMID-delta (`--full` for the full corpus); `embed` runs MedCPT-Article (GPU via
the pod); `insert` upserts into Qdrant. The scheduled refresh runs as the `pubmed-update` Enju
workflow (`workflows/pubmed-update/`).

## Key scripts (`scripts/`)

- `download.py` — fetch the NCBI PubMed baseline + updatefiles.
- `chunk_pubmed_to_jsonl.py` — XML → MedCPT input shards (PMID-delta).
- `build_existing_pmids.py`, `tracking.py` — already-embedded PMID set for incremental runs.

See [docs/how-it-works.md](../../docs/how-it-works.md) for the substrate and
[docs/cli.md](../../docs/cli.md) for the full build reference.

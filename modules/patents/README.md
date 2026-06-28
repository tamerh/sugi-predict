# patents

Builds the two patent-derived collections of Sugi Predict from SureChEMBL (plus a USPTO
full-text overlay): the patent compounds and the patent text.

## Collections built here

- **`patent_compounds`** — every drug-like SureChEMBL compound, with a Morgan ECFP4 vector,
  structure, predicted human targets (chemical k-NN to the ChEMBL reference), and patent
  provenance. Built by:

  ```bash
  ./bioyoda.sh build compounds <stage>      # chunk | predict | ingest | provenance | denoise | all
  ```

  `chunk` splits the compounds parquet; `predict` runs the fused k-NN to the ChEMBL reference
  (GPU); `ingest` writes structure + FPs + predictions; `provenance`/`denoise` bake the patent
  span and clean the reverse target landscape.

- **`patents_text`** (→ `patents_text_medcpt`) — patent title + USPTO full-text, MedCPT-Article
  768-d. Built by:

  ```bash
  ./bioyoda.sh build patents-text <stage>   # prepare | embed | insert | all
  ```

The incremental USPTO full-text gap-fill runs as the `patents-text-update` Enju workflow
(`workflows/patents-text-update/`); the monthly compound refresh as `patents-compound-update`.

## Key scripts (`scripts/`)

- `download_surechembl.py`, `download_uspto*.py`, `parse_uspto.py` — source acquisition + parsing.
- `chunk_compounds.py` — stream the compounds parquet into chunks for the k-NN.
- `prepare_medcpt_shards.py` — build the patent-text JSONL shards (title + USPTO full-text).
- `extract_us_patent_ids.py`, `tracking.py` — SureChEMBL→US-ID filter and delta tracking.

The compound prediction/provenance/denoise logic lives in `modules/compounds/`.

See [docs/how-it-works.md](../../docs/how-it-works.md) for the method and
[docs/cli.md](../../docs/cli.md) for the full build reference.

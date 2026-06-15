# BioYoda — Colab GPU workflow (MedCPT migration & re-embeds)

GPU-heavy embedding (MedCPT migration #Q1, big benchmarks, future re-embeds) is **infeasible
on the 32-core/no-GPU box** (~1 text/s → weeks for ~72M vectors). This is the established
Colab + Google-Drive pattern, generalized for MedCPT.

**Flow:** local `export+push` → **Colab GPU embed** → local `pull+insert`. Drive folder
`MyDrive/bioyoda/` ⟷ rclone remote `gdrive:bioyoda` (same place).

```
local box                         Google Drive (gdrive:bioyoda)            Colab GPU
─────────                         ────────────────────────────            ─────────
export_text_for_embed.py  ──►  medcpt_input/<collection>/*.jsonl   ──►  embed_text_medcpt_gpu.py
                                medcpt_output/<collection>/*.index  ◄──  (FAISS + sidecar, resume)
insert_from_faiss.py      ◄──   (pull)
```

---

## 1. LOCAL — export (id+payload+text) shards, push to Drive

Start Qdrant, then (pubmed first — biggest, highest-value; its payload holds the FULL text,
so MedCPT recovers what the 75-token S-BioBERT truncated):

```bash
./bioyoda.sh qdrant start
python scripts/gpu/export_text_for_embed.py \
    --collection pubmed_abstracts --text-field chunk_text \
    --output-dir work/data/medcpt_input/pubmed_abstracts
# clinical_trials: --collection clinical_trials --text-field chunk_text
# patents_text: payload is title-only for most points -> export will skip them; re-PARSE
#   from raw (process_patents.py path) to get full text before embedding. (see issues #Q1)

rclone copy work/data/medcpt_input/pubmed_abstracts \
    gdrive:bioyoda/medcpt_input/pubmed_abstracts --progress --transfers 8
```

## 2. COLAB — embed on GPU (paste these cells; GPU runtime)

```python
# cell 1 — mount + deps + get the script
from google.colab import drive; drive.mount('/content/drive')
!pip -q install transformers faiss-cpu
!cp /content/drive/MyDrive/bioyoda/scripts/gpu/embed_text_medcpt_gpu.py .   # (push it once, step 3)
```
```python
# cell 2 — run (background + resume; safe to re-run / reconnect)
!nohup python embed_text_medcpt_gpu.py \
    --input-dir  /content/drive/MyDrive/bioyoda/medcpt_input/pubmed_abstracts \
    --output-dir /content/drive/MyDrive/bioyoda/medcpt_output/pubmed_abstracts \
    --batch-size 64 > medcpt_pubmed.log 2>&1 &
```
```python
# cell 3 — watch
!tail -n 20 medcpt_pubmed.log
```
Resume-safe: if Colab disconnects, just re-run cell 2 — finished shards are skipped.

## 3. LOCAL — push the GPU script once, then pull results & insert

```bash
# one-time: make the embed script available in Drive for Colab
rclone copy scripts/gpu/embed_text_medcpt_gpu.py gdrive:bioyoda/scripts/gpu/

# after Colab finishes: pull embeddings
rclone copy gdrive:bioyoda/medcpt_output/pubmed_abstracts \
    work/data/medcpt_output/pubmed_abstracts --progress --transfers 8

# insert into a NEW collection (keep the S-BioBERT one until A/B'd), 768d, pmid point-id
python modules/qdrant/scripts/insert_from_faiss.py \
    --faiss-dir work/data/medcpt_output/pubmed_abstracts \
    --collection pubmed_abstracts_medcpt --qdrant-url http://localhost:6333 --vector-size 768
```

---

## Notes
- **MedCPT is asymmetric**: this embeds the corpus with `ncbi/MedCPT-Article-Encoder`. Queries
  (in `bioyoda-serve`, #M1) must use `ncbi/MedCPT-Query-Encoder`. Both 768d.
- **Insert into `_medcpt` collections first** and A/B against the S-BioBERT ones with
  `eval/retrieval_benchmark.py` before cutting over — don't destroy the old index until proven.
- **patents_text** needs full text re-parsed from raw (payload is title-only) — handle as a
  separate prep before embedding; pubmed + clinical_trials work directly from this export.
- Justification (hard numbers): `eval/` → MedCPT +40–66% nDCG@10 over S-BioBERT on NFCorpus/SciFact.

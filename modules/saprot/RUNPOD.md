# SaProt Stage 3 — RunPod GPU run

Stages 1 (AFDB fetch) and 2 (Foldseek 3Di) already ran on the bioyoda host.
Stage 3 (`score_saprot.py`, wt-marginal LLR) is the only GPU step. Validated on CPU:
SaProt vs the ESM1b reference correlates at **Spearman 0.751** — independent, correct-sign signal.

## Pod
- **GPU:** 1× A100 40GB (any single modern GPU works; wt-marginal is light). PyTorch image.
- **Disk:** ~15 GB (2.5 GB model + ~4 GB gzipped output + inputs).

## Setup on the pod
```bash
pip install -q transformers                      # torch is in the PyTorch image
git clone --depth 1 https://github.com/westlake-repl/SaProt   # only for utils/constants.py
# upload these 3 from the bioyoda host (scp / runpodctl):
#   combined_seqs.jsonl   (66 MB)  out_prod/work/saprot/
#   isoform_list.csv      (1.3 MB) /data/biobtree/raw_data/esm1b/
#   score_saprot.py                modules/saprot/scripts/
```

## Run
```bash
python score_saprot.py \
  --combined combined_seqs.jsonl \
  --genes    isoform_list.csv \
  --saprot   ./SaProt \
  --model    westlake-repl/SaProt_650M_AF2 \
  --out      saprot_llr.tsv.gz \
  --batch 8 --device cuda
```
- Model auto-downloads (~2.5 GB) on first run. The "contact_head not initialized" warning is benign (unused head; the MLM head is loaded).
- 41,672 proteins, mean 532 residues → **~422M missense rows**, output ~3–4 GB gzipped.
- If OOM on a long protein, drop `--batch` to 4. Expected wall time ~15–40 min → **~$1**.
- Smoke test first: add `--limit 20` and eyeball a few LLRs (WT-conserved sites strongly negative).

## Back on the bioyoda host
Download `saprot_llr.tsv.gz` to `out_prod/work/saprot/`. This is the handoff artifact for
biobtree — same 5-column contract as the ESM1b reference:
`uniprot <tab> protein_variant <tab> position <tab> llr <tab> gene_symbol` (no header, WT diagonal skipped).

# MedCPT migration — RunPod A100 runbook (turnkey)

Rent an A100 to re-embed text collections with MedCPT (the GPU-gated quality leap; CPU is
infeasible at ~219 vec/s). Same gdrive hub as the Colab flow, but `rclone` instead of
`drive.mount`. Full float32, full sidecars (text in payload) — no precision/fidelity tradeoff.

**Box:** RunPod · A100 PCIe 80 GB · 16 vCPU · 117 GB RAM · **disk 300 GB** ·
template `runpod/pytorch:…torch280-ubuntu2404`. ≈ $1.40/hr GPU + ~$0.03/hr disk + **$0 bandwidth**.
pubmed (~7 h) ≈ **$10 all-in**.

Sizes (full pubmed, float32): input ~60 GB + vectors ~89 GB (28.9M×768×4B) + sidecars ~60 GB.

---

## PHASE 0 — LOCAL: export shards  (⚠️ do this BEFORE renting the box — it's local + Qdrant-only, no reason to pay for an idle GPU during the ~20 min export. Qdrant scroll = guaranteed 1:1 with the collection, the right source. Further: pre-stage to a persistent RunPod network volume to also skip the rsync-idle.)
```bash
./bioyoda.sh qdrant start
# full pubmed export (no --max-records) -> ~578 shards (~60 GB); ~30-45 min scroll
python scripts/gpu/export_text_for_embed.py \
  --collection pubmed_abstracts --text-field chunk_text \
  --output-dir work/data/medcpt_input/pubmed
# stage to gdrive (this upload is bounded by YOUR local upload bandwidth — start early)
rclone copy work/data/medcpt_input/pubmed gdrive:bioyoda/medcpt_input/pubmed --transfers 8 --progress
rclone copy scripts/gpu/embed_text_medcpt_gpu.py gdrive:bioyoda/scripts/gpu/
```
(Alternative: skip gdrive, `scp`/`rsync` shards straight to the box once it's up — one hop, often faster.)

## PHASE 1 — rent the box
RunPod → A100 PCIe 80 GB, **disk 300 GB**, the torch280 template. Open a web terminal / SSH.

## PHASE 2 — RENTED BOX: setup
```bash
pip install -q transformers faiss-cpu
curl https://rclone.org/install.sh | sudo bash
# bring your gdrive remote: paste ~/.config/rclone/rclone.conf, OR `rclone config` (re-auth)
mkdir -p /workspace/input /workspace/output
rclone copy gdrive:bioyoda/medcpt_input/pubmed /workspace/input/pubmed --transfers 8 --progress
rclone copy gdrive:bioyoda/scripts/gpu/embed_text_medcpt_gpu.py /workspace/
nvidia-smi --query-gpu=name --format=csv,noheader   # confirm A100
```

## PHASE 3 — EMBED on GPU (background + resume-safe)
```bash
cd /workspace
nohup python embed_text_medcpt_gpu.py \
  --input-dir /workspace/input/pubmed \
  --output-dir /workspace/output/pubmed \
  --batch-size 256 > medcpt.log 2>&1 &
tail -f medcpt.log    # ~1,200 vec/s on A100 -> ~7 h for 28.9M; resume = re-run, finished shards skip
```

## PHASE 4 — push outputs, then TERMINATE the box (stop billing)
```bash
rclone copy /workspace/output/pubmed gdrive:bioyoda/medcpt_output/pubmed --transfers 8 --progress
# delete rclone.conf if you pasted it (it holds your Drive token), then terminate the pod
```

## PHASE 5 — LOCAL: insert into a NEW collection + A/B (do NOT destroy the S-BioBERT one)
```bash
rclone copy gdrive:bioyoda/medcpt_output/pubmed work/data/medcpt_output/pubmed --transfers 8 --progress
./bioyoda.sh qdrant start
python modules/qdrant/scripts/insert_from_faiss.py \
  --faiss-dir work/data/medcpt_output/pubmed \
  --collection pubmed_abstracts_medcpt \
  --qdrant-url http://localhost:6333 --vector-size 768
# A/B: spot-check pubmed_abstracts (S-BioBERT) vs pubmed_abstracts_medcpt on the same queries;
# the BEIR eval already showed MedCPT +40-66% nDCG. Cut over only once satisfied.
```

---
## Notes
- **MedCPT is asymmetric**: this embeds the corpus with `ncbi/MedCPT-Article-Encoder`. The query
  side (in bioyoda-serve later) must use `ncbi/MedCPT-Query-Encoder`. Both 768d.
- **Pilot first (recommended):** do ONE batch (e.g. `--max-records 1000000` at export) end-to-end
  (~$1.50, ~20 min GPU) to validate the whole loop + a real A/B before the full 60 GB / 7 h run.
- **clinical_trials / patents_text** migrations follow the same recipe later (patents_text needs a
  text re-parse first — its payload is title-only).
- Security: the rclone.conf you paste grants Drive access — remove it before terminating the box.

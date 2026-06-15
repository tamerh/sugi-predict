# BioYoda — Research Directions: Pipeline Roadmap + Preprint Plan

**Synthesis of 5 research streams (embedding-models, retrieval-indexing, data-systems, literature-review, publication-strategy), reconciled against the live code at `/data/bioyoda`.**
Date: 2026-06-15. Author: Tamer (solo dev). Scope (locked): BioYoda = a **standalone, self-hosted, multi-modal biomedical vector service**, published like biobtree, demonstrated useful via an **MCP endpoint**. Reasoning/agent work → "Sugi Atlas" (out of scope). biobtree id-grounding integration → part 2 (out of scope).

---

## 0. Ground-truth reconciliation (what the code actually says)

Before any recommendation: the streams disagreed on several "is it implemented?" facts. I checked the code. The corrected baseline:

| Fact | Verdict (from code) | Source line |
|---|---|---|
| Text encoder | `pritamdeka/S-BioBERT-snli-multinli-stsb`, 768d, across pubmed + patents_text + CT | `config/config.yaml:33,79,156` |
| MedCPT already anticipated | Yes — listed as a commented candidate | `config/config.yaml:32` |
| Quantization | **ENABLED by default** — scalar int8, quantile=0.99 (`enable_quantization=True`) | `insert_from_faiss.py:211,237-240` |
| Compounds distance | **`Distance.COSINE`** on 2048-bit Morgan/ECFP — single code path, **no Jaccard/Tanimoto path** | `insert_from_faiss.py:257` |
| Exact-Tanimoto re-rank | **NOT shipped anywhere** in repo (0 hits outside sugi-agent) | grep |
| Payload indexes | **NONE** — `create_payload_index` = 0 hits across `modules/` + `config/` | grep |
| ESM-2 pooling | **Mean pool** over residues, skip BOS/EOS | `generate_embeddings.py:95` |
| Search/serving layer | Only in `sugi-agent/` (the component being spun out) | — |

**Two stream claims were wrong and are corrected here:** (a) the retrieval stream said "zero quantization configured" — false, scalar int8 is the default. (b) The compounds collection does **not** have a Tanimoto path; it scores cosine on binary-fingerprint floats. This is the cheminformatics-correctness bug the publication stream flagged, and it is real.

**Net:** three "we already do X" beliefs (Tanimoto re-rank, payload indexes, a standalone search layer) are **aspirational, not in code**. Plan accordingly.

---

# PART A — PIPELINE IMPROVEMENT ROADMAP ("are we doing it right?")

## A.1 Per-modality model verdicts

### TEXT (S-BioBERT 768d, ~67M of 99M vectors) → **UPGRADE to MedCPT** — highest-ROI change in the pipeline
S-BioBERT is BioBERT fine-tuned on *general-domain NLI/STS* (SNLI+MultiNLI+STSb). BioYoda's workload is *asymmetric retrieval* (query→abstract/patent/trial), not STS. That is a model–task mismatch. **MedCPT** (NCBI, *Bioinformatics* 2023) is contrastively trained on 255M PubMed click pairs, is SOTA on BEIR biomedical IR (beating GTR-XXL 4.8B and OpenAI cpt-text-XL despite 330M params), outputs **768d (drop-in — no schema/HNSW change)**, and supports article-to-article search. Use the asymmetric pair: **MedCPT-Article-Encoder** for the corpus, **MedCPT-Query-Encoder** at request time (both 768d, shared space, free at query time).
- Cost: one-time CPU re-embed of ~67M vectors. Same BERT-base arch → per-doc cost ≈ identical to S-BioBERT; only the re-embed is new. Stage it via existing ID-delta + Colab-GPU machinery as a rolling background job. *Verdict: UPGRADE first.*
- Don't chase NV-Embed/7B generalists (impractical on CPU at this scale) or NeuML/pubmedbert-embeddings (it wins *STS*, not *retrieval*).

### PROTEIN (ESM-2 650M 1280d, 574K vectors) → **KEEP as published default; ADD ESM-C 600M as opt-in**
ESM-C 600M (Cambrian, Dec 2024) rivals ESM-2 3B / approaches 15B at ~the same inference cost as ESM-2 650M. **But it ships under the Cambrian Non-Commercial License** — a real distribution constraint for a service "published like biobtree" (others self-host). So: keep **ESM-2 650M** (permissive, proven) as the default; add **ESM-C 600M as an opt-in encoder** for academic deployments. Re-embed is trivial (574K, brute-force, ~hours). Permissive upgrade alternatives (ProtT5-XL-U50, Ankh) are heavier or also NC. **Free A/B worth running:** mean-pool vs CLS/BOS-token pooling (`generate_embeddings.py:95` currently mean-pools). Don't jump to ESM-2 3B/15B — the literature says 650M is "frequently sufficient" and downstream sets <10⁴ examples can't leverage bigger.

### CHEMISTRY (Morgan/ECFP4 2048-bit, 30.9M vectors) → **KEEP fingerprints; FIX the distance metric**
"Benchmarking Pretrained Molecular Embedding Models" (arXiv 2508.06199, 2025) evaluated 25 models on 25 datasets: **only ONE beat ECFP, and it was itself fingerprint-based (CLAMP); every GNN, Uni-Mol, and MoLFormer did worse.** For unsupervised structural similarity search, learned embeddings are a downgrade and need GPU for 30.9M compounds. **Do NOT migrate to learned chemistry embeddings.** BUT the current collection scores **cosine on binary-ECFP floats** (`insert_from_faiss.py:257`) — wrong metric *and* wasteful (storing bits as float32). Fix: store as binary, use **Tanimoto/Jaccard** (native to Qdrant for binary, or ANN-candidate + exact-Tanimoto re-rank). Optional free tweak: expose count-ECFP (the baseline the benchmark singles out).

## A.2 Retrieval / indexing / eval upgrades

1. **Eval harness (Tier-0 BLOCKER).** No retrieval-quality number exists today — only speed. Build `bench/`: pull BEIR via `ir_datasets`, wire the Qdrant query path as a BEIR retriever, emit **nDCG@10 + Recall@100 + MRR + latency p50/p95**. Free gold sets that overlap pubmed: **TREC-COVID** (50 queries, 66k judgments), **NFCorpus** (323 queries), **BioASQ**, **SciFact**. This is the gate for every quality claim and *is* the paper's results section.
2. **Hybrid dense+BM25 (RRF), native Qdrant 1.10+ Query API.** Dense-only misses exact lexical hits — gene symbols ("TP53"), drug names, NCT IDs, accessions — catastrophic in biomedicine. Add a sparse named vector to `pubmed_abstracts` + `patents_text`, fuse with RRF, no new infra. Start plain BM25 (free); SPLADE only after measuring (inference-free SPLADE is −4.7 nDCG vs siamese — not a clean drop-in).
3. **"Retrieve-cheap, rerank-exact" as a unifying design across all 3 modalities.** Text: top-100 → MedCPT cross-encoder / ColBERTv2 (ColBERT ~2 orders faster than cross-encoder, ~+3–4pp on PubMedQA). Chemistry: **actually ship** the exact-Tanimoto re-rank (it doesn't exist yet). Protein: ESM-2 cosine top-k → Smith-Waterman/DIAMOND rescore (mirrors DHR: >10% sensitivity over DIAMOND, up to 22× faster than PSI-BLAST). One clean narrative, not three hacks.
4. **Payload indexes (currently zero).** Add `create_payload_index` after collection creation for `nct_id, patent_id, surechembl_id, pmid, protein_id, chunk_type, molecular_weight`. Without them, every filtered query (CT section filter, MW range) is a linear scan at 28–38M points. Cheapest win on the board; makes the "filtered search" claim *true*.
5. **Tune `ef_search` per collection; publish the recall-vs-latency Pareto.** Build params (`m=32, ef_construct=256`) are fine; `ef_search` is the untuned query-time recall knob. Sweep {64,128,256,512}, publish per-collection curve. An afternoon; reviewers expect the figure.
6. **Fix patents chunking — the likely worst quality bug.** patents_text concatenates title+abstract+claims+description into ONE 768d vector; S-BioBERT truncates at 512 tokens, so **most of the description and claims are silently discarded** and four text types are averaged into a blurry centroid. Make it match the *good* clinical_trials design: **per-section vectors**, mean-pool *within* section, **max/RRF across sections** to a patent-id. Measurable, defensible.

## A.3 Systems hardening (gates publishability + redeployability)

- **H1 — Build a standalone serving layer (BLOCKER).** The only search code lives in `sugi-agent/`, which is leaving. Extract a thin `bioyoda-serve` (FastMCP + a few REST routes): embed-query → Qdrant search → return payloads. No LLM, no biobtree. *Without this there is no service to publish.*
- **H2 — Quantization is already on (scalar int8); now MEASURE it.** Produce a recall@k × RAM × latency table across {none, scalar-int8, binary+rescore} on real collections. This is the strongest systems-paper angle. The 2048d compound fingerprints are *ideal* binary candidates (already bit-natured) — binary quant there is near-free RAM. TurboQuant (Qdrant 1.18) 4-bit hits 0.965 recall, ~0.996 with rescore at 8× — worth a row. Skip PQ (not SIMD-friendly).
- **H3 — Idempotency must cover update+delete, not just insert.** Today: additions-only ID-delta. PubMed deletions are *downloaded but never applied* to Qdrant; revised abstracts/patents are silently *skipped* (stay stale). Wire the existing-but-unused `compute_patent_hash` (`tracking.py:58`) as a content-hash gate so revisions re-embed; apply the PubMed deletions list as Qdrant `delete` by pmid.
- **H4 — Hash-collision audit.** 64-bit truncated SHA256 across 38.7M patents → P(collision) ≈ n²/2·2⁶⁴ ≈ **~4%**; a collision silently overwrites a different patent. Either move to native string/UUID point IDs (Qdrant supports them) or document + add a detection check. esm2 already got bitten by this class once.
- **H5 — Reproducibility packaging.** Ship `docker-compose` (Qdrant + bioyoda-serve), a **pinned model+dataset-version manifest** (S-BioBERT/MedCPT rev, ESM-2 checkpoint, UniProt 2026_01, SureChEMBL snapshot date, PubMed baseline), and a **~100K-vector public sample collection** so a reviewer can `docker compose up` without 1.4TB.

## A.4 Data / modality additions

- **ADD GO terms + pathways** (Reactome/KEGG descriptions) as a small text collection — few hundred K short texts, CPU-embeddable in hours via the existing text path. Highest value-per-effort new dataset; natural bridge toward biobtree id-grounding without doing the integration now.
- **ADD ChEMBL bioactivity as PAYLOAD enrichment on patents_compounds** (compound → known targets/activities), NOT a new vectorized collection. A structure hit then returns "similar compound, active against target X." Low creep.
- **DEFER: protein structures** (second project), **TrEMBL** (~250M entries — would dominate the entire systems budget for marginal curated value; keep clean 574K SwissProt), **single-cell** (wrong modality for v1).

## A.5 RANKED change table

| # | Change / addition | Why | Effort | Payoff | Preprint-relevant? |
|---|---|---|---|---|---|
| 0 | **Eval harness** (BEIR: TREC-COVID/NFCorpus/BioASQ/SciFact; nDCG@10+Recall@100+MRR+latency) | No quality claim is publishable without it; *is* the results section | Low | **Blocker** | **YES — spine** |
| 1 | **Standalone `bioyoda-serve` (MCP+REST)** | Only search code is in the component being removed; no service without it | Med | **Blocker** | **YES — the deliverable** |
| 2 | **Fix ECFP distance** → binary store + Tanimoto/Jaccard (+ exact re-rank) | Current cosine-on-binary is wrong chemistry; reviewer rejects on sight; also cuts RAM | Low–Med | High | **YES (C3 correctness)** |
| 3 | **Payload indexes** (nct/patent/surechembl/pmid/protein/chunk_type/MW) | Filtered search is O(n) at 38M today; makes the claim true | Low | High | YES |
| 4 | **Text encoder → MedCPT** (Article+Query, 768d drop-in) | Biggest single quality lever; same schema; re-embed only | Low (build) / Med (compute) | High | YES (best quality result) |
| 5 | **Incremental-update cost study** (full vs ID-delta, real PubMed-2026 run, ~15×) | Your most novel engineering result; data already exists | Low | High | **YES — best novelty fig** |
| 6 | **Measure quantization** (none/int8/binary+rescore table) | Strongest systems angle; near-free RAM on 2048d compounds | Med | High | YES |
| 7 | **Hybrid dense+BM25 (RRF)** | Fixes lexical misses (gene/drug/ID); native Qdrant, no new infra | Low–Med | Med–High | YES |
| 8 | **Retrieve-cheap rerank-exact** (ship Tanimoto; text/protein rerank) | Unifying narrative; +3–4pp text; correct chemistry | Low | High | YES (framing) |
| 9 | **Fix patents chunking** → per-section | Silently truncating to 512 tokens today; likely worst quality bug | Med–High | Med–High | YES |
| 10 | **Idempotency: update+delete** (wire content-hash, apply deletions) | "Never delete / skip revisions" is a correctness hole reviewers probe | Med | Med | YES |
| 11 | **Tune `ef_search`; publish Pareto** | Reviewers expect the recall/latency curve | Low | Low–Med | YES |
| 12 | **ESM-C 600M opt-in** (keep ESM-2 default) | Real rep gain; trivial 574K re-embed; NC-license-gated | Low | Med | Optional |
| 13 | **GO/pathways text collection** | Best value-per-effort new data; bridge to id-grounding | Low | High | Optional |
| 14 | **ChEMBL bioactivity as payload** | Enriches compounds without new modality | Low–Med | Med | Optional |
| 15 | **Hash-collision audit** (string IDs or doc + check) | ~4% collision at 38M underpins every "idempotent" claim | Low | Med | YES (Methods) |
| 16 | **docker-compose + version manifest + sample collection** | Difference between "tool paper" and "system we built" | Med | High | **YES (reproducibility)** |
| 17 | ColBERT as *first-stage* index | Storage blowup at 99M; use as reranker only (#8) | High | Med | LATER |
| 18 | Cross-modal *joint* embedding space | Reviewers will probe; bridge by biobtree ID instead | High | — | NOT NOW (part 2/3) |
| 19 | Learned chemistry embeddings | Benchmarks show they LOSE to ECFP for similarity | — | Negative | **NOT WORTH IT** |
| 20 | TrEMBL / protein structures / single-cell | Dominate systems budget; wrong scope for v1 | High | — | **NOT NOW** |

**NOW (cheap, high-value):** #0,1,2,3,5,11,15. **SOON (the quality story):** #4,6,7,8,9,16. **LATER:** #10,12,13,14,17,18. **NOT WORTH IT:** #19,20.

---

# PART B — PREPRINT DIRECTION (standalone bioyoda, useful via MCP)

## B.1 Sharpened thesis

> **BioYoda: a self-hosted, multi-modal biomedical vector service with identifier-keyed incremental updates, served over MCP on a single commodity (no-GPU) server.**
> Four embedding modalities — literature (28.9M PubMed abstracts), patent text (38.7M), chemical structure (30.9M Morgan/ECFP4 fingerprints), protein sequence (ESM-2, 574K) — plus section-level clinical-trial text, totalling **~99M vectors** in Qdrant on **one 32-core / 125 GB box, no GPU**. Every record is keyed to a stable domain identifier (PMID, patent no., SureChEMBL id, UniProt accession, NCT id), enabling **entity-delta incremental refresh** (~15× cheaper PubMed updates), exposed as an **MCP tool provider**.

**The contribution is the conjunction, not any single piece.** Not "biomedical vector search" (crowded), not "MCP server" (MCPmed/BioMCP/BioContextAI/BioinfoMCP already filled it in 2025–26), not a new encoder (you use off-the-shelf). The defensible whitespace is the **four-way intersection: multi-modal × ~100M-scale × self-hosted-one-box × MCP-native**, plus the genuinely-uncommon **id-keyed incremental-update result**.

## B.2 Gap vs related work (the 4-axis table)

| System | Multi-modal | ~100M scale | Self-hosted (one box) | MCP-native |
|---|:--:|:--:|:--:|:--:|
| MedCPT / BMRetriever | text only | encoder, not a service | weights only | no |
| ESM Atlas | protein only | yes (100s M) | no (hosted) | no |
| SureChEMBL | chem only | yes (17M) | no (EBI portal) | no |
| TrialGPT | trials only | no (per-query) | partial | no |
| MolBind / MAMMAL / BioVERSE | **fused space** (training) | no (benchmark) | research code | no |
| **BioMCP** (closest comp) | multi (federated APIs) | N/A (live APIs) | no (remote deps) | **yes** |
| MCPmed | (proposal) | N/A | (proposal) | yes (vision) |
| **BioYoda** | **yes (5 modalities, multi-index)** | **yes (~99M)** | **yes (no GPU)** | **yes** |

**Gap stated precisely:** no published system occupies all four columns. BioMCP (closest) is a **federation wrapper over remote APIs** — owns no index, inherits upstream rate-limits/latency, cannot do fingerprint or protein-embedding search. ESM Atlas / SureChEMBL own large self-hosted indexes but are single-modality non-MCP portals. The multi-modal-embedding papers build *fused spaces at benchmark scale*, not deployed services. **BioYoda owns the index, self-hosted, 5 modalities, with an MCP front door.**

**Critical positioning nuance:** BioYoda is multi-modal in the **systems/service** sense (separate per-modality indexes behind one retrieval surface), NOT the **fused-embedding-space** sense of MolBind/MAMMAL. State this explicitly or reviewers conflate the two and call you derivative. Honest claim = "unified *retrieval surface*," not "unified *embedding space*."

**Closest prior works to position against (cite, in order):** (1) **BioMCP** — "owned-index vs federation-of-APIs"; (2) **MCPmed** — "we are the vector substrate your vision lacks"; (3) **ESM Atlas** — protein is one tile, not a competitor on coverage; (4) **SureChEMBL** — same ECFP/Tanimoto recipe, co-located with text+protein; (5) **MedCPT** — SOTA *encoder* (swappable infra, your upgrade path); (6) **TrialGPT** — we provide the section-level trial substrate it needs. (Distinguish from **MAMMAL/MolBind** to draw the multi-index vs fused-space line.)

## B.3 Target venue + framing

**bioRxiv NOW (bank priority — this space moves in months) → then *Database* (Oxford) OR *Bioinformatics* Application Note.**
- ***Database* (OUP)** — scope = "translation of biological information into organized formats integrating literature + large datasets supporting computational analysis." A 99M-vector multi-modal store + exported similarity datasets *is* this. No word cap → room for the resource framing. **Primary if you want space.**
- ***Bioinformatics* Application Note** — ~2,600 words, FAIR/open mandate, ML claims need an independent test set. Tight, fast, "a tool" framing forces honesty. **Primary if you want speed.**
- **AVOID NAR Web Server** — needs a real web UI + "new biological insight," and **explicitly rejects servers that primarily aggregate data from several sources** (you aggregate PubMed+SureChEMBL+USPTO+UniProt+CT). High desk-reject risk. NAR *Database* issue is a fallback only if framed as a novel derived resource.
- **Not Nature Methods/Biotech** — below the method-novelty/community-adoption bar (BioContextAI got only a *Correspondence*).

**Frame as a RESOURCE/SYSTEMS paper** (à la ESM Atlas, EBI Search, SureChEMBL): the contribution is the integrated index + serving + MCP + incremental machinery, **not** the encoder. Put the honest novelty statement in the paper: *"Individually each modality has a stronger incumbent; BioYoda's contribution is the engineering of a unified, id-keyed, incrementally-updatable multi-modal store at 100M scale on commodity hardware, exposed as an agent-ready MCP service."*

## B.4 Claims → Evidence table

| # | Claim (defensible) | Evidence / experiment | Figure/table | Status |
|---|---|---|---|---|
| C1 | Multi-modal coverage at scale (5 collections, ~99M, one box) | Inventory: name, model, dim, #vec, index, RAM/disk | Table 1 + system diagram | **Have** — just write |
| C2 | **Competitive** intrinsic retrieval (NOT SOTA) | S-BioBERT *and* MedCPT on TREC-COVID/NFCorpus/BioASQ/SciFact vs MedCPT/BM25/BMRetriever; nDCG@10/Recall@k | Table 2 | **MISSING — top priority** |
| C3 | Chemical structure search is correct | Tanimoto recovery on known-similar pairs vs RDKit ground truth | Table/Fig | **BLOCKED by ECFP-cosine bug — fix then strength** |
| C4 | Dual protein similarity (ESM-2 + DIAMOND) is complementary | SCOP/Pfam remote-homology: ESM-2 finds homologs DIAMOND misses; RRF > either | Fig (recall-vs-identity) | MISSING (cheap, CPU-only) |
| C5 | **Entity-delta update ~15× cheaper** | Real PubMed-2026 delta (28.25M known → ~695K new): vectors, GPU-h, wall-clock, $ full vs delta | Table | **Have the run — formalize** |
| C6 | Filtered semantic search at scale | Latency with/without payload indexes at 30–38M | Table | **BLOCKED — build indexes (A.2 #4)** |
| C7 | Self-hosted at 100M on commodity HW | RSS/mmap/disk, p50/p95 latency, throughput, $ vs managed DB | Table 3 | Mostly have — add latency bench |
| C8 | Reproducible | Lockfile, pinned model revs, deterministic point-id, Zenodo snapshot | Methods | Partial — pin everything |
| C9 | MCP-native usefulness | ≥1 cross-modal query no single incumbent answers + MCP tool trace | Fig (case study) | MISSING — wire tools + demo |
| C10 | Irreplaceable mined corpora (data moat) | 519K USPTO-chem mirror (dead source) + AACT provenance | Availability note | **Have** (`IRREPLACEABLE.md`) |

**Minimum publishable set:** C1, C2, C5, C7, C8 + (C3 fixed) + one C9 case study. C4 and C6 are strong "make it solid" adds.

## B.5 The 2–3 evaluations that are the SPINE (exactly how to run on the current box)

1. **Retrieval-quality benchmark (C2) — the must-have.** `pip install ir_datasets beir`; pull **TREC-COVID + NFCorpus** (overlap pubmed), plus BioASQ/SciFact. Wire the Qdrant query path as a BEIR retriever. Run **S-BioBERT vs MedCPT** side-by-side; report **nDCG@10 + Recall@100 + MRR**, macro-averaged, vs published MedCPT/BM25/BMRetriever numbers. CPU-only; the headline row is "MedCPT vs S-BioBERT, +N nDCG@10 on TREC-COVID." Be explicit you *trail SOTA* and claim **competitive-at-a-fraction-of-the-infra**, not "best."
2. **Incremental-update cost study (C5) — the most original result.** Formalize the real PubMed-2026 refresh into one table: full re-embed vs ID-delta (vectors embedded, GPU-hours, wall-clock, $). The ~15× number is already in the memory audit; this needs writing up, not new compute.
3. **System resource + latency benchmark (C7) + quantization table (H2).** On the one box: per-collection p50/p95 query latency, throughput, RSS/mmap/disk; sweep `ef_search`; and a recall × RAM × latency table across {none, scalar-int8, binary+rescore}. This is the "99M multi-modal vectors served from 125 GB, no GPU, p95 < Y ms" systems contribution. Pure measurement, no model training.

Supporting (cheap, high-differentiation): the **protein dual-similarity eval (C4)** — ESM-2 vs DIAMOND vs RRF on a remote-homology set, CPU-only.

## B.6 Prioritized "add before submission" checklist

**P0 — correctness / truth-of-claims (reviewers WILL hit these):**
1. Fix the cosine-on-binary-ECFP bug → recreate `patents_compounds` with Tanimoto/Jaccard + binary quant (also large RAM cut). Without this C3 is false.
2. Create payload indexes (CT phase/status, patents date/cpc/assignee, compounds MW/formula) → makes C6 true.
3. Fix CT point-id non-idempotency (orphaned-vector leak on rebuild) *before* rebuilding the CT collection you cite.
4. Pin env + model revisions (conda/pip lock, HF commit hashes); deterministic point-id spec → C8 + FAIR.

**P1 — the evaluations that make it a paper:**
5. Run the retrieval benchmark (C2). *Single most important missing item.*
6. Formalize the incremental-update study (C5).
7. System/latency + quantization benchmark (C7/H2).
8. One end-to-end MCP cross-modal case study (C9) — wire the unregistered text-search tools first.
9. Protein dual-similarity eval (C4).

**P2 — reviewer-proofing:**
10. Pick the axis you DO win (breadth / cost-per-M-vectors / update-cost / self-hosted footprint) and tabulate vs MedCPT-only / managed DB / single-vertical incumbent.
11. Public artifact + Zenodo DOI (sample collection + similarity TSVs + regeneration recipe — full 615GB can't go on Zenodo).
12. Minimal demo surface (small hosted MCP endpoint + 1-page query UI screenshot — helps any OUP venue).
13. Deletion-handling answer in Methods (deleted.pmids downloaded, not applied).
14. Explicit paragraph defusing the "mere aggregation" critique (embeddings + id-keyed join + incremental machinery = derived resource).

## B.7 Honest novelty-risk summary

- **HIGH risk** leading with "MCP" or "biomedical vector search" — both crowded; reviewer says "incremental."
- **LOW–MED risk** leading with the conjunction (4 modalities × 99M × self-hosted-no-GPU × id-keyed incremental × MCP). No surfaced paper does all of it.
- **Two hard truths to state plainly:** (1) embeddings are dated, **not SOTA** — claim cost/breadth/reproducibility; (2) it's a **single-box SPOF** — claim cost/ownership, not HA. Pre-empting both makes the paper credible, not over-claimed.

---

## Appendix — load-bearing file paths
- `/data/bioyoda/config/config.yaml` — encoders (`:33,79,156`), MedCPT comment (`:32`), esm2 (`:265`), compounds_hnsw_on_disk
- `/data/bioyoda/modules/qdrant/scripts/insert_from_faiss.py` — quantization (`:237-240`), **compounds Distance.COSINE (`:257`)**, point-id idempotency (`:81-151`), CT delete (`:416-457`); **no payload-index calls**
- `/data/bioyoda/modules/esm2/scripts/generate_embeddings.py:95` — mean pooling
- `/data/bioyoda/modules/patents/scripts/tracking.py:58` — `compute_patent_hash` (exists, unwired)
- `/data/bioyoda/modules/pubmed/scripts/index.py` — PMID-delta; deletions downloaded, not applied
- `/data/bioyoda/sugi-agent/modules/api/routes/{compound,protein}_similarity.py` — only search routes (the H1 blocker, being spun out)
- `/data/bioyoda/docs/PRODUCT_ASSESSMENT.md`, `/data/bioyoda/IRREPLACEABLE.md` — internal grounding

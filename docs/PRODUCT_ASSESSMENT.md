# sugi.bio — Comprehensive Product Assessment

*Lead-author synthesis of five grounded dimension assessments (pipeline/code, vector capabilities, ecosystem integration, product uniqueness, preprint angle). Every system claim is grounded in files read on disk; file paths are cited inline. Landscape claims are cited to external sources. Date: 2026-06-14.*

---

## 1. Executive summary

**What sugi.bio is.** A self-hosted, solo-built biomedical data platform with four complementary parts running on **one 32-core / 125 GB box, no GPU**:

1. **BioBTree** (`/data/biobtree`) — a *published* B+tree identifier-mapping & dataset engine (~95 datasets, chain-query syntax `BRCA1 >> ensembl >> uniprot >> pdb`, served gRPC `:9292` / web / MCP). The **deterministic / symbolic** layer: "what is true, what maps to what."
2. **Sugi Atlas** (`/data/sugi-atlas`) — deterministic curated written pages (29,337 genes / 18,616 diseases / 4,701 drugs), pure functions of a biobtree bundle. The **synthesis** layer.
3. **BioYoda** (`/data/bioyoda`, *this pipeline*) — the **semantic / vector** layer: five Qdrant collections, ~99M vectors total (pubmed_abstracts 28.95M · patents_text 38.74M · patents_compounds 30.94M · esm2 574,648 · clinical_trials ~554K rebuilding to ~4.6M). "What is similar / nearby."
4. **sugi-agent** (`/data/bioyoda/sugi-agent`) — the FastAPI multi-LLM agent that is the *only* surface where symbolic + semantic are reasoned over jointly.

**Core thesis.** The defensible asset is **the join, not any one corner.** Every individual capability has a stronger standalone incumbent (SureChEMBL for chemistry, UniProt/ESM Atlas for proteins, MedCPT/Consensus for literature, PrimeKG for curated KGs). What no one offers is *all four modalities joined through stable curated identifiers, owned end-to-end, reproducible, and answer-traceable, self-hosted at ~100M-vector scale with no GPU*. BioYoda's deepest and most underappreciated contribution is that it **distills its semantic neighborhoods into symbolic UniProt cross-reference edges** (`esm2_similarity`, `diamond_similarity`) that BioBTree then serves as first-class chain-queryable datasets — a working **bidirectional symbolic↔semantic loop**.

**The three biggest takeaways.**

1. **The data assets are excellent and rare; the vector engineering under-serves them.** Four modalities, ~99M vectors, self-hosted, paired with a published ID-mapping engine — that breadth is genuinely uncommon. But it is held back by one outright scientific correctness bug (cosine distance on binary ECFP fingerprints), **zero payload indexes** (filtered semantic search is full-scan, unusable at 30-38M points), three search capabilities **built-but-unwired** (PubMed/patents/trials search exists in the client but is not exposed as agent tools), and no cross-modal fusion despite having every ingredient.

2. **The product surface — not the data — is the gate.** sugi-agent is "the most churned, least complete piece"; the test harness aborts at the API step; `:8000` collides with the published BioBTree MCP. The differentiated *data* exists and is GREEN; the *query layer* that exposes it does not yet reliably run. **No positioning or paper fixes this — shipping a stable query/MCP surface is the gating move for both product and preprint.**

3. **There is a live correctness hazard in the orchestration during an active rebuild.** The clinical_trials point-id scheme is non-idempotent and silently leaks orphaned vectors on re-run unless `--update-mode` is passed (which no default orchestrator path passes). CT is being rebuilt to ~4.6M vectors *right now*. This must be fixed before the next refresh touches the irreplaceable DB.

---

## 2. Pipeline & code state

The infrastructure is the work of someone who has been operationally burned and learned: a clean bash command-dispatcher (`bioyoda.sh` + `scripts/lib/*.sh`), config-driven path construction that let the 2026-06-13 `work/raw_data` reorg move code with **zero Snakefile edits**, a genuinely good delete-guard (`assert_deletable` in `scripts/lib/common.sh`, refuses `/`, `/data`, repo-root, and anything under `raw_data|qdrant|snapshots`), and warranted insert resilience for an NFS/Singularity Qdrant (`upsert_with_retry` + `wait_for_green_status`). The PMID/compound delta-bootstrap pattern (`build_existing_pmids.py`, `build_existing_compound_ids.py`) is correct and proven. This is **solid**.

The risk concentrates in a long single-owner evolution. Top tech-debt, ranked by severity:

| # | Issue | Severity | Location |
|---|---|---|---|
| 1 | **CT point-id is non-idempotent → silent orphaned-vector leak.** `get_point_id_from_metadata` keys CT points on `hash(nct_id:global_chunk_id)`, but `global_chunk_id` is a **per-file counter that resets to 0 each chunk file** (`process_trials_chunk.py:84`, `process_trials.py:309`). On reprocessing, a section hashes to a *different* point id; plain upsert inserts a new point and orphans the old one. The remedy (`--update-mode`, delete-by-nct_id) is built only in the CT rule and **never passed by the default `full` path**. CT is rebuilding now → live. | **Correctness, do first** | `insert_from_faiss.py:81-125`, `:117` |
| 2 | **Qdrant Snakefile is 5× copy-paste** (~80-line shell blocks per collection). Divergence already started: `--vector-size 2048` is **hardcoded** in the compounds rule (line 527) while esm2 uses `{params.vector_dim}` and others rely on a 768 default — a silent dim-mismatch corruption risk. | High (maintainability) | `modules/qdrant/Snakefile` |
| 3 | **Delta machinery exists but is NOT wired into the orchestrator.** `grep existing-pmids\|existing-ids modules/*/Snakefile` → zero hits. The documented "incremental update" is reachable only via out-of-band hand-runs, not `bioyoda.sh run`. | High (consistency cliff) | `modules/{pubmed,patents}/Snakefile` |
| 4 | **GPU/CPU script twins have drifted.** Every module ships `*_gpu.py` parallel impls; the `global_chunk_id` logic is duplicated between `process_trials.py` and `process_trials_chunk.py` — exactly where bug #1 must be fixed in N places. On a no-GPU box these are dead weight that must still be kept in sync. | Medium-High | all `modules/*/scripts/*_gpu.py` |
| 5 | **Dual half-orchestrator state.** Snakemake (real data, no delta wiring) vs Enju (delta-aware paths but **fixtures/static fan-out**, `publish: mode: none`, git-commit-serialized draining). Every Enju run also leaves the worktree on a run branch. Two half-done orchestrators is the biggest *architectural* debt. | Medium-High (architectural) | `scripts/commands/enju.sh`, `workflows/*/enju.yaml` |
| 6 | **Per-vector FAISS reconstruct** (`for i: index.reconstruct(i)` vs `reconstruct_n`) — measurable insert tax at 38.7M points. `--enable-quantization` is a no-op default. | Medium (perf) | `insert_from_faiss.py:757-759, :960` |
| 7 | **Trackers loaded by `importlib` path-walking** (`dirname×3` of faiss_dir) — couples the insert script to runtime layout depth, exactly what the reorg perturbs. | Medium (fragility) | `insert_from_faiss.py:516-579` |
| 8 | **Reproducibility gaps.** No pinned env lockfile (`tamer.yml` referenced, no committed lock; model revisions unpinned → embedding drift on an *irreplaceable* DB). `datetime.now()` baked into every payload (`:781`). Per-file try/except + `--retries 3` **swallows partial-insert failures**, yet the `.done` marker still writes (`Snakefile:539`) → half-inserted collection looks complete. | Medium (correctness/repro) | `insert_from_faiss.py:781, :837-840` |
| 9 | **Thin/broken testing.** Harness aborts at a removed `api.sh` probe (`test.sh:19-23`). **No unit tests** for the load-bearing pure functions (`get_point_id_from_metadata`, `assert_deletable`, the delta skip-sets, `map_faiss_to_source_file`) — precisely where a silent bug corrupts the irreplaceable DB. | Medium | `scripts/commands/test.sh` |

**Verdict:** fix #1–#3 *before* the next CT/patents refresh. The infra is solid; the danger is the point-id hazard on the live rebuild, the insert-layer copy-paste where divergence already began, and the unfinished dual-orchestrator state.

---

## 3. Vector-DB capabilities & gaps

### Have (verified)
Four genuine modalities — literature (text), chemistry (structure), protein (sequence), trials (text) — that breadth *is* the differentiator vs. a single-corpus vector DB. Entity-hash point IDs (pmid/nct/patent/surechembl/protein_id) make additive incremental refresh idempotent (after the esm2 `protein_id`-hash fix, commit `c493051`). The big-three collections are HNSW-indexed on-disk (RSS ~30-50 GB, rest mmapped); esm2/CT are brute-force under the 1M threshold (fine at that size).

### Could-have (days of CPU work — converts "impressive corpus" into "usable platform")
1. **Tanimoto for compounds — fixes a real scientific bug.** ECFP/Morgan are **binary** fingerprints; chemists compare them with **Tanimoto/Jaccard**, but the collection is created with `Distance.COSINE` (`insert_from_faiss.py:257`, verified — no per-collection override exists; grep for tanimoto/jaccard/binary returns nothing). Cosine on binary vectors rank-orders *differently* from Tanimoto, and the score returned to users is mislabeled. Re-create with binary quantization + Jaccard: fixes correctness **and** cuts ~64× memory on the largest liability (2048-bit stored as float32). **High value, low effort.**
2. **Payload indexes — the single biggest usability win.** `grep create_payload_index` → **0 hits**. Rich filterable payload exists (CT `phase/overall_status/conditions`; patents `pub_date/cpc_codes/assignees`; compounds `molecular_weight/formula`) but **none indexed** → any "phase 3 AND recruiting" or "MW < 500" filter is a full scan, catastrophic at 30-38M points. Filtered semantic search — the dominant biomedical query pattern — is effectively unusable at scale today. A handful of `create_payload_index` calls fixes it.
3. **Register the text-search tools.** `search_pubmed`, `search_patents_text`, `search_clinical_trials` exist in `qdrant_client.py` but **only 4 tools are registered** (`factory.py:37-40`: 2 biobtree + protein + compound similarity) — verified. The reasoning agent cannot reach three of its four text modalities. Near-zero effort, unlocks literature/trials/patent semantic search for the agent.

### Missing (structural)
- **No hybrid dense+sparse (BM25) search.** Pure dense S-BioBERT misses exact-token matches — gene symbols, NCT IDs, CPC codes, accessions — exactly the identifiers biomedical users search by. Qdrant supports sparse vectors natively; unused.
- **No reranking** (single-stage ANN, no cross-encoder pass).
- **No deletion handling** — `deleted.pmids` downloaded but never applied; stale points accumulate.
- **Dated, mis-scoped models.** S-BioBERT is a symmetric STS encoder; for a *retrieval* workload an asymmetric retrieval model (MedCPT, query/doc-trained, the config's own commented-out alternative) would lift recall. ESM-2 650M mean-pool is a fine conservative choice.
- **Lossy patent chunking — wasted mined signal.** patents_text concatenates title+abstract+claims+description into one 768-d vector, then S-BioBERT **truncates at ~512 tokens / ~256 words** (`process_patents.py:190-209`). The expensive 174K USPTO full-text claims/description you mined are *mostly thrown away at embed time*. Multi-vector patents (separate title/abstract/claims) would recover it — but needs GPU re-embedding.
- **Inconsistent chunking across modalities** (1 vec/patent vs many/trial vs 1/abstract) makes cross-collection score-merging ill-defined.
- **Stale config:** `config.yaml` lists esm2 dim as 640 (or 480 in one place) but the live DB is 1280 — fix before it bites a rebuild.

---

## 4. Ecosystem integration

The four parts divide cleanly by **epistemic role**: BioBTree = symbolic facts (no false positives, only what's curated); Atlas = deterministic synthesis (curated pages, pure functions of a biobtree bundle); BioYoda = semantic similarity (high recall, probabilistic); sugi-agent = the only joint-reasoning surface. This factoring is genuinely well-designed and complementary.

**The shared grounding is the upstream accession** (UniProt `P01942`, ChEMBL/SureChEMBL, NCT, MONDO/EFO) — but it lives in *convention and per-ingester parsing code* (`extractUniProtID` in `protein_similarity.go`), **not** in any shared schema, registry, or event bus.

The integration edges, by how tightly wired they actually are:

- **BioYoda → BioBTree (semantically TIGHT, operationally LOOSE).** The most consequential link. BioYoda doesn't just dump vectors — it distills similarity into symbolic graph edges: `diamond_similarity` (dataset `id:39`, ingested by `src/update/protein_similarity.go`, which emits **real UniProt xrefs** so `P01942 >> diamond_similarity >> uniprot` becomes traversable) and `esm2_similarity` (`id:750`, `src/update/esm2_similarity.go`). A *learned ESM-2 neighborhood* and a *DIAMOND homology hit* both become the symbolic vocabulary the graph speaks. But the mechanism is a manual TSV hand-off across **hard-coded absolute snapshot paths**, no trigger — and two re-ingest items dangle in `issues.md`. Fragile.
- **BioBTree → BioYoda (the trials.json hand-off).** CT vectors are now built from biobtree's curated `trials.json` — so the vectors are **id-grounded at ingest**. The cleanest example of id-grounded embeddings in the stack.
- **Atlas → BioBTree (TIGHT, API-based).** The only tightly-coupled consumer (`atlas/biobtree/client.py`, direct `/ws/` transport, ~10× faster). Atlas pages are pure functions of a biobtree bundle.
- **Atlas → BioBTree-MCP (proposed, not built).** `ATLAS_MCP_INTEGRATION.md` (DRAFT) would serve Atlas summaries as MCP grounding — but **BioYoda is entirely absent from it.**
- **sugi-agent (the only true joint surface, least complete).** `protein_similarity_tool.py`/`compound_similarity_tool.py` each hold *both* clients (resolve gene→UniProt/ChEMBL via biobtree → vector-search → re-enrich via biobtree) — a real hybrid primitive, but the broken step in the revival.

**Making the stack more than the sum of its parts (ranked):**
1. **Graph-constrained vector search in sugi-agent (highest leverage, partially built).** Today biobtree only resolves-in and enriches-out. Instead use it to **constrain** the Qdrant query: "PubMed/patent neighbors of TP53 *restricted to* payload ids in `TP53 >> chembl_target >> chembl_molecule`." Qdrant payload filtering + biobtree allow-list converts probabilistic recall into id-grounded, citable recall. No new infra — a filter pushed into the existing client call. **(This is also exactly the same `create_payload_index` work as §3.2.)**
2. **Promote similarity export to an Enju refresh trigger, not a frozen path.** Make the esm2/diamond export an Enju task that writes the TSV *and* flips biobtree's `dataset_state`. Turns the loosest edge into an automated semantic→symbolic pipeline; kills the two dangling re-ingest items.
3. **Atlas surfaces BioYoda — close the missing edge.** `esm2_similarity` is *already in biobtree*, so an Atlas "Semantically nearest proteins" section needs **no new dependency** — one more `bbmap` chain `>> esm2_similarity`. Nearly free; the data already round-trips BioYoda→biobtree→Atlas.
4. **Tiered MCP router:** deterministic facts → curated Atlas synthesis → BioYoda semantic neighbors, decreasing-confidence, each citing ids. Makes the MCP a symbolic-*or*-semantic router rather than symbolic-only.
5. **Make the canonical-accession convention explicit** (one `IDENTIFIER_GROUNDING.md` + a tiny shared module) so the next collection can't silently key on a non-canonical id and fail to join.

---

## 5. Product direction & uniqueness

**Positioning thesis.** *sugi.bio is the only self-hosted, reproducible system that puts a deterministic biomedical ID-mapping graph and five modalities of domain embeddings behind one ID-grounded query surface, at ~100M-vector scale, on a single commodity box with no GPU.* The wedge is the **ID-grounded join**, not any single vertical.

**Lean into (real differentiators):**
- **Bidirectional graph↔vector exchange** (esm2/diamond TSV *into* BioBTree; trials.json *out*) — the headline; nothing public does both directions self-hosted.
- **Dual-similarity proteins** (ESM-2 semantic *and* DIAMOND alignment, both id-mapped — complementary: ESM-2 finds remote functional homologs, DIAMOND finds sequence-identity hits; RRF fusion beats either alone).
- **Dual-modality chemistry** (patent *text* + Morgan *structure* in one patent id space).
- **Entity-hash point IDs** → idempotent additive refresh.
- **Irreplaceable corpora** (dead-source 519K USPTO-chem mirror per `IRREPLACEABLE.md`; broken-endpoint AACT) — a data moat that cannot be re-acquired.
- **Published, citable graph core** (BioBTree, F1000Research) — credibility most vector startups lack.

**Honest competitive read — where sugi.bio is NOT differentiated:**
- **The graph is shallower than purpose-built KGs.** BioBTree maps *ids*; it does not curate the deep typed relationship layer that PrimeKG (4.05M typed edges; 2026 Overton Prize) or Hetionet (29 relation types) encode. For drug-repurposing reasoning those are stronger.
- **Embeddings are dated** (S-BioBERT, ESM-2 650M, 2021-22 vintage). A retrieval-quality benchmark would likely show sugi.bio's vectors trailing MedCPT/ESM-3-class SOTA — and re-embedding 99M points is GPU-weeks the constraint forbids. **The most material technical gap.** Do **not** claim IR SOTA.
- **Generic vector DBs win on ops/scale/latency.** A single 125 GB box is a SPOF with no HA/sharding. sugi.bio wins on cost + ownership + curation, not infra robustness.
- **Each vertical has a stronger incumbent** (SureChEMBL, UniProt/ESM Atlas/AlphaFold DB, ClinicalTrials.gov/AACT, PubMed/Consensus/Elicit). If a user needs *one* vertical, an incumbent beats it.
- **Frontier LLMs are absorbing the easy middle.** The durable defense is exactly what generic models lack: deterministic id round-tripping, structure search, reproducibility, provenance. Sell *traceable evidence at scale*, not "ask biomedical questions."
- **The query/agent surface is the weakest link today** — and no positioning fixes that.

**Recommended direction.** Lead with **(A) an ID-grounded MCP retrieval backend** built on **(B) the patent-chemistry + literature competitive-intelligence bundle** (38.7M patent text + 30.9M structures + 28.9M PubMed + the irreplaceable mined corpus). It (a) uses assets that already work, (b) sits where the ecosystem is converging (domain MCP servers, e.g. SureChEMBL-MCP, 2025), and (c) plays to the one thing frontier LLMs and generic vector DBs both lack. **Gate:** fix the `:8000` collision and orphaned API seam first.

---

## 6. Prioritized recommendations

Single ranked table, impact × effort. **P0 = correctness/gating, do before next refresh.**

| Rank | Action | Impact | Effort | Files |
|---|---|---|---|---|
| 1 (P0) | **Fix CT point-ids:** replace `global_chunk_id` keying with deterministic `hash(nct_id:chunk_type:chunk_id)`, OR make delete-by-nct_id unconditional for CT. Stops silent orphan accumulation on the live rebuild. | Very high | Low | `insert_from_faiss.py:81-125` |
| 2 (P0) | **Tanimoto/Jaccard for compounds** + binary quantization. Fixes the cosine-on-ECFP scientific bug, honest score label, ~64× memory cut. | Very high | Low-Med | `insert_from_faiss.py:257` |
| 3 (P0) | **Create payload indexes** (CT phase/status/conditions; patents pub_date/cpc/assignees; compounds MW/formula). Turns filtered search from full-scan to instant. | Very high | Low | new `create_payload_index` calls |
| 4 (P0) | **Register text-search tools** (`search_pubmed/_patents_text/_clinical_trials`) with the agent. Unlocks 3 modalities the reasoning engine can't currently reach. | High | Very low | `sugi-agent/.../tools/factory.py:37-40` |
| 5 (P1) | **Stabilize the query surface:** resolve `:8000` collision with biobtree MCP, remove orphaned `api.sh` seam, un-break the test harness. **The product + preprint gate.** | Very high | Med | `scripts/commands/test.sh`, sugi-agent |
| 6 (P1) | **Graph-constrained vector filtering** in sugi-agent (biobtree allow-list → Qdrant payload filter). Probabilistic → citable recall. Reuses #3. | High | Low-Med | `protein/compound_similarity_tool.py`, `qdrant_client.py` |
| 7 (P1) | **Wire delta flags into Snakemake module rules** (`--existing-pmids/--existing-ids` gated on `update_mode`), or formally retire Snakemake. | High | Low-Med | `modules/{pubmed,patents}/Snakefile` |
| 8 (P1) | **De-duplicate the 5 Qdrant insert rules** into one wildcard rule / shared `insert.sh`; remove hardcoded `--vector-size 2048`, use per-collection config. | High (maint) | Med | `modules/qdrant/Snakefile:527` |
| 9 (P1) | **Add unit tests** for `get_point_id_from_metadata`, `assert_deletable`, `map_faiss_to_source_file`, delta skip-sets. Tiny surface, guards the irreplaceable DB. | High | Low | new `tests/` |
| 10 (P2) | **Automate similarity export as Enju trigger** that also flips biobtree `dataset_state`; clear the two dangling re-ingest items. | Med-High | Med | `scripts/commands/enju.sh`, biobtree datasets |
| 11 (P2) | **Decide one orchestrator.** Finish Enju (dynamic `list<string>` fan-out, batched tasks, real-data run, `track:false`) and retire Snakemake — or keep Snakemake and mark Enju experimental. Don't ship both half-done. | High (arch) | High | `workflows/*/enju.yaml` |
| 12 (P2) | **Atlas "nearest proteins/related literature" section** via the already-present `esm2_similarity` chain. | Med | Low | sugi-atlas templates |
| 13 (P2) | **Collapse GPU/CPU twins** into device-parameterized cores; kill duplicated `global_chunk_id` logic. | Med | Med | `modules/*/scripts/*_gpu.py` |
| 14 (P2) | **Batch FAISS `reconstruct_n`**; fix `--enable-quantization` no-op; make trackers importable modules; don't bake `datetime.now()` into payloads. | Med | Low-Med | `insert_from_faiss.py:757, :516-579, :781` |
| 15 (P3) | **Hybrid dense+sparse search** (gene symbols/NCT/CPC exact + concepts semantic). | High | Med-High | qdrant collections |
| 16 (P3) | **Pin environment** (conda/pip lock + model revisions) for the irreplaceable DB. | Med | Low | `tamer.yml` lock |
| 17 (P3, GPU) | **Multi-vector patents** (title/abstract/claims) + S-BioBERT→MedCPT swap. Recovers the wasted 174K full-text signal. | High | High (GPU-weeks) | `process_patents.py:190-209` |

---

## 7. Preprint plan

**Publishability boundary (honest).** BioBTree is already published (F1000Research 8:145 + v2 preprint) — re-claiming it is self-overlap. Enju has its own preprint. **What has never been written up is BioYoda (the vector half) and its bidirectional coupling to the symbolic engine.** That is the paper.

**Recommended thesis (angle c + d):**
> *Identifier-grounded multi-modal retrieval: coupling a symbolic biomedical identifier-mapping engine with a 100M-vector, multi-modal vector store on a single commodity server.* Every embedded record across four modalities is keyed to a stable curated identifier, making the vector store a first-class, addressable participant in deterministic cross-database id-mapping — not an opaque text index. Id-grounding yields (i) **entity-delta incremental updates** (embed only new ids, not re-embed all) and (ii) a **bidirectional symbolic↔semantic loop** (ESM-2/DIAMOND similarity exported as curated relationship datasets into the engine; the engine's curated trial extractions consumed as embedding inputs). Built and served on one 32-core/125 GB box, no GPU.

This is the only combination that is both genuinely novel *and* ~70% backed by artifacts already on disk. A generic "integrated platform" paper is weak (Bio2RDF, Monarch, Open Targets, Pharos exist); the novel seam is the *bidirectional bridge*, not "a graph next to a vector DB."

**Key claims & evidence status:**

| Claim | Evidence | Baseline | Metric | Status |
|---|---|---|---|---|
| C1: Id-grounding enables entity-delta updates near-free | PubMed 2025→26: ~695K embedded of 29M; compounds +86,889; esm2 +987; USPTO +174,058, 0 clobbered | naive full re-embed | embedding-work reduction × ; merged-collection correctness | **EXISTS (strong); need one anchored full-rebuild baseline timed on this box** |
| C2: Bidirectional symbolic↔semantic loop adds capability neither side has | diamond/esm2 TSV → biobtree xref datasets (chain-queryable); trials.json → vectors | vector-only (no id pivot) | answerable@k for cross-DB linked answers; id-join precision | **PARTIAL — plumbing verified at file level; the headline; needs a worked end-to-end query set + biobtree re-ingest (pending in `issues.md`)** |
| C3: Id-grounded RAG beats text-only RAG on mechanism-level answers | existing 50-Q drug→target harness (`old/benchmark_bte_rag/`), curated error analysis (10-12/50 better via biobtree, e.g. Octreotide→SSTR2) | text-only dense RAG + LLM-only | mechanistic precision; ablate id-enrichment | **PARTIAL — re-run existing code on revived stack (API seam rotted, port 8000 now biobtree)** |
| C4: 100M+ multi-modal vectors built *and served* on one no-GPU box | 5 collections audited GREEN, dims/index/615 GB storage; cluster 512 GB-VSZ failure as clean before/after | the failed cluster attempt | build CPU-h; storage; **latency p50/p95, QPS, HNSW recall@k vs flat** | **EXISTS for build; MISSING for serving (latency/recall never measured)** |
| C5: Reproducible / provenance-tracked | DAG + per-task git-commit provenance (Enju); `IRREPLACEABLE.md` protections | — | — | **PARTIAL — Enju proven on fixtures only; scope claim to "Snakemake-orchestrated, Enju-portable" or run one real modality through Enju** |

**Related work to position against:** MedCPT / BioASQ / MedRAG (single-modality IR — orthogonal: claim grounding+multimodality, *not* encoder quality; note honestly S-BioBERT < MedCPT). Bio2RDF / Monarch / Open Targets / Pharos / BioThings (symbolic, no vectors). UniProt-IDmapping / bioDBnet / g:Profiler / biobtree itself (id-mapping — biobtree is the substrate, cite don't re-claim). ESM-2 / DIAMOND / Morgan-ECFP (standard components). Qdrant / FAISS / Milvus (the no-GPU single-box entity-delta operating point is the systems contribution). PrimeKG / Hetionet (richer curated KGs — concede the deep-relationship gap).

**Paper outline:** (1) Intro — the grounding gap, contributions C1-C4; (2) Related work; (3) System design — four modalities, embeddings, id-as-point-id hashing (and the esm2 collision hazard + fix); (4) Id-grounding & entity-delta — **Table 2, the money table**; (5) Symbolic↔semantic coupling — export + consume + worked chain query; (6) Systems & reproducibility — single-box, cluster-failure contrast; (7) Evaluation — drug→target benchmark, latency/recall, ablations (±id-grounding, optional MedCPT vs S-BioBERT); (8) Limitations — S-BioBERT not SOTA, additions-only delta (revisions/deletions un-purged), single-node ceiling, irreplaceable-data fragility, the patents truncation; (9) Availability.

**Hardest-to-get evidence, ranked:**
1. **The worked bidirectional-loop query set (C2)** — exists only as file plumbing; biobtree-side re-ingest still pending. Without a retrieval result it's an architecture diagram, not a finding. **Highest priority, and blocked on the same query-surface gate as the product (rec #5).**
2. **Serving latency/QPS/recall@k (C4)** — never measured, yet "served" is in the thesis.
3. **One anchored full-rebuild baseline (C1)** — current reduction factors lean on estimates.

~70% of the evidence is on disk; the remaining ~30% (a worked loop query, serving numbers, one rebuild baseline, a benchmark re-run) is buildable on the current box with no new data and no GPU — which is itself consistent with the paper's central claim.

---

*Note: `docs/ALVESSA_VS_BIOYODA_COMPARISON.md`, `notes2.txt`, `usecases.txt`, `todo.txt` are 0-byte/empty on disk — no competitive notes were available, so §5's competitive read is built from the external landscape directly.*

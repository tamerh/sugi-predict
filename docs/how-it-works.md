# How Sugi Predict works

Sugi Predict is an open, reproducible **predicted-target atlas of patent chemical
space**. Every drug-like patent compound extracted from SureChEMBL (~30.9M) is
annotated with its likely human protein targets, joined to the patent provenance
that says who claimed which chemistry against which target. This page explains the
method and the engine beneath it. To run it, see
[getting-started.md](getting-started.md); for the wire format see [api.md](api.md)
and [cli.md](cli.md); for the engine's place in the family see
[../README.md](../README.md).

Sugi Predict is the predictive member of the [sugi.bio](https://sugi.bio) family —
alongside BioBTree (identifier grounding), Sugi Atlas (a deterministic reference
catalog), and Enju (workflow orchestration). The engine's internal codename is
`bioyoda`; you will see it in paths and scripts.

## The one principle: similar molecules, similar targets

Everything rests on the **molecular-similarity principle** — structurally similar
molecules tend to bind the same proteins. This is the same well-established idea
behind SEA, SwissTargetPrediction, and PPB2; Sugi Predict's contribution is not a
new algorithm but running that established method *openly and reproducibly over the
entire patent record*, with held-out validation and honest confidence on every call.

A prediction is therefore an explicit, limited statement: **"this molecule lies in
the chemical neighbourhood of known ligands of target X"** — not an assertion that
it binds X. Patent membership, chemical proximity, and confirmed activity are three
distinct things; we claim only the first two.

## Prediction by chemical k-NN

The "answer key" is a ligand→target reference assembled from ChEMBL: **1,248,456
distinct compounds** across **7,929 protein targets** (~2.8M ligand→target
associations, uncapped — every reported ligand per target is kept). Each compound is
a Morgan/ECFP4 fingerprint (radius 2, 2048-bit, RDKit); similarity is the **exact
Tanimoto coefficient**, computed by an FPSim2 index.

For a query molecule, the engine retrieves its nearest reference ligands and
transfers their targets ([`modules/compounds/target.py`](../modules/compounds/target.py)):

- It takes the **top `KNN = 20`** nearest ligands above a Tanimoto floor of
  **`MIN_TAN = 0.30`**.
- Each candidate target gets two numbers:
  - **confidence** — the best Tanimoto from the query to any known ligand of that
    target (the calibrated quality score);
  - **support** — how many of those top-20 nearest ligands back the target (the
    discriminator that separates a real hit from noise when several targets tie at
    confidence 1.00, e.g. EGFR 18/20 vs. a coincidental 1/20).
- Targets are ranked by confidence, then support, then vote weight, and reported at
  the **human gene** level — non-human orthologs are collapsed to their human
  counterpart, which alone lifts top-1 recovery on the drug panel from 44% to 56%.

**The abstention is the honest core.** Below a nearest-neighbour Tanimoto of 0.3 a
query has no close known analogue. It is labelled **novel** (chemical whitespace)
and is *not* given a confident prediction — it is flagged to be read with caution.
Confidence bands: HIGH ≥0.5, MODERATE ≥0.4, LOW ≥0.3, NOVEL below.

## Patent-scale annotation and the two directions

The same procedure is run over **30,937,359** SureChEMBL patent compounds; the
drug-like subset (≥10 heavy atoms, excluding solvents and fragments) yields target
annotations for **30,046,840** compounds. The expensive neighbour search is run
**once** (on GPU, exact-Tanimoto), storing each compound's raw nearest neighbours;
ranking and confidence are then computed cheaply and locally, so scoring can be
re-tuned without re-searching. Of the annotated compounds, **39.8%** are
high-confidence (≥0.5), **68.4%** reach ≥0.4, and only **6.5%** are novel whitespace
(median nearest-ligand Tanimoto 0.457) — the uncapped reference leaves little of
drug-like patent chemistry unreachable, though reliability falls with similarity.

One index, **two query directions**:

1. **compound → predicted targets** — what is this molecule likely to hit?
2. **target → patented chemistry** — invert the index to get the patented chemical
   matter predicted against a target, *and who claimed it*.

## Patent provenance: the join

Because every compound carries its SureChEMBL identifier, the predicted landscape
joins directly to **patent provenance**
([`provenance` in `mcp_srv/engine.py`](../mcp_srv/engine.py)): for each compound,
the patent number(s), assignee, publication date, and whether the compound is
**claimed** versus merely **disclosed**. This turns a compound list into an
attributable view of who is patenting which chemistry against a target.

A foundational + current-frontier span of patents is **baked into the
`patent_compounds` payload** (`prov = {n, noise, patents}`) by
[`modules/compounds/bake_provenance.py`](../modules/compounds/bake_provenance.py),
so a lookup reads the payload directly instead of scanning the multi-billion-row
SureChEMBL parquet; anything not baked falls back to the live parquet join. The
`noise` flag marks ubiquitous tool compounds (e.g. imatinib, ~124k patents) that
appear in most patents only *incidentally* — those patents say nothing about the
compound's target, so the patent-text check below is suppressed for them. Only
publication date is available locally; priority/filing dates would need external
family enrichment.

## The supporting substrate (context, not predictor)

The engine holds a small multi-modal substrate beyond chemistry. It is **retrieval
context, explicitly not a predictor** — chemical similarity is the *only*
relationship validated as predictive here. Two candidate predictive routes were
tested on the same harness and **dropped** because they did not beat baseline:
peptide sequence-embedding similarity (chance) and protein-homology repurposing
(below random). Only ligand→target chemical similarity survived.

| Modality | Embedding | Vectors | Role |
|---|---|---|---|
| Patent compounds | Morgan ECFP4 (2048-bit, binary) | ~30.9M | the predictor |
| Patent text | MedCPT (768-d) | ~39.6M | context + consistency check |
| Clinical trials | MedCPT (768-d) | ~4.5M | retrieval context |
| Proteins (UniProt/SwissProt) | ESM-2 (1280-d) | ~0.57M | selectivity context |
| ChEMBL reference | Morgan ECFP4 (2048-bit, binary) | ~1.25M | the answer key |

Trials and proteins are queried by similarity to surface relevant context around a
target; they never inform a prediction.

## The patent-text consistency check (honest framing)

A panel on the compound page asks: does the compound's own **patent abstract** rank
its chemistry-predicted target highly? We score the patent text against every human
target with a biomedical sentence encoder
(MedCPT), debias against a background of generically text-proximal targets, and
count a target as supported when it lands in the text's **top 10 of 4,885**
([`patent_text_support` in `mcp_srv/engine.py`](../mcp_srv/engine.py)). No model runs
at request time — both sides are precomputed, L2-normalised vectors and the check is
a dot product.

Read this signal carefully, because the project's credibility depends on not
overstating it:

- It is a **weak, abstract-level consistency check** — the patent's own text is
  *about* the predicted target — **not independent corroboration** of binding. It
  reflects the inventor's stated purpose, and the available text is usually an
  abstract, not a full specification.
- It is available for only **~1 in 7** of the patents linked to atlas compounds
  (about 1.4% of all patents have machine-readable text).
- Where available, it agrees with the support-ranked landscape for **~47%** of
  full-text compounds (vs. 0.2% for a random target), and the agreement climbs with
  **support** (6.5% at one supporting neighbour → 38.6% at eight or more) — so
  support, not raw confidence, is the operative quality knob.
- It is strongly **target-class dependent**: high for proteins that are the *subject*
  of patents (nuclear receptors, aminergic GPCRs 90–100%, EGFR 73%), low for those
  appearing as selectivity counter-screens (hERG, SCN5A 2–4%). It survives a strict
  same-classification null (~14× gap), so it is genuinely — but only weakly —
  independent. We read it as corroborating, never confirmatory.

## Validation — lead with the realistic number

The predictor is tested on held-out data, not asserted to work. The
**deployment-realistic figure is a temporal split: recall@1 ≈ 41% (40.8%)**, recall@5
55.8% — trained on ligands disclosed up to 2018, tested on later compounds with all
post-cutoff chemistry excluded from the neighbour pool. That is the regime the atlas
actually runs in (predicting targets for newly disclosed patent chemistry).

The easier splits are **interpolation upper bounds**, not the deployment number:
leave-one-out recall@1 83.0%, scaffold split 77.0%. Accuracy throughout is
**proportional to chemical similarity to prior art** — 76% recall@1 where a
pre-cutoff analogue at Tanimoto ≥0.7 exists, falling to ~23% in the 0.3–0.5 band
where genuinely new chemistry lands. On the temporal split the deployed
confidence+support ranking (40.8%) beats single-NN transfer (37.5%), a SEA-style
set-size correction (32.2%), naive Bayes over fingerprint bits (20.8%), and the
popularity floor (0.4%); the k-neighbour aggregation earns its margin further down
the list (recall@10 61.0% vs. single-NN 48.5%). The reverse (landscape) direction is
a precision question: 20% at confidence ≥0.5 rising to 52% at ≥0.7, lower-bounded
because ChEMBL annotations are sparse. Scripts live in
[`../validation/`](../validation/).

## The engine: CPU-served, millisecond, reproducible

Data processing and serving are deliberately separated. Building a collection's
vectors uses GPU and a strong per-modality embedder — a cost paid once per refresh —
while **serving runs on CPU with no query-time GPU**.

All vectors live in **Qdrant** ([`mcp_srv/engine.py`](../mcp_srv/engine.py),
[`modules/qdrant/collection_profiles.py`](../modules/qdrant/collection_profiles.py)).
Memory is the binding constraint, so the build is engineered around it: fingerprints
use **binary quantization** (kept in RAM, ~8GB, ~Tanimoto); the large dense text
collections keep full vectors **on disk** (mmap) while the HNSW graph stays in RAM
for low latency; the store runs in a memory-capped container. All ~77M vectors are
searched in **4–6 ms** holding ~18 GB resident on a single 32-core server. The
collections served, keyed by modality:

- `patent_compounds` — chemical, 2048-d (the unified compound collection: structure
  + baked predictions + provenance; a Qdrant alias → `patent_compounds_v2`)
- `chembl` — chemical, 2048-d (the reference ligands)
- `clinical_trials_medcpt` — text, 768-d
- `patents_text` — text, 768-d (alias → `patents_text_medcpt`)
- `esm2` — protein, 1280-d

The engine is the **single source of truth**: the REST API and the MCP server both
call the same three primitives — **`query`** (retrieve by filter or by similarity,
embedding free-text / SMILES / protein server-side), **`predict`** (rank a molecule's
targets), and **`provenance`** (resolve a compound to its patents) — so a researcher,
a programmatic client, and an autonomous agent all get **identical answers**. The web
atlas is a separate HTTP consumer of this same engine.

## The build pipeline

Every collection rebuilds from source via `./bioyoda.sh build <collection>`. The
neighbour search is the one expensive step; everything downstream is a deterministic
function of the reference set and the patent corpus, so the annotation is regenerated
whenever either is refreshed, and updates apply by deterministic-identifier upsert
rather than full rebuild. Orchestration is **bash `build` steps + Enju workflow DAGs**
— there is no Snakemake (the old Snakefiles are retired). Small-data fixture tests run
with `./bioyoda.sh test [--atlas]`. BioBTree handles raw-source grounding (resolving a
target to its gene/protein, a compound to its registry ids) — a light convenience
layer over the vector pipeline, not a pillar of the method.

## See also

- [getting-started.md](getting-started.md) — install and first query
- [api.md](api.md) — the REST surface
- [cli.md](cli.md) — the command-line tools
- [../README.md](../README.md) — the engine in the sugi.bio family

"""Per-collection build profiles for BioYoda's Qdrant collections.

The single source of truth for HOW each collection is built — derived from the configs proven
in production (2026-06). Consumed by scripts/rebuild_collection.py. The guiding lessons:

  * Match QUANTIZATION to the data + RAM budget (this is the real build lever, not segment size):
      - binary fingerprints (Morgan/ECFP4)  -> BINARY quant, always_ram (8GB fits RAM, ~Tanimoto,
        fast in-RAM build; int8-on-disk was 35x slower to query AND ~20h to build — avoid).
      - dense text/protein embeddings        -> scalar int8, always_ram=FALSE (quant mmap'd; the
        always_ram=TRUE default once pinned 144GB and froze the box — never use it at our scale).
  * Big collections that can't fit vectors in RAM -> vectors.on_disk=TRUE (mmap). HNSW graph stays
    on_disk=FALSE (in RAM) to keep query latency ~30ms. Hot/smaller collections keep vectors in RAM.
  * Build with indexing DEFERRED (high threshold) so the insert can't OOM, then trigger the HNSW
    build as a separate, monitored step (rebuild_collection.py does this).
  * Distance is Cosine everywhere; payload always on_disk.
"""

# Quant shorthands resolved in rebuild_collection.py
INT8 = {"type": "scalar_int8", "always_ram": False}   # dense embeddings (mmap quant)
BINARY = {"type": "binary", "always_ram": True}        # 0/1 fingerprints (in-RAM, ~8GB)

PROFILES = {
    "pubmed_abstracts_medcpt": {
        "dim": 768, "vectors_on_disk": False, "hnsw_m": 16, "hnsw_ef": 100,
        "quant": INT8,
        "faiss_source": "work/data/medcpt_output/pubmed",
        "query_encoder": "ncbi/MedCPT-Query-Encoder",       # asymmetric; corpus = Article-Encoder
        "notes": "hot literature; vectors in-RAM for lowest latency (~16ms). NOT currently served (no prod "
                 "PubMed collection at present); recipe kept live for `bioyoda.sh build text` + pubmed-update.",
    },
    "clinical_trials_medcpt": {
        "dim": 768, "vectors_on_disk": False, "hnsw_m": 16, "hnsw_ef": 100,
        "quant": INT8,
        "faiss_source": "work/data/medcpt_output/clinical_trials",
        "query_encoder": "ncbi/MedCPT-Query-Encoder",
        "notes": "multi-section trials; dedup results by nct_id at query time.",
    },
    "patents_text_medcpt": {
        "dim": 768, "vectors_on_disk": True, "hnsw_m": 32, "hnsw_ef": 256,
        "quant": INT8,
        "faiss_source": "work/data/medcpt_output/patents",
        "query_encoder": "ncbi/MedCPT-Query-Encoder",       # asymmetric; corpus = Article-Encoder (atlas text pipeline)
        "notes": "~39.6M patents (title + USPTO full-text where available), MedCPT-Article embeddings; "
                 "vectors on_disk (mmap) — too big for RAM; ~30ms queries. Served as `patents_text` (alias).",
    },
    "esm2": {
        "dim": 1280, "vectors_on_disk": False, "hnsw_m": 32, "hnsw_ef": 256,
        "quant": INT8,
        "faiss_source": "snapshots/esm2_latest/data/processed/esm2/embeddings",
        "query_encoder": None,  # protein: query is an ESM-2 vector (by protein_id) or raw embedding
        "notes": "574K proteins; small, vectors in-RAM. Mixed point-ids (legacy seq + delta hash).",
    },
    "chembl": {
        "dim": 2048, "vectors_on_disk": False, "hnsw_m": 32, "hnsw_ef": 256,
        "quant": BINARY,
        "faiss_source": None,   # built from work/chembl_reference/ via modules/qdrant/scripts/build_chembl_collection.py
        "query_encoder": None,  # compound: query is a Morgan/ECFP4 fingerprint (RDKit), like patents_compounds
        "notes": "683K ChEMBL ligands, Morgan r2/2048, BINARY quant, in-RAM. The ligand->target answer key as a "
                 "general target-labeled modality (payload: cid, smiles, targets[UniProt]). Symmetric with "
                 "patents_compounds; exact-Tanimoto prediction still uses the FPSim2 index (work/chembl_reference).",
    },
    # LEGACY raw-FP recipe (NOT the served collection). This rebuilds the structure-only Morgan-FP
    # collection from the Dec patents FAISS source. The SERVED compound collection is `patent_compounds`
    # (Qdrant alias -> patent_compounds_v2): raw FPs PLUS predictions/provenance/denoised targets, assembled
    # from work/atlas_nbrs by build_patent_compounds.py — there is no single FAISS dir for it, so it is built
    # via `bioyoda.sh build compounds ...` (ingest/provenance/denoise/build) and rebuilt via clean_copy.py ->
    # swap_alias.py, NOT via `qdrant rebuild`. Kept here only as the raw-substrate recipe; key left as-is so a
    # legacy raw rebuild still resolves. Do NOT point this at the served collection.
    "patents_compounds": {
        "dim": 2048, "vectors_on_disk": True, "hnsw_m": 32, "hnsw_ef": 256,
        "quant": BINARY,
        "faiss_source": "snapshots/patents_latest/data/processed/patents/compounds",
        "faiss_source_extra": ["work/data/processed/patents/compounds_new"],  # +86,889 parity batch
        "query_encoder": None,  # compound: query is a Morgan/ECFP4 fingerprint (RDKit)
        "notes": "LEGACY raw substrate (structure-only, no predictions): 30.94M fingerprints, BINARY quant "
                 "(always_ram, ~8GB) — built in 78min, ~17ms queries, 90% recall@100 vs exact Tanimoto. "
                 "Superseded as the served layer by patent_compounds (alias -> patent_compounds_v2), which "
                 "adds predictions/provenance and is built by `bioyoda.sh build compounds`, not from FAISS.",
    },
}

# Shared build/serving constants
DISTANCE = "Cosine"
MAX_SEGMENT_SIZE = 20_000_000     # big segments -> fewer HNSW merges per query (favors query speed)
MEMMAP_THRESHOLD = 500_000
DEFER_THRESHOLD = 100_000_000     # >> any collection -> NO HNSW build during insert (safe, no OOM)
BUILD_THRESHOLD = 20_000          # lower this post-insert to trigger the HNSW build
MAX_INDEXING_THREADS = 8          # bound the build burst so it doesn't starve prod/biobtree

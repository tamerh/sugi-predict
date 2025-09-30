# Qdrant Database Setup for BioYoda

This directory contains scripts and configurations for setting up and managing Qdrant vector database on the HPC cluster.

## Overview

**Migration Goal**: Import FAISS indices and metadata into Qdrant database for:
- Better metadata filtering and search
- Scalable vector database management
- Future multi-dataset support (PubMed, PMC, ClinicalTrials, etc.)

## Current Status

**Input Data**:
- `master_pubmed2.index` - 90GB FAISS index with ~1.4M vectors (768 dimensions)
- `master_metadata2.json` - 19GB metadata with PMID, titles, abstracts

**Target**: Qdrant database with proper collection structure and metadata indexing

## HPC Cluster Setup

**Environment**: SGE cluster with Singularity (no Docker)
**Approach**: Use Singularity containers for Qdrant deployment

## Directory Structure

```
scripts/qdrant/
├── README.md                    # This file
├── setup/
│   ├── singularity/            # Singularity container configs
│   └── qdrant_config.yaml      # Qdrant configuration
├── migration/
│   ├── migrate_faiss_to_qdrant.py    # Main migration script
│   └── batch_uploader.py             # Batch upload utilities
├── client/
│   ├── qdrant_client.py              # Qdrant client wrapper
│   └── search_interface.py           # Search API for Qdrant
└── jobs/
    ├── run_qdrant_server.sh          # Job script to run Qdrant
    └── run_migration.sh              # Job script for migration
```

## Next Steps

1. **Phase 1**: Set up Singularity container for Qdrant
2. **Phase 2**: Create migration scripts
3. **Phase 3**: Test with sample data
4. **Phase 4**: Full migration of PubMed data
5. **Phase 5**: Create search interface

## Future Datasets

- `pubmed/` - Current PubMed abstracts
- `pmc/` - PMC full-text articles (future)
- `clinical_trials/` - ClinicalTrials.gov data (future)
- `patents/` - Patent data (future)



Perfect! I've created a complete Qdrant setup for your HPC cluster. Here's what we've built:

  📁 Complete Qdrant Structure Created

  scripts/qdrant/
  ├── README.md                           # Documentation
  ├── setup_qdrant.sh                     # Main setup script
  ├── setup/
  │   ├── build_container.sh              # Builds Singularity container
  │   └── singularity/
  │       ├── qdrant.def                  # Singularity definition
  │       ├── config.yaml                 # Qdrant configuration
  │       └── qdrant.sif                  # (Will be created)
  ├── migration/
  │   └── migrate_faiss_to_qdrant.py      # FAISS → Qdrant migration
  └── jobs/
      ├── run_qdrant_server.sh            # Job script for Qdrant server
      └── run_migration.sh                # Job script for migration

  🚀 Quick Start Process

  1. Run the setup script:
  cd /data/scc/ag-gruber/GROUP/tgur/x/bioyoda/scripts/qdrant
  ./setup_qdrant.sh

  2. Start Qdrant server:
  qsub jobs/run_qdrant_server.sh

  3. Run migration (after server starts):
  qsub jobs/run_migration.sh

  🔧 What This System Does

  Migration Process:
  1. Loads your master_pubmed2.index (90GB) + master_metadata2.json (19GB)
  2. Extracts vectors in batches (memory-efficient)
  3. Uploads to Qdrant with proper metadata structure
  4. Creates searchable database with PMID, titles, abstracts

  Result: Your FAISS data becomes a proper database with:
  - ✅ Vector similarity search
  - ✅ Metadata filtering (by PMID, date, etc.)
  - ✅ REST API access
  - ✅ Scalable for future datasets

  🎯 Next Steps

  Once migration completes, you'll have a running Qdrant database that you can:
  - Query via REST API
  - Filter by metadata
  - Use for building better search interfaces
  - Scale to add PMC, ClinicalTrials, etc.
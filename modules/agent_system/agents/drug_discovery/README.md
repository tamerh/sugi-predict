# Drug Discovery Agent

A specialized agent for comprehensive disease-to-drug discovery queries using multiple evidence paths.

## Overview

The Drug Discovery Agent answers questions like "What drugs are available for glioblastoma?" by querying multiple biological databases through BioBTree and consolidating the results.

## Multi-Path Architecture

The agent uses a specialized `disease_drug_discovery` tool that runs multiple query paths internally:

### Working Paths

| Path | Source | Ontology | Query Chain | Status |
|------|--------|----------|-------------|--------|
| PATH 1 | Direct Indications | EFO | `disease >> efo >> chembl_molecule` | ✅ Working |
| PATH 2 | GWAS | EFO | `disease >> efo >> gwas >> ensembl >> drugs` | ✅ Working |
| PATH 3 | ClinVar | MONDO | `disease >> mondo >> clinvar >> ensembl >> drugs` | ✅ Working |

### Pending Paths (Code Ready, Awaiting BioBTree Links)

| Path | Source | Issue |
|------|--------|-------|
| PATH 4 | Reactome | No `efo >> reactome` link in BioBTree |
| PATH 5 | UniProt | No `efo >> uniprot` link in BioBTree |

## Example Results (Glioblastoma)

```
PATH 1 - Direct Indications: 12 drugs (Phase 3+)
  - BEVACIZUMAB (Phase 4 - Approved)
  - salinosporamide A (Phase 3)

PATH 2 - GWAS: 5 genes -> 303 drugs
  Genes: TP53, MPG, EGFR, SLC16A8, TERT

PATH 3 - ClinVar: 3 genes -> 160 drugs
  Genes: FGFR2, KIF5C, ALK
  Notable: ALK has drugs like CERITINIB (known ALK inhibitor)

Total: 8 unique genes, 463+ drugs
```

## Tool Parameters

```python
disease_drug_discovery(
    disease="glioblastoma",        # Disease name or EFO/MONDO ID
    min_indication_phase=3,        # Phase 3+ for direct indications (default: 3)
    include_gwas=True,             # Include GWAS genetic associations
    include_clinvar=True,          # Include ClinVar variant associations
    include_reactome=True,         # Include Reactome pathways (pending)
    include_uniprot=True           # Include UniProt annotations (pending)
)
```

## Key Files

```
agents/drug_discovery/
├── README.md           # This file
├── agent.py            # Agent class with routing logic
├── prompt.txt          # System prompt for LLM
├── chains.yaml         # Query chain definitions
├── examples.yaml       # Few-shot examples
└── backup_multipath/   # Backup of LLM-orchestrated approach

tools/
└── disease_drug_tool.py  # Specialized tool (runs all queries internally)
```

## Technical Details

### Two-Step Gene-to-Drug Mapping

For gene-based paths (GWAS, ClinVar), we use a two-step approach:

1. **Step 1**: Get genes associated with disease
   - GWAS: `disease >> efo >> gwas >> ensembl`
   - ClinVar: `disease >> mondo >> clinvar >> ensembl`

2. **Step 2**: Map genes to drugs via ChEMBL
   ```
   genes >> ensembl >> uniprot >> chembl_target_component
         >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule
   ```

### Why Specialized Tool vs LLM Orchestration?

We initially tried having the LLM orchestrate multiple BioBTree queries, but:
- Different models had varying reliability (Llama skipped queries, Gemini hallucinated)
- Claude Haiku worked best but still added latency
- Specialized tool is faster, more reliable, and model-agnostic

### Indication Phase Filtering

The tool filters by **indication-specific phase**, not drug-level phase:
- A drug might be Phase 4 overall but only Phase 2 for a specific disease
- We filter based on the phase for the queried disease specifically

## BioBTree Path Discovery Notes

Available links from EFO:
- `efo >> gwas` ✅
- `efo >> chembl_molecule` ✅
- `efo >> clinvar` ❌ (use MONDO instead)
- `efo >> reactome` ❌
- `efo >> uniprot` ❌

Available links from MONDO:
- `mondo >> clinvar` ✅
- `mondo >> clinvar >> ensembl` ✅

## Future Work / TODOs

1. **Reactome Integration**: Find correct ontology path (try MONDO?)
2. **UniProt Integration**: Find correct ontology path
3. **Pathogenic Filter**: Add ClinVar pathogenic variant filter
   - Syntax issue: `clinvar[clinvar.germline_classification=="Pathogenic"]` errors
4. **Gene Deduplication**: Merge overlapping genes across sources
5. **Drug Ranking**: Rank drugs by evidence strength (multiple sources)
6. **Response Formatting**: Improve agent's response formatting

## Usage

```python
from modules.agent_system.tools.disease_drug_tool import DiseaseDrugDiscoveryTool
from modules.agent_system.core.config import get_config
from modules.agent_system.integrations.biobtree_client import create_biobtree_client

config = get_config()
client = create_biobtree_client(config.integrations.biobtree)
tool = DiseaseDrugDiscoveryTool(client)

result = await tool.execute("glioblastoma", min_indication_phase=3)

if result.success:
    data = result.data
    print(f"Direct indications: {data['direct_indications']['count']}")
    print(f"GWAS genes: {data['gwas_targets']['genes']}")
    print(f"ClinVar genes: {data['clinvar_targets']['genes']}")
```

## History

- **Initial**: LLM-orchestrated multi-path queries (backup in `backup_multipath/`)
- **Current**: Specialized tool with parallel query execution
- **ClinVar Fix**: Changed from EFO to MONDO ontology for ClinVar access

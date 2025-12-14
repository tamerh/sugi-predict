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
| PATH 2 | GWAS | EFO | `disease >> efo >> gwas >> ensembl >> ChEMBL drugs` | ✅ Working |
| PATH 3 | ClinVar | MONDO | `disease >> mondo >> clinvar >> ensembl >> ChEMBL drugs` | ✅ Working |
| PATH 6 | PubChem FDA | - | `genes >> ensembl >> uniprot >> pubchem_activity >> pubchem[fda_approved]` | ✅ Working |
| PATH 7 | Reactome Pathways | - | `genes >> ensembl >> reactome` | ✅ Working |
| PATH 8 | Similar Proteins | Qdrant ESM-2 | 573K SwissProt proteins | ✅ Working |
| PATH 9 | Similar Compounds | Qdrant Morgan FP | 30.8M patent compounds | ✅ Working |

### Pending Paths (Code Ready, Awaiting BioBTree Links)

| Path | Source | Issue |
|------|--------|-------|
| PATH 4 | Reactome | No `efo >> reactome` link in BioBTree |
| PATH 5 | UniProt | No `efo >> uniprot` link in BioBTree |

## Example Results (Glioblastoma)

```
PATH 1 - Direct Indications (ChEMBL): 12 drugs (Phase 3+)
  - BEVACIZUMAB (Phase 4 - Approved)
  - salinosporamide A (Phase 3)

PATH 2 - GWAS (ChEMBL): 5 genes -> 303 drugs
  Genes: TP53, MPG, EGFR, SLC16A8, TERT

PATH 3 - ClinVar (ChEMBL): 3 genes -> 160 drugs
  Genes: FGFR2, KIF5C, ALK
  Notable: ALK has drugs like CERITINIB (known ALK inhibitor)

PATH 6 - PubChem FDA-approved: 3 genes -> 154 drugs
  FDA-approved drugs from PubChem bioactivity data

PATH 7 - Reactome Pathways: 7 genes -> 156 pathways
  ALK: ceritinib-resistant ALK mutants (disease), Disease
  CDKN2A: Defective Intrinsic Pathway for Apoptosis (disease)
  EGFR: Clathrin-mediated endocytosis, Cargo recognition...

Total: 7 unique genes, 312+ ChEMBL drugs, 154 PubChem FDA drugs, 156 pathways
```

## Tool Parameters

```python
disease_drug_discovery(
    disease="glioblastoma",        # Disease name or EFO/MONDO ID
    min_indication_phase=3,        # Phase 3+ for direct indications (default: 3)
    include_gwas=True,             # Include GWAS genetic associations
    include_clinvar=True,          # Include ClinVar variant associations
    include_reactome=True,         # Include Reactome pathways (pending)
    include_uniprot=True,          # Include UniProt annotations (pending)
    include_pubchem=True,          # Include PubChem FDA-approved drugs (default: True)
    include_similar_proteins=False,  # Find similar proteins via ESM-2 (default: False)
    include_similar_compounds=False, # Find similar compounds via Morgan FP (default: False)
    similarity_limit=5             # Number of similar items per query (default: 5)
)
```

### Similarity Search (PATH 8 & 9)

When enabled, the tool finds:
- **Similar Proteins**: Uses ESM-2 embeddings (1280-dim) from 573K SwissProt proteins to find structurally similar proteins to disease targets
- **Similar Compounds**: Uses Morgan fingerprints (2048-bit) from 30.8M SureChEMBL patent compounds to find analogs of discovered drugs

Example with similarity search enabled:
```
Direct indications: 28 drugs
Similar proteins: 21 proteins for 7 targets (scores 0.98-0.99)
Similar compounds: 19 compounds for 8 drugs (scores 0.95-1.0)
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

2. **Step 2a**: Map genes to drugs via ChEMBL
   ```
   genes >> ensembl >> uniprot >> chembl_target_component
         >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule
   ```

3. **Step 2b**: Map genes to FDA-approved drugs via PubChem
   ```
   genes >> ensembl >> uniprot >> pubchem_activity >> pubchem[pubchem.is_fda_approved==true]
   ```

### ChEMBL vs PubChem

| Feature | ChEMBL | PubChem |
|---------|--------|---------|
| **Drug Phase** | ✅ Phase 0-4 per indication | ❌ Only FDA approved flag |
| **Disease Context** | ✅ Disease-specific phase | ❌ No disease linkage |
| **Data Source** | Curated literature | High-throughput screening |
| **Best For** | Clinical candidate ranking | FDA-approved compound coverage |

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

## BioBTree Data Issues

### Issue 1: EFO Disease Name Mapping - FIXED ✅
**Status**: FULLY FIXED

**Problem was**: Querying "glioblastoma" only returned 75 drugs (page 1), missing BEVACIZUMAB (Phase 4 approved) which was on page 2.

**Fix applied**: Added pagination to `_query_direct_indications()` to fetch ALL pages of results.

**Result**: Now returns 150+ drugs including all Phase 4 approved drugs:
- BEVACIZUMAB (shown as BEVZ-92, CHEMBL1201583) - Phase 4
- BCNU - Phase 4
- Spexotras - Phase 4
- And 25+ more Phase 3+ drugs

### Issue 2: EFO → Reactome/UniProt Links Missing
- `efo >> reactome` - No link exists
- `efo >> uniprot` - No link exists

These paths would enable additional drug discovery evidence sources.

### Issue 3: PubChem Synonyms/Drug Names Not Populated
**Problem**: PubChem entries only have IUPAC names in the `title` field. The `synonyms` and `drug_names` fields are empty.

**Example**:
```
CID 123631 (Gefitinib/Iressa - a well-known EGFR inhibitor):
- title: "N-(3-chloro-4-fluorophenyl)-7-methoxy-6-(3-morpholin-4-ylpropoxy)quinazolin-4-amine"
- synonyms: []
- drug_names: []
```

**Expected**: Common names like "Gefitinib" and trade names like "Iressa" should be in synonyms/drug_names.

**Fix needed**: Populate `synonyms` and `drug_names` fields from PubChem compound data during BioBTree build.

## Future Work / TODOs

1. **Reactome Integration**: Find correct ontology path (try MONDO?)
2. **UniProt Integration**: Find correct ontology path
3. **Pathogenic Filter**: Add ClinVar pathogenic variant filter
   - Syntax issue: `clinvar[clinvar.germline_classification=="Pathogenic"]` errors
4. **Gene Deduplication**: Merge overlapping genes across sources
5. **Drug Ranking**: Rank drugs by evidence strength (multiple sources)
6. **Response Formatting**: Improve agent's response formatting
7. **Output Token Cost Optimization**: Full pagination now returns 2000+ drugs
   - Current: All results returned to agent (high token cost)
   - Options to consider:
     - Return top N to agent, save full results to file
     - Store full results in Qdrant for semantic search ("show ALK inhibitors")
     - Summary + reference ID approach
   - Goal: Keep completeness (selling point) while reducing LLM token usage
   - Currently showing top N in agent response, but full data flows through context

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
    print(f"Direct indications (ChEMBL): {data['direct_indications']['count']}")
    print(f"GWAS genes: {data['gwas_targets']['genes']}")
    print(f"ClinVar genes: {data['clinvar_targets']['genes']}")
    print(f"PubChem FDA drugs: {data['pubchem_targets']['drug_count']}")
```

## History

- **Initial**: LLM-orchestrated multi-path queries (backup in `backup_multipath/`)
- **Current**: Specialized tool with parallel query execution
- **ClinVar Fix**: Changed from EFO to MONDO ontology for ClinVar access
- **Formatter Fix**: Updated `_format_disease_drug_result()` to include all sources (was only showing GWAS)
- **Consistency Fix**: Sorted gene lists to ensure consistent results across runs (sets are unordered)
- **PubChem Integration**: Added PATH 6 for FDA-approved drugs from PubChem bioactivity data
- **Reactome Integration**: Added PATH 7 for pathway context using genes >> ensembl >> reactome
- **Drug Name Improvement**: Added `_get_best_drug_name()` to prefer common names over IUPAC
- **Full Pagination**: Added pagination to ALL BioBTree queries to get complete results
  - Before: 3 direct drugs, 152 GWAS, 160 ClinVar, 154 PubChem, 156 pathways
  - After: 28 direct drugs, 723 GWAS, 697 ClinVar, 321 PubChem, 255 pathways
  - BEVACIZUMAB now found (was on page 2)

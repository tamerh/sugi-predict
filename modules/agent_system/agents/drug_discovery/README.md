# Drug Discovery Agent

A specialized agent for comprehensive disease-to-drug discovery queries using multiple evidence paths.

## Overview

The Drug Discovery Agent answers questions like "What drugs are available for glioblastoma?" by querying multiple biological databases through BioBTree and consolidating the results.

## Multi-Path Architecture

The agent uses a specialized `disease_drug_discovery` tool that runs multiple query paths internally:

### Working Paths

Paths are organized into three phases based on data dependencies:

- **Phase 1 (Disease-based)**: Query directly from disease name (PATH 1, 2, 3, 11, 14, 15)
- **Phase 2 (Gene-based)**: Enrich genes collected from Phase 1 (PATH 6b, 7, 16-20, 22)
- **Phase 3 (Drug-based)**: Enrich drugs collected from Phase 1-2 (PATH 6a, 12, 13, 21)

| Path | Source | Ontology | Query Chain | Status |
|------|--------|----------|-------------|--------|
| PATH 1 | Direct Indications | MONDO→EFO | `disease >> mondo >> efo >> chembl_molecule` | ✅ Working |
| PATH 2 | GWAS | MONDO→EFO | `disease >> mondo >> efo >> gwas >> ensembl >> ChEMBL drugs` + study metadata | ✅ Working |
| PATH 3 | ClinVar | MONDO | `disease >> mondo >> clinvar >> ensembl >> ChEMBL drugs` | ✅ Working |
| PATH 6a | PubChem Enrichment | - | `ChEMBL drugs >> InChI key >> PubChem search` | ✅ Working (enhanced) |
| PATH 6b | PubChem Activity | - | `genes >> ensembl >> uniprot >> pubchem_activity >> pubchem[fda]` | ✅ Working |
| PATH 7 | Reactome Pathways | - | `genes >> ensembl >> reactome` | ✅ Working |
| PATH 8 | Similar Proteins | Qdrant ESM-2 | `genes >> uniprot >> ESM-2 embedding search` | ✅ Working |
| PATH 9 | Similar Compounds | Qdrant Morgan FP | `drugs >> SMILES >> Morgan FP search (30M compounds)` | ✅ Working |
| PATH 11 | Clinical Trials | ClinicalTrials.gov | `disease >> clinical_trials` | ✅ Working |
| PATH 12 | Patent Compounds | SureChEMBL | ChEMBL drugs >> InChI key >> patent_compound >> patent | ✅ Working (via workaround) |
| PATH 13 | BindingDB | - | `ChEMBL drugs >> bindingdb` | ✅ Working |
| PATH 14 | Antibodies | EFO | `disease >> efo >> antibody` | ✅ Working |
| PATH 15 | GenCC | MONDO | `disease >> efo >> mondo >> gencc >> genes >> ChEMBL drugs` | ✅ Working |
| PATH 16 | Expression | Bgee | `genes >> ensembl >> bgee` | ✅ Working |
| PATH 17 | GO Enrichment | - | `genes >> ensembl >> uniprot >> go` | ✅ Working |
| PATH 18 | PPI Network | STRING | `genes >> ensembl >> uniprot >> string` | ✅ Working |
| PATH 19 | Structures | PDB | `genes >> ensembl >> uniprot >> pdb` | ✅ Working |
| PATH 20 | InterPro Domains | InterPro | `genes >> ensembl >> uniprot >> interpro` | ✅ Working |
| PATH 21 | MeSH Enrichment | MeSH | `drugs >> pubchem >> mesh` | ✅ Working |
| PATH 22 | HMDB Metabolites | HMDB | `genes >> ensembl >> uniprot >> hmdb` | ✅ Working |
| PATH 23 | Bioactivity | PubChem | `drugs >> pubchem >> pubchem_activity >> pubchem_assay` | ✅ Working |
| PATH 23+ | BAO Annotations | BAO | `pubchem_assay >> bao` (assay classification ontology) | ⏳ Next Release |
| PATH 24 | CTD Interactions | CTD | `mesh_id >> ctd` (chemical-gene-disease) | ✅ Working |
| PATH 25 | DrugCentral MOA | DrugCentral | `struct_id >> drugcentral` (drug-target MOA) | ✅ Working |
| PATH 26 | MSigDB Gene Sets | MSigDB | `gene >> hgnc >> msigdb` (gene set enrichment) | ✅ Working |
| PATH 27 | BioGRID PPI | BioGRID | `biogrid_id >> biogrid` (protein interactions) | ⚠️ Partial (xrefs only) |

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

PATH 2 - GWAS (ChEMBL): 5 genes -> 303 drugs, 5 studies (648 associations)
  Genes: TP53, MPG, EGFR, SLC16A8, TERT
  Studies (evidence sources):
    - PMID:36810956 (2023-02-21): 607 associations
    - PMID:30152087 (2018-08-27): 20 associations
    - PMID:26424050 (2015-10-01): 12 associations

PATH 3 - ClinVar (ChEMBL): 3 genes -> 160 drugs
  Genes: FGFR2, KIF5C, ALK
  Notable: ALK has drugs like CERITINIB (known ALK inhibitor)

PATH 6a - PubChem + MeSH Enrichment: 15 drugs -> 10 in PubChem -> 9 with MeSH
  Enriches ChEMBL drugs with:
  - PubChem: FDA status, synonyms, molecular data, drug-likeness
  - MeSH: Drug class, trade names, therapeutic scope
  - Pharmacological Actions: Drug mechanism (e.g., "ACE Inhibitors", "Statins")
  - Drug-Likeness: Lipinski Rule of 5 assessment
  - External IDs: UNII (FDA), DTXSID (EPA toxicity), NSC (NCI)
  Via: ChEMBL >> InChI key >> PubChem >> MeSH
  Example: Temozolomide -> Drug Class: "Antineoplastic Agents, Alkylating"
           Trade Names: ["Temodar", "Temodal", "Methazolastone"]
           Scope: "treatment of MALIGNANT GLIOMA and MALIGNANT MELANOMA"
           Lipinski: 0 violations → Drug-like: True

PATH 6b - PubChem Activity: 45 targets -> 4 with compounds -> 139 FDA compounds
  FDA-approved compounds with bioactivity on disease-associated targets
  Via: genes >> ensembl >> uniprot >> pubchem_activity >> pubchem[fda]

PATH 7 - Reactome Pathways: 7 genes -> 156 pathways
  ALK: ceritinib-resistant ALK mutants (disease), Disease
  CDKN2A: Defective Intrinsic Pathway for Apoptosis (disease)
  EGFR: Clathrin-mediated endocytosis, Cargo recognition...

PATH 11 - Clinical Trials: 50+ trials
  NCT02655601: Phase 1/2 - Temozolomide + BMX-001 (COMPLETED)
  NCT03426891: Phase 3 - Bevacizumab combination (RECRUITING)
  Breakdown: PHASE3 (15), PHASE2 (20), PHASE1 (10), RECRUITING (12)

PATH 12 - Patent Compounds (when enabled): 4000+ patents from 14 drugs
  Via InChI key workaround (pending BioBTree direct connection):
  CHEMBL513 (Bevacizumab): 199 patents
  CHEMBL941 (Temozolomide): 198 patents
  Sample patents: US-20140197062-A1, WO-2019113041-A1

Total: 23 unique genes, 1700+ ChEMBL drugs, 139 PubChem FDA compounds, 386 pathways, 93 clinical trials, 10 antibodies
```

## PubChem Data Fields (Enhanced Jan 2026)

PATH 6a now extracts comprehensive drug data from PubChem:

### Classification Fields
| Field | Description | Example |
|-------|-------------|---------|
| `compound_type` | Classification | `drug`, `literature`, `patent`, `bioactive`, `biologic` |
| `pharmacological_actions` | Drug mechanism/class | `["ACE Inhibitors", "Antihypertensive Agents"]` |
| `fda_approved` | FDA approval status | `True` |
| `mesh_terms` | MeSH descriptors | `["Atorvastatin"]` |

### Drug-Likeness (Lipinski Rule of 5)
| Field | Description | Threshold |
|-------|-------------|-----------|
| `molecular_weight` | Molecular weight (Da) | ≤ 500 |
| `hydrogen_bond_donors` | HBD count | ≤ 5 |
| `hydrogen_bond_acceptors` | HBA count | ≤ 10 |
| `xlogp` | Lipophilicity | ≤ 5 |
| `tpsa` | Topological polar surface area | - |
| `rotatable_bonds` | Flexibility measure | - |
| `lipinski_violations` | Number of rule violations | 0-4 |
| `drug_like` | Oral drug-likeness | `True` if ≤1 violation |

### External Database IDs
| Field | Description | Example |
|-------|-------------|---------|
| `unii` | FDA Unique Ingredient Identifier | `A0JWA85V8F` |
| `dtxsid` | EPA DSSTox Substance ID (toxicity) | `DTXSID8029868` |
| `nsc_ids` | NCI compound numbers | `["NSC123456"]` |

### Cross-Reference Counts (FDA drugs only)
| Field | Description |
|-------|-------------|
| `literature_count` | Number of PubMed references |
| `patent_count` | Number of patent citations |

### Example Output
```python
{
    'chembl_id': 'CHEMBL1078',
    'name': 'Atorvastatin',
    'pubchem_cid': '60823',
    'fda_approved': True,
    'compound_type': 'drug',
    'pharmacological_actions': ['Anticholesteremic Agents', 'HMG-CoA Reductase Inhibitors'],

    # Drug-likeness
    'molecular_weight': 558.6,
    'xlogp': 4.1,
    'hydrogen_bond_donors': 4,
    'hydrogen_bond_acceptors': 6,
    'lipinski_violations': 1,  # MW > 500
    'drug_like': True,  # 1 violation is acceptable

    # External IDs
    'unii': 'A0JWA85V8F',
    'dtxsid': 'DTXSID8029868',

    # Literature/Patents
    'literature_count': 75,
    'patent_count': 75,
}
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
    include_clinical_trials=True,  # Include ClinicalTrials.gov trials (default: True)
    include_patents=False,         # Include SureChEMBL patents (default: False, can be slow)
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
├── README.md                       # This file
├── RESTRUCTURE_PLAN.md             # Migration plan to agent-centric architecture
├── agent.py                        # Agent class with routing logic
├── prompt.txt                      # System prompt for LLM
├── chains.yaml                     # Query chain definitions
├── examples.yaml                   # Few-shot examples
│
├── phases/                         # Six-phase reasoning loop
│   ├── __init__.py
│   └── gather.py                   # Phase 2: GatherPhase orchestrator
│
├── paths/                          # Individual data gathering paths
│   ├── __init__.py
│   ├── base.py                     # BasePath abstract class, PathResult
│   ├── direct_indications.py       # PATH 1: disease >> efo >> chembl_molecule
│   ├── gwas.py                     # PATH 2: GWAS genetic associations
│   ├── clinvar.py                  # PATH 3: ClinVar variant associations
│   ├── pubchem.py                  # PATH 6a/6b: PubChem (enrichment + activity)
│   ├── reactome.py                 # PATH 7: Reactome pathways
│   ├── clinical_trials.py          # PATH 11: ClinicalTrials.gov
│   ├── patents.py                  # PATH 12: SureChEMBL patents
│   ├── bindingdb.py                # PATH 13: BindingDB binding data
│   ├── antibody.py                 # PATH 14: Therapeutic antibodies
│   ├── gencc.py                    # PATH 15: GenCC expert-curated gene-disease
│   ├── bgee.py                     # PATH 16: Bgee tissue expression
│   ├── go_enrichment.py            # PATH 17: GO functional annotations
│   ├── ppi.py                      # PATH 18: STRING protein-protein interactions
│   ├── structures.py               # PATH 19: PDB protein structures
│   ├── interpro.py                 # PATH 20: InterPro protein domains
│   ├── mesh_enrichment.py          # PATH 21: MeSH drug classification
│   ├── hmdb.py                     # PATH 22: HMDB metabolites
│   ├── bioactivity.py              # PATH 23: PubChem bioactivity (IC50, Ki, targets)
│   ├── ctd.py                      # PATH 24: CTD chemical-gene-disease interactions
│   ├── drugcentral.py              # PATH 25: DrugCentral drug-target MOA
│   └── msigdb.py                   # PATH 26: MSigDB gene set enrichment
│
├── extractors/                     # Data extraction utilities
│   ├── __init__.py
│   ├── drug_extractor.py           # Extract drugs from BioBTree results
│   ├── gene_extractor.py           # Extract genes from results
│   ├── trial_extractor.py          # Extract clinical trials
│   ├── patent_extractor.py         # Extract patents
│   ├── pathway_extractor.py        # Extract Reactome pathways
│   └── pubchem_extractor.py        # Extract PubChem drugs
│
├── utils/                          # Shared utilities
│   ├── __init__.py
│   ├── drug_names.py               # INN drug name selection
│   └── pagination.py               # Paginated BioBTree queries
│
└── backup_multipath/               # Backup of LLM-orchestrated approach

tools/
└── disease_drug_tool.py            # Facade (delegates to new modules)
```

## Architecture (Agent-Centric)

The agent uses a modular architecture with clear separation:

1. **Paths**: Individual query routes (PATH 1-12), each in its own module
2. **Phases**: Six-phase reasoning loop (Gather implemented, others TODO)
3. **Extractors**: Transform BioBTree results into structured data
4. **Utils**: Shared utilities (pagination, drug name selection)

See `RESTRUCTURE_PLAN.md` for the full migration plan.

## Technical Details

### Two-Step Gene-to-Drug Mapping

For gene-based paths (GWAS, ClinVar), we use a two-step approach:

1. **Step 1**: Get genes associated with disease
   - GWAS: `disease >> mondo >> efo >> gwas >> ensembl`
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

### Available links from EFO:
- `efo >> gwas` ✅
- `efo >> chembl_molecule` ✅
- `efo >> antibody` ✅
- `efo >> clinvar` ❌ (use MONDO instead)
- `efo >> reactome` ❌
- `efo >> uniprot` ❌
- `efo >> pubchem` ❌
- `efo >> clinical_trials` ❌

### Available links from MONDO:
- `mondo >> clinvar` ✅
- `mondo >> clinvar >> ensembl` ✅
- `mondo >> clinical_trials` ❌
- `mondo >> gwas` ❌

### PubChem Mapping Gaps (Investigated 2025-01)

The following direct PubChem mappings **do not exist** in BioBTree:

| Attempted Path | Status | Notes |
|----------------|--------|-------|
| `EFO >> pubchem` | ❌ Missing | No direct disease→PubChem link |
| `chembl_molecule >> pubchem` | ❌ Missing | No ChEMBL→PubChem cross-reference |
| `pubchem >> chembl_molecule` | ❌ Missing | Reverse also missing |
| `clinical_trials >> pubchem` | ❌ Missing | No trial→compound link |

**Workarounds implemented:**

1. **PATH 6a (InChI Key Bridging)**:
   - Get InChI keys from ChEMBL drugs via `chembl_molecule` attributes
   - Search PubChem by InChI key (exact match)
   - Returns FDA status, synonyms, trade names from PubChem

2. **PATH 6b (Target Bioactivity)**:
   - Map genes to proteins: `genes >> ensembl >> uniprot[reviewed]`
   - Query bioactivity: `uniprot >> pubchem_activity >> pubchem[fda_approved]`
   - Returns FDA compounds with bioactivity data on disease targets

### MeSH Cross-References (Investigated 2025-01)

MeSH in BioBTree links to **drug descriptors**, not disease terms:

| Path | Works? | Notes |
|------|--------|-------|
| `pubchem >> mesh` | ✅ | Links compounds to drug MeSH descriptors |
| `mesh >> pubchem` | ✅ | Reverse works (drug MeSH → CID) |
| `mesh (disease) >> pubchem` | ❌ | Disease MeSH IDs don't link to compounds |
| `mesh >> mondo` | ✅ | Only useful disease-related link |

**Useful fields in drug MeSH descriptors:**
- `pharmacological_actions`: Drug class (e.g., "Antineoplastic Agents, Alkylating")
- `entry_terms`: Trade names, synonyms (e.g., "Temodar", "Temodal")
- `scope_note`: Therapeutic description (e.g., "treatment of MALIGNANT GLIOMA")

**Integration:** PATH 6a now queries `pubchem >> mesh` to enrich drugs with drug class and trade names.

### BAO (BioAssay Ontology) - Coming Next Release

BAO provides standardized classification of bioassays. When loaded in BioBTree, PATH 23 will be enhanced with:

| BAO Field | Description | Example Values |
|-----------|-------------|----------------|
| `detection_technology` | How the assay measures activity | luminescence, fluorescence polarization, mass spectrometry |
| `molecular_target` | Target type classification | protein target: enzyme: kinase, GPCR, ion channel |
| `biological_process` | Cellular process measured | cell death, apoptosis, gene expression |
| `assay_format` | Assay methodology | cell-based format, biochemical format |
| `assay_design` | Assay design type | binding reporter, enzymatic assay |
| `assay_stage` | Screening stage | primary, confirmatory, counter-screen |

**Use cases:**
- Filter assays by technology (e.g., only enzymatic assays)
- Distinguish primary screens from confirmatory assays
- Group activities by target class (kinases vs GPCRs)

**Query chain (when available):** `pubchem_assay >> bao`

### Additional Working Paths (Verified 2025-01)

The following paths have been **confirmed working** and are available for integration:

| Dataset | Working Path | Data Fields |
|---------|-------------|-------------|
| **GO** | `uniprot >> go` | type (biological_process/molecular_function/cellular_component), name, synonyms |
| **PDB** | `uniprot >> pdb` | method (x-ray/em), resolution, chains |
| **STRING** | `uniprot >> string` | partner IDs, interaction scores, annotations |
| **IntAct** | `uniprot >> intact` | partner_uniprot, detection_method, confidence_score, pubmed_id |
| **Bgee** | `ensembl >> bgee` | tissue/cell type, expression (present/absent), score, rank, quality (gold/silver) |
| **GenCC** | `gene_symbol >> gencc`, `mondo >> gencc` | classification (Definitive/Strong/Moderate/Limited), MOI, submitter |

**GenCC** (Gene Curation Coalition) is particularly valuable:
- Curated gene-disease validity assertions
- Evidence sources: ClinGen, OMIM, Orphanet, PanelApp, Ambry Genetics
- Classifications: Definitive > Strong > Moderate > Limited > Disputed
- Mode of inheritance (AD, AR, XL)
- Could serve as **PATH 15** - complement to GWAS (PATH 2) and ClinVar (PATH 3)

**Potential New Paths to Implement:**

| Path # | Name | Query Chain | Value |
|--------|------|-------------|-------|
| PATH 15 | GenCC | `disease >> mondo >> gencc` | Expert-curated gene-disease with evidence levels |
| PATH 16 | Expression | `genes >> ensembl >> bgee` | Tissue-specific expression for target prioritization |
| PATH 17 | GO Enrichment | `genes >> uniprot >> go` | Functional annotations, biological process grouping |
| PATH 18 | PPI Network | `genes >> uniprot >> string/intact` | Protein interaction network expansion |
| PATH 19 | Structures | `genes >> uniprot >> pdb` | Druggability assessment via structure availability |

### ClinVar/Clinical Trials Gaps

- `clinvar` search returns 0 for disease names (index issue?)
- `clinical_trials` dataset name is plural (`clinical_trials` not `clinical_trial`)

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

### Issue 4: Patent Compound Connections - WORKAROUND IMPLEMENTED
**Status**: Workaround in place, awaiting BioBTree fix

**Problem**: The following BioBTree paths are not working:
- `disease >> patent` - Text search returns 0 results
- `patent_compound >> chembl_molecule` - Standalone query returns 0 (but works in chains)
- `chembl_molecule >> patent_compound` - Reverse lookup returns 0
- `pubchem >> chembl_molecule` - Returns 0 (PubChem-ChEMBL link broken)
- `chembl_molecule >> pubchem` - Returns 0

**Working paths**:
- `patent >> patent_compound` - Works
- `patent >> patent_compound >> chembl_molecule` - Works (auto-injection)
- `patent >> pubchem` - Works
- `pubchem >> patent` - Works
- `patent_compound >> patent` - Works (for some IDs)

**Workaround implemented**: PATH 12 now uses InChI key lookup:
1. Get ChEMBL drugs from direct indications (PATH 1)
2. For each drug, get its InChI key from BioBTree
3. Search `patent_compound` by InChI key (REST API)
4. Extract associated patents from search results

This finds thousands of relevant patents (e.g., 4480 patents from 14 glioblastoma drugs).

**Note**: When BioBTree adds direct `chembl_molecule >> patent_compound` connection,
this can be simplified to a single chain query.

### Issue 3: PubChem Title Field - PARTIALLY FIXED ✅
**Status**: Most fields fixed, title fix coming in next BioBTree release

**Original problem**: PubChem entries only had IUPAC names in the `title` field. The `synonyms` and `drug_names` fields were empty.

**Current status (Jan 2026)**:
- ✅ `synonyms`: Now populated (100+ synonyms per drug)
- ✅ `pharmacological_actions`: Now populated (e.g., "ACE Inhibitors", "Statins")
- ✅ `compound_type`: Now populated (drug, literature, patent, bioactive, biologic)
- ✅ `mesh_terms`: Now populated from PubChem data
- ✅ Drug-likeness fields: molecular_weight, xlogp, HBD, HBA, TPSA, rotatable_bonds
- ✅ External IDs: unii, dtxsid, nsc_ids
- ⏳ `title`: Still shows IUPAC name (fix coming in next BioBTree release)
- ⏳ `drug_names`: Will be populated in next BioBTree release

**Workaround**: Agent now uses `pharmacological_actions` for drug classification and first synonym as display name when title is IUPAC.

## Evidence Scoring (PHASE 6)

The tool now includes an evidence scoring system that ranks drugs and genes by confidence:

### Scoring Weights
```python
WEIGHTS = {
    # Drug scoring
    "indication_phase_4": 40,    # Approved drug
    "indication_phase_3": 30,    # Late-stage trials
    "trials_base": 15,           # Base score for having trials
    "trials_per_recruiting": 2,  # Bonus per recruiting trial

    # Gene scoring
    "gwas": 20,                  # GWAS association
    "clinvar_pathogenic": 25,   # Pathogenic variants
    "clinvar_default": 15,      # Other variants
    "reactome": 10,             # Pathway membership
    "uniprot": 10,              # Protein annotation

    # Bonuses
    "multi_source_bonus": 10,   # 3+ evidence sources
}
```

### Confidence Levels
- **High (70+)**: Multiple validated sources, clinical evidence
- **Medium (40-69)**: Some validation, moderate evidence
- **Low (<40)**: Limited evidence, potentially novel targets

### Detected Patterns
- `high_confidence`: Entities with score >= 70
- `multi_source`: Entities in 3+ evidence sources
- `novel_targets`: Genes with disease variants but no targeting drugs
- `approved_drugs`: Phase 4 approved drugs
- `active_development`: Drugs in recruiting trials
- `gaps`: High-evidence genes without therapeutic options

### Usage
```python
result = await tool.execute(
    "glioblastoma",
    include_scoring=True,    # Enable scoring (default: True)
    include_literature=False  # Literature enrichment (default: False)
)

# Access scoring results
scoring = result.data["scoring"]
print(f"High-confidence drugs: {scoring['summary']['high_confidence_drugs']}")
for drug in scoring["scored_drugs"][:5]:
    print(f"  {drug['name']}: {drug['score']} ({drug['confidence']})")

# Access detected patterns
print(f"Novel targets: {scoring['patterns']['novel_targets']}")
print(f"Therapeutic gaps: {scoring['patterns']['gaps']}")
```

## Literature Enrichment (Qdrant Integration)

When enabled, the tool enriches top entities with relevant PubMed literature:

### Method
- Uses BioBERT embeddings (768-dim) for semantic similarity
- Searches 28M+ PubMed abstracts in Qdrant
- Returns top 3 papers per entity

### Usage
```python
result = await tool.execute(
    "glioblastoma",
    include_scoring=True,
    include_literature=True  # Enable PubMed enrichment
)

# Access literature
literature = result.data["literature"]
for gene, papers in literature["gene_literature"].items():
    print(f"{gene}:")
    for paper in papers:
        print(f"  PMID:{paper['pmid']} (score: {paper['score']:.2f})")
```

## Future Work / TODOs

1. **Reactome Integration**: Find correct ontology path (try MONDO?)
2. **UniProt Integration**: Find correct ontology path
3. **Pathogenic Filter**: Add ClinVar pathogenic variant filter
   - Syntax issue: `clinvar[clinvar.germline_classification=="Pathogenic"]` errors
4. ~~**Gene Deduplication**: Merge overlapping genes across sources~~ ✅ DONE
5. ~~**Drug Ranking**: Rank drugs by evidence strength~~ ✅ DONE (Evidence Scoring)
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
- **Patent InChI Workaround**: Implemented workaround for PATH 12 using InChI key lookup
  - BioBTree: `chembl_molecule >> patent_compound` not yet connected
  - Workaround: Get InChI keys from ChEMBL drugs, search patent_compound by InChI key
  - Result: 4480 patents found for glioblastoma drugs (14 molecules)
  - Note: Will simplify to single query when BioBTree connection is established
- **Gene Deduplication**: Merges genes across GWAS, ClinVar, Reactome, UniProt sources
  - Skips Ensembl IDs in favor of gene symbols
  - Tracks which sources each gene appears in
- **Evidence Scoring (PHASE 6)**: Ranks drugs/genes by evidence strength
  - Scores based on indication phase, clinical trials, patents, multi-source presence
  - Detects patterns: high_confidence, novel_targets, therapeutic gaps
  - Creates confidence levels: High (70+), Medium (40-69), Low (<40)
- **Literature Enrichment**: PubMed semantic search via Qdrant
  - Uses BioBERT embeddings (768-dim) for similarity search
  - Enriches top genes/drugs with relevant PubMed abstracts
  - 28M+ PubMed abstracts searchable
- **PubChem Dual-Path Architecture (2025-01)**: Split PATH 6 into two complementary paths
  - PATH 6a (Enrichment): ChEMBL drugs → InChI key → PubChem → MeSH (FDA status, drug class, trade names)
  - PATH 6b (Activity): genes → ensembl → uniprot → pubchem_activity → pubchem[fda] (FDA compounds by target)
  - Documented missing BioBTree mappings: EFO>>pubchem, chembl_molecule>>pubchem
- **MeSH Integration (2025-01)**: Added drug MeSH descriptor enrichment to PATH 6a
  - Drug class via `pharmacological_actions` (e.g., "Tyrosine Kinase Inhibitors")
  - Trade names via `entry_terms` (e.g., "Temodar", "Gleevec")
  - Therapeutic scope via `scope_note` (describes indications)
  - Note: MeSH links to drug descriptors, not disease terms
- **BindingDB Integration (PATH 13)**: Binding affinity data for drugs (Ki, Kd, IC50, EC50)
- **Antibody Integration (PATH 14)**: Therapeutic antibodies via EFO >> antibody
- **GWAS Study Metadata (2025-01)**: Added evidence sourcing to PATH 2
  - Fetches GWAS study metadata via `disease >> efo >> gwas_study`
  - Includes: PubMed IDs, study titles, first author, publication date
  - Tracks association counts per study
  - Enables citation of primary literature sources
- **New BioBTree Paths Verified (2025-01)**: Tested and documented additional working paths
  - `uniprot >> go`: Gene Ontology annotations (biological process, molecular function, cellular component)
  - `uniprot >> pdb`: Protein structures with resolution, method (x-ray/EM)
  - `uniprot >> string`: STRING protein-protein interactions with scores
  - `uniprot >> intact`: IntAct curated interactions with PubMed references
  - `ensembl >> bgee`: Bgee tissue expression with quality scores (gold/silver)
  - `mondo >> gencc`: GenCC expert-curated gene-disease associations with evidence levels
  - Ready for PATH 15-19 implementation
- **GenCC Integration (PATH 15) (2025-01)**: Expert-curated gene-disease associations
  - Path: `disease >> efo >> mondo >> gencc >> genes >> ChEMBL drugs`
  - Evidence classifications: Definitive > Strong > Moderate > Limited > Disputed
  - Includes mode of inheritance (AD, AR, XL)
  - Tracks submitter sources (ClinGen, OMIM, Orphanet, PanelApp, Ambry, G2P)
  - Note: GenCC covers Mendelian/heritable diseases (not complex diseases like cancer)
  - Tested: breast cancer → 10 genes (2 Definitive, 3 Moderate, 7 Limited) → 887 drugs
- **Bgee Expression (PATH 16) (2025-01)**: Tissue-specific expression for target prioritization
  - Path: `genes >> ensembl >> bgee`
  - Provides tissue/cell type expression levels with quality scores (gold/silver)
  - Ranks tissues by expression score
  - Identifies shared tissues across disease-associated genes
  - Use case: Prioritize targets expressed in disease-relevant tissues
- **GO Enrichment (PATH 17) (2025-01)**: Gene Ontology functional annotations
  - Path: `genes >> ensembl >> uniprot >> go`
  - Groups genes by biological process, molecular function, cellular component
  - Identifies shared GO terms across disease-associated genes
  - Use case: Understand functional context of disease targets
- **PPI Network (PATH 18) (2025-01)**: Protein-protein interaction networks from STRING
  - Path: `genes >> ensembl >> uniprot >> string`
  - Returns interaction partners with confidence scores (0-1000)
  - Identifies hub proteins connecting multiple disease genes
  - Use case: Find network-based drug targets and mechanisms
- **Structures (PATH 19) (2025-01)**: Protein structure availability from PDB
  - Path: `genes >> ensembl >> uniprot >> pdb`
  - Returns available X-ray and cryo-EM structures with resolution
  - Sorted by resolution (best first)
  - Use case: Assess druggability via structure-based drug design readiness
- **MONDO Disease Name Resolution (2026-01)**: Fixed disease text search for PATH 1 and PATH 2
  - Problem: EFO text search failed for common terms (e.g., "breast cancer" not found, "breast carcinoma" works)
  - Solution: Changed query from `>> efo >>` to `>> mondo >> efo >>` for better synonym coverage
  - MONDO has richer disease name synonyms than EFO
  - Before: "breast cancer" → 0 drugs (EFO search failed)
  - After: "breast cancer" → MONDO:0007254 → EFO:0000305 → 58 drugs
  - GWAS: "breast cancer" now finds 807 drugs, 94 studies (was 0)
- **InterPro Domains (PATH 20) (2026-01)**: Protein domain analysis for druggability assessment
  - Path: `genes >> ensembl >> uniprot >> interpro`
  - Classifies domains into druggable categories: kinase, GPCR, ion_channel, protease, etc.
  - Identifies genes with druggable domain families
  - Tested: EGFR correctly identified with kinase domains (4 kinase-related domains)
- **MeSH Drug Enrichment (PATH 21) (2026-01)**: Drug classification and mechanism of action
  - Path: `drugs >> pubchem >> mesh`
  - Returns pharmacological actions (e.g., "Tyrosine Kinase Inhibitors", "Antineoplastic Agents")
  - Returns therapeutic categories from MeSH drug hierarchy
  - Tested: gefitinib → TKI, erlotinib → TKI, aspirin → NSAIDs + antiplatelet
- **HMDB Metabolites (PATH 22) (2026-01)**: Gene-metabolite associations
  - Path: `genes >> ensembl >> uniprot >> hmdb`
  - Returns metabolites associated with gene products (enzymes, transporters)
  - Includes pathways, biofluids, chemical structures
  - Tested: EGFR → 8 metabolites (ADP, ATP, Aldosterone, etc.)
- **PubChem Enhanced Fields (PATH 6a) (2026-01)**: Comprehensive drug data extraction
  - New classification fields: `compound_type`, `pharmacological_actions`
  - Drug-likeness (Lipinski Rule of 5): `xlogp`, `hydrogen_bond_donors/acceptors`, `tpsa`, `rotatable_bonds`, `lipinski_violations`, `drug_like`
  - External IDs: `unii` (FDA UNII), `dtxsid` (EPA toxicity), `nsc_ids` (NCI)
  - Cross-reference counts: `literature_count`, `patent_count` (for FDA drugs)
  - Added `compute_lipinski_violations()` helper function
  - Tested: Atorvastatin → Pharm Actions: ["HMG-CoA Reductase Inhibitors"], Lipinski: 1 violation (MW), Drug-like: True
- **PubChem Bioactivity (PATH 23) (2026-01)**: Detailed bioactivity measurements
  - Path: `drugs >> pubchem >> pubchem_activity >> pubchem_assay`
  - Activity types: IC50, Ki, Kd, EC50, AC50, ED50, GI50
  - Values normalized to nM for comparison
  - Potency categories: ultra_potent (<1nM), very_potent (1-10nM), potent (10-100nM), moderate (100nM-1µM), weak (1-10µM)
  - Assay metadata: source (BindingDB, ChEMBL), outcome type (Screening/Confirmatory), hit rate
  - Target proteins: UniProt IDs for off-target analysis
  - Use cases: potency ranking, target validation, off-target profiling
  - Tested: Atorvastatin → 75 activities across 75 targets including P51639 (HMG-CoA Reductase)
  - Future: BAO (BioAssay Ontology) for assay classification (detection technology, target type, assay stage)
- **CTD Integration (PATH 24) (2026-01)**: Chemical-gene-disease interactions from Comparative Toxicogenomics Database
  - Path: `mesh_id >> ctd` or `drug_name >> text >> ctd`
  - Gene interactions: action types (increases/decreases expression, binding, transport, etc.)
  - Disease associations: direct evidence and gene-inferred connections
  - PubMed references for each interaction
  - Effect categorization: expression, activity, binding, metabolism, transport, secretion
  - Tested: Aspirin (D001241) → 50 gene interactions, 30 disease associations
- **DrugCentral Integration (PATH 25) (2026-01)**: Drug-target interactions with mechanism of action
  - Path: `struct_id >> drugcentral` or `drug_name >> text >> drugcentral`
  - Target proteins with UniProt accessions and gene symbols
  - Action types: INHIBITOR, AGONIST, ANTAGONIST, MODULATOR, etc.
  - Activity values: Ki, IC50 with potency interpretation
  - Target classes: Enzyme, GPCR, Ion channel, Kinase, etc.
  - Target Development Level (TDL): Tclin, Tchem, Tbio, Tdark (from TCRD/Pharos)
  - Shared target detection (proteins targeted by multiple drugs)
  - Tested: Atorvastatin (struct_id 4474) → 8 targets including HMGCR (INHIBITOR)
- **MSigDB Integration (PATH 26) (2026-01)**: Molecular Signatures Database gene set enrichment
  - Path: `gene >> hgnc >> msigdb` or `geneset_name >> msigdb`
  - Collections: H (Hallmark), C1-C8 (Positional, Curated, Regulatory, Computational, Ontology, Oncogenic, Immunologic, Cell Type)
  - Gene set membership with overlap calculation
  - Simple fold enrichment scoring
  - Use cases: pathway enrichment, functional annotation, oncogenic signatures
  - Tested: BRCA1 → 75 gene sets, HALLMARK_APOPTOSIS → 161 genes
- **BioGRID Status (PATH 27) (2026-01)**: Protein-protein interactions - PARTIAL
  - Path: `biogrid_id >> biogrid`
  - Status: Cross-references working (UniProt, Entrez, PubMed, RefSeq)
  - Issue: Attributes empty (`{"Empty": true}`) - interaction metadata not stored
  - Recommend: Report to BioBTree team for next release
  - Note: For PPI, use PATH 18 (STRING) which is fully functional

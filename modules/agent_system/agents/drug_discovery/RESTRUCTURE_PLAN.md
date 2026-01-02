# Drug Discovery Agent Restructure Plan

## Status: Phase 1 Complete ✅ | BioBTree Paths Enhanced ✅

**Last Updated:** 2026-01-02

---

## Overview

Restructured from "tool-centric" to "agent-centric" architecture.

**Before:** All logic in `tools/disease_drug_tool.py` (2262 lines) - Agent called a mega-tool
**After:** Agent orchestrates phases directly - No mega-tool needed

---

## Completed Work ✅

### Architecture Change
```
BEFORE:
Agent → LLM decides → DiseaseDrugDiscoveryTool (2262 lines) → Returns everything

AFTER:
Agent.run()
├── Phase 1: Understand (regex-based disease extraction)
├── Phase 2: Gather (GatherPhase → 9 BioBTree paths in parallel)
├── Phase 3: Score (EvidenceScorer)
├── Phase 6: Synthesize (LLM generates response)
└── Fallback: ReAct loop for ad-hoc queries
```

### BioBTree Paths (9 Total)

| Path | File | Mapping Chain | Status |
|------|------|---------------|--------|
| PATH 1 | `direct_indications.py` | disease >> efo >> chembl_molecule | ✅ |
| PATH 2 | `gwas.py` | disease >> gwas >> ensembl >> ... >> chembl_molecule | ✅ |
| PATH 3 | `clinvar.py` | disease >> clinvar >> ensembl >> ... >> chembl_molecule | ✅ |
| PATH 6 | `pubchem.py` | genes >> ensembl >> uniprot >> pubchem_activity >> pubchem[fda] | ✅ |
| PATH 7 | `reactome.py` | genes >> ensembl >> uniprot >> reactome | ✅ |
| PATH 11 | `clinical_trials.py` | disease >> efo >> clinical_trials | ✅ |
| PATH 12 | `patents.py` | drugs >> chembl_molecule >> patent_compound >> patent | ✅ Updated |
| PATH 13 | `bindingdb.py` | drugs >> chembl_molecule >> bindingdb | ✅ New |
| PATH 14 | `antibody.py` | Search therapeutic antibodies by indication | ✅ New |

### Latest Updates (2026-01-02)

#### Patents Path Updated
- **Old:** REST API InChI key workaround (slow, manual HTTP per molecule)
- **New:** Direct gRPC mapping `chembl_molecule >> patent_compound >> patent`
- **Result:** 1500 patents in 301ms vs sequential HTTP requests

#### BindingDB Path Added (PATH 13)
- **Mapping:** `chembl_molecule >> bindingdb`
- **Data:** BindingDB IDs, URLs, binding affinity data (Ki, Kd, IC50)
- **Use case:** Enrich drugs with binding data

#### Antibody Path Added (PATH 14)
- **Method:** Query therapeutic antibodies, filter by indication
- **Data source:** TheraSAbDab (Therapeutic Structural Antibody Database)
- **Data:** name, targets, indications, isotype, format, sequences
- **Result:** 10 antibodies found for glioblastoma (bevacizumab, pembrolizumab, nivolumab, etc.)

### Files Created/Updated
| File | Description | Status |
|------|-------------|--------|
| `phases/gather.py` | GatherPhase orchestrator, GatherOptions, GatherResult | ✅ Updated |
| `phases/score.py` | EvidenceScorer (moved from tools/) | ✅ |
| `paths/base.py` | BasePath abstract class, PathResult dataclass | ✅ |
| `paths/direct_indications.py` | PATH 1: disease >> efo >> chembl_molecule | ✅ |
| `paths/gwas.py` | PATH 2: disease >> gwas >> genes >> drugs | ✅ |
| `paths/clinvar.py` | PATH 3: disease >> clinvar >> genes >> drugs | ✅ |
| `paths/pubchem.py` | PATH 6: genes >> pubchem >> FDA drugs | ✅ |
| `paths/reactome.py` | PATH 7: genes >> reactome pathways | ✅ |
| `paths/clinical_trials.py` | PATH 11: disease >> clinical_trials | ✅ |
| `paths/patents.py` | PATH 12: drugs >> patents (gRPC direct mapping) | ✅ Updated |
| `paths/bindingdb.py` | PATH 13: drugs >> BindingDB | ✅ New |
| `paths/antibody.py` | PATH 14: Therapeutic antibodies by indication | ✅ New |
| `extractors/*.py` | Drug, Gene, Trial, Patent, Pathway, PubChem extractors | ✅ |
| `utils/drug_names.py` | get_best_drug_name() utility | ✅ |

### Files Deleted
| File | Reason |
|------|--------|
| `tools/disease_drug_tool.py` | Logic moved to agent + phases |
| `tools/evidence_scorer.py` | Moved to phases/score.py |
| `utils/pagination.py` | Moved to biobtree_client.py (shared) |

### BioBTree Client Enhanced
- Added `preserve_sources` parameter to `map_query_all_pages()`
- Pagination is now a shared client feature, not agent-specific

---

## Current Directory Structure

```
agents/drug_discovery/
├── agent.py                    # Main orchestrator (phase-based)
├── __init__.py
├── README.md
├── prompt.txt                  # LLM system prompt (kept for reference)
├── RESTRUCTURE_PLAN.md         # This file
│
├── phases/
│   ├── __init__.py             # Exports GatherPhase, EvidenceScorer
│   ├── gather.py               # Phase 2: GatherPhase, GatherOptions, GatherResult
│   └── score.py                # Phase 3: EvidenceScorer
│
├── paths/
│   ├── __init__.py             # Exports all path classes
│   ├── base.py                 # BasePath, PathResult
│   ├── direct_indications.py   # PATH 1
│   ├── gwas.py                 # PATH 2
│   ├── clinvar.py              # PATH 3
│   ├── pubchem.py              # PATH 6
│   ├── reactome.py             # PATH 7
│   ├── clinical_trials.py      # PATH 11
│   ├── patents.py              # PATH 12 (updated: gRPC direct)
│   ├── bindingdb.py            # PATH 13 (new)
│   └── antibody.py             # PATH 14 (new)
│
├── extractors/
│   ├── __init__.py
│   ├── drug_extractor.py
│   ├── gene_extractor.py
│   ├── trial_extractor.py
│   ├── patent_extractor.py
│   ├── pathway_extractor.py
│   └── pubchem_extractor.py
│
└── utils/
    ├── __init__.py
    └── drug_names.py           # get_best_drug_name()

integrations/
└── biobtree_client.py          # Enhanced with preserve_sources pagination
```

---

## Test Results ✅

```
Query: "What drugs are available for glioblastoma?"

Results:
- Disease extracted: 'glioblastoma'
- Direct indication drugs: 28
- GWAS genes: 4, drugs: 761
- ClinVar genes: 9, drugs: 834
- PubChem FDA drugs: 167
- Reactome pathways: 386
- Clinical trials: 93 (16 recruiting)
- Patents: 1121 (6 molecules with patents)
- BindingDB: 10 drugs with binding data
- Therapeutic antibodies: 10 (bevacizumab, pembrolizumab, nivolumab, etc.)
- Total unique drugs: 1782
- Total genes: 23
```

---

## BioBTree Dataset Exploration

### Available Datasets Tested
| Dataset | Connection Status | Data Quality |
|---------|------------------|--------------|
| `chembl_molecule` | ✅ Full connectivity | Rich molecule data |
| `chembl_target` | ✅ Via assay chain | Requires full chain |
| `patent` | ✅ Direct mapping | Title, country, date, URL |
| `patent_compound` | ✅ Intermediate | Links molecules to patents |
| `bindingdb` | ✅ Direct mapping | IDs, URLs (sparse affinity data) |
| `antibody` | ✅ Search-based | Rich: targets, indications, sequences |
| `pubchem` | ✅ Via activity | FDA approval filter works |
| `pubchem_activity` | ✅ Intermediate | Bioassay data |
| `gwas` | ✅ Via EFO | Gene associations |
| `clinvar` | ✅ Via EFO | Variant data |
| `reactome` | ✅ Via UniProt | Pathway data |
| `clinical_trials` | ⚠️ Limited | EFO connection weak |

### Mapping Chain Insights

**ChEMBL Molecule to Drugs via Genes:**
```
gene >> ensembl[homo_sapiens] >> uniprot[reviewed]
     >> chembl_target_component >> chembl_target
     >> chembl_assay >> chembl_activity >> chembl_molecule
```
- Direct `uniprot >> chembl_target` returns 0 results
- Must go through full assay chain

**PubChem >> Patent (discovered):**
```
pubchem >> patent  # Returns 150+ results
```
- PubChem drugs can have patents not linked via ChEMBL
- Future enhancement: add patent enrichment to PubChem path

---

## Future Work

### Qdrant Paths (Priority)

| Path | Description | Status |
|------|-------------|--------|
| `similar_proteins.py` | PATH 8: Qdrant ESM-2 protein similarity | TODO |
| `similar_compounds.py` | PATH 9: Qdrant Morgan FP compound similarity | TODO |

### Phase Improvements

#### Phase 1: Understand - LLM-Based Intent Parsing
**Current:** Regex pattern matching extracts disease name only
**Future:** LLM parses full intent with parameters

```python
# phases/understand.py (FUTURE)
class UnderstandPhase:
    async def execute(self, query: str) -> QueryIntent:
        """
        Parse: "What Phase 3+ drugs for glioblastoma target EGFR?"

        Returns:
        QueryIntent(
            query_type="filtered_drug_discovery",
            disease="glioblastoma",
            min_phase=3,
            target_genes=["EGFR"],
            focus_areas=["direct_indications"],
            output_format="detailed"
        )
        """
```

#### Phase 6: Synthesize - Improved Response Generation
**Current:** Simple synthesis prompt, bullet-point output
**Future:** Context-aware formatting with templates

### Potential Enhancements

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| PubChem >> Patent enrichment | Add patents from PubChem drugs (2850 patents found in test) | Medium |
| BindingDB affinity data | Fetch full Ki/Kd/IC50 from BindingDB API | Low |
| Antibody sequences | Include VH/VL sequences for structure analysis | Low |
| DrugBank integration | Check `chembl >> drugbank` connection | Medium |
| UniProt >> PDB | Structural data for targets | Medium |

---

## GatherOptions

```python
@dataclass
class GatherOptions:
    min_indication_phase: int = 3
    include_gwas: bool = True
    include_clinvar: bool = True
    include_reactome: bool = True
    include_uniprot: bool = True
    include_pubchem: bool = True
    include_clinical_trials: bool = True
    include_patents: bool = False         # Disabled by default (can be slow)
    include_bindingdb: bool = True        # Enabled by default
    include_antibodies: bool = True       # Enabled by default
    include_similar_proteins: bool = False  # TODO: Qdrant
    include_similar_compounds: bool = False  # TODO: Qdrant
    max_genes: int = 50
    max_drugs_for_enrichment: int = 50
```

---

## Architecture Principles

1. **Agent IS the orchestrator** - No mega-tools
2. **Generic functionality in tools/clients** - Pagination, connection handling
3. **Agent-specific logic in agent** - Intent parsing, response formatting
4. **Paths are composable** - Each path is independent, can run in parallel
5. **Phases are sequential** - Understand → Gather → Score → Reason → Follow-up → Synthesize

---

## How to Test

```bash
# Run CLI test
python modules/agent_system/tests/cli.py "What drugs for glioblastoma?"

# Quick import test
python -c "from modules.agent_system.agents import create_reasoning_engine; print('OK')"

# Test new paths
python -c "
from modules.agent_system.agents.drug_discovery.paths import BindingDBPath, AntibodyPath
print('BindingDB and Antibody paths imported successfully')
"
```

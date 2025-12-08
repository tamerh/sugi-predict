# BioYoda Multi-Agent System

Intelligent RAG system with specialized agents that blend deterministic mappings (BioBTree) and semantic search (BioYoda) for bioinformatics analysis.

## Structure

```
modules/agent_system/
├── agents/                 # Agent system (Reasoning Engine + specialized agents)
│   ├── __init__.py         # Public exports
│   ├── base.py             # Base Agent class with ReAct pattern
│   ├── reasoning_engine.py # Query router
│   ├── factory.py          # Agent creation utilities
│   ├── id_mapping/         # ID Mapping Agent (self-contained)
│   │   ├── __init__.py
│   │   ├── agent.py        # Agent implementation
│   │   ├── prompt.txt      # System prompt
│   │   ├── chains.yaml     # BioBTree chain templates
│   │   └── examples.yaml   # Test queries and expected results
│   └── drug_discovery/     # Drug Discovery Agent (self-contained)
│       ├── __init__.py
│       ├── agent.py        # Agent implementation
│       ├── prompt.txt      # System prompt
│       ├── chains.yaml     # BioBTree chain templates
│       └── examples.yaml   # Test queries and known issues
├── core/                   # Configuration management
├── data/                   # Data files
│   ├── fine_tuning/        # Fine-tuning training data (JSONL)
│   └── issues/             # Issue tracking (issues.log)
├── integrations/           # BioBTree gRPC client + protobuf
├── llm/                    # Multi-provider LLM framework
│   ├── gemini_provider.py  # Google Gemini
│   ├── claude_manual_provider.py # Development mode (Claude as LLM)
│   └── factory.py          # Provider creation
├── tools/                  # Tool abstraction layer (BioBTree tools)
├── prompts/                # Centralized prompts
│   └── reasoning_engine/   # Routing prompts
└── tests/                  # Testing
    ├── cli.py              # Interactive CLI (uses LLM API)
    ├── manual_cli.py       # Development CLI (Claude as LLM)
    ├── runner.py           # Automated test runner
    └── test_cases.yaml     # Test definitions
```

## Quick Start

```bash
# Activate environment
conda activate bioyoda

# IMPORTANT: Run from agent_system directory
cd modules/agent_system

# Test with reasoning engine
python -m tests.cli "Map EGFR to UniProt"

# Test in direct mode (bypass agents)
python -m tests.cli --direct "Map EGFR to UniProt"

# Run automated tests
python -m tests.runner --quick
python -m tests.runner --agent --quick  # Test with reasoning engine
```

## Components

### Phase 1 (Complete)
- **Configuration**: Pydantic-based config with YAML loading (`core/config.py`)
- **BioBTree Client**: Async gRPC client with lite/full mode support (`integrations/`)
- **LLM Framework**: Multi-provider with function calling (`llm/`)
- **Tool Layer**: BioBTree query/search tools with native filtering (`tools/`)

### Phase 2 (Complete)
- **Base Agent Class**: ReAct pattern implementation with tool execution
- **ID Mapping Agent**: Specialized for biological ID mapping (gene→protein, pathways, GO terms)
- **Drug Discovery Agent**: Finds drugs/compounds targeting genes/proteins
- **Reasoning Engine**: Query router that selects appropriate agent
- **Agent Factory**: Utilities for creating and configuring agents
- **Manual Provider**: Development mode with Claude Code acting as LLM

### BioBTree Features
- **Lite mode**: Compact ID-only responses (default)
- **Native filtering**: Server-side species and canonical protein filtering
- **Multi-term queries**: `"TP53,BRCA1,EGFR >> ensembl >> uniprot"`

### Next Steps (Phase 3+)
- Variant Analysis Agent
- BioYoda Search Tool (semantic search)
- Response Formatter
- Fine-tuning with collected training data

## Testing

```bash
# IMPORTANT: Run from agent_system directory
cd modules/agent_system

# Manual testing with LLM API
python -m tests.cli                           # Interactive mode (reasoning engine)
python -m tests.cli "your query"              # Single query
python -m tests.cli --direct "query"          # Direct mode (bypass agents)

# Automated tests
python -m tests.runner --list                 # List all tests
python -m tests.runner -t "test name"         # Run single test
python -m tests.runner --quick                # Quick smoke test
python -m tests.runner --agent                # Test with reasoning engine
python -m tests.runner                        # Full suite (direct mode)
```

Add tests to `tests/test_cases.yaml`:
```yaml
- name: "My test"
  query: "Map KRAS to UniProt"
  expect_tool: biobtree_query
  expect_agent: id_mapping     # For agent mode
  expect_contains: ["P01116"]
```

## Development Mode (Manual Provider)

For development without LLM API costs, use the **Manual Provider** where Claude Code acts as the LLM:

```bash
# IMPORTANT: Run from agent_system directory
cd modules/agent_system

# Interactive development mode
python -m tests.manual_cli --interactive

# Single query
python -m tests.manual_cli "What drugs target EGFR?"
```

### How It Works

1. **You run a query** → System shows the prompt and available tools
2. **You (or Claude) provide JSON response** → Tool call or text answer
3. **System executes the real tool** → BioBTree query runs
4. **Results shown** → You provide final answer
5. **Auto-saved** → Fine-tuning data collected in `data/fine_tuning/`

### Response Format

```bash
# Tool call:
{"tool": "biobtree_query", "args": {"chain_query": "EGFR >> ensembl >> uniprot"}}

# Text response:
{"content": "The UniProt ID for EGFR is P00533"}

# Skip (empty response):
skip
```

### Example Session

```
Query: What drugs target EGFR?

[System shows prompt and tools]

> {"tool": "biobtree_query", "args": {"chain_query": "EGFR >> ensembl >> uniprot >> chembl_target_component >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule"}}

[Tool executes, shows 150 drug molecules]

> {"content": "Found 150 drug molecules targeting EGFR including CHEMBL3142195, CHEMBL67009..."}

[Saved to fine-tuning data]
```

### Fine-Tuning Data

Automatically collected in OpenAI JSONL format:
- Location: `data/fine_tuning/bioyoda_training.jsonl`
- Use with: OpenAI fine-tuning API (GPT-4o mini, GPT-4.1 nano)

### Issue Reporting

When something doesn't work, log it to `data/issues/issues.log`:

```
# Format: [DATE] [TYPE] Query | Issue | Notes
# Types: MAPPING_FAIL, TOOL_ERROR, ROUTING_WRONG, DATA_MISSING

[2024-12-08] [MAPPING_FAIL] "BCR-ABL query" | Not found in ensembl | Fusion gene
[2024-12-08] [DATA_MISSING] "Drug X" | No ChEMBL data | Check if loaded
```

Issue types:
- `MAPPING_FAIL` - BioBTree couldn't map the identifier
- `TOOL_ERROR` - Tool execution failed
- `ROUTING_WRONG` - Query went to wrong agent
- `DATA_MISSING` - Expected data not in database

## Usage Example

```python
# Using Reasoning Engine (recommended)
from modules.agent_system.agents import create_reasoning_engine

engine = create_reasoning_engine()
response = await engine.process("Map TP53 to UniProt")
print(response.answer)
print(response.agent_used)  # "id_mapping"

# Direct tool use (bypass agents)
from modules.agent_system.tools import setup_tools

registry = setup_tools()
result = await registry.execute_tool(
    "biobtree_query",
    chain_query="TP53 >> ensembl >> uniprot"
)
print(result.data)  # {'mode': 'lite', 'mappings': [...]}
```

## Configuration

Main config: `config/agent_system.yaml`

Key settings:
- BioBTree: `scc2:7777` (gRPC), `scc2:9292` (REST)
- LLM: Merges with `config/config.yaml` → `rag` section
- Default: Gemini 2.0 Flash Lite

## BioBTree Query Syntax

```
identifier >> source_dataset >> target_dataset

Examples:
  EGFR >> ensembl >> uniprot                    # Gene to protein
  P04637 >> uniprot >> ensembl                  # Protein to gene
  TP53,BRCA1 >> ensembl >> uniprot              # Multiple terms
  EGFR >> ensembl >> uniprot >> reactome        # Gene to pathways

Datasets: ensembl, uniprot, chembl_target, chembl_molecule,
          reactome, go, dbsnp, drugbank, hgnc
```

## Agent Architecture

```
User Query
    │
    ▼
┌──────────────────┐
│ Reasoning Engine │ ← Routes queries to agents
└────────┬─────────┘
         │
    ┌────┼────────────┐
    ▼    ▼            ▼
┌────────┐ ┌─────────┐ ┌────────┐
│  ID    │ │  Drug   │ │ Direct │
│Mapping │ │Discovery│ │Response│
│ Agent  │ │  Agent  │ │  (LLM) │
└────┬───┘ └────┬────┘ └────────┘
     │          │
     └────┬─────┘
          ▼
    ┌──────────┐
    │ BioBTree │
    │   Tool   │
    └──────────┘
```

### Supported Query Types

| Query Type | Agent | Example Chain |
|------------|-------|---------------|
| Gene → Protein | `id_mapping` | `TP53 >> ensembl >> uniprot` |
| Gene → Pathways | `id_mapping` | `TP53 >> ensembl >> uniprot >> reactome` |
| Gene → GO Terms | `id_mapping` | `BRCA1 >> ensembl >> uniprot >> go` |
| Gene → Drugs | `drug_discovery` | `EGFR >> ensembl >> uniprot >> chembl_target_component >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule` |
| General Biology | `direct` | LLM answers from knowledge |

## Adding New Agents

Each agent is self-contained in its own folder with all related files:

```
agents/new_agent/
├── __init__.py      # Export agent class
├── agent.py         # Agent implementation (extends base.Agent)
├── prompt.txt       # System prompt loaded automatically
├── chains.yaml      # BioBTree chain templates
└── examples.yaml    # Test queries with expected results and known issues
```

### Steps to Add a New Agent

1. **Create folder**: `agents/new_agent/`

2. **Create `__init__.py`**:
   ```python
   from .agent import NewAgent
   __all__ = ["NewAgent"]
   ```

3. **Create `agent.py`** (extend base Agent):
   ```python
   from pathlib import Path
   from typing import Optional
   from ..base import Agent

   class NewAgent(Agent):
       AGENT_DIR = Path(__file__).parent
       _cached_prompt: Optional[str] = None  # Class-level cache (load once)

       def __init__(self, llm, tool_registry, system_prompt=None):
           if system_prompt is None:
               if NewAgent._cached_prompt is None:
                   prompt_file = self.AGENT_DIR / "prompt.txt"
                   if prompt_file.exists():
                       NewAgent._cached_prompt = prompt_file.read_text()
               system_prompt = NewAgent._cached_prompt
           super().__init__(llm, tool_registry, system_prompt)
   ```
   > **Note**: Use class-level `_cached_prompt` to avoid disk reads on every request in production.

4. **Create `prompt.txt`**: System prompt with agent capabilities and BioBTree syntax

5. **Create `chains.yaml`**: BioBTree chain templates
   ```yaml
   template_name:
     description: "What this chain does"
     chain: "{variable} >> dataset >> dataset"
     example: "GENE >> ensembl >> uniprot"
   ```

6. **Create `examples.yaml`**: Test queries and known issues
   ```yaml
   queries:
     - q: "User query"
       chain: "Expected BioBTree chain"
       expected: "Expected result summary"
       status: ok
   issues:
     - q: "Failing query"
       issue: "What went wrong"
       workaround: "How to work around it"
       date: "2024-12-08"
   ```

7. **Register in `factory.py`**:
   ```python
   from .new_agent import NewAgent

   agents = {
       "id_mapping": IDMappingAgent,
       "drug_discovery": DrugDiscoveryAgent,
       "new_agent": NewAgent,  # Add here
   }
   ```

8. **Update `__init__.py`**: Export the new agent class

## BioBTree Reference

When developing agents that use BioBTree, refer to these documentation sources:

### Documentation Locations
```
bioyoda_dev2/biobtreev2/
├── README.md                          # Main BioBTree documentation
├── tests/xintegration/
│   └── integration_tests.json         # Full test suite with query examples
├── tests/datasets/
│   └── <dataset>/                     # Per-dataset documentation
│       ├── README.md                  # Dataset overview, attributes, use cases
│       ├── test_cases.json            # Dataset-specific test queries
│       └── reference_data.json        # Expected data for validation
└── src/pbuf/
    └── attr.proto                     # Protocol buffer definitions (attribute names)
```

### Key Datasets for Agents

| Dataset | Description | Key Attributes |
|---------|-------------|----------------|
| `ensembl` | Gene IDs/symbols | `genome`, `biotype`, `hgnc.*` |
| `uniprot` | Proteins | `reviewed`, `genes`, `names` |
| `chembl_molecule` | Drugs/compounds | `highestDevelopmentPhase`, `type`, `smiles` |
| `chembl_activity` | Bioactivity | `pChembl`, `value`, `bao` |
| `chembl_target` | Drug targets | `type`, `tax` |
| `reactome` | Pathways | `name`, `is_disease_pathway` |
| `go` | Gene Ontology | `type` (biological_process, molecular_function, cellular_component) |
| `clinvar` | Clinical variants | `germline_classification`, `review_status` |
| `bgee` | Gene expression | `expression_score`, `call_quality` |
| `gwas` | GWAS associations | `p_value`, `pvalue_mlog` |
| `dbsnp` | SNP variants | `allele_frequency`, `clinical_significance` |
| `intact` | Protein interactions | `confidence_score`, `detection_method` |

### Filter Syntax
```bash
# Basic filter
dataset[attribute==value]
dataset[attribute>value]
dataset[attribute<value]

# String filter (use quotes)
dataset[attribute=="string_value"]

# Examples
uniprot[uniprot.reviewed==true]
ensembl[ensembl.genome=="homo_sapiens"]
chembl_molecule[chembl.molecule.highestDevelopmentPhase>2]
chembl_activity[chembl.activity.pChembl>7]
go[go.type=="biological_process"]
```

### Common Chain Patterns
```bash
# Gene to protein (canonical)
GENE >> ensembl >> uniprot[uniprot.reviewed==true]

# Gene to drugs (full ChEMBL path)
GENE >> ensembl >> uniprot >> chembl_target_component >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule

# Gene to pathways
GENE >> ensembl >> uniprot >> reactome

# Gene to GO terms
GENE >> ensembl >> uniprot >> go[go.type=="biological_process"]

# Gene to clinical variants
GENE >> ensembl >> clinvar

# Protein to interactions
P00533 >> uniprot >> intact
```

### Finding Attribute Names
1. Check `tests/datasets/<dataset>/README.md` for attribute documentation
2. Check `src/pbuf/attr.proto` for exact protobuf field names
3. Use format: `dataset.attribute` (e.g., `chembl.molecule.highestDevelopmentPhase`)

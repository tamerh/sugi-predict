# Query Execution Flow - BioYoda Multi-Agent RAG System

**Document Version:** 1.0
**Date:** 2025-11-24
**Purpose:** Detailed flow showing how queries are processed from user input to results

---

## Overview

This document explains the complete flow of a user query through the BioYoda Multi-Agent RAG System, showing:
- Where LLM prompts are created and used
- How queries are dispatched to BioBTree or BioYoda
- Where and how BioBTree chain queries are built
- Where agents play their role
- Where results are produced and formatted

---

## Complete Query Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: USER INPUT                                              │
│                                                                 │
│ User: "Find drugs targeting EGFR and their side effects"       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: QUERY GATEWAY (Entry Point)                            │
│ Location: modules/agent_system/gateway/query_gateway.py        │
│                                                                 │
│ • Validates query                                               │
│ • Extracts entities (EGFR)                                      │
│ • Passes to Reasoning Engine                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: REASONING ENGINE (Query Understanding)                 │
│ Location: modules/agent_system/orchestration/reasoning_engine.py│
│                                                                 │
│ 📝 PROMPT 1: "Agent Selection Prompt"                          │
│ ────────────────────────────────────────────────────────────── │
│ System: You are a biomedical query router.                     │
│                                                                 │
│ Available agents:                                               │
│ - Drug Discovery Agent: targets, compounds, trials (HYBRID)    │
│ - Variant Analysis Agent: SNPs, GWAS, ClinVar (HYBRID)         │
│ - Literature Agent: papers, reviews (SEMANTIC)                  │
│ - Identifier Mapping Agent: ID lookups (DETERMINISTIC)         │
│                                                                 │
│ Query: "Find drugs targeting EGFR and their side effects"      │
│                                                                 │
│ Which agent should handle this? Output JSON:                   │
│ {"agent": "drug_discovery", "reasoning": "..."}                │
│ ────────────────────────────────────────────────────────────── │
│                                                                 │
│ 🤖 LLM Response:                                                │
│ {                                                               │
│   "agent": "drug_discovery",                                    │
│   "reasoning": "Query needs compound lookup (BioBTree) and     │
│                 side effects (BioYoda semantic search)"         │
│ }                                                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: DRUG DISCOVERY AGENT (Multi-Step Execution)            │
│ Location: modules/agent_system/agents/drug_discovery/agent.py  │
│                                                                 │
│ 📝 PROMPT 2: "Agent Execution Prompt" (ReAct Pattern)          │
│ ────────────────────────────────────────────────────────────── │
│ System: You are a Drug Discovery Agent.                        │
│                                                                 │
│ Available tools:                                                │
│ 1. biobtree_query(chain_query: str)                            │
│    - For deterministic data                                     │
│    - Syntax: "EGFR >> uniprot >> chembl_target"                │
│    - Datasets: uniprot, chembl, reactome, etc.                 │
│                                                                 │
│ 2. bioyoda_search(query: str, collection: str)                 │
│    - For semantic search                                        │
│    - Collections: pubmed, clinical_trials, patents             │
│                                                                 │
│ User Query: "Find drugs targeting EGFR and their side effects" │
│                                                                 │
│ Use ReAct pattern:                                              │
│ Thought: What do I need?                                        │
│ Action: tool_name(params)                                       │
│ Observation: tool result                                        │
│ Thought: Do I need more?                                        │
│ ... repeat ...                                                  │
│ Answer: final response                                          │
│ ────────────────────────────────────────────────────────────── │
│                                                                 │
│ Agent starts reasoning loop...                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
      ┌──────────────────────┼──────────────────────┐
      │                      │                      │
      ▼                      ▼                      ▼
┌──────────────┐   ┌──────────────────┐   ┌─────────────────┐
│ ITERATION 1  │   │  ITERATION 2     │   │  ITERATION 3    │
└──────────────┘   └──────────────────┘   └─────────────────┘
```

---

## Detailed Iteration Breakdown

### ITERATION 1: Get Compounds from BioBTree

```
┌─────────────────────────────────────────────────────────────────┐
│ 🤖 Agent's LLM Thought:                                         │
│ "I need to find compounds targeting EGFR. EGFR is a gene,      │
│  so I need: gene → protein → targets → compounds"              │
│                                                                 │
│ 🤖 Agent's LLM Action:                                          │
│ biobtree_query("EGFR >> uniprot >> chembl_target >> chembl_molecule")│
│                                                                 │
│       │                                                         │
│       ▼                                                         │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ BIOBTREE TOOL EXECUTION                                   │ │
│ │ Location: modules/agent_system/tools/biobtree/tool.py    │ │
│ │                                                            │ │
│ │ ❌ No prompts here! Just executes:                        │ │
│ │ 1. Parse: "EGFR >> uniprot >> chembl_target >> chembl_molecule"│ │
│ │ 2. Call BioBTree REST API:                                │ │
│ │    GET /ws/map/?i=EGFR&m=uniprot>>chembl_target>>chembl_molecule│ │
│ │ 3. Parse response                                          │ │
│ │ 4. Return to agent                                         │ │
│ └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│ 🔍 Tool Response (from BioBTree):                              │
│ {                                                               │
│   "success": true,                                              │
│   "source": "biobtree",                                         │
│   "confidence_type": "deterministic",                           │
│   "results": [                                                  │
│     {"chembl_id": "CHEMBL6939", "name": "Gefitinib"},          │
│     {"chembl_id": "CHEMBL941", "name": "Erlotinib"},           │
│     {"chembl_id": "CHEMBL1173655", "name": "Afatinib"},        │
│     ... 42 more compounds                                       │
│   ]                                                             │
│ }                                                               │
│                                                                 │
│ 🤖 Agent's LLM Observation:                                     │
│ "Found 45 compounds targeting EGFR via ChEMBL. Top compounds:  │
│  Gefitinib, Erlotinib, Afatinib - all FDA approved."           │
└─────────────────────────────────────────────────────────────────┘
```

### ITERATION 2: Get Side Effects from BioYoda

```
┌─────────────────────────────────────────────────────────────────┐
│ 🤖 Agent's LLM Thought:                                         │
│ "Now I need side effects. I'll search clinical trials for      │
│  information about these EGFR inhibitors"                      │
│                                                                 │
│ 🤖 Agent's LLM Action:                                          │
│ bioyoda_search(                                                 │
│   query="EGFR inhibitor side effects adverse events",          │
│   collection="clinical_trials"                                 │
│ )                                                               │
│                                                                 │
│       │                                                         │
│       ▼                                                         │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ BIOYODA TOOL EXECUTION                                    │ │
│ │ Location: modules/agent_system/tools/bioyoda/tool.py     │ │
│ │                                                            │ │
│ │ ❌ No prompts here! Just executes:                        │ │
│ │ 1. Get embedding for query (S-BioBERT)                   │ │
│ │ 2. Call Qdrant:                                           │ │
│ │    qdrant_client.search(                                  │ │
│ │      collection="clinical_trials",                        │ │
│ │      query_vector=embedding,                              │ │
│ │      limit=20                                             │ │
│ │    )                                                       │ │
│ │ 3. Return results to agent                                │ │
│ └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│ 🔍 Tool Response (from Qdrant):                                │
│ {                                                               │
│   "success": true,                                              │
│   "source": "qdrant",                                           │
│   "confidence_type": "semantic",                                │
│   "results": [                                                  │
│     {                                                           │
│       "nct_id": "NCT01234567",                                 │
│       "title": "Safety of Erlotinib in NSCLC",                │
│       "adverse_events": "skin rash (78%), diarrhea (45%)...",  │
│       "similarity": 0.94                                        │
│     },                                                          │
│     {                                                           │
│       "nct_id": "NCT09876543",                                 │
│       "title": "Gefitinib toxicity study",                     │
│       "adverse_events": "acne, rash, interstitial pneumonia",  │
│       "similarity": 0.91                                        │
│     },                                                          │
│     ... 18 more trials                                          │
│   ]                                                             │
│ }                                                               │
│                                                                 │
│ 🤖 Agent's LLM Observation:                                     │
│ "Found 20 clinical trials mentioning EGFR inhibitor side       │
│  effects. Most common: skin rash (60-80%), diarrhea (40-50%),  │
│  fatigue (30-40%). Some reports of interstitial lung disease." │
└─────────────────────────────────────────────────────────────────┘
```

### ITERATION 3: Generate Final Answer

```
┌─────────────────────────────────────────────────────────────────┐
│ 🤖 Agent's LLM Thought:                                         │
│ "I have compounds from BioBTree (deterministic) and side       │
│  effects from clinical trials (semantic). I can now answer     │
│  the user's question comprehensively."                         │
│                                                                 │
│ 🤖 Agent's LLM Action:                                          │
│ No action - ready to answer                                     │
│                                                                 │
│ 📝 PROMPT 3: "Answer Synthesis" (Implicit in ReAct)            │
│ ────────────────────────────────────────────────────────────── │
│ The LLM synthesizes from conversation history:                 │
│ - User query: "Find drugs targeting EGFR and their side effects"│
│ - Tool 1 result: 45 compounds from BioBTree (deterministic)    │
│ - Tool 2 result: 20 clinical trials from BioYoda (semantic)    │
│                                                                 │
│ Generate a coherent, comprehensive answer with:                │
│ - List of compounds                                             │
│ - Side effect profile                                           │
│ - Source attribution                                            │
│ ────────────────────────────────────────────────────────────── │
│                                                                 │
│ 🤖 Agent's LLM Answer:                                          │
│                                                                 │
│ "I found 45 drugs that target EGFR, including several FDA-     │
│  approved inhibitors:                                          │
│                                                                 │
│  🔒 COMPOUNDS (from ChEMBL - Deterministic):                   │
│  • Gefitinib (CHEMBL6939) - FDA approved                       │
│  • Erlotinib (CHEMBL941) - FDA approved                        │
│  • Afatinib (CHEMBL1173655) - FDA approved                     │
│  • Lapatinib (CHEMBL554) - FDA approved                        │
│  ... and 41 more compounds                                      │
│                                                                 │
│  🔍 SIDE EFFECTS (from 20 Clinical Trials - Semantic):         │
│  Based on clinical trial data, the most common side effects    │
│  of EGFR inhibitors are:                                       │
│                                                                 │
│  • Skin rash/acne (60-80% of patients)                         │
│    - Typically appears within first 2-4 weeks                  │
│    - Often correlates with efficacy                            │
│                                                                 │
│  • Diarrhea (40-50%)                                           │
│    - Usually manageable with standard treatments               │
│                                                                 │
│  • Fatigue (30-40%)                                            │
│                                                                 │
│  • Less common but serious: Interstitial lung disease (<5%)    │
│                                                                 │
│  📊 Data Sources:                                               │
│  - Compound data: BioBTree → ChEMBL (100% deterministic)       │
│  - Safety data: Qdrant → Clinical Trials (semantic search,     │
│    similarity scores 0.91-0.94)                                │
│                                                                 │
│  Note: Skin toxicity, while common, is often a positive        │
│  indicator of drug efficacy with EGFR inhibitors."             │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
```

---

## STEP 5: Response Formatting

```
┌─────────────────────────────────────────────────────────────────┐
│ RESPONSE FORMATTER                                              │
│ Location: modules/agent_system/gateway/response_formatter.py   │
│                                                                 │
│ Takes agent's answer and formats for API response:             │
│                                                                 │
│ • Add confidence labels (🔒 deterministic, 🔍 semantic)        │
│ • Calculate blend percentages                                   │
│ • Format according to user preferences (text/table/json)       │
│ • Include reasoning trace if requested                          │
│ • Add metadata (cost, time, sources)                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
```

---

## STEP 6: Final API Response

```json
{
  "query_id": "uuid-1234",
  "session_id": "session-5678",
  "success": true,

  "answer": "I found 45 drugs that target EGFR, including several FDA-approved inhibitors...",

  "sources": [
    {
      "type": "structured",
      "name": "ChEMBL via BioBTree",
      "icon": "🔒",
      "confidence_type": "deterministic",
      "confidence_score": 1.0,
      "reproducible": true,
      "query": "EGFR >> uniprot >> chembl_target >> chembl_molecule",
      "result_count": 45
    },
    {
      "type": "semantic",
      "name": "Clinical Trials via Qdrant",
      "icon": "🔍",
      "confidence_type": "similarity",
      "confidence_score": 0.92,
      "reproducible": "configurable",
      "query": "EGFR inhibitor side effects adverse events",
      "result_count": 20
    }
  ],

  "reasoning": {
    "query_analysis": "Query requires deterministic compound lookup + semantic side effect search",
    "selected_agent": "drug_discovery",
    "agent_type": "hybrid",
    "tool_calls": [
      {
        "tool": "biobtree_query",
        "input": {"chain_query": "EGFR >> uniprot >> chembl_target >> chembl_molecule"},
        "output": {"success": true, "result_count": 45}
      },
      {
        "tool": "bioyoda_search",
        "input": {"query": "EGFR inhibitor side effects", "collection": "clinical_trials"},
        "output": {"success": true, "result_count": 20}
      }
    ],
    "reasoning_steps": 2
  },

  "blend_info": {
    "actual_blend": {
      "deterministic": 0.42,
      "semantic": 0.33,
      "llm": 0.25
    },
    "data_sources_used": ["biobtree", "qdrant_clinical_trials"]
  },

  "metadata": {
    "agent_used": "drug_discovery",
    "agent_type": "hybrid",
    "execution_time_ms": 4234,
    "user_tier": "researcher",
    "queries_remaining_today": 987,
    "llm_usage": {
      "provider": "anthropic",
      "model": "claude-3-5-sonnet-20241022",
      "input_tokens": 2456,
      "output_tokens": 789,
      "cost_usd": 0.048
    }
  }
}
```

---

## Summary Tables

### Where Prompts Are Created

| # | Prompt Name | Location | Purpose | Who Uses It |
|---|-------------|----------|---------|-------------|
| **1** | Agent Selection | `modules/agent_system/orchestration/reasoning_engine.py` | Route query to right agent | Reasoning Engine LLM |
| **2** | Agent Execution (ReAct) | `modules/agent_system/agents/{agent_name}/agent.py` | Multi-step tool usage loop | Agent's LLM |
| **3** | Answer Synthesis | Implicit in ReAct loop | Synthesize final answer from tool results | Agent's LLM |

### Where BioBTree/BioYoda Queries Are Built

| Component | Builds Queries? | How? | Responsibility |
|-----------|-----------------|------|----------------|
| **Reasoning Engine** | ❌ No | Only selects which agent | Routes query |
| **Agent (LLM)** | ✅ Yes | Decides BioBTree chain syntax via ReAct | **Builds queries** |
| **BioBTree Tool** | ❌ No | Just executes what agent provides | Executes query |
| **BioYoda Tool** | ❌ No | Just executes semantic search | Executes search |

**Key Point**: The **Agent's LLM** builds the queries by:
1. Understanding user intent
2. Knowing tool capabilities (from tool description in system prompt)
3. Using ReAct pattern to decide exactly what to query
4. Example: `biobtree_query("EGFR >> uniprot >> chembl_target >> chembl_molecule")`

### Where Agents Play a Role

```
Reasoning Engine
  ↓
  Selects which agent based on query type
  ↓
Specialized Agent (e.g., Drug Discovery Agent)
  ↓
  • Orchestrates multiple tools
  • Builds specific BioBTree/BioYoda queries
  • Decides when to stop querying
  • Synthesizes final answer from tool results
  ↓
Tools (BioBTree/BioYoda)
  ↓
  Execute queries without reasoning
  ↓
Agent receives results
  ↓
  Decides next step or final answer
```

### Tool vs Agent Responsibilities

| Responsibility | Tool | Agent |
|----------------|------|-------|
| Know data source syntax | ✅ Yes | ❌ No |
| Execute queries | ✅ Yes | ❌ No |
| Understand user goal | ❌ No | ✅ Yes |
| Build query strategy | ❌ No | ✅ Yes |
| Decide when to stop | ❌ No | ✅ Yes |
| Synthesize answer | ❌ No | ✅ Yes |
| Multi-step reasoning | ❌ No | ✅ Yes |

---

## File Structure for Prompts

```
modules/agent_system/
├── orchestration/
│   ├── reasoning_engine.py
│   │   └── Contains PROMPT 1: Agent selection
│   └── prompts/
│       ├── agent_selection_system.txt      # System prompt template
│       └── agent_selection_examples.txt    # Few-shot examples
│
├── agents/
│   ├── drug_discovery/
│   │   ├── agent.py
│   │   │   └── Contains PROMPT 2: ReAct execution
│   │   └── prompts/
│   │       ├── system_prompt.txt          # ReAct system prompt
│   │       └── few_shot_examples.txt      # Example interactions
│   │
│   ├── variant_analysis/
│   │   ├── agent.py
│   │   └── prompts/
│   │       └── system_prompt.txt
│   │
│   ├── protein_analysis/
│   │   ├── agent.py
│   │   └── prompts/
│   │       └── system_prompt.txt
│   │
│   └── literature_discovery/
│       ├── agent.py
│       └── prompts/
│           └── system_prompt.txt
│
└── tools/
    ├── biobtree/
    │   └── tool.py                        # ❌ No prompts - just execution
    │
    └── bioyoda/
        └── tool.py                        # ❌ No prompts - just execution
```

---

## Key Design Principles

### 1. **Separation of Concerns**
- **Tools** know HOW to execute (syntax, API calls)
- **Agents** know WHAT to do (strategy, user intent)
- **Reasoning Engine** knows WHICH agent to use

### 2. **LLM-Powered Intelligence**
- Agents use natural language reasoning
- No hard-coded query patterns
- Adapts to new questions dynamically

### 3. **Transparency**
- All tool calls logged
- Reasoning steps visible
- Sources clearly attributed

### 4. **Deterministic + Semantic Blend**
- BioBTree queries: 100% reproducible
- BioYoda searches: Configurable similarity threshold
- Blend happens naturally based on agent's execution

### 5. **Scalability**
- New agents can reuse existing tools
- New tools can be added without changing agents
- Same pattern works for all agent types

---

## Example Variations

### Simple Deterministic Query

**Query**: "What is the UniProt ID for BRCA1?"

**Flow**:
1. Reasoning Engine → Selects Identifier Mapping Agent (deterministic)
2. Agent → Single tool call: `biobtree_query("BRCA1 >> uniprot")`
3. BioBTree Tool → Returns P38398
4. Agent → Answer: "UniProt ID: P38398"
5. **Blend**: 100% deterministic, 0% semantic, 0% LLM

### Complex Multi-Agent Query

**Query**: "Find SNPs associated with Alzheimer's, their gene context, and recent papers"

**Flow**:
1. Reasoning Engine → Could use Variant Analysis Agent OR coordinate multiple agents
2. Variant Agent →
   - Iteration 1: `biobtree_query("Alzheimer >> ... >> gwas")`
   - Iteration 2: `biobtree_query("rs123 >> dbsnp >> ensembl >> hgnc")`
   - Iteration 3: `bioyoda_search("rs123 Alzheimer", "pubmed_abstracts")`
3. Agent synthesizes from all sources
4. **Blend**: 40% deterministic, 35% semantic, 25% LLM

---

## Conclusion

This flow demonstrates:
- ✅ Clear separation between reasoning (agents) and execution (tools)
- ✅ LLM-powered query building by agents
- ✅ Transparent multi-step execution with ReAct pattern
- ✅ Automatic blending of deterministic and semantic data
- ✅ Tools are reusable, agents are flexible
- ✅ System scales with new agents and tools

The key innovation is that **agents decide WHAT to query, tools execute HOW to query**, with all reasoning driven by LLMs that understand both the user's intent and the tool capabilities.

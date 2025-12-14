# BioYoda Multi-Agent RAG System - Architecture Design Document

**Version:** 1.0
**Date:** 2025-11-19
**Status:** Design Phase - Living Document
**Authors:** BioYoda Development Team

---

## 📌 Important Notes

**API-First Architecture:**
- All user requests go through REST API (authentication, billing, rate limiting)
- No direct Python module imports for end users
- Single entry point for security and monitoring

**Configuration Management:**
- All configs centralized in `config/` directory
- No config files scattered in module directories
- Easier management and deployment

**Iterative Design Philosophy:**
- This document represents initial design based on current understanding
- Many details will be refined as we build and test the system
- Agent orchestration, blend weights, and presentation logic will evolve with user feedback
- This is a living specification, not a fixed blueprint
- We'll update based on real-world performance and learnings

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Core Value Proposition: Data Blending](#2-core-value-proposition-data-blending)
3. [System Overview](#3-system-overview)
4. [Agent Classification](#4-agent-classification)
5. [Architecture Design](#5-architecture-design)
6. [Core Components](#6-core-components)
7. [Specialized Agents](#7-specialized-agents)
8. [Result Presentation & Blending](#8-result-presentation--blending)
9. [Data Integration](#9-data-integration)
10. [API Specifications](#10-api-specifications)
11. [Data Flows](#11-data-flows)
12. [Deployment Architecture](#12-deployment-architecture)
13. [Security & Privacy](#13-security--privacy)
14. [Performance & Scalability](#14-performance--scalability)
15. [Testing Strategy](#15-testing-strategy)
16. [Monitoring & Observability](#16-monitoring--observability)
17. [Development Roadmap](#17-development-roadmap)
18. [Appendices](#18-appendices)

---

## 1. Executive Summary

### 1.1 Vision

The BioYoda Multi-Agent RAG System is an intelligent biomedical research platform that **uniquely blends four data paradigms**:
- **Structured data** (BioBTree): Deterministic facts, exact relationships across 40+ databases
- **Semantic vectors** (Qdrant): Similarity-based discovery through embeddings
- **Full-text literature** (Qdrant): Citation-backed evidence from 30M+ documents
- **LLM reasoning**: Synthesis and explanation connecting all sources

**The Core Innovation**: Users control the blend - adjusting weights, synthesis levels, and output formats to match their research needs.

### 1.2 Key Objectives

1. **Data Blending Engine**: Intelligently combine structured, semantic, and literature data with user-controllable weights
2. **Unified Query Interface**: Single entry point for deterministic lookups and exploratory discovery
3. **Intelligent Orchestration**: Automatic query planning and multi-step execution
4. **Domain Expertise**: Specialized agents for drug discovery, variant analysis, protein analysis
5. **Modular Architecture**: Agents work standalone or as part of unified system
6. **Multi-Provider LLM**: Support for Anthropic, OpenAI, Gemini with flexible selection
7. **Output Control**: Users control synthesis levels, confidence labeling, and result presentation

### 1.3 Success Metrics

**Phase 1-2 (Core + Initial Agents):**
- 80%+ success rate on simple queries (1-2 steps)
- <5 second latency for simple queries
- <$0.05 cost per query
- 10 demo queries working end-to-end

**Phase 3-6 (Full System):**
- 60%+ success rate on complex queries (3-5 steps)
- <30 second latency for complex queries
- 100+ queries/day throughput
- Multi-turn conversation support

---

## 2. Core Value Proposition: Data Blending

### 2.1 The Four Data Paradigms

The BioYoda Multi-Agent RAG System's unique value comes from **intelligently blending four complementary data paradigms**, each with distinct characteristics:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        THE BLENDING ENGINE                           │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  1. STRUCTURED DATA (BioBTree)                                 │ │
│  │     • Nature: Deterministic, exact relationships               │ │
│  │     • Query: BRCA1 >> uniprot >> chembl_target                 │ │
│  │     • Confidence: 100% (same input → same output)              │ │
│  │     • Use: Identifier mapping, cross-references, pathways      │ │
│  │     • Speed: Fast (<100ms), Cheap ($0.001)                     │ │
│  │     • Reproducibility: Perfect - critical for research         │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  2. SEMANTIC VECTORS (Qdrant Embeddings)                       │ │
│  │     • Nature: Similarity-based, conceptual matching            │ │
│  │     • Query: "CRISPR off-target effects" → similar embeddings  │ │
│  │     • Confidence: 60-95% (similarity scores)                   │ │
│  │     • Use: Discovery, finding related concepts                 │ │
│  │     • Speed: Fast (<500ms), Moderate cost ($0.01)              │ │
│  │     • Reproducibility: Good (same vectors, tunable threshold)  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  3. FULL-TEXT LITERATURE (Qdrant Documents)                    │ │
│  │     • Nature: Citation-backed evidence from publications       │ │
│  │     • Query: Papers/trials/patents with specific content       │ │
│  │     • Confidence: High (verifiable citations)                  │ │
│  │     • Use: Evidence gathering, literature review               │ │
│  │     • Speed: Moderate (<2s), Moderate cost ($0.02)             │ │
│  │     • Reproducibility: Good (documents don't change)           │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  4. LLM REASONING (Synthesis)                                  │ │
│  │     • Nature: Generative, connecting insights                  │ │
│  │     • Query: Synthesize findings across all sources            │ │
│  │     • Confidence: Variable (depends on grounding)              │ │
│  │     • Use: Explanation, hypothesis, pattern detection          │ │
│  │     • Speed: Slow (1-5s), Expensive ($0.05-0.10)               │ │
│  │     • Reproducibility: Low (non-deterministic)                 │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│              🎯 USER CONTROLS THE BLEND ← KEY VALUE!                │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Why Blending Matters

**The Problem with Single-Paradigm Systems:**
- **Structured-only** (traditional bioinformatics): Answers "what is" but not "what's related"
- **Semantic-only** (pure LLM/RAG): Discovers connections but lacks factual grounding
- **Literature-only** (PubMed search): Finds papers but doesn't connect to databases

**The BioYoda Solution:**
Blend all four paradigms with user-controllable weights to match research intent:

| Research Need | Structured | Semantic | Literature | LLM | Example Query |
|---------------|-----------|----------|------------|-----|---------------|
| **Exact Lookup** | 90% | 5% | 5% | Minimal | "What is UniProt ID for BRCA1?" |
| **Discovery** | 20% | 60% | 20% | Moderate | "Find novel EGFR pathway proteins" |
| **Evidence Review** | 10% | 20% | 60% | Full | "What do papers say about rs429358?" |
| **Balanced (default)** | 40% | 30% | 20% | Moderate | "Drugs targeting EGFR side effects" |
| **Clinical Decision** | 70% | 10% | 20% | Minimal | "ClinVar pathogenicity of variant X" |

### 2.3 Intelligent Blending: The Reasoning Engine Decides

**Key Innovation**: The system **automatically** determines the optimal blend based on query understanding.

**How It Works:**

```
User Query: "Find drugs targeting EGFR with side effects"
    ↓
┌─────────────────────────────────────────────────────────────┐
│  REASONING ENGINE (LLM-Powered Orchestrator)                │
│                                                              │
│  System Prompt includes:                                    │
│  • All agent capabilities (deterministic/semantic/hybrid)   │
│  • Data sources each agent uses (BioBTree/BioYoda)          │
│  • Cost, speed, reproducibility of each agent               │
│                                                              │
│  LLM analyzes query and decides:                            │
│  "This needs Drug Discovery Agent because:                  │
│   - 'drugs targeting EGFR' → BioBTree (deterministic)       │
│   - 'side effects' → BioYoda clinical trials (semantic)"    │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│  DRUG DISCOVERY AGENT (Hybrid Agent)                        │
│                                                              │
│  Agent internally knows its data sources:                   │
│  • BioBTree: For deterministic compound lookup              │
│  • BioYoda: For semantic trial/paper search                 │
│                                                              │
│  Step 1: EGFR >> uniprot >> chembl_target → 45 compounds    │
│          (BioBTree - deterministic)                          │
│                                                              │
│  Step 2: Search clinical_trials for "side effects"          │
│          (BioYoda - semantic)                                │
│                                                              │
│  Agent automatically blends its results                      │
└─────────────────────────────────────────────────────────────┘
    ↓
Result: 40% deterministic + 30% semantic + 30% LLM synthesis
(Automatically determined by agent's execution)
```

**User Control (Optional Constraints):**

Users don't manually set blend weights. Instead, they can:

```python
{
  "query": "Find drugs targeting EGFR",

  # Option 1: Let system decide (DEFAULT - RECOMMENDED)
  "mode": "auto",  # Reasoning engine chooses optimal agents

  # Option 2: Constrain to deterministic only
  "mode": "deterministic_only",  # Only BioBTree data, no semantic

  # Option 3: Force specific agent (skip reasoning)
  "agent": "drug_discovery",  # Use this agent directly

  # Option 4: Control LLM synthesis level
  "llm_synthesis": "moderate",  # none | minimal | moderate | full

  # Option 5: Output formatting
  "output_options": {
    "separate_sources": true,      # Show deterministic vs semantic separately
    "label_confidence": true,      # Mark each result type
    "format": "auto",              # text | table | json
    "verbosity": "medium"          # brief | medium | detailed
  }
}
```

**Why This Is Better Than Manual Weights:**

| Manual Weights (❌) | Intelligent Reasoning (✅) |
|---------------------|---------------------------|
| User must understand system internals | User just asks natural language questions |
| Wrong weights = poor results | System optimizes automatically |
| Static per query | Dynamic based on query complexity |
| Requires technical knowledge | Works for non-technical users |
| Hard to maintain as system grows | Scales with new agents automatically |

### 2.4 Example: Reasoning Engine in Action

**Query**: "What drugs target EGFR and what are their side effects?"

**Reasoning Engine Decision:**
```
Query Analysis:
- "drugs target EGFR" → Requires deterministic compound lookup (BioBTree)
- "side effects" → Requires semantic literature search (BioYoda)
- Complexity: Medium

Selected Agent: Drug Discovery Agent (Hybrid)
Estimated Blend: ~40% deterministic, ~35% semantic, ~25% LLM
Estimated Cost: $0.05
Estimated Time: 4-6s
```

#### Output (Automatically Blended)
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EGFR-Targeting Drugs & Side Effects Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[🔒 STRUCTURED DATA - ChEMBL] Deterministic
├─ 45 compounds targeting EGFR (UniProt: P00533)
├─ Top by potency:
│  • Afatinib (CHEMBL1173655): IC50 0.5nM, FDA approved
│  • Erlotinib (CHEMBL941): IC50 2nM, FDA approved
│  • Gefitinib (CHEMBL6939): IC50 33nM, FDA approved
└─ Confidence: 100%

[🔍 SEMANTIC ANALYSIS - Clinical Trials] Similarity-based
├─ 243 trials mention EGFR inhibitor adverse events
├─ Common side effects (clustered):
│  • Skin toxicity (rash): 189 trials (score: 0.94)
│  • Diarrhea: 156 trials (score: 0.91)
│  • Fatigue: 134 trials (score: 0.87)
└─ Confidence: High (>0.85 similarity)

[📄 LITERATURE - PubMed] Citation-backed
├─ 1,247 papers on EGFR inhibitor safety (2020-2024)
├─ Key findings:
│  • "Skin rash in 60-80% of patients" (PMID:28374321)
│  • "Severity correlates with efficacy" (PMID:27856432)
└─ Confidence: Verified citations

[💡 AI SYNTHESIS] LLM-generated
Structured data identifies 45 EGFR inhibitors with nanomolar
potency. Clinical evidence shows skin toxicity is the most
common side effect (60-80% incidence), with interesting
correlation between rash severity and treatment efficacy -
suggesting it's an on-target pharmacodynamic effect.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Automatically Determined Blend: 40% Deterministic | 35% Semantic | 25% LLM
Reasoning Engine: Selected Drug Discovery Agent (Hybrid)
Execution time: 4.2s | Cost: $0.05
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### User Constraint Example: Deterministic-Only Mode

**Query**: "What drugs target EGFR" with `mode: "deterministic_only"`

**Reasoning Engine Decision:**
```
User constraint: deterministic_only detected
Skipping semantic search
Selected Agent: Identifier Mapping Agent (Deterministic)
```

**Output:**
```
EGFR-Targeting Compounds (ChEMBL via BioBTree)

🔒 DETERMINISTIC RESULTS (100% Reproducible)
Source: EGFR >> uniprot (P00533) >> chembl_target >> chembl_activity

| Compound  | ChEMBL ID     | IC50   | Phase | Approval |
|-----------|---------------|--------|-------|----------|
| Afatinib  | CHEMBL1173655 | 0.5nM  | 4     | FDA      |
| Erlotinib | CHEMBL941     | 2nM    | 4     | FDA      |
| Gefitinib | CHEMBL6939    | 33nM   | 4     | FDA      |

Total: 45 compounds identified
Blend: 100% Deterministic | 0% Semantic | 0% LLM
Execution time: 0.3s | Cost: $0.001
```

### 2.5 Competitive Advantages

**vs. Traditional Bioinformatics Databases (e.g., UniProt, Ensembl web interfaces):**
- ❌ They have: Structured data only
- ✅ We add: Semantic discovery + literature evidence + AI synthesis

**vs. Pure LLM Solutions (e.g., ChatGPT with web search):**
- ❌ They have: No structured data grounding, hallucination risk
- ✅ We add: Deterministic facts from 40+ databases, citation verification

**vs. Biomedical RAG Systems (e.g., PubMed + LLM):**
- ❌ They have: Literature only, no identifier mapping
- ✅ We add: Full database integration (genes → proteins → compounds → trials)

**vs. Graph Databases (e.g., Neo4j biomedical graphs):**
- ❌ They have: Structured relationships only
- ✅ We add: Semantic discovery, full-text search, AI reasoning

**Our Unique Position:**
```
          Structured Data
                 ▲
                 │
Traditional ────┼──── BioYoda (US!)
Databases       │      │
                │      │
        ────────┼──────┼────────► Semantic Search
                │      │
                │      └─────────► Full-text Literature
                │
Pure LLMs ──────┘
```

### 2.6 Trust & Reproducibility Framework

Critical for scientific research: Users must know which results are reproducible.

**Confidence Labeling System:**

| Data Source | Icon | Label | Reproducibility | When to Use |
|-------------|------|-------|-----------------|-------------|
| BioBTree | 🔒 | DETERMINISTIC | 100% - Exact same results | Identifier lookup, mapping, clinical decisions |
| Qdrant Vectors | 🔍 | SIMILARITY-BASED | 90% - Configurable threshold | Discovery, finding related concepts |
| Qdrant Documents | 📄 | CITATION-BACKED | 95% - Documents don't change | Evidence gathering, literature review |
| LLM Synthesis | 💡 | AI-GENERATED | 60% - Non-deterministic | Explanation, hypothesis generation |

**Output Example with Confidence Labels:**
```json
{
  "results": [
    {
      "data": "BRCA1 maps to UniProt P38398",
      "source": "biobtree",
      "confidence_type": "deterministic",
      "confidence_score": 1.0,
      "reproducible": true,
      "icon": "🔒"
    },
    {
      "data": "Similar to TP53 with functional similarity",
      "source": "qdrant_esm2",
      "confidence_type": "similarity",
      "confidence_score": 0.87,
      "reproducible": "configurable",
      "icon": "🔍"
    },
    {
      "data": "Skin rash occurs in 60-80% of patients",
      "source": "pubmed",
      "pmid": "28374321",
      "confidence_type": "citation",
      "confidence_score": 0.95,
      "reproducible": true,
      "icon": "📄"
    },
    {
      "data": "This suggests on-target pharmacodynamic effect",
      "source": "llm_synthesis",
      "confidence_type": "generated",
      "confidence_score": 0.75,
      "reproducible": false,
      "icon": "💡"
    }
  ]
}
```

---

## 3. System Overview

### 3.1 Current State

#### BioYoda (Semantic Search)
- **Technology**: Qdrant vector database, S-BioBERT/ESM-2 embeddings
- **Data**: 30M PubMed abstracts, 554K clinical trials, 43M patents, 570K proteins
- **Capabilities**: Semantic search, RAG Q&A, protein similarity
- **Limitations**: No identifier resolution, no graph traversal, no multi-hop queries

#### BioBTree (Structured Navigation)
- **Technology**: LMDB/MDBX B+ tree database
- **Data**: 40+ datasets, millions of cross-references
- **Capabilities**: Identifier mapping, chain queries, genomic coordinates, pathway navigation
- **Limitations**: No semantic search, no LLM integration, no full-text search

### 3.2 System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER LAYER                                   │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │  Web UI    │  │  CLI Tool    │  │  External    │                │
│  │            │  │              │  │  Integrations│                │
│  └─────┬──────┘  └──────┬───────┘  └──────┬───────┘                │
└────────┼─────────────────┼──────────────────┼─────────────────────────┘
         │               │               │                │
         └───────────────┴───────────────┴────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                        QUERY GATEWAY                                  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ • Natural Language Processing (entity extraction, intent)      │  │
│  │ • Query Preprocessing (normalization, validation)              │  │
│  │ • Session Management (multi-turn conversations)                │  │
│  │ • Response Aggregation (result merging, formatting)            │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────▼──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                        ORCHESTRATION LAYER                            │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                      PLANNER AGENT                             │  │
│  │  • Query Understanding (decompose complex queries)             │  │
│  │  • Execution Planning (create DAG of steps)                    │  │
│  │  • Agent Selection (route to specialized agents)               │  │
│  │  • Dependency Management (handle data flow between steps)      │  │
│  │  • Error Handling (retry, fallback strategies)                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    AGENT REGISTRY                              │  │
│  │  • Agent Discovery (list available agents)                     │  │
│  │  • Capability Matching (find agents for tasks)                 │  │
│  │  • Load Balancing (distribute requests)                        │  │
│  │  • Health Monitoring (agent availability)                      │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    EXECUTION ENGINE                            │  │
│  │  • Step Execution (run plan steps)                             │  │
│  │  • Parallel Processing (concurrent step execution)             │  │
│  │  • Context Management (share state between steps)              │  │
│  │  • Result Caching (Redis-based caching)                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────▼──────────────────────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
┌────────▼──────────┐  ┌────────▼──────────┐  ┌──────▼──────────────┐
│  DRUG DISCOVERY   │  │  VARIANT ANALYSIS │  │  PROTEIN ANALYSIS   │
│      AGENT        │  │       AGENT       │  │       AGENT         │
│                   │  │                   │  │                     │
│ Tools:            │  │ Tools:            │  │ Tools:              │
│ • TargetFinder    │  │ • SNPLookup       │  │ • SimilaritySearch  │
│ • CompoundSearch  │  │ • GWASAnalysis    │  │ • InteractionNet    │
│ • TrialFinder     │  │ • ClinVarQuery    │  │ • DomainAnalysis    │
│ • PathwayNav      │  │ • PhenotypeMap    │  │ • ExpressionQuery   │
│ • LitSearch       │  │ • PopFrequency    │  │ • GOEnrichment      │
└────────┬──────────┘  └────────┬──────────┘  └──────┬──────────────┘
         │                      │                      │
         └──────────────────────┴──────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
┌────────▼──────────┐  ┌────────▼──────────┐  ┌──────▼──────────────┐
│   TOOL LAYER      │  │   LLM LAYER       │  │   CACHE LAYER       │
│                   │  │                   │  │                     │
│ • BioBTreeClient  │  │ • Anthropic       │  │ • Redis (results)   │
│ • BioYodaClient   │  │ • OpenAI          │  │ • Query cache       │
│ • EntityDetector  │  │ • Gemini          │  │ • Session state     │
│ • ChainBuilder    │  │ • Local LLMs      │  │ • Rate limiting     │
└────────┬──────────┘  └───────────────────┘  └─────────────────────┘
         │
         └──────────────────────┬──────────────────────┐
                                │                      │
┌───────────────────────────────▼──────┐  ┌───────────▼─────────────┐
│         BIOBTREE LAYER                │  │    BIOYODA LAYER        │
│                                       │  │                         │
│  ┌─────────────────────────────────┐ │  │  ┌───────────────────┐  │
│  │ BioBTree gRPC API (Port 7777)   │ │  │  │ Qdrant Collections│  │
│  │ • Search()                      │ │  │  │ • pubmed_abstracts│  │
│  │ • Mapping()                     │ │  │  │ • clinical_trials │  │
│  │ • Entry()                       │ │  │  │ • patents_text    │  │
│  │ • Filter()                      │ │  │  │ • patents_cmpds   │  │
│  │ • Meta()                        │ │  │  │ • esm2_proteins   │  │
│  └─────────────────────────────────┘ │  │  └───────────────────┘  │
│                                       │  │                         │
│  ┌─────────────────────────────────┐ │  │  ┌───────────────────┐  │
│  │ LMDB/MDBX Database              │ │  │  │ BioYoda API       │  │
│  │ • 40+ datasets                  │ │  │  │ • /search         │  │
│  │ • Millions of cross-refs        │ │  │  │ • /ask (RAG)      │  │
│  │ • Genomic coordinates           │ │  │  │ • /collections    │  │
│  │ • Ontology hierarchies          │ │  │  └───────────────────┘  │
│  └─────────────────────────────────┘ │  │                         │
└───────────────────────────────────────┘  └─────────────────────────┘
```

### 2.3 Key Design Principles

1. **Separation of Concerns**: Agents, tools, and data sources are independent modules
2. **Composability**: Tools can be combined to create complex workflows
3. **Extensibility**: New agents and tools can be added without modifying core system
4. **Fault Tolerance**: Failures in one component don't cascade
5. **Observability**: Every step is logged and traceable
6. **Cost Optimization**: Caching, efficient prompt engineering, provider selection

---

## 4. Agent Classification

### 4.1 Three Agent Types

Based on data source utilization, agents are classified into three categories:

#### **Type 1: Deterministic Agents** (BioBTree-only)

**Characteristics:**
- Use only structured data from BioBTree
- Same input → Same output (100% reproducible)
- Minimal or no LLM usage (only for query understanding/parameter extraction)
- Fast (<1 second), cheap (<$0.001 per query)
- **Perfect for**: Clinical decisions, identifier mapping, data export

**Examples:**
```python
# Identifier Mapping Agent
Query: "Convert BRCA1, TP53, EGFR to UniProt IDs"
Process:
  1. Parse gene symbols (minimal LLM or regex)
  2. BioBTree query: genes >> uniprot
  3. Return structured results
Cost: $0.001 | Time: 0.2s | Reproducibility: 100%

# Genomic Coordinate Agent
Query: "Find genes in chr17:41196312-41277500"
Process:
  1. Parse coordinates (regex, no LLM)
  2. BioBTree: >>ensembl[ensembl.overlaps(41196312, 41277500)]
  3. Return gene list
Cost: $0.001 | Time: 0.3s | Reproducibility: 100%

# Cross-Reference Agent
Query: "Get all ChEMBL targets for EGFR"
Process:
  1. Entity detection: EGFR
  2. BioBTree: EGFR >> uniprot >> chembl_target
  3. Return targets
Cost: $0.001 | Time: 0.1s | Reproducibility: 100%

# Pathway Traversal Agent
Query: "List all proteins in Alzheimer pathway"
Process:
  1. Entity detection: Alzheimer
  2. BioBTree: Alzheimer >> reactome >> uniprot
  3. Return proteins
Cost: $0.002 | Time: 0.5s | Reproducibility: 100%
```

**Implementation Strategy:**
- Lightweight wrapper around BioBTree API
- Simple NLP for entity extraction (or even regex patterns)
- LLM only if query is ambiguous
- Can be implemented as REST API endpoints without complex orchestration

#### **Type 2: Semantic Agents** (BioYoda-only)

**Characteristics:**
- Use only Qdrant vector/document search
- Similarity-based, not exact matches
- Heavy LLM usage for reasoning and synthesis
- Slower (2-10 seconds), more expensive ($0.05-0.10 per query)
- **Perfect for**: Discovery, exploration, literature review

**Examples:**
```python
# Literature Discovery Agent
Query: "Find papers about CRISPR off-target effects"
Process:
  1. LLM query understanding
  2. Qdrant search: pubmed_abstracts
  3. LLM synthesis of findings
Cost: $0.06 | Time: 3s | Reproducibility: 85% (tunable)

# Chemical Similarity Agent
Query: "Find compounds chemically similar to Aspirin"
Process:
  1. Resolve Aspirin → SMILES
  2. Compute Morgan fingerprint
  3. Qdrant search: patents_compounds
  4. LLM explain structural similarities
Cost: $0.04 | Time: 2s | Reproducibility: 90%

# Protein Function Agent
Query: "Find functionally similar proteins to TP53"
Process:
  1. Resolve TP53 → UniProt P04637
  2. Get ESM-2 embedding or retrieve from Qdrant
  3. Qdrant search: esm2_proteins
  4. LLM explain functional similarities
Cost: $0.05 | Time: 4s | Reproducibility: 85%
```

**Implementation Strategy:**
- Full agent orchestration with ReAct pattern
- Vector search with configurable thresholds
- LLM-based result ranking and explanation
- Citation verification for literature sources

#### **Type 3: Hybrid Agents** (BioBTree + BioYoda)

**Characteristics:**
- Combine deterministic and semantic paradigms
- **Deterministic steps** for facts, **semantic steps** for context
- Variable cost and speed depending on blend
- **Perfect for**: Complex research questions requiring both exact data and discovery

**Examples:**
```python
# Drug Discovery Agent (Hybrid)
Query: "Find drugs targeting EGFR and clinical trial outcomes"
Process:
  🔒 Step 1 (Deterministic): EGFR >> uniprot >> chembl_target >> compounds
      Cost: $0.002 | Time: 0.5s | Reproducibility: 100%
      Result: 45 compounds

  🔍 Step 2 (Semantic): Search clinical_trials for compound names
      Cost: $0.02 | Time: 2s | Reproducibility: 90%
      Result: 243 trials

  📄 Step 3 (Semantic): Search pubmed for "EGFR inhibitor outcomes"
      Cost: $0.02 | Time: 1.5s | Reproducibility: 90%
      Result: 1,247 papers

  💡 Step 4 (LLM): Synthesize findings
      Cost: $0.01 | Time: 2s

Total: $0.05 | Time: 6s | Reproducibility: Partial (steps 1 is exact)

# Variant Analysis Agent (Hybrid)
Query: "Clinical significance of rs429358 and disease associations"
Process:
  🔒 Step 1 (Deterministic): rs429358 >> dbsnp >> ensembl >> hgnc
      Result: APOE gene

  🔒 Step 2 (Deterministic): rs429358 >> gwas
      Result: Alzheimer's disease (p=1e-150)

  🔒 Step 3 (Deterministic): rs429358 >> clinvar
      Result: Pathogenic

  📄 Step 4 (Semantic): Search pubmed for "rs429358 Alzheimer"
      Result: 1,247 papers

  💡 Step 5 (LLM): Synthesize clinical report

Total: $0.04 | Time: 5s | Reproducibility: High (steps 1-3 exact)

# Protein Analysis Agent (Hybrid)
Query: "Find functionally similar proteins to TP53 that interact with it"
Process:
  🔍 Step 1 (Semantic): ESM-2 similarity search for TP53
      Result: 50 similar proteins (scores 0.75-0.95)

  🔒 Step 2 (Deterministic): TP53 >> intact >> confidence_filter
      Result: 127 interaction partners

  🔧 Step 3 (Compute): Intersect similar & interactors
      Result: 8 proteins

  🔒 Step 4 (Deterministic): Get GO terms for 8 proteins
      Result: GO annotations

  💡 Step 5 (LLM): Explain functional relationships

Total: $0.06 | Time: 7s | Reproducibility: Moderate
```

### 4.2 Agent Classification Matrix

| Agent Type | BioBTree | BioYoda | LLM | Cost | Speed | Reproducibility | Use Case |
|------------|----------|---------|-----|------|-------|-----------------|----------|
| **Deterministic** | ✅✅✅ | ❌ | Minimal | $0.001 | <1s | 100% | Lookups, mapping, clinical |
| **Semantic** | ❌ | ✅✅✅ | Heavy | $0.05 | 2-10s | 60-90% | Discovery, exploration |
| **Hybrid** | ✅✅ | ✅✅ | Moderate | $0.03-0.10 | 3-15s | Partial | Research questions |

### 4.3 Automatic Agent Selection

The Planner Agent automatically selects agent type based on query intent:

```python
class AgentSelector:
    """Select appropriate agent type based on query."""

    INTENT_TO_AGENT_TYPE = {
        # Deterministic intents
        "identifier_lookup": "deterministic",
        "coordinate_query": "deterministic",
        "cross_reference": "deterministic",
        "pathway_members": "deterministic",

        # Semantic intents
        "literature_discovery": "semantic",
        "similarity_search": "semantic",
        "concept_exploration": "semantic",

        # Hybrid intents
        "drug_discovery": "hybrid",
        "variant_analysis": "hybrid",
        "protein_analysis": "hybrid",
        "evidence_synthesis": "hybrid",
    }

    async def select_agent(self, query: str, entities: List[Entity]) -> str:
        """Select agent type based on query analysis."""

        intent = await self.classify_intent(query)

        # Default mapping
        agent_type = self.INTENT_TO_AGENT_TYPE.get(
            intent,
            "hybrid"  # Default to hybrid if unsure
        )

        # Override based on user preferences
        if "only facts" in query.lower() or "deterministic" in query.lower():
            agent_type = "deterministic"
        elif "explore" in query.lower() or "discover" in query.lower():
            agent_type = "semantic"

        return agent_type
```

### 4.4 Cost-Benefit Analysis

**When to Use Each Agent Type:**

**Use Deterministic Agents when:**
- ✅ You need exact, reproducible results
- ✅ Query involves identifier mapping or database lookup
- ✅ Speed and cost are priorities
- ✅ Results will be used for clinical decisions or publications
- ✅ You're doing batch processing (thousands of queries)

**Use Semantic Agents when:**
- ✅ You're exploring new research areas
- ✅ You want to find conceptually related entities
- ✅ Exact matches aren't available/sufficient
- ✅ You're doing literature review
- ✅ You want AI-powered insights

**Use Hybrid Agents when:**
- ✅ You need both facts and context
- ✅ Query requires multi-step reasoning
- ✅ You want grounded AI responses
- ✅ You're answering complex research questions
- ✅ You need explainable, citation-backed answers

### 4.5 Multi-Step Query Execution: Who Builds BioBTree Queries?

**Critical Design Question**: BioBTree has a specific query language (`EGFR >> uniprot >> chembl_target`). For complex questions requiring multiple queries, who should be responsible for building and executing these queries?

#### The Tool-Agent Division of Responsibility

```
┌─────────────────────────────────────────────────────────────────┐
│  AGENT LAYER (High-Level Reasoning - LLM Powered)               │
│                                                                  │
│  Responsibilities:                                              │
│  • Understand user's ultimate goal                              │
│  • Decide what information is needed                            │
│  • Plan multi-step query strategy                               │
│  • Decide when to stop (sufficient answer)                      │
│  • Synthesize results into coherent answer                      │
│  • Coordinate multiple tools (BioBTree + BioYoda)               │
│                                                                  │
│  Pattern: ReAct (Reasoning + Acting)                            │
│    Thought → Action → Observation → Thought → ...              │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├──────────────────┬───────────────────┐
             │                  │                   │
┌────────────▼──────────┐  ┌───▼──────────────┐  ┌▼──────────────┐
│  BIOBTREE TOOL        │  │  BIOYODA TOOL    │  │  OTHER TOOLS  │
│  (Executor)           │  │  (Executor)      │  │               │
│                       │  │                  │  │               │
│  Responsibilities:    │  │  Responsibilities│  │               │
│  • Know BioBTree      │  │  • Know Qdrant   │  │               │
│    syntax & datasets  │  │    collections   │  │               │
│  • Execute queries    │  │  • Execute search│  │               │
│  • Parse results      │  │  • Parse results │  │               │
│  • Provide capability │  │  • Provide caps  │  │               │
│    description to LLM │  │    to LLM        │  │               │
│                       │  │                  │  │               │
│  Does NOT:            │  │  Does NOT:       │  │               │
│  ✗ Decide strategy    │  │  ✗ Decide what   │  │               │
│  ✗ Know user goal     │  │    to search     │  │               │
└───────────────────────┘  └──────────────────┘  └───────────────┘
```

#### Example: Complex Multi-Step Query

**User Query**: "What pathways contain EGFR and what other proteins are in those pathways?"

**Agent Execution (ReAct Pattern):**

```python
# Agent's internal reasoning loop

Iteration 1:
  Thought: "I need to find EGFR-related pathways. EGFR is a gene,
            so I need: gene → protein → pathways"

  Action: biobtree_tool.query("EGFR >> uniprot >> reactome")

  Observation: {
    "results": [
      {"pathway_id": "R-HSA-177929", "name": "Signaling by EGFR"},
      {"pathway_id": "R-HSA-1643685", "name": "Disease"},
      ...  # 15 pathways total
    ]
  }

Iteration 2:
  Thought: "Good! Found 15 pathways. Now I need proteins in these
            pathways. I'll query the main pathway."

  Action: biobtree_tool.query("R-HSA-177929 >> reactome >> uniprot")

  Observation: {
    "results": [
      {"uniprot_id": "P00533", "gene": "EGFR"},
      {"uniprot_id": "P04626", "gene": "SHC1"},
      {"uniprot_id": "P62993", "gene": "GRB2"},
      ...  # 47 proteins total
    ]
  }

Iteration 3:
  Thought: "I have sufficient data now. User wanted pathways and
            their proteins - I have both."

  Answer: "EGFR is involved in 15 Reactome pathways. The primary
          pathway is 'Signaling by EGFR' (R-HSA-177929), which
          contains 47 proteins including EGFR itself (P00533),
          SHC1 (P04626), GRB2 (P62993), and others involved in
          signal transduction..."
```

#### Tool Implementation

**File**: `modules/agent_system/tools/biobtree/biobtree_tool.py`

```python
from typing import Dict, List, Optional
from modules.agent_system.tools.base import Tool, ToolMetadata, ToolParameter

class BioBTreeQueryTool(Tool):
    """
    Executes BioBTree chain queries.
    Agent decides WHAT to query, tool executes HOW.
    """

    def __init__(self, biobtree_client: BioBTreeClient):
        self.client = biobtree_client

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="biobtree_query",
            description="""
            Execute BioBTree chain queries for deterministic biological data lookup.

            BioBTree Query Language:
            - Chain syntax: entity >> dataset >> dataset
            - Filters: dataset[field==value]
            - Bidirectional: works both ways

            Common patterns:
            • Gene to protein: BRCA1 >> uniprot
            • Protein to pathways: P00533 >> reactome
            • Protein to compounds: P00533 >> chembl_target >> chembl_molecule
            • SNP to gene: rs429358 >> dbsnp >> ensembl >> hgnc
            • Pathway to proteins: R-HSA-177929 >> reactome >> uniprot

            Available datasets (40+):
            - Proteins: uniprot, uniparc, uniref
            - Genes: ensembl, hgnc
            - Compounds: chembl_molecule, chembl_target, chembl_activity
            - Variants: dbsnp, clinvar, gwas
            - Pathways: reactome
            - Interactions: intact
            - Expression: bgee
            - And 30+ more...
            """,
            parameters=[
                ToolParameter(
                    name="chain_query",
                    type="string",
                    description="BioBTree chain query (e.g., 'EGFR >> uniprot >> reactome')",
                    required=True
                ),
                ToolParameter(
                    name="detail",
                    type="boolean",
                    description="Return full details (d=1 parameter)",
                    required=False,
                    default=False
                )
            ],
            returns="Dictionary with query results",
            examples=[
                {
                    "input": {
                        "chain_query": "BRCA1 >> uniprot",
                        "detail": False
                    },
                    "output": {
                        "results": [{"uniprot_id": "P38398", "gene": "BRCA1"}]
                    }
                },
                {
                    "input": {
                        "chain_query": "P00533 >> chembl_target >> chembl_molecule",
                        "detail": False
                    },
                    "output": {
                        "results": [
                            {"chembl_id": "CHEMBL6939", "name": "Gefitinib"},
                            {"chembl_id": "CHEMBL941", "name": "Erlotinib"}
                        ]
                    }
                }
            ]
        )

    async def execute(
        self,
        chain_query: str,
        detail: bool = False
    ) -> Dict:
        """
        Execute BioBTree chain query.

        Agent provides the query, tool executes it.
        """

        try:
            # Parse the chain to extract components
            parts = chain_query.split(">>")
            input_term = parts[0].strip()
            mapfilter = " >> ".join(p.strip() for p in parts[1:]) if len(parts) > 1 else ""

            if mapfilter:
                # Mapping query
                result = await self.client.map_query(
                    terms=input_term,
                    mapfilter=mapfilter,
                    detail=detail
                )
            else:
                # Simple lookup
                result = await self.client.query(
                    terms=input_term,
                    detail=detail
                )

            return {
                "success": True,
                "query": chain_query,
                "results": result,
                "result_count": len(result.get("entries", [])),
                "source": "biobtree",
                "confidence_type": "deterministic",
                "reproducible": True
            }

        except Exception as e:
            return {
                "success": False,
                "query": chain_query,
                "error": str(e)
            }


class BioBTreeHelperTool(Tool):
    """
    Common BioBTree query patterns as helper functions.
    Reduces agent's need to know exact syntax.
    """

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="biobtree_helpers",
            description="Common BioBTree query patterns",
            parameters=[
                ToolParameter(
                    name="helper_name",
                    type="string",
                    description="Helper function name",
                    required=True
                ),
                ToolParameter(
                    name="entity",
                    type="string",
                    description="Input entity",
                    required=True
                )
            ],
            returns="Query results"
        )

    async def get_protein(self, gene: str) -> Dict:
        """Gene → UniProt protein"""
        return await self.client.map_query(gene, "uniprot")

    async def get_pathways(self, protein: str) -> Dict:
        """Protein → Reactome pathways"""
        return await self.client.map_query(protein, "reactome")

    async def get_compounds(self, target: str) -> Dict:
        """Target → ChEMBL compounds"""
        return await self.client.map_query(
            target,
            "chembl_target >> chembl_activity >> chembl_molecule"
        )

    async def get_gene_from_snp(self, snp: str) -> Dict:
        """SNP → Gene"""
        return await self.client.map_query(snp, "dbsnp >> ensembl >> hgnc")
```

#### Agent Using Tools (ReAct Pattern)

**File**: `modules/agent_system/agents/drug_discovery/agent.py`

```python
class DrugDiscoveryAgent:
    """
    Uses tools to answer drug discovery questions.
    LLM decides strategy, tools execute.
    """

    def __init__(
        self,
        biobtree_tool: BioBTreeQueryTool,
        bioyoda_tool: BioYodaSearchTool,
        llm: LLMProvider
    ):
        self.biobtree = biobtree_tool
        self.bioyoda = bioyoda_tool
        self.llm = llm

    async def execute(self, user_query: str) -> AgentResult:
        """
        Execute query using ReAct pattern.
        Agent reasons, tools act.
        """

        system_prompt = f"""You are a Drug Discovery Agent. Answer questions about
drugs, targets, compounds, and clinical trials.

Available tools:
1. biobtree_query: {self.biobtree.metadata.description}
2. bioyoda_search: {self.bioyoda.metadata.description}

Use ReAct pattern:
Thought: Analyze what information you need
Action: Call a tool with appropriate parameters
Observation: Review tool results
Thought: Decide if you need more information or can answer
... repeat until you have sufficient data
Answer: Provide final answer to user

Important:
- BioBTree queries are DETERMINISTIC (exact, reproducible)
- BioYoda searches are SEMANTIC (similarity-based)
- Use BioBTree for identifier mapping, relationships
- Use BioYoda for literature, side effects, contextual info
- You can call tools multiple times
- Stop when you have sufficient information
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]

        # Tool definitions for function calling
        tools = [
            self.biobtree.as_function_spec(),
            self.bioyoda.as_function_spec()
        ]

        max_iterations = 10
        tool_calls = []

        for i in range(max_iterations):
            # LLM decides next action
            response = await self.llm.function_call(
                messages=messages,
                functions=tools,
                temperature=0.3  # Lower temp for more deterministic reasoning
            )

            if response.function_call:
                # LLM wants to use a tool
                tool_name = response.function_call.name
                tool_args = response.function_call.arguments

                # Execute tool
                if tool_name == "biobtree_query":
                    result = await self.biobtree.execute(**tool_args)
                elif tool_name == "bioyoda_search":
                    result = await self.bioyoda.execute(**tool_args)
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}

                tool_calls.append({
                    "tool": tool_name,
                    "input": tool_args,
                    "output": result
                })

                # Add observation to conversation
                messages.append({
                    "role": "assistant",
                    "content": f"Thought: {response.content}\nAction: {tool_name}\nObservation: {result}"
                })

            else:
                # LLM has final answer
                return AgentResult(
                    success=True,
                    answer=response.content,
                    tool_calls=tool_calls,
                    reasoning_steps=len(tool_calls)
                )

        # Max iterations reached
        return AgentResult(
            success=False,
            error="Max iterations reached without conclusive answer",
            tool_calls=tool_calls
        )
```

#### Why This Design Works

**1. Separation of Concerns:**
- **Tool**: Knows HOW to query BioBTree (syntax, API)
- **Agent**: Knows WHAT to query (user intent, strategy)

**2. Flexibility:**
- Agent adapts to new questions without changing tool
- Tool can be used by multiple agents
- Easy to add new BioBTree datasets - just update tool description

**3. LLM-Powered Intelligence:**
- Agent uses natural language reasoning
- No hard-coded query patterns
- Adapts to complex multi-step scenarios

**4. Transparency:**
- Tool calls are logged
- User can see reasoning steps
- Reproducible (BioBTree queries are deterministic)

**5. Scalability:**
- Same pattern for all tools (BioYoda, external APIs)
- New agents can reuse existing tools
- Tools compose naturally

---

## 5. Architecture Design

### 5.1 Layered Architecture

#### Layer 1: User Interface Layer
- **Responsibility**: User interaction, input validation, result presentation
- **Components**: Web UI, CLI Tool, External integrations (all via REST API)
- **Technology**: FastAPI (backend), React/Vue (web UI), Click/Typer (CLI)

#### Layer 2: Gateway Layer
- **Responsibility**: Request routing, session management, response aggregation
- **Components**: Query Gateway, Session Manager, Response Formatter
- **Technology**: FastAPI, Redis (sessions)

#### Layer 3: Orchestration Layer
- **Responsibility**: Query planning, agent coordination, execution management
- **Components**: Planner Agent, Agent Registry, Execution Engine
- **Technology**: LangGraph, custom orchestrator

#### Layer 4: Agent Layer
- **Responsibility**: Domain-specific reasoning, tool invocation, result synthesis
- **Components**: Drug Discovery Agent, Variant Analysis Agent, Protein Analysis Agent
- **Technology**: LangChain, custom agent framework

#### Layer 5: Tool Layer
- **Responsibility**: Data access, computation, external service integration
- **Components**: BioBTree Client, BioYoda Client, Entity Detector
- **Technology**: httpx, qdrant-client, custom tools

#### Layer 6: Data Layer
- **Responsibility**: Data storage and retrieval
- **Components**: BioBTree DB, Qdrant Vector DB, Redis Cache
- **Technology**: LMDB/MDBX, Qdrant, Redis

### 3.2 Agent Architecture Pattern

Each specialized agent follows a consistent pattern:

```
┌─────────────────────────────────────────────────────────┐
│                    AGENT INTERFACE                       │
│  • query(user_input: str, context: Dict) -> AgentResult │
│  • get_capabilities() -> List[Capability]                │
│  • validate_input(user_input: str) -> bool               │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  AGENT CORE                              │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ REASONING ENGINE (LLM-powered)                     │ │
│  │ • Understand user intent                           │ │
│  │ • Plan steps to answer query                       │ │
│  │ • Select appropriate tools                         │ │
│  │ • Generate final response                          │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ STATE MANAGER                                      │ │
│  │ • Track conversation history                       │ │
│  │ • Maintain intermediate results                    │ │
│  │ • Store tool outputs                               │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ TOOL EXECUTOR                                      │ │
│  │ • Validate tool inputs                             │ │
│  │ • Execute tool calls                               │ │
│  │ • Handle errors and retries                        │ │
│  └────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┬───────────────┐
         │                       │               │
┌────────▼────────┐  ┌───────────▼──────┐  ┌────▼────────┐
│   TOOL SET      │  │  PROMPT LIBRARY  │  │  VALIDATORS │
│                 │  │                  │  │             │
│ • Tool 1        │  │ • System prompt  │  │ • Input val │
│ • Tool 2        │  │ • Few-shot exs   │  │ • Output val│
│ • Tool 3        │  │ • Task templates │  │ • Schema val│
└─────────────────┘  └──────────────────┘  └─────────────┘
```

### 3.3 Communication Patterns

#### Synchronous Pattern (Simple Queries)
```
User Request
    ↓
Query Gateway (validate, route)
    ↓
Agent (process, respond)
    ↓
Format & Return Response
```

#### Asynchronous Pattern (Complex Queries)
```
User Request
    ↓
Query Gateway (validate, create job)
    ↓
Return job_id to user
    ↓
Background: Planner → Agent(s) → Results
    ↓
User polls /jobs/{job_id} or WebSocket notification
```

#### Multi-Agent Collaboration
```
Planner Agent
    ↓
Creates execution plan:
    Step 1: Variant Agent (get SNP→gene mapping)
    Step 2: Drug Agent (get gene→compounds)
    Step 3: Literature Agent (get compound papers)
    ↓
Execute steps (sequential or parallel)
    ↓
Aggregate results
    ↓
Planner generates final answer
```

---

## 4. Core Components

### 4.1 Query Gateway

#### Responsibilities
1. Accept queries from all interfaces (API, Web UI, SDK, CLI)
2. Validate and normalize input
3. Detect entities (genes, proteins, compounds, diseases, SNPs)
4. Classify query intent
5. Route to appropriate agent(s)
6. Manage sessions for multi-turn conversations
7. Aggregate and format responses

#### Implementation

**File**: `modules/agent_system/gateway/query_gateway.py`

```python
class QueryGateway:
    """Main entry point for all user queries."""

    def __init__(
        self,
        entity_detector: EntityDetector,
        intent_classifier: IntentClassifier,
        agent_registry: AgentRegistry,
        session_manager: SessionManager
    ):
        self.entity_detector = entity_detector
        self.intent_classifier = intent_classifier
        self.agent_registry = agent_registry
        self.session_manager = session_manager

    async def process_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> QueryResponse:
        """Process a user query and return results."""

        # 1. Validate input
        if not self._validate_query(query):
            raise ValueError("Invalid query")

        # 2. Get or create session
        session = self.session_manager.get_or_create(session_id, user_id)

        # 3. Detect entities
        entities = await self.entity_detector.detect(query)

        # 4. Classify intent
        intent = await self.intent_classifier.classify(query, entities)

        # 5. Route to agent
        agent = self.agent_registry.get_agent_for_intent(intent)

        # 6. Execute query
        result = await agent.query(
            user_input=query,
            context={
                "entities": entities,
                "intent": intent,
                "session": session,
            }
        )

        # 7. Update session
        session.add_interaction(query, result)

        # 8. Format response
        return self._format_response(result)
```

#### Entity Detection

**File**: `modules/agent_system/gateway/entity_detector.py`

```python
class EntityDetector:
    """Detect biological entities in user queries."""

    PATTERNS = {
        "gene": r"\b[A-Z][A-Z0-9]+\b",  # BRCA1, TP53
        "uniprot": r"\b[OPQ][0-9][A-Z0-9]{3}[0-9]\b",  # P53_HUMAN
        "snp": r"\brs\d+\b",  # rs429358
        "chembl": r"\bCHEMBL\d+\b",  # CHEMBL6939
        "disease": r"\b(?:cancer|diabetes|alzheimer|parkinson)\b",
        "pathway": r"\bR-HSA-\d+\b",  # Reactome IDs
    }

    def __init__(self, biobtree_client: BioBTreeClient):
        self.biobtree_client = biobtree_client

    async def detect(self, query: str) -> List[Entity]:
        """Detect entities using regex + BioBTree validation."""

        entities = []

        # Regex-based detection
        for entity_type, pattern in self.PATTERNS.items():
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                entities.append(Entity(
                    text=match,
                    type=entity_type,
                    confidence=0.8
                ))

        # Validate with BioBTree
        validated_entities = await self._validate_entities(entities)

        return validated_entities
```

#### Intent Classification

**File**: `modules/agent_system/gateway/intent_classifier.py`

```python
class IntentClassifier:
    """Classify user query intent."""

    INTENTS = {
        "drug_discovery": [
            "find drugs", "compounds targeting", "inhibitors of",
            "clinical trials for", "targets of"
        ],
        "variant_analysis": [
            "SNP", "rs number", "variant", "mutation", "GWAS",
            "genotype", "allele"
        ],
        "protein_analysis": [
            "similar proteins", "protein interactions", "domains",
            "expression", "homologs"
        ],
        "literature_search": [
            "papers about", "research on", "studies of",
            "publications", "reviews"
        ],
    }

    async def classify(
        self,
        query: str,
        entities: List[Entity]
    ) -> Intent:
        """Classify intent using keyword matching + LLM."""

        # Keyword-based classification (fast)
        for intent, keywords in self.INTENTS.items():
            if any(kw in query.lower() for kw in keywords):
                return Intent(name=intent, confidence=0.9)

        # LLM-based classification (fallback)
        return await self._llm_classify(query, entities)
```

### 4.2 Planner Agent

#### Responsibilities
1. Decompose complex queries into steps
2. Create execution plan (DAG)
3. Select appropriate agents for each step
4. Manage dependencies between steps
5. Handle errors and retries
6. Generate final response from step results

#### Implementation

**File**: `modules/agent_system/agents/planner/planner_agent.py`

```python
class PlannerAgent:
    """Orchestrates multi-step query execution."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        agent_registry: AgentRegistry,
        execution_engine: ExecutionEngine
    ):
        self.llm = llm_provider
        self.agent_registry = agent_registry
        self.execution_engine = execution_engine

    async def query(
        self,
        user_input: str,
        context: Dict
    ) -> AgentResult:
        """Plan and execute multi-step query."""

        # 1. Decompose query into steps
        plan = await self._create_plan(user_input, context)

        # 2. Validate plan
        if not self._validate_plan(plan):
            return AgentResult(
                success=False,
                error="Unable to create valid execution plan"
            )

        # 3. Execute plan
        results = await self.execution_engine.execute(plan)

        # 4. Synthesize final answer
        final_answer = await self._synthesize_answer(
            user_input, plan, results
        )

        return AgentResult(
            success=True,
            answer=final_answer,
            sources=self._collect_sources(results),
            metadata={
                "plan": plan.to_dict(),
                "step_results": results
            }
        )

    async def _create_plan(
        self,
        user_input: str,
        context: Dict
    ) -> ExecutionPlan:
        """Use LLM to create step-by-step plan."""

        prompt = f"""You are a biomedical query planner. Break down this query into steps:

Query: {user_input}

Detected entities: {context.get('entities', [])}
Intent: {context.get('intent', 'unknown')}

Available agents:
{self._format_agent_capabilities()}

Create a step-by-step plan. For each step, specify:
1. Agent to use
2. Action to perform
3. Input (from user or previous step)
4. Expected output

Output as JSON:
{{
    "steps": [
        {{
            "step_id": 1,
            "agent": "drug_discovery",
            "action": "find_targets",
            "input": "EGFR",
            "depends_on": []
        }},
        ...
    ]
}}
"""

        response = await self.llm.generate(prompt)
        plan = ExecutionPlan.from_json(response)
        return plan
```

### 4.3 Tool Abstraction Layer

#### Tool Interface

**File**: `modules/agent_system/tools/base.py`

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from pydantic import BaseModel, Field

class ToolParameter(BaseModel):
    """Tool parameter specification."""
    name: str
    type: str  # "string", "integer", "array", etc.
    description: str
    required: bool = True
    default: Any = None

class ToolMetadata(BaseModel):
    """Tool metadata for discovery and documentation."""
    name: str
    description: str
    parameters: List[ToolParameter]
    returns: str
    examples: List[Dict[str, Any]] = []

class Tool(ABC):
    """Base class for all tools."""

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Tool metadata."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool."""
        pass

    def validate_input(self, **kwargs) -> bool:
        """Validate input parameters."""
        required_params = [
            p.name for p in self.metadata.parameters if p.required
        ]
        return all(param in kwargs for param in required_params)
```

#### Example Tools

**File**: `modules/agent_system/tools/biobtree/gene_to_protein.py`

```python
class GeneToProteinTool(Tool):
    """Map gene symbols to UniProt protein IDs."""

    def __init__(self, biobtree_client: BioBTreeClient):
        self.client = biobtree_client

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="gene_to_protein",
            description="Map gene symbol(s) to UniProt protein IDs",
            parameters=[
                ToolParameter(
                    name="genes",
                    type="array",
                    description="Gene symbols (e.g., ['BRCA1', 'TP53'])",
                    required=True
                ),
                ToolParameter(
                    name="reviewed_only",
                    type="boolean",
                    description="Return only reviewed (SwissProt) entries",
                    required=False,
                    default=True
                )
            ],
            returns="List of UniProt IDs with metadata",
            examples=[
                {
                    "input": {"genes": ["BRCA1"], "reviewed_only": True},
                    "output": [{"uniprot_id": "P38398", "gene": "BRCA1", ...}]
                }
            ]
        )

    async def execute(
        self,
        genes: List[str],
        reviewed_only: bool = True
    ) -> List[Dict]:
        """Execute gene to protein mapping."""

        results = []

        for gene in genes:
            # BioBTree chain query: GENE >> uniprot
            filter_expr = ""
            if reviewed_only:
                filter_expr = "[uniprot.reviewed==true]"

            query = f"{gene} >> uniprot{filter_expr}"
            response = await self.client.query(query)

            results.extend(response.get("entries", []))

        return results
```

### 4.4 BioBTree gRPC Client

**File**: `modules/agent_system/integrations/biobtree_client.py`

**Protocol**: gRPC (primary) with optional REST fallback

**Why gRPC**:
- **Performance**: 30-50% faster than REST (binary protocol, HTTP/2)
- **Lower latency**: Critical for high-frequency agent queries
- **Connection efficiency**: Single persistent connection for all requests
- **Strongly typed**: Protocol Buffer definitions prevent runtime errors
- **Native async**: Built for concurrent/streaming operations
- **Production-ready**: BioBTree gRPC service (`port 7777`) fully tested

**Key Operations**:
- `Search()`: Lookup identifiers across datasets
- `Mapping()`: Execute chain queries (e.g., `EGFR >> uniprot >> chembl_target`)
- `Entry()`: Retrieve specific dataset entry
- `Filter()`: Apply CEL filter expressions
- `Meta()`: Get dataset metadata

**Protocol Buffer Definitions**: BioBTree provides `.proto` files in `biobtreev2/src/pbuf/`:
- `app.proto`: Service definitions (Search, Mapping, Entry, Filter, Page, Meta)
- `attr.proto`: Dataset attribute structures

**Python Implementation**: Uses `grpcio` library with auto-generated stubs from `.proto` files. Client handles connection pooling, retry logic, and optional REST fallback for debugging.

**Data Flow for LLM Consumption**: gRPC responses (Protocol Buffers) are automatically converted to Python dictionaries using built-in protobuf methods (`MessageToDict`). This conversion is fast (microseconds) and allows seamless integration with LLM APIs that expect JSON. The agent system benefits from gRPC's binary protocol for network transfer (30-50% faster) while maintaining standard dict/JSON interfaces for LLM function calling.

**Tool Exposure via Function Calling**: BioBTree operations are exposed to LLMs as function calling tools (structured JSON schemas). The function definitions specify tool signatures (parameters, types), while system prompts provide domain knowledge (BioBTree query language, datasets, syntax). See Section 6.1 for details on the Function Calling + Prompts architecture.

**Configuration** (`config/agent_system.yaml`):
```yaml
biobtree:
  protocol: grpc          # Primary: "grpc", Fallback: "rest"
  grpc:
    host: localhost
    port: 7777
    max_connections: 50
    keepalive_time: 30    # seconds
  rest:                   # Optional fallback for debugging
    host: localhost
    port: 9292
```

### 4.5 Multi-Provider LLM Framework

**File**: `modules/agent_system/llm/base.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, AsyncIterator
from pydantic import BaseModel

class Message(BaseModel):
    """Chat message."""
    role: str  # "user", "assistant", "system"
    content: str

class FunctionCall(BaseModel):
    """Function call from LLM."""
    name: str
    arguments: Dict

class LLMResponse(BaseModel):
    """LLM response."""
    content: str
    function_call: Optional[FunctionCall] = None
    usage: Dict = {}
    model: str = ""

class LLMProvider(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> str:
        """Generate text completion."""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> LLMResponse:
        """Chat completion."""
        pass

    @abstractmethod
    async def function_call(
        self,
        messages: List[Message],
        functions: List[Dict],
        temperature: float = 0.7
    ) -> LLMResponse:
        """Chat with function calling."""
        pass

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream text completion."""
        pass
```

**File**: `modules/agent_system/llm/anthropic_provider.py`

```python
import anthropic
from typing import List, Dict, Optional, AsyncIterator

class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> str:
        """Generate text completion."""

        messages = [Message(role="user", content=prompt)]
        response = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.content

    async def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Chat completion."""

        anthropic_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        kwargs = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self.client.messages.create(**kwargs)

        return LLMResponse(
            content=response.content[0].text,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            },
            model=response.model
        )

    async def function_call(
        self,
        messages: List[Message],
        functions: List[Dict],
        temperature: float = 0.7
    ) -> LLMResponse:
        """Chat with function calling (tool use)."""

        anthropic_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        # Convert functions to Anthropic tool format
        tools = [
            {
                "name": func["name"],
                "description": func["description"],
                "input_schema": func["parameters"]
            }
            for func in functions
        ]

        response = await self.client.messages.create(
            model=self.model,
            messages=anthropic_messages,
            tools=tools,
            temperature=temperature,
            max_tokens=4000
        )

        # Check if tool use
        function_call = None
        content = ""

        for block in response.content:
            if block.type == "tool_use":
                function_call = FunctionCall(
                    name=block.name,
                    arguments=block.input
                )
            elif block.type == "text":
                content = block.text

        return LLMResponse(
            content=content,
            function_call=function_call,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            },
            model=response.model
        )

    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream text completion."""

        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4000,
            "stream": True
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
```

---

## 5. Specialized Agents

### 5.1 Drug Discovery Agent

**File**: `modules/agent_system/agents/drug_discovery/drug_discovery_agent.py`

#### Capabilities
1. Target identification (gene/protein → drug targets)
2. Compound search (target → active compounds)
3. Chemical similarity search
4. Clinical trial lookup
5. Pathway analysis
6. Safety profile analysis
7. Literature context retrieval

#### Tools
```python
DRUG_DISCOVERY_TOOLS = [
    # BioBTree-based tools
    "gene_to_protein",          # GENE >> uniprot
    "protein_to_target",        # uniprot >> chembl_target_component >> chembl_target
    "target_to_compounds",      # chembl_target >> chembl_activity >> chembl_molecule
    "compound_to_properties",   # chembl_molecule details (MW, logP, etc.)
    "compound_to_trials",       # chembl_molecule >> clinical_trials
    "protein_to_pathways",      # uniprot >> reactome
    "pathway_to_proteins",      # reactome >> uniprot

    # BioYoda-based tools
    "chemical_similarity",      # Patents compound fingerprint search
    "pubmed_search",            # Semantic search PubMed
    "patent_search",            # Semantic search patents
    "trial_search",             # Semantic search clinical trials
]
```

#### Example Query Flows

**Query 1**: "Find drugs targeting EGFR"
```
Step 1: gene_to_protein("EGFR") → P00533
Step 2: protein_to_target(P00533) → CHEMBL203
Step 3: target_to_compounds(CHEMBL203) → [CHEMBL6939, CHEMBL941, ...]
Step 4: compound_to_properties([CHEMBL6939, ...]) → Drug details
Step 5: pubmed_search("EGFR inhibitors") → Literature context
Response: "Found 45 compounds targeting EGFR (UniProt: P00533). Top compounds include Gefitinib (CHEMBL6939), Erlotinib (CHEMBL941)..."
```

**Query 2**: "Find clinical trials for compounds similar to Ibuprofen for inflammation"
```
Step 1: chemical_similarity("Ibuprofen") → Similar compounds
Step 2: compound_to_trials(similar_compounds) → Trials
Step 3: trial_search("inflammation") → Filter by semantic relevance
Response: "Found 23 trials testing NSAIDs similar to Ibuprofen for inflammatory conditions..."
```

### 5.2 Variant Analysis Agent

**File**: `modules/agent_system/agents/variant_analysis/variant_analysis_agent.py`

#### Capabilities
1. SNP lookup and annotation
2. GWAS association analysis
3. ClinVar pathogenicity assessment
4. Phenotype mapping (HPO, MONDO)
5. Population frequency analysis
6. Gene context retrieval
7. Literature evidence gathering

#### Tools
```python
VARIANT_ANALYSIS_TOOLS = [
    # BioBTree-based tools
    "snp_to_gene",              # rs123 >> dbsnp >> ensembl >> hgnc
    "snp_to_gwas",              # rs123 >> gwas
    "snp_to_clinvar",           # rs123 >> clinvar
    "clinvar_to_phenotype",     # clinvar >> hpo >> mondo
    "gene_to_variants",         # hgnc >> ensembl >> dbsnp
    "variant_to_protein",       # dbsnp >> ensembl >> uniprot

    # BioYoda-based tools
    "pubmed_variant_search",    # Search papers mentioning variant
    "trial_variant_search",     # Trials studying variant
]
```

#### Example Query Flows

**Query**: "What diseases are associated with rs429358?"
```
Step 1: snp_to_gene(rs429358) → APOE gene
Step 2: snp_to_gwas(rs429358) → [Alzheimer's disease (p=1e-150), ...]
Step 3: snp_to_clinvar(rs429358) → Pathogenic for AD
Step 4: clinvar_to_phenotype(rs429358) → [HP:0002511, MONDO:0004975]
Step 5: pubmed_variant_search("rs429358") → Recent papers
Response: "rs429358 (APOE gene) is strongly associated with Alzheimer's disease (p<1e-150). ClinVar classifies it as pathogenic. Found 1,247 papers discussing this variant..."
```

### 5.3 Protein Analysis Agent

**File**: `modules/agent_system/agents/protein_analysis/protein_analysis_agent.py`

#### Capabilities
1. Functional similarity search (ESM-2)
2. Sequence similarity search (DIAMOND)
3. Protein interaction networks
4. Domain and feature analysis
5. Tissue expression patterns
6. GO term enrichment
7. Structural information

#### Tools
```python
PROTEIN_ANALYSIS_TOOLS = [
    # BioYoda-based tools
    "esm2_similarity",          # ESM-2 functional similarity
    "diamond_similarity",       # DIAMOND sequence similarity

    # BioBTree-based tools
    "protein_interactions",     # uniprot >> intact
    "protein_domains",          # uniprot features (InterPro via xrefs)
    "protein_expression",       # uniprot >> bgee
    "protein_to_go",            # uniprot >> go
    "go_enrichment",            # Multiple proteins → GO enrichment
    "protein_structure",        # uniprot >> alphafold (via xrefs)

    # Hybrid tools
    "pubmed_protein_search",    # Papers mentioning protein
]
```

#### Example Query Flows

**Query**: "Find functionally similar proteins to TP53 that interact with it"
```
Step 1: esm2_similarity("P04637") → [Q16637, Q00987, ...] (similar proteins)
Step 2: protein_interactions("P04637") → [Q16637, P67775, ...] (interactors)
Step 3: Intersect similar & interactors → [Q16637, ...]
Step 4: protein_to_go([Q16637, ...]) → GO terms
Step 5: pubmed_protein_search("TP53 interactions") → Literature
Response: "Found 15 proteins functionally similar to TP53 (UniProt: P04637) that also interact with it, including TP63 (Q16637)..."
```

---

## 6. Prompt Engineering & Organization

Prompts are the core of the LLM-powered reasoning in BioYoda. This section describes **where prompts are created**, **how they are organized**, and **best practices** for versioning and iteration.

### 6.1 Prompt Location Strategy

**Function Calling vs Prompts: A Complementary Relationship**

The agent system uses **both function calling and prompts** in a complementary way:

- **Function Calling** (LLM API feature): Defines **WHAT tools exist** via structured JSON schemas
  - Tool signatures (name, parameters, types)
  - Parameter validation (types, required fields)
  - Structured output (no parsing errors)
  - Example: `{"name": "biobtree_query", "parameters": {"chain_query": {"type": "string"}}}`

- **Prompts** (Text instructions): Explains **HOW to use tools intelligently**
  - Domain knowledge (BioBTree query language, 40+ datasets)
  - Usage patterns (when to use deterministic vs semantic search)
  - Syntax guidance (chain query syntax: `EGFR >> hgnc >> uniprot`)
  - Filter expressions (e.g., `[uniprot.reviewed==true]`)
  - Few-shot examples (successful query patterns)

**Why both are essential**:
- Function calling ensures reliable tool invocation (no parsing errors)
- Prompts provide the domain expertise to use tools correctly
- Together: LLM knows the tool exists (function call) AND how to build valid queries (prompt)

**Example for BioBTree**:
```python
# Function definition (WHAT)
tools = [{
    "name": "biobtree_query",
    "description": "Query BioBTree database with chain syntax",
    "parameters": {
        "type": "object",
        "properties": {
            "chain_query": {"type": "string", "description": "Chain query like 'EGFR >> hgnc >> uniprot'"}
        },
        "required": ["chain_query"]
    }
}]

# System prompt (HOW) - loaded from prompts/agents/shared/biobtree_syntax.txt
biobtree_guide = """
BioBTree Query Language:
- Chain syntax: term >> dataset >> dataset
- Available datasets: hgnc (genes), uniprot (proteins), chembl_target (drug targets),
  chembl_compound (drugs), dbsnp (variants), reactome (pathways)
- Filters: [dataset.field==value]
- Examples:
  - Find proteins for gene: "BRCA1 >> hgnc >> uniprot"
  - Find drugs for gene: "EGFR >> hgnc >> uniprot >> chembl_target >> chembl_compound"
  - Filter reviewed proteins: "TP53 >> hgnc >> uniprot[uniprot.reviewed==true]"
"""
```

**Prompt Locations in Query Flow**

Prompts are created at **three key locations** in the query execution flow (see `docs/QUERY_EXECUTION_FLOW.md` for detailed flow):

#### Location 1: Agent Selection (Reasoning Engine)
**When**: After query validation, before agent execution
**Purpose**: Decide which agent(s) should handle the query
**Input**: User query + agent capability descriptions
**Output**: Selected agent(s) with confidence scores

**Example Prompt**:
```
You are the Reasoning Engine for BioYoda, a bioinformatics RAG system.

User Query: "{user_query}"

Available Agents:
1. Drug Discovery Agent
   - Capabilities: Drug-target interactions, clinical trials, bioactivity, mechanism of action
   - Data sources: ChEMBL (deterministic), PubMed (semantic), clinical trials (semantic)
   - Best for: Drug discovery, target identification, compound analysis

2. Variant Analysis Agent
   - Capabilities: SNP-disease associations, genomic coordinates, clinical annotations
   - Data sources: dbSNP (deterministic), ClinVar (deterministic), GWAS Catalog (deterministic)
   - Best for: Genetic variants, disease associations, population genetics

3. Protein Analysis Agent
   - Capabilities: Sequence similarity, functional similarity, interactions, expression
   - Data sources: UniProt (deterministic), ESM-2 (semantic), DIAMOND (semantic)
   - Best for: Protein function, homology, interactions

Task: Analyze the query and select the most appropriate agent(s).
Output format: {{"agent": "drug_discovery", "confidence": 0.95, "reasoning": "..."}}
```

#### Location 2: Agent Execution (ReAct Loop)
**When**: During agent execution, for each iteration
**Purpose**: Guide agent's tool selection and reasoning
**Input**: System prompt + conversation history + function definitions (tools)
**Output**: Tool calls or final answer

**How Function Calling + Prompts Work Together**:
- **Function definitions** are passed to the LLM API separately from the prompt
- **System prompt** teaches the agent HOW to use those functions effectively
- LLM sees both and produces structured function calls with correct parameters

**Example Setup** (Drug Discovery Agent):
```python
# Function definitions (passed to LLM API)
tools = [
    {
        "name": "biobtree_query",
        "description": "Query BioBTree database with chain syntax",
        "parameters": {
            "type": "object",
            "properties": {
                "chain_query": {"type": "string", "description": "Chain query syntax"}
            },
            "required": ["chain_query"]
        }
    },
    {
        "name": "bioyoda_search",
        "description": "Semantic search across PubMed, clinical trials, patents",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "collection": {"type": "string", "enum": ["pubmed", "clinical_trials", "patents"]},
                "top_k": {"type": "integer"}
            },
            "required": ["query", "collection"]
        }
    }
]

# System prompt (teaches HOW to use tools)
system_prompt = """
You are the Drug Discovery Agent for BioYoda. Your role is to answer drug discovery queries using available tools.

Tool Usage Guidelines:

**biobtree_query**: For deterministic mappings across databases
- Syntax: "term >> dataset >> dataset"
- Datasets: hgnc (genes), uniprot (proteins), chembl_target (drug targets), chembl_compound (drugs)
- Filters: [dataset.field==value]
- Examples:
  - Find proteins: "EGFR >> hgnc >> uniprot"
  - Find drugs: "EGFR >> hgnc >> uniprot >> chembl_target >> chembl_compound"
  - Filter reviewed: "BRCA1 >> hgnc >> uniprot[uniprot.reviewed==true]"

**bioyoda_search**: For semantic/literature search
- Use for: Mechanisms, clinical outcomes, research findings
- Collections: pubmed (research), clinical_trials (trials), patents (IP)
- Example: bioyoda_search("EGFR inhibitor resistance mechanisms", "pubmed", 10)

ReAct Pattern:
Thought: What information do I need to answer this query?
Action: tool_name(parameters)
Observation: [tool result will be inserted here]
Thought: Do I have enough information? If yes, provide Answer. If no, continue.
Action: another_tool_name(parameters)
...
Answer: [final response with citations and confidence labels]

Confidence Labels:
- 🔒 Deterministic (BioBTree mappings)
- 🔍 Semantic (similarity-based search)
- 📄 Citation-backed (from literature)
- 💡 LLM-inferred (reasoning)

User Query: "{user_query}"

Begin your reasoning:
```

#### Location 3: Answer Synthesis
**When**: After agent completes execution
**Purpose**: Format results for user presentation
**Input**: Agent results + user preferences
**Output**: Formatted response (text, JSON, table, etc.)

**Example Prompt**:
```
Format the following agent results for the user:

Agent Results: {agent_results}
User Preferences: {format: "text", include_citations: true}

Instructions:
1. Start with a concise summary (2-3 sentences)
2. Present key findings with confidence labels
3. Include citations for semantic/literature results
4. Add "Learn more" links for deterministic results
5. End with suggested follow-up questions

Output format: Plain text with markdown formatting
```

### 6.2 Centralized Prompt Organization

All prompts are stored in a centralized directory structure for version control, testing, and iteration:

```
modules/agent_system/prompts/
├── reasoning_engine/
│   ├── agent_selection.txt           # Location 1: Agent selection prompt
│   ├── agent_selection_examples.json # Few-shot examples for agent selection
│   └── versions/
│       ├── agent_selection_v1.txt    # Version history
│       └── agent_selection_v2.txt
│
├── agents/
│   ├── drug_discovery/
│   │   ├── system_prompt.txt         # Location 2: ReAct execution prompt
│   │   ├── few_shot_examples.json    # Few-shot examples for this agent
│   │   └── versions/
│   │       ├── system_prompt_v1.txt
│   │       └── system_prompt_v2.txt
│   │
│   ├── variant_analysis/
│   │   ├── system_prompt.txt
│   │   └── few_shot_examples.json
│   │
│   ├── protein_analysis/
│   │   ├── system_prompt.txt
│   │   └── few_shot_examples.json
│   │
│   └── shared/
│       ├── react_pattern.txt         # Shared ReAct instructions
│       ├── biobtree_syntax.txt       # BioBTree query language guide (HOW to build queries)
│       ├── biobtree_datasets.txt     # Available datasets and their relationships
│       ├── biobtree_filters.txt      # Filter syntax and common patterns
│       ├── confidence_labels.txt     # Confidence labeling instructions
│       └── citation_format.txt       # Citation formatting guide
│
├── response_formatting/
│   ├── text_format.txt               # Location 3: Text response formatting
│   ├── json_format.txt               # JSON response formatting
│   ├── table_format.txt              # Table response formatting
│   └── versions/
│       └── text_format_v1.txt
│
└── templates/
    └── jinja2_helpers.py             # Jinja2 template utilities
```

### 6.3 Prompt Types

#### Agent Selection Prompts
**File**: `prompts/reasoning_engine/agent_selection.txt`
**Purpose**: Help reasoning engine choose the right agent
**Variables**: `{user_query}`, `{agent_descriptions}`, `{conversation_history}`

#### ReAct Execution Prompts
**File**: `prompts/agents/{agent_name}/system_prompt.txt`
**Purpose**: Guide agent's reasoning and tool usage
**Variables**: `{user_query}`, `{tools}`, `{conversation_history}`

#### Shared Pattern Prompts
**Files**: `prompts/agents/shared/*.txt`
**Purpose**: Reusable prompt components across agents (domain knowledge for tool usage)
**Examples**:
- `react_pattern.txt`: Standard ReAct instructions
- `biobtree_syntax.txt`: BioBTree query language (chain syntax, operators)
- `biobtree_datasets.txt`: Available datasets (40+ databases) and typical query paths
- `biobtree_filters.txt`: Filter expressions and common patterns
- `confidence_labels.txt`: When to use 🔒🔍📄💡

**Note**: These prompts complement function calling definitions. Function calls define tool signatures (WHAT exists), these prompts teach usage patterns (HOW to use effectively).

#### Response Formatting Prompts
**Files**: `prompts/response_formatting/*.txt`
**Purpose**: Format agent results for user display
**Variables**: `{agent_results}`, `{format}`, `{user_preferences}`

### 6.4 Prompt Loader Implementation

The `PromptLoader` class loads prompts with Jinja2 templating support:

```python
# File: modules/agent_system/core/prompt_loader.py

from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Template, Environment, FileSystemLoader
import json

class PromptLoader:
    """Load and manage prompts with templating support."""

    def __init__(self, prompts_dir: Path):
        """Initialize with prompts directory path."""
        self.prompts_dir = Path(prompts_dir)
        self.env = Environment(
            loader=FileSystemLoader(self.prompts_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        self._cache: Dict[str, str] = {}

    def load(self, prompt_path: str, **kwargs) -> str:
        """
        Load prompt with Jinja2 template variables.

        Args:
            prompt_path: Relative path to prompt file (e.g., "agents/drug_discovery/system_prompt.txt")
            **kwargs: Template variables to substitute

        Returns:
            Rendered prompt string

        Example:
            loader = PromptLoader("modules/agent_system/prompts")
            prompt = loader.load(
                "agents/drug_discovery/system_prompt.txt",
                user_query="What are EGFR inhibitors?",
                tools=tool_descriptions
            )
        """
        # Load template (with caching)
        if prompt_path not in self._cache:
            full_path = self.prompts_dir / prompt_path
            if not full_path.exists():
                raise FileNotFoundError(f"Prompt not found: {full_path}")

            with open(full_path, 'r') as f:
                self._cache[prompt_path] = f.read()

        # Render with Jinja2
        template = Template(self._cache[prompt_path])
        return template.render(**kwargs)

    def load_with_examples(
        self,
        prompt_path: str,
        examples_path: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Load prompt with few-shot examples.

        Args:
            prompt_path: Path to main prompt file
            examples_path: Path to examples JSON (default: auto-detect)
            **kwargs: Template variables

        Returns:
            Prompt with examples inserted
        """
        # Auto-detect examples file
        if examples_path is None:
            base = prompt_path.replace('.txt', '')
            examples_path = f"{base}_examples.json"

        # Load examples
        examples_file = self.prompts_dir / examples_path
        if examples_file.exists():
            with open(examples_file, 'r') as f:
                examples = json.load(f)
            kwargs['examples'] = examples

        return self.load(prompt_path, **kwargs)

    def list_versions(self, prompt_path: str) -> list[str]:
        """List all versions of a prompt."""
        base_dir = (self.prompts_dir / prompt_path).parent / "versions"
        if not base_dir.exists():
            return []

        return sorted([f.name for f in base_dir.glob("*.txt")])

    def load_version(self, prompt_path: str, version: str, **kwargs) -> str:
        """Load a specific version of a prompt."""
        base = Path(prompt_path)
        version_path = base.parent / "versions" / f"{base.stem}_{version}.txt"
        return self.load(str(version_path), **kwargs)


# Usage Example
class DrugDiscoveryAgent:
    def __init__(self):
        self.prompt_loader = PromptLoader("modules/agent_system/prompts")

    async def execute(self, user_query: str) -> AgentResult:
        # Load system prompt with current query
        system_prompt = self.prompt_loader.load(
            "agents/drug_discovery/system_prompt.txt",
            user_query=user_query,
            tools=self._format_tool_descriptions()
        )

        # Execute ReAct loop with this prompt
        messages = [{"role": "system", "content": system_prompt}]
        # ... rest of ReAct execution
```

### 6.5 Example Prompt Templates

#### Example 1: Agent Selection Prompt
**File**: `prompts/reasoning_engine/agent_selection.txt`

```
You are the Reasoning Engine for BioYoda, a bioinformatics RAG system that blends deterministic mappings and semantic search.

Your task: Analyze the user's query and select the most appropriate agent(s) to handle it.

## Available Agents

{% for agent in agents %}
{{ loop.index }}. {{ agent.name }}
   Description: {{ agent.description }}
   Capabilities: {{ agent.capabilities | join(", ") }}
   Data Sources: {{ agent.data_sources | join(", ") }}
   Agent Type: {{ agent.agent_type }}  {# deterministic, semantic, or hybrid #}
   Best For: {{ agent.best_for }}
{% endfor %}

## User Query
"{{ user_query }}"

## Agent Selection Guidelines
1. **Deterministic agents** (BioBTree-only): Use when query requires exact mappings, IDs, or relationships
2. **Semantic agents** (BioYoda-only): Use when query requires literature search, semantic similarity, or concept exploration
3. **Hybrid agents**: Use when query benefits from both deterministic mappings AND semantic search
4. **Multiple agents**: Consider if query spans multiple domains (e.g., drug + variant analysis)

## Output Format
Return a JSON object:
{
  "primary_agent": "agent_name",
  "confidence": 0.95,
  "reasoning": "Why this agent was selected",
  "additional_agents": ["other_agent"] // optional
}

## Examples
{% for example in examples %}
Query: "{{ example.query }}"
Selected: {{ example.agent }}
Reasoning: {{ example.reasoning }}
---
{% endfor %}

Now analyze the user's query and select the agent:
```

#### Example 2: Drug Discovery Agent System Prompt
**File**: `prompts/agents/drug_discovery/system_prompt.txt`

```
You are the **Drug Discovery Agent** for BioYoda. Your role is to answer drug discovery, target identification, and compound analysis queries using available tools.

## Your Capabilities
- Drug-target interactions (ChEMBL)
- Clinical trial information
- Compound bioactivity and properties
- Mechanism of action analysis
- Target-disease associations
- Literature search for drug discovery

## Available Tools

1. **biobtree_query**(chain_query: str, detail: bool = False) -> Dict
   - Execute deterministic BioBTree chain queries
   - Syntax: "input_term >> relationship >> relationship"
   - Example: "EGFR >> uniprot >> chembl_target >> chembl_compound"
   - Returns: Mapped IDs with optional details
   - Confidence: 🔒 Deterministic (100% reproducible)

2. **bioyoda_search**(query: str, collection: str, top_k: int = 10, threshold: float = 0.7) -> List[Dict]
   - Semantic search across PubMed abstracts, clinical trials, patents
   - Collections: "pubmed", "clinicaltrials", "patents"
   - Returns: Ranked documents with similarity scores
   - Confidence: 🔍 Semantic (similarity-based)

3. **bioyoda_protein_similarity**(sequence_or_id: str, method: str = "esm2") -> List[Dict]
   - Find functionally/structurally similar proteins
   - Methods: "esm2" (functional), "diamond" (sequence)
   - Confidence: 🔍 Semantic (embedding-based)

## Query Building Guidelines

### BioBTree Chain Syntax
- Format: `input >> relationship >> relationship >> ...`
- Example chains:
  * Drug to targets: `compound_id >> chembl_compound >> chembl_target >> uniprot`
  * Gene to diseases: `gene_symbol >> hgnc >> uniprot >> mondo`
  * Target to pathways: `uniprot_id >> uniprot >> reactome`

See {% include "agents/shared/biobtree_syntax.txt" %} for full syntax guide.

## ReAct Pattern
{% include "agents/shared/react_pattern.txt" %}

## Confidence Labeling
{% include "agents/shared/confidence_labels.txt" %}

## User Query
"{{ user_query }}"

{% if conversation_history %}
## Conversation History
{% for turn in conversation_history %}
User: {{ turn.user }}
Assistant: {{ turn.assistant }}
{% endfor %}
{% endif %}

## Instructions
1. Break down the query into sub-questions
2. Use ReAct pattern: Thought → Action → Observation
3. Execute tools to gather information
4. Synthesize results with proper confidence labels
5. Provide citations for semantic/literature results
6. Suggest follow-up questions if appropriate

Begin your reasoning:
```

#### Example 3: Shared ReAct Pattern
**File**: `prompts/agents/shared/react_pattern.txt`

```
Use the ReAct (Reasoning + Acting) pattern for multi-step queries:

**Thought**: Analyze what information you need. Break the query into steps.
**Action**: tool_name(parameters) - Call a tool to gather information
**Observation**: [Tool result will be inserted by the system]
**Thought**: Evaluate if you have enough information. If yes, provide Answer. If no, continue.
**Action**: another_tool(parameters) - Call another tool if needed
**Observation**: [Another tool result]
...
**Answer**: Synthesize all observations into a final response

Example:
```
Thought: To find EGFR inhibitors, I need to first get the ChEMBL target ID for EGFR, then find compounds targeting it.
Action: biobtree_query("EGFR >> uniprot >> chembl_target")
Observation: ChEMBL target CHEMBL203 (EGFR, P00533)
Thought: Now I have the target ID. Let me find compounds with high affinity for this target.
Action: biobtree_query("CHEMBL203 >> chembl_target >> chembl_compound", detail=True)
Observation: Found 1,247 compounds including Erlotinib (CHEMBL558), Gefitinib (CHEMBL939), ...
Thought: I have compounds. Let me search literature for recent clinical insights.
Action: bioyoda_search("EGFR inhibitors clinical trials", "pubmed", top_k=5)
Observation: [5 recent papers about EGFR inhibitor efficacy...]
Answer: **EGFR Inhibitors Overview**
Found 1,247 compounds targeting EGFR (ChEMBL203) 🔒. Top inhibitors include:
- Erlotinib (CHEMBL558): FDA-approved for NSCLC
- Gefitinib (CHEMBL939): First-line therapy for EGFR+ patients
Recent literature 🔍 shows improved outcomes with osimertinib in T790M mutations (PMID:12345678).
```
```

#### Example 4: BioBTree Syntax Guide (Shared Prompt)
**File**: `prompts/agents/shared/biobtree_syntax.txt`

This prompt file provides domain knowledge for using BioBTree effectively. It complements the function calling definition of `biobtree_query()`.

```
# BioBTree Query Language Guide

BioBTree uses chain syntax to traverse relationships across 40+ biological databases.

## Basic Chain Syntax

Format: `input_term >> dataset >> dataset >> ...`

Each `>>` operator maps entries from the left dataset to the right dataset based on biological relationships (e.g., gene → protein → drug target).

## Available Datasets (Common Ones)

**Genes & Proteins:**
- `hgnc`: Human gene symbols (BRCA1, TP53, EGFR)
- `uniprot`: Protein sequences and annotations
- `ensembl`: Genomic coordinates and transcripts

**Drug Discovery:**
- `chembl_compound`: Small molecule drugs and bioactive compounds
- `chembl_target`: Drug targets (proteins, cells)
- `drugbank`: FDA-approved drugs and drug candidates

**Variants:**
- `dbsnp`: SNP identifiers (rs numbers)
- `clinvar`: Clinical variant annotations
- `ensembl_variation`: Genomic variant consequences

**Pathways & Functions:**
- `reactome`: Biological pathways
- `go`: Gene Ontology terms (function, process, location)
- `interpro`: Protein domains and families

**Disease:**
- `mondo`: Disease ontology (unified disease terms)
- `omim`: Genetic disorders
- `orphanet`: Rare diseases

## Common Query Patterns

**Gene → Protein → Pathways:**
```
BRCA1 >> hgnc >> uniprot >> reactome
```
Finds pathways involving BRCA1 protein.

**Gene → Drug Targets → Compounds:**
```
EGFR >> hgnc >> uniprot >> chembl_target >> chembl_compound
```
Finds drugs targeting EGFR.

**Variant → Gene → Disease:**
```
rs429358 >> dbsnp >> hgnc >> mondo
```
Links SNP to diseases via affected genes.

**Compound → Targets → Pathways:**
```
CHEMBL25 >> chembl_compound >> chembl_target >> uniprot >> reactome
```
Finds mechanisms of action for a drug.

## Filter Syntax

Apply filters to narrow results: `[dataset.field==value]` or `[dataset.field>value]`

**Examples:**
```
TP53 >> hgnc >> uniprot[uniprot.reviewed==true]
```
Only retrieve reviewed (Swiss-Prot) protein entries.

```
BRCA1 >> hgnc >> uniprot >> go[go.aspect==biological_process]
```
Only biological process GO terms (not molecular function or cellular component).

## Multi-term Queries

You can query multiple terms at once (especially useful for batch lookups):
```
["BRCA1", "BRCA2", "TP53"] >> hgnc >> uniprot
```

## Detail Flag

- `detail=False` (default): Returns only identifiers (fast, compact)
- `detail=True`: Returns full metadata (names, descriptions, scores)

**When to use detail=True:**
- Need human-readable names
- Require additional metadata (sequence length, publication dates)
- Building final answer for user

**When to use detail=False:**
- Intermediate mapping steps
- Checking if mapping exists
- Large result sets (thousands of entries)

## Tips for Effective Queries

1. **Start specific, expand gradually**: Begin with a single gene/compound, then broaden
2. **Check intermediate steps**: For long chains, break into smaller queries to verify each hop
3. **Use filters early**: Apply filters as early as possible to reduce result set size
4. **Leverage detail flag**: Use `detail=False` for exploration, `detail=True` for final results
5. **Know your datasets**: Some datasets are bidirectional (gene ↔ protein), others are unidirectional (variant → gene but not gene → variant)

## Error Handling

If a query returns empty results:
- Check dataset spelling (case-sensitive: `hgnc` not `HGNC`)
- Verify input term exists in source dataset
- Try alternative identifiers (gene symbol vs Ensembl ID)
- Break chain into smaller steps to find where mapping fails
```

**How this prompt is used**:
- Included in agent system prompts via `{% include "agents/shared/biobtree_syntax.txt" %}`
- Loaded at runtime by PromptLoader
- Combined with function calling definition to give LLM both structure (function schema) and knowledge (query language guide)

### 6.6 Versioning & A/B Testing

#### Version Control Strategy
1. **Main prompt**: `system_prompt.txt` (always latest stable version)
2. **Version history**: `versions/system_prompt_v1.txt`, `v2.txt`, etc.
3. **Experimental prompts**: `system_prompt_experimental.txt`

#### A/B Testing Implementation
```python
class PromptABTest:
    """Run A/B tests on prompt variations."""

    def __init__(self, prompt_loader: PromptLoader):
        self.loader = prompt_loader
        self.results: Dict[str, List[float]] = {}

    async def run_test(
        self,
        base_prompt_path: str,
        variant_prompt_path: str,
        test_queries: List[str],
        evaluation_fn: Callable
    ) -> Dict[str, Any]:
        """
        Run A/B test between two prompt versions.

        Args:
            base_prompt_path: Path to baseline prompt
            variant_prompt_path: Path to variant prompt
            test_queries: List of test queries
            evaluation_fn: Function to evaluate results (returns score 0-1)

        Returns:
            Statistical comparison results
        """
        base_scores = []
        variant_scores = []

        for query in test_queries:
            # Test baseline
            base_result = await self._execute_with_prompt(base_prompt_path, query)
            base_score = evaluation_fn(base_result, query)
            base_scores.append(base_score)

            # Test variant
            variant_result = await self._execute_with_prompt(variant_prompt_path, query)
            variant_score = evaluation_fn(variant_result, query)
            variant_scores.append(variant_score)

        # Statistical comparison
        from scipy import stats
        t_stat, p_value = stats.ttest_ind(base_scores, variant_scores)

        return {
            "base_mean": np.mean(base_scores),
            "variant_mean": np.mean(variant_scores),
            "improvement": np.mean(variant_scores) - np.mean(base_scores),
            "p_value": p_value,
            "significant": p_value < 0.05,
            "winner": "variant" if np.mean(variant_scores) > np.mean(base_scores) else "base"
        }
```

#### Prompt Monitoring
Track prompt performance metrics:
```python
# Log prompt usage and outcomes
{
    "timestamp": "2025-01-15T10:30:00Z",
    "prompt_path": "agents/drug_discovery/system_prompt.txt",
    "prompt_version": "v2",
    "query": "What are EGFR inhibitors?",
    "agent": "drug_discovery",
    "execution_time": 3.2,
    "tool_calls": 3,
    "success": true,
    "user_feedback": 5,  # 1-5 rating
    "cost_tokens": 1250
}
```

### 6.7 Best Practices

#### 1. Prompt Engineering Principles
- **Be specific**: Clear instructions produce better results
- **Use examples**: Few-shot examples improve accuracy (3-5 examples ideal)
- **Label confidence**: Always distinguish deterministic vs semantic results
- **Iterate**: Start simple, measure performance, refine

#### 2. Template Variables
- Use `{{ variable }}` for required variables
- Use `{% if variable %} ... {% endif %}` for optional sections
- Keep variable names consistent across prompts

#### 3. Shared Components
- Extract common instructions to `shared/` directory
- Use `{% include "path/to/shared.txt" %}` for reuse
- Examples: ReAct pattern, BioBTree syntax, citation format

#### 4. Testing Strategy
- **Unit tests**: Test prompt loading and rendering
- **Integration tests**: Test prompts with actual LLM calls
- **Evaluation sets**: Curated queries with expected outputs
- **A/B testing**: Compare prompt variations statistically

#### 5. Documentation
- Add comments in prompts using `{# comment #}`
- Document template variables at top of file
- Include example outputs in prompt files

---

## 7. Data Integration

### 7.1 BioBTree Integration

#### Available Datasets (40+)

**Proteins & Genes**:
- UniProt (SwissProt: 570K, TrEMBL: 250M)
- Ensembl (6 divisions: main, bacteria, fungi, metazoa, plants, protists)
- HGNC (gene nomenclature)

**Chemistry & Drugs**:
- ChEMBL (2.3M+ compounds, targets, bioactivity)
- HMDB (metabolites)
- ChEBI (chemical entities)
- SwissLipids (779K+ lipids)

**Variants & Genetics**:
- dbSNP (SNPs, genomic coordinates)
- ClinVar (clinical variant annotations)
- GWAS Catalog (1M+ SNP-trait associations)

**Pathways & Ontologies**:
- Reactome (23K+ pathways)
- GO (Gene Ontology)
- HPO (Human Phenotype Ontology)
- MONDO (disease ontology)
- EFO, ECO, UBERON, CL

**Expression & Interactions**:
- Bgee (gene expression, 30+ species)
- IntAct (1.8M+ protein interactions)
- STRING (protein-protein interactions)

**Clinical & Patents**:
- ClinicalTrials.gov
- SureChEMBL (43M+ patents)

**Others**:
- RNACentral (49.8M+ ncRNAs)
- AlphaFold (structure predictions)
- NCBI Taxonomy

#### Query Patterns

**Simple Mapping**:
```
BRCA1 >> uniprot
```

**Multi-hop**:
```
EGFR >> uniprot >> chembl_target >> chembl_activity
```

**Filtering**:
```
BRCA1 >> uniprot[uniprot.reviewed==true] >> go[go.type=="biological_process"]
```

**Genomic Coordinates**:
```
>>ensembl[ensembl.overlaps(114129278,114129328)]
```

**Parent/Child Navigation**:
```
GO:0008150 >> go.children
```

### 7.2 BioYoda Integration

#### Available Collections

**PubMed Abstracts**:
- **Size**: ~30M documents
- **Embeddings**: S-BioBERT (768-dim)
- **Metadata**: PMID, title, abstract, authors, journal, pub_date, MeSH terms
- **Update**: Incremental (baseline + daily updates)

**Clinical Trials**:
- **Size**: ~554K trials (3M chunks)
- **Embeddings**: S-BioBERT (768-dim)
- **Chunking**: By section (title, summary, eligibility, outcomes)
- **Metadata**: NCT ID, status, phase, conditions, interventions, sponsor
- **Drug Mapping**: Automatic ChEMBL linking

**Patents (Text)**:
- **Size**: 43M patents
- **Embeddings**: S-BioBERT (768-dim)
- **Metadata**: Patent ID, title, abstract, assignee, filing date
- **Sources**: SureChEMBL + USPTO enrichment

**Patents (Compounds)**:
- **Size**: 30M compounds
- **Embeddings**: Morgan fingerprints (2048-bit)
- **Metadata**: Compound ID, SMILES, patent ID
- **Use**: Chemical similarity search

**ESM-2 Proteins**:
- **Size**: 570K+ proteins (SwissProt)
- **Embeddings**: ESM-2 650M model (1280-dim)
- **Metadata**: UniProt ID, protein name, organism
- **Use**: Functional similarity search

#### Query Capabilities

**Single Collection Search**:
```python
await qdrant_client.search(
    collection_name="pubmed_abstracts",
    query_vector=embed("CRISPR gene editing"),
    limit=20
)
```

**Multi-Collection Search**:
```python
results = await bioyoda_client.multi_search(
    query="EGFR inhibitor side effects",
    collections=["pubmed_abstracts", "clinical_trials"],
    limit=10
)
```

**RAG Q&A**:
```python
answer = await bioyoda_client.ask(
    question="What are the side effects of EGFR inhibitors?",
    collections=["pubmed_abstracts", "clinical_trials"],
    llm_provider="anthropic"
)
```

### 7.3 Integration Patterns

#### Pattern 1: Identifier Resolution → Semantic Search
```
User: "Find papers about BRCA1 mutations"
    ↓
Step 1: Detect entity "BRCA1"
Step 2: BioBTree resolve: BRCA1 >> uniprot → P38398
Step 3: BioBTree get synonyms: P38398, BRCA1, breast cancer type 1
Step 4: BioYoda search: "P38398 OR BRCA1 mutations"
    ↓
Return: Papers with context
```

#### Pattern 2: Semantic Search → Structured Navigation
```
User: "What compounds are similar to drugs mentioned in Alzheimer papers?"
    ↓
Step 1: BioYoda search PubMed: "Alzheimer drugs"
Step 2: Extract drug names from papers (NER or LLM)
Step 3: BioBTree map: drug_names >> chembl_molecule
Step 4: BioYoda chemical similarity: chembl_smiles → similar compounds
    ↓
Return: Similar compounds with papers
```

#### Pattern 3: Hybrid Multi-Step
```
User: "Find proteins in EGFR pathway expressed in brain with recent papers"
    ↓
Step 1: BioBTree: EGFR >> uniprot >> reactome (get pathways)
Step 2: BioBTree: pathway >> uniprot (get pathway proteins)
Step 3: BioBTree: proteins >> bgee[tissue=="brain"] (filter by expression)
Step 4: BioYoda: search("protein_name brain expression")
    ↓
Return: Proteins with expression data + papers
```

---

## 8. API Specifications

### 8.1 API-First Architecture

**Key Principle**: All user interactions go through the REST API layer.

**Why API-First:**
- 🔐 **Authentication/Authorization**: API keys, user tier enforcement
- 💰 **Billing & Metering**: Track usage, implement free vs paid tiers
- 🚦 **Rate Limiting**: Prevent abuse, manage costs
- 📊 **Monitoring**: Track performance, costs, errors per user
- 🛡️ **Security**: Single entry point, easier to secure
- 📈 **Scalability**: Can add load balancing, caching layers

### 8.2 REST API

**Base URL**: `http://localhost:8000/api/v1`

**Authentication**: API Key in header
```
Authorization: Bearer <api_key>
```

#### User Tiers & Rate Limits

| Tier | Cost | Queries/Day | LLM Synthesis | Priority |
|------|------|-------------|---------------|----------|
| Free | $0 | 10 | Minimal only | Low |
| Researcher | $29/mo | 1,000 | All levels | Medium |
| Institution | $299/mo | 10,000 | All levels | High |
| Enterprise | Custom | Unlimited | All levels | Highest |

#### Endpoints

**POST /query**
```json
Request:
{
    "query": "Find drugs targeting EGFR",
    "session_id": "optional-session-id",

    // Execution Mode (Reasoning Engine Control)
    "mode": "auto",  // auto (default) | deterministic_only | semantic_only

    // Optional: Skip reasoning and force specific agent
    "agent": null,  // null (auto-select) | "drug_discovery" | "variant_analysis" | etc.

    // LLM Control
    "llm_synthesis": "moderate",  // none | minimal | moderate | full

    // Output Control
    "output_options": {
        "separate_sources": true,      // Show deterministic vs semantic separately
        "label_confidence": true,      // Mark each result with confidence type
        "show_evidence_strength": true,// Display similarity scores
        "format": "auto",              // auto | text | table | json | mixed
        "verbosity": "medium",         // brief | medium | detailed
        "max_results_per_source": 10
    },

    // Filters (applied by agents)
    "filters": {
        "min_semantic_score": 0.8,     // Filter low-similarity results
        "literature_year_min": 2020,   // Recent papers only
        "max_results": 20
    },

    // Advanced Options
    "options": {
        "llm_provider": "anthropic",   // anthropic | openai | gemini
        "include_reasoning": false,    // Include reasoning engine's decision process
        "stream": false                // Stream results as they come
    }
}

Response:
{
    "query_id": "uuid",
    "session_id": "session-uuid",
    "success": true,
    "answer": "Found 45 compounds targeting EGFR...",
    "results": [
        {
            "compound_id": "CHEMBL6939",
            "compound_name": "Gefitinib",
            "target_id": "CHEMBL203",
            "activity": {...},
            "source": "ChEMBL"
        },
        ...
    ],
    "sources": [
        {
            "type": "structured",
            "name": "ChEMBL",
            "icon": "🔒",
            "confidence_type": "deterministic",
            "confidence_score": 1.0,
            "reproducible": true,
            "query": "P00533 >> chembl_target >> chembl_activity",
            "result_count": 45
        },
        {
            "type": "semantic",
            "name": "Clinical Trials",
            "icon": "🔍",
            "confidence_type": "similarity",
            "confidence_score": 0.89,
            "reproducible": "configurable",
            "query": "EGFR inhibitor side effects",
            "result_count": 243
        },
        {
            "type": "literature",
            "name": "PubMed",
            "icon": "📄",
            "confidence_type": "citation",
            "confidence_score": 0.95,
            "reproducible": true,
            "document_id": "PMID:12345678",
            "title": "...",
            "result_count": 1247
        }
    ],
    "reasoning": {
        "query_analysis": "Query requires deterministic compound lookup + semantic side effect search",
        "selected_agent": "drug_discovery",
        "agent_type": "hybrid",
        "estimated_blend": {
            "deterministic": 0.40,
            "semantic": 0.35,
            "llm": 0.25
        },
        "decision_rationale": "Drug Discovery Agent can handle both BioBTree lookup and BioYoda semantic search"
    },
    "blend_info": {
        "actual_blend": {
            "deterministic": 0.42,
            "semantic": 0.33,
            "llm": 0.25
        },
        "data_sources_used": ["biobtree", "qdrant_clinical_trials", "qdrant_pubmed"],
        "llm_synthesis_level": "moderate"
    },
    "metadata": {
        "agent_used": "drug_discovery",
        "agent_type": "hybrid",
        "execution_time_ms": 4234,
        "step_count": 5,
        "user_tier": "researcher",
        "queries_remaining_today": 987,
        "llm_usage": {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "input_tokens": 1234,
            "output_tokens": 567,
            "cost_usd": 0.048
        }
    }
}
```

**GET /query/{query_id}**
```json
Response:
{
    "query_id": "uuid",
    "status": "completed",  // or "running", "failed"
    "created_at": "2025-11-19T10:30:00Z",
    "completed_at": "2025-11-19T10:30:05Z",
    "query": "...",
    "result": {...}  // Same as POST /query response
}
```

**GET /sessions/{session_id}**
```json
Response:
{
    "session_id": "uuid",
    "user_id": "user-123",
    "created_at": "2025-11-19T10:00:00Z",
    "last_activity": "2025-11-19T10:30:00Z",
    "queries": [
        {
            "query_id": "query-1",
            "query": "...",
            "timestamp": "2025-11-19T10:15:00Z"
        },
        ...
    ]
}
```

**GET /agents**
```json
Response:
{
    "agents": [
        {
            "id": "drug_discovery",
            "name": "Drug Discovery Agent",
            "description": "Target identification, compound search, trials",
            "capabilities": ["target_finding", "compound_search", ...],
            "status": "available"
        },
        ...
    ]
}
```

**POST /agents/{agent_id}/query**
```json
Request:
{
    "query": "...",
    "context": {...}
}

Response:
{
    // Same as POST /query
}
```

**WebSocket /ws/stream**
```
Client → Server:
{
    "action": "query",
    "query": "Find drugs targeting EGFR",
    "session_id": "..."
}

Server → Client (streaming):
{
    "type": "step_start",
    "step": 1,
    "description": "Resolving gene to protein..."
}
{
    "type": "step_complete",
    "step": 1,
    "result": {...}
}
{
    "type": "answer_chunk",
    "content": "Found 45 compounds..."
}
{
    "type": "complete",
    "result": {...}
}
```

### 8.3 CLI Tool

**Note**: CLI wraps the REST API - no direct module imports.

```bash
# Simple query
bioyoda query "Find drugs targeting EGFR"

# Interactive mode
bioyoda interactive

# Specific agent
bioyoda query --agent drug_discovery "Find EGFR inhibitors"

# Stream output
bioyoda query --stream "Complex multi-step query..."

# Export results
bioyoda query "..." --output results.json
bioyoda query "..." --format csv --output results.csv
```

---

## 9. Data Flows

### 9.1 Simple Query Flow

```
┌─────────┐
│  User   │ "Find drugs targeting EGFR"
└────┬────┘
     │
     ▼
┌────────────────┐
│ Query Gateway  │
│ • Parse query  │
│ • Detect EGFR  │
│ • Intent: drug │
└────┬───────────┘
     │
     ▼
┌──────────────────────┐
│ Drug Discovery Agent │
│ • Plan steps:        │
│   1. EGFR → protein  │
│   2. protein → target│
│   3. target → cmpds  │
└────┬─────────────────┘
     │
     ├──────────────────────────────────┐
     │                                  │
     ▼                                  ▼
┌────────────────┐              ┌──────────────┐
│ BioBTree Tools │              │ BioYoda Tools│
│ • gene_to_prot │              │ • pubmed_srch│
│ • prot_to_tgt  │              └──────────────┘
│ • tgt_to_cmpd  │
└────┬───────────┘
     │
     ▼
┌────────────────┐
│ BioBTree API   │
│ EGFR >> uniprot│
│ >> chembl_tgt  │
│ >> chembl_act  │
└────┬───────────┘
     │
     ▼
┌─────────────────────┐
│ Results Aggregation │
│ • Merge tool outputs│
│ • Rank by relevance │
│ • Add citations     │
└────┬────────────────┘
     │
     ▼
┌────────────────┐
│ LLM Synthesis  │
│ "Found 45      │
│  compounds..." │
└────┬───────────┘
     │
     ▼
┌────────────┐
│  Response  │
└────────────┘
```

### 9.2 Complex Multi-Agent Flow

```
┌─────────┐
│  User   │ "Find trials for compounds similar to Ibuprofen
└────┬────┘  that target proteins in inflammation pathway"
     │
     ▼
┌─────────────────┐
│  Planner Agent  │
│  Decompose:     │
│  1. Ibuprofen   │
│     → similar   │
│  2. Pathway     │
│     → proteins  │
│  3. Compounds   │
│     → trials    │
└────┬────────────┘
     │
     ├────────────────┬───────────────┐
     │                │               │
     ▼                ▼               ▼
┌──────────┐    ┌──────────┐   ┌───────────┐
│ Step 1   │    │ Step 2   │   │  Step 3   │
│ Chem Sim │    │ Pathway  │   │  Trials   │
│          │    │ Analysis │   │  Search   │
│ BioYoda  │    │ BioBTree │   │  BioBTree │
│ Patents  │    │ Reactome │   │ + BioYoda │
└────┬─────┘    └────┬─────┘   └─────┬─────┘
     │               │               │
     │   [Similar    │  [Proteins]   │
     │    compounds] │               │
     │               │               │
     └───────┬───────┴───────┬───────┘
             │               │
             ▼               ▼
        ┌─────────────────────────┐
        │  Results Aggregation    │
        │  • Match compounds      │
        │    to trials            │
        │  • Filter by proteins   │
        │  • Rank by relevance    │
        └─────┬───────────────────┘
              │
              ▼
        ┌─────────────────┐
        │  LLM Synthesis  │
        │  Generate final │
        │  answer with    │
        │  citations      │
        └─────┬───────────┘
              │
              ▼
        ┌──────────┐
        │ Response │
        └──────────┘
```

### 9.3 Multi-Turn Conversation Flow

```
Turn 1:
User: "What is EGFR?"
  ↓
Gateway → Literature Agent
  ↓
BioYoda PubMed search → Summary
  ↓
Session State: {
  "entities": {"EGFR": "gene"},
  "context": "EGFR is a receptor tyrosine kinase..."
}

Turn 2:
User: "What drugs target it?"
  ↓
Gateway (with session context)
  ↓
Planner: "it" = EGFR (from session)
  ↓
Drug Discovery Agent
  ↓
BioBTree: EGFR >> uniprot >> chembl
  ↓
Session State: {
  "entities": {"EGFR": "gene", "P00533": "protein"},
  "drugs": ["CHEMBL6939", "CHEMBL941", ...],
  "context": "..."
}

Turn 3:
User: "Show clinical trials for the first one"
  ↓
Planner: "first one" = CHEMBL6939 (from session)
  ↓
Drug Discovery Agent
  ↓
BioYoda trials search + BioBTree mapping
  ↓
Response with trials
```

---

## 10. Deployment Architecture

### 10.1 Development Environment

```
┌─────────────────────────────────────────────────────────┐
│              Developer Machine (Local)                   │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Docker Compose Stack                             │  │
│  │                                                    │  │
│  │  ┌──────────────┐  ┌──────────────┐              │  │
│  │  │ Agent System │  │  BioBTree    │              │  │
│  │  │ (FastAPI)    │  │  (REST API)  │              │  │
│  │  │ Port: 8000   │  │  Port: 9292  │              │  │
│  │  └──────────────┘  └──────────────┘              │  │
│  │                                                    │  │
│  │  ┌──────────────┐  ┌──────────────┐              │  │
│  │  │   Qdrant     │  │    Redis     │              │  │
│  │  │ Port: 6333   │  │  Port: 6379  │              │  │
│  │  └──────────────┘  └──────────────┘              │  │
│  │                                                    │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │         Volumes                              │ │  │
│  │  │  • biobtree_data/ (LMDB)                     │ │  │
│  │  │  • qdrant_data/   (vectors)                  │ │  │
│  │  │  • redis_data/    (cache)                    │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  agent_system:
    build: ./modules/agent_system
    ports:
      - "8000:8000"
    environment:
      - BIOBTREE_URL=http://biobtree:9292
      - QDRANT_URL=http://qdrant:6333
      - REDIS_URL=redis://redis:6379
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - biobtree
      - qdrant
      - redis
    volumes:
      - ./modules/agent_system:/app

  biobtree:
    image: biobtree:latest
    ports:
      - "9292:9292"
    volumes:
      - ./biobtree_data:/data

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - ./qdrant_data:/qdrant/storage

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - ./redis_data:/data
```

### 10.2 Production Environment (HPC)

```
┌──────────────────────────────────────────────────────────────┐
│                    HPC Cluster (SLURM/SGE)                    │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Login Node                                            │  │
│  │  • Job submission                                      │  │
│  │  • Code deployment                                     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Compute Nodes (Singularity Containers)                │  │
│  │                                                         │  │
│  │  ┌──────────────────┐  ┌──────────────────┐           │  │
│  │  │ Agent System     │  │  BioBTree        │           │  │
│  │  │ (bioyoda.sif)    │  │  (biobtree.sif)  │           │  │
│  │  │ • Web API        │  │  • REST API      │           │  │
│  │  │ • Agents         │  │  • Query engine  │           │  │
│  │  └──────────────────┘  └──────────────────┘           │  │
│  │                                                         │  │
│  │  ┌──────────────────┐  ┌──────────────────┐           │  │
│  │  │  Qdrant          │  │  Redis           │           │  │
│  │  │  (qdrant.sif)    │  │  (redis.sif)     │           │  │
│  │  └──────────────────┘  └──────────────────┘           │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  GPU Nodes (Optional - for ESM-2, local LLMs)          │  │
│  │  • ESM-2 embedding server                              │  │
│  │  • vLLM inference server                               │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Shared Storage (NFS)                                   │  │
│  │  • /data/biobtree_db/                                  │  │
│  │  • /data/qdrant_storage/                               │  │
│  │  • /data/agent_logs/                                   │  │
│  │  • /data/cache/                                        │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**SLURM Job Script**:
```bash
#!/bin/bash
#SBATCH --job-name=bioyoda_agent_system
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=7-00:00:00

# Load Singularity
module load singularity

# Start services
singularity instance start \
    --bind /data:/data \
    bioyoda_agent.sif agent_system

singularity instance start \
    --bind /data:/data \
    biobtree.sif biobtree

singularity instance start \
    --bind /data:/data \
    qdrant.sif qdrant

# Monitor
tail -f /data/agent_logs/agent_system.log
```

### 10.3 Cloud Deployment (Optional)

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Ingress (Load Balancer)                               │ │
│  │  • HTTPS termination                                   │ │
│  │  • Route /api/v1 → agent_system                        │ │
│  └────────┬───────────────────────────────────────────────┘ │
│           │                                                  │
│  ┌────────▼───────────────────────────────────────────────┐ │
│  │  Agent System Deployment                               │ │
│  │  • Replicas: 3                                         │ │
│  │  • Autoscaling: CPU > 70%                              │ │
│  │  • Resources: 4 CPU, 16GB RAM                          │ │
│  └────────┬───────────────────────────────────────────────┘ │
│           │                                                  │
│  ┌────────┼─────────────┬────────────────┐                  │
│  │        │             │                │                  │
│  ▼        ▼             ▼                ▼                  │
│  ┌───────────┐  ┌───────────┐  ┌────────────┐              │
│  │ BioBTree  │  │  Qdrant   │  │   Redis    │              │
│  │ StatefulSet│  │ StatefulSet│  │ Deployment │              │
│  │ Replicas:1│  │ Replicas:3│  │ Replicas:1 │              │
│  └───────────┘  └───────────┘  └────────────┘              │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Persistent Volumes (Cloud Storage)                    │ │
│  │  • biobtree-pv: 500GB SSD                              │ │
│  │  • qdrant-pv: 2TB SSD (per replica)                    │ │
│  │  • redis-pv: 50GB SSD                                  │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 11. Security & Privacy

### 11.1 Authentication & Authorization

**API Authentication**:
- API key-based authentication
- JWT tokens for session management
- OAuth 2.0 for third-party integrations (optional)

**Authorization Levels**:
- **Public**: Read-only access, limited queries/day
- **Researcher**: Full read access, higher rate limits
- **Admin**: Full access including system management

### 11.2 Data Privacy

**No User Data Storage**:
- Queries are not stored by default
- Optional query logging (anonymized) for system improvement
- Session data expires after 24 hours

**Sensitive Data Handling**:
- All data from public databases (no PHI/PII)
- No genetic data tied to individuals
- Compliance with data source licenses

### 11.3 Rate Limiting

```python
# Per API key
- Public: 100 queries/day
- Researcher: 1000 queries/day
- Admin: Unlimited

# Per IP
- 10 queries/minute
- 100 queries/hour
```

### 11.4 Input Validation

- Query length limits (max 1000 characters)
- SQL injection prevention
- No code execution in queries
- Sanitize all user inputs

---

## 12. Performance & Scalability

### 12.1 Performance Requirements

**Latency Targets**:
- Simple queries (1-2 steps): <5 seconds
- Complex queries (3-5 steps): <30 seconds
- Multi-agent queries: <60 seconds

**Throughput Targets**:
- Phase 1: 10 concurrent queries
- Phase 2: 50 concurrent queries
- Phase 3: 100+ concurrent queries

### 12.2 Optimization Strategies

**Caching**:
```python
# Redis caching layers
1. Query result cache (TTL: 24 hours)
   - Key: hash(query + options)
   - Value: Result JSON

2. Tool output cache (TTL: 7 days)
   - Key: hash(tool_name + params)
   - Value: Tool output

3. BioBTree query cache (TTL: 30 days)
   - Key: hash(biobtree_query)
   - Value: BioBTree response

4. Embedding cache (TTL: permanent)
   - Key: hash(text)
   - Value: Embedding vector
```

**Parallel Execution**:
```python
# Execute independent steps in parallel
async def execute_plan(plan):
    for level in plan.dependency_levels:
        # All steps in a level have no dependencies
        results = await asyncio.gather(
            *[execute_step(step) for step in level]
        )
```

**Database Optimization**:
- BioBTree: LMDB tuning (cache size, page size)
- Qdrant: HNSW parameter tuning (M, ef_construct)
- Redis: Connection pooling, pipeline commands

**LLM Cost Optimization**:
- Use smaller models for simple tasks (Haiku vs Sonnet)
- Prompt caching (Anthropic)
- Batch API requests where possible
- Local LLMs for classification/routing

### 12.3 Scalability Considerations

**Horizontal Scaling**:
- Stateless agent system (can run multiple instances)
- Load balancer distributes requests
- Shared Redis for coordination

**Vertical Scaling**:
- Qdrant can scale to billions of vectors
- BioBTree handles millions of entries efficiently
- Redis clustering for larger cache

**Resource Allocation**:
```
Agent System:
  - CPU: 4-8 cores
  - RAM: 16-32 GB
  - Disk: 50 GB (logs, temp)

BioBTree:
  - CPU: 8-16 cores
  - RAM: 64-128 GB (LMDB cache)
  - Disk: 500 GB (database)

Qdrant:
  - CPU: 8-16 cores
  - RAM: 128-256 GB (vector cache)
  - Disk: 2-4 TB SSD (vectors)

Redis:
  - CPU: 2-4 cores
  - RAM: 32-64 GB
  - Disk: 50 GB
```

---

## 13. Testing Strategy

### 13.1 Unit Tests

**Coverage Target**: >80%

**Test Files**:
```
tests/
├── test_gateway/
│   ├── test_entity_detector.py
│   ├── test_intent_classifier.py
│   └── test_query_gateway.py
├── test_agents/
│   ├── test_planner_agent.py
│   ├── test_drug_discovery_agent.py
│   ├── test_variant_analysis_agent.py
│   └── test_protein_analysis_agent.py
├── test_tools/
│   ├── test_biobtree_tools.py
│   ├── test_bioyoda_tools.py
│   └── test_tool_executor.py
├── test_llm/
│   ├── test_anthropic_provider.py
│   ├── test_openai_provider.py
│   └── test_gemini_provider.py
└── test_integrations/
    ├── test_biobtree_client.py
    └── test_bioyoda_client.py
```

**Example Test**:
```python
@pytest.mark.asyncio
async def test_gene_to_protein_tool():
    client = Mock BioBTreeClient()
    tool = GeneToProteinTool(client)

    result = await tool.execute(genes=["BRCA1"], reviewed_only=True)

    assert len(result) > 0
    assert result[0]["uniprot_id"] == "P38398"
    assert result[0]["gene"] == "BRCA1"
```

### 13.2 Integration Tests

**Test Suites**:
```python
# Drug Discovery Agent
test_drug_discovery_integration():
    - test_find_drugs_for_gene()
    - test_compound_similarity()
    - test_clinical_trials_search()
    - test_pathway_analysis()

# Variant Analysis Agent
test_variant_analysis_integration():
    - test_snp_to_gene()
    - test_gwas_associations()
    - test_clinvar_pathogenicity()
    - test_phenotype_mapping()

# Protein Analysis Agent
test_protein_analysis_integration():
    - test_esm2_similarity()
    - test_protein_interactions()
    - test_expression_patterns()
    - test_go_enrichment()
```

### 13.3 End-to-End Tests

**Gold Standard Queries** (50+ biological questions with expected answers):

```python
E2E_QUERIES = [
    {
        "query": "Find drugs targeting EGFR",
        "expected_results": {
            "contains_compound": "CHEMBL6939",  # Gefitinib
            "source_database": "ChEMBL",
            "min_results": 10
        }
    },
    {
        "query": "What diseases are associated with rs429358?",
        "expected_results": {
            "contains_disease": "Alzheimer",
            "source_database": "GWAS Catalog",
            "min_pvalue": 1e-50
        }
    },
    {
        "query": "Find proteins similar to TP53 that interact with it",
        "expected_results": {
            "contains_protein": "Q16637",  # TP63
            "source_database": "IntAct",
            "min_results": 5
        }
    },
    # ... 47 more queries
]
```

### 13.4 Performance Tests

**Load Testing**:
```python
# locust test script
class AgentSystemUser(HttpUser):
    wait_time = between(1, 5)

    @task
    def query_drug_discovery(self):
        self.client.post("/api/v1/query", json={
            "query": "Find drugs targeting EGFR"
        })
```

**Benchmarks**:
- Measure latency at 1, 10, 50, 100 concurrent users
- Measure throughput (queries/second)
- Monitor resource usage (CPU, RAM, network)

### 13.5 LLM Evaluation

**Metrics**:
- **Accuracy**: % queries with correct answers
- **Hallucination Rate**: % false statements
- **Citation Quality**: % properly cited facts
- **Completeness**: % queries fully answered

**Evaluation Dataset**:
- 100 biological questions with expert-verified answers
- Automated scoring + human review

---

## 14. Monitoring & Observability

### 14.1 Logging

**Structured Logging** (JSON format):
```json
{
    "timestamp": "2025-11-19T10:30:00.123Z",
    "level": "INFO",
    "service": "agent_system",
    "component": "drug_discovery_agent",
    "query_id": "uuid",
    "session_id": "uuid",
    "message": "Executing step 1: gene_to_protein",
    "metadata": {
        "gene": "EGFR",
        "execution_time_ms": 234
    }
}
```

**Log Levels**:
- ERROR: Failures, exceptions
- WARN: Retries, fallbacks
- INFO: Query start/end, major steps
- DEBUG: Detailed tool execution (dev only)

### 14.2 Metrics

**Prometheus Metrics**:
```python
# Request metrics
agent_system_requests_total{agent="drug_discovery", status="success"}
agent_system_request_duration_seconds{agent="drug_discovery", quantile="0.95"}

# Tool metrics
tool_execution_total{tool="gene_to_protein", status="success"}
tool_execution_duration_seconds{tool="gene_to_protein"}

# LLM metrics
llm_requests_total{provider="anthropic", model="claude-3-5-sonnet"}
llm_tokens_total{provider="anthropic", type="input"}
llm_cost_usd_total{provider="anthropic"}

# Cache metrics
cache_hit_rate{cache_type="query_results"}
cache_size_bytes{cache_type="query_results"}

# Database metrics
biobtree_queries_total{status="success"}
qdrant_searches_total{collection="pubmed_abstracts"}
```

### 14.3 Tracing

**OpenTelemetry Tracing**:
```
Trace: query_execution
  ├─ Span: query_gateway.process_query [2341ms]
  │   ├─ Span: entity_detector.detect [123ms]
  │   ├─ Span: intent_classifier.classify [234ms]
  │   └─ Span: agent_registry.get_agent [5ms]
  │
  ├─ Span: planner_agent.query [1890ms]
  │   ├─ Span: planner._create_plan [567ms]
  │   │   └─ Span: llm.generate [543ms]
  │   │
  │   └─ Span: execution_engine.execute [1234ms]
  │       ├─ Span: tool.gene_to_protein [345ms]
  │       │   └─ Span: biobtree_client.map_query [321ms]
  │       │
  │       ├─ Span: tool.protein_to_target [456ms]
  │       └─ Span: tool.target_to_compounds [433ms]
  │
  └─ Span: planner._synthesize_answer [567ms]
      └─ Span: llm.generate [543ms]
```

### 14.4 Alerting

**Alert Rules**:
```yaml
groups:
  - name: agent_system
    rules:
      - alert: HighErrorRate
        expr: rate(agent_system_requests_total{status="error"}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate in agent system"

      - alert: HighLatency
        expr: histogram_quantile(0.95, agent_system_request_duration_seconds) > 30
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "95th percentile latency > 30s"

      - alert: LLMCostSpike
        expr: rate(llm_cost_usd_total[1h]) > 100
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "LLM costs > $100/hour"
```

---

## 15. Development Roadmap

### Phase 1: Foundation (Weeks 1-3)

**Milestone 1.1: Core Infrastructure**
- [ ] Project structure setup
- [ ] BioBTree Python client
- [ ] Enhanced BioYoda client
- [ ] Multi-provider LLM framework
- [ ] Configuration management

**Milestone 1.2: Gateway & Tools**
- [ ] Query gateway implementation
- [ ] Entity detector
- [ ] Intent classifier
- [ ] Tool abstraction layer
- [ ] Basic tool set (10+ tools)

**Milestone 1.3: Orchestration**
- [ ] Planner agent (basic)
- [ ] Agent registry
- [ ] Execution engine
- [ ] Context manager

**Deliverables**:
- Core framework code
- Unit tests (>70% coverage)
- Basic API endpoints
- Configuration files

### Phase 2: Initial Agents (Weeks 4-6)

**Milestone 2.1: Drug Discovery Agent**
- [ ] Agent implementation
- [ ] Tool definitions (target finding, compound search, etc.)
- [ ] Integration with BioBTree & BioYoda
- [ ] Prompt engineering

**Milestone 2.2: Variant & Protein Agents**
- [ ] Variant Analysis Agent
- [ ] Protein Analysis Agent
- [ ] Shared tool library
- [ ] Agent-specific prompts

**Milestone 2.3: Testing & Validation**
- [ ] Integration tests (20+ queries per agent)
- [ ] End-to-end tests (10 gold standard queries)
- [ ] Performance benchmarks
- [ ] Documentation

**Deliverables**:
- 3 working specialized agents
- 50+ tool implementations
- Test suites
- API documentation

### Phase 3: Advanced Features (Weeks 7-9)

**Milestone 3.1: Enhanced Orchestration**
- [ ] Advanced planner (DAG execution, dependencies)
- [ ] Parallel step execution
- [ ] Error handling & retries
- [ ] Result aggregation improvements

**Milestone 3.2: Multi-Turn Conversations**
- [ ] Session management
- [ ] Context retention
- [ ] Follow-up handling
- [ ] Clarification requests

**Milestone 3.3: Hybrid Search**
- [ ] Semantic + keyword search
- [ ] Result ranking fusion
- [ ] Citation validation

**Deliverables**:
- Improved orchestration
- Session support
- Enhanced search capabilities

### Phase 4: Standalone Apps (Weeks 10-12)

**Milestone 4.1: DrugDiscoveryGPT**
- [ ] Standalone API
- [ ] Web UI (Streamlit/Gradio)
- [ ] Specialized features (SAR analysis, etc.)
- [ ] Deployment scripts

**Milestone 4.2: VariantExplorer**
- [ ] Standalone API
- [ ] VCF upload support
- [ ] Annotation table UI
- [ ] Deployment

**Milestone 4.3: Inter-Agent Communication**
- [ ] Service registry
- [ ] REST-based communication
- [ ] Message queue (optional)

**Deliverables**:
- 2-3 standalone applications
- UIs for each app
- Docker containers
- Deployment documentation

### Phase 5: Unified System (Weeks 13-16)

**Milestone 5.1: Central Orchestrator**
- [ ] Unified API gateway
- [ ] Agent hub
- [ ] Load balancing
- [ ] Monitoring integration

**Milestone 5.2: Web Interface**
- [ ] React/Vue frontend
- [ ] Chat interface
- [ ] Execution viewer
- [ ] Result explorer

**Milestone 5.3: Production Readiness**
- [ ] Performance tuning
- [ ] Security hardening
- [ ] Comprehensive testing
- [ ] Documentation finalization

**Deliverables**:
- Production-ready unified system
- Web UI
- Deployment configurations
- Complete documentation

### Phase 6: Polish & Scale (Weeks 17-18)

**Milestone 6.1: Optimization**
- [ ] Performance profiling
- [ ] Cost optimization
- [ ] Cache tuning
- [ ] Database optimization

**Milestone 6.2: Additional Agents**
- [ ] Literature Research Agent
- [ ] Pathway Analysis Agent
- [ ] 2-3 more specialized agents

**Milestone 6.3: Advanced Features**
- [ ] Export & integration (Jupyter, PDF reports)
- [ ] Python SDK
- [ ] CLI improvements
- [ ] Admin dashboard

**Deliverables**:
- Optimized system
- Additional agents
- SDK & CLI
- Production deployment

---

## 16. Appendices

### Appendix A: Technology Stack Summary

**Backend**:
- Python 3.10+
- FastAPI (web framework)
- Pydantic (data validation)
- grpcio (gRPC client/server)
- httpx (async HTTP for REST endpoints)
- qdrant-client (vector DB)

**Agent Framework**:
- LangChain / LangGraph (agent orchestration)
- OR custom framework

**LLM Providers**:
- Anthropic Claude API
- OpenAI GPT API
- Google Gemini API
- (Future: vLLM for local models)

**Databases**:
- BioBTree (LMDB/MDBX)
- Qdrant (vector database)
- Redis (caching, sessions)

**Monitoring**:
- Prometheus (metrics)
- Grafana (dashboards)
- OpenTelemetry (tracing)
- Structured logging (JSON)

**Deployment**:
- Docker / Docker Compose
- Singularity (HPC)
- Kubernetes (optional, cloud)

**Frontend** (optional):
- React or Vue.js
- Streamlit/Gradio (for standalone apps)

### Appendix B: File Structure

```
bioyoda_dev2/
├── config/                         # ← ALL configs centralized here
│   ├── bioyoda.yaml               # Existing - BioYoda data processing
│   ├── biobtree.yaml              # Existing - BioBTree database
│   ├── qdrant.yaml                # Existing - Qdrant vector DB
│   ├── agent_system.yaml          # NEW - Agent system configuration
│   └── api_config.yaml            # NEW - API auth, rate limits, tiers
│
├── modules/
│   └── agent_system/
│       ├── __init__.py
│       ├── gateway/
│       │   ├── query_gateway.py
│       │   ├── entity_detector.py
│       │   └── intent_classifier.py
│       ├── orchestration/
│       │   ├── planner_agent.py
│       │   ├── agent_registry.py
│       │   ├── execution_engine.py
│       │   └── context_manager.py
│       ├── agents/
│       │   ├── base.py
│       │   ├── drug_discovery/
│       │   │   ├── agent.py
│       │   │   ├── tools.py
│       │   │   └── prompts.py
│       │   ├── variant_analysis/
│       │   │   ├── agent.py
│       │   │   ├── tools.py
│       │   │   └── prompts.py
│       │   └── protein_analysis/
│       │       ├── agent.py
│       │       ├── tools.py
│       │       └── prompts.py
│       ├── tools/
│       │   ├── base.py
│       │   ├── biobtree/
│       │   │   ├── gene_to_protein.py
│       │   │   ├── protein_to_target.py
│       │   │   └── ... (30+ tools)
│       │   └── bioyoda/
│       │       ├── semantic_search.py
│       │       ├── chemical_similarity.py
│       │       └── ... (10+ tools)
│       ├── integrations/
│       │   ├── biobtree_client.py
│       │   └── bioyoda_client.py
│       ├── llm/
│       │   ├── base.py
│       │   ├── anthropic_provider.py
│       │   ├── openai_provider.py
│       │   └── gemini_provider.py
│       ├── api/
│       │   ├── main.py
│       │   ├── routes/
│       │   │   ├── query.py
│       │   │   ├── agents.py
│       │   │   └── sessions.py
│       │   └── models.py
│       ├── tests/
│       │   ├── test_gateway/
│       │   ├── test_agents/
│       │   ├── test_tools/
│       │   └── test_integration/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── README.md
│
├── standalone_apps/
│   ├── drug_discovery_gpt/
│   │   ├── api/
│   │   ├── ui/
│   │   ├── Dockerfile
│   │   └── README.md
│   └── variant_explorer/
│       ├── api/
│       ├── ui/
│       ├── Dockerfile
│       └── README.md
│
├── bioyoda_rag_system/
│   ├── web_ui/
│   │   ├── src/
│   │   ├── public/
│   │   └── package.json
│   ├── api/
│   └── docker-compose.yml
│
├── docs/
│   ├── AGENT_SYSTEM_ARCHITECTURE.md (this document)
│   ├── AGENT_DEVELOPMENT_GUIDE.md
│   ├── API_DOCUMENTATION.md
│   ├── DEPLOYMENT_GUIDE.md
│   └── USER_MANUAL.md
│
└── docker-compose.yml
```

### Appendix C: Configuration Examples

**File Location**: `config/agent_system.yaml`
```yaml
system:
  name: "BioYoda Multi-Agent RAG System"
  version: "1.0.0"
  debug: false

gateway:
  max_query_length: 1000
  session_timeout_hours: 24

integrations:
  biobtree:
    protocol: "grpc"  # "grpc" (default) or "rest"
    grpc:
      host: "localhost"
      port: 7777
    rest:  # Optional fallback
      host: "localhost"
      port: 9292
    timeout_seconds: 30
    retry_attempts: 3
    max_connections: 50

  qdrant:
    url: "http://localhost:6333"
    timeout_seconds: 10

  redis:
    url: "redis://localhost:6379"
    cache_ttl_hours: 24

llm:
  default_provider: "anthropic"

  providers:
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"
      max_tokens: 4000
      temperature: 0.7

    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4-turbo"
      max_tokens: 4000
      temperature: 0.7

    gemini:
      api_key: "${GOOGLE_API_KEY}"
      model: "gemini-1.5-pro"
      max_tokens: 4000
      temperature: 0.7

agents:
  planner:
    enabled: true
    llm_provider: "anthropic"

  drug_discovery:
    enabled: true
    llm_provider: "anthropic"
    tools:
      - gene_to_protein
      - protein_to_target
      - target_to_compounds
      - chemical_similarity
      - pubmed_search
      - trial_search

  variant_analysis:
    enabled: true
    llm_provider: "anthropic"
    tools:
      - snp_to_gene
      - snp_to_gwas
      - snp_to_clinvar
      - clinvar_to_phenotype

  protein_analysis:
    enabled: true
    llm_provider: "anthropic"
    tools:
      - esm2_similarity
      - protein_interactions
      - protein_expression
      - protein_to_go

monitoring:
  prometheus:
    enabled: true
    port: 9090

  logging:
    level: "INFO"
    format: "json"
    file: "/var/log/agent_system/agent.log"

performance:
  max_concurrent_queries: 10
  tool_execution_timeout_seconds: 60
  llm_request_timeout_seconds: 120
  cache_enabled: true
```

### Appendix D: Glossary

**Agent**: Autonomous component that can reason and use tools to accomplish tasks

**BioBTree**: Graph-based identifier mapping system with B+ tree database

**BioYoda**: Semantic search system with vector database backend

**Chain Query**: BioBTree query syntax using `>>` for multi-hop navigation

**Embedding**: Vector representation of text or molecules

**Entity**: Biological identifier (gene, protein, compound, SNP, etc.)

**Intent**: User's goal (drug discovery, variant analysis, etc.)

**LLM**: Large Language Model (Claude, GPT, Gemini)

**Orchestration**: Coordination of multiple agents/tools to execute complex queries

**Planner**: Agent that decomposes queries into execution plans

**RAG**: Retrieval Augmented Generation (semantic search + LLM)

**Tool**: Function that agents can call (database query, search, etc.)

**Vector Database**: Database optimized for similarity search (Qdrant)

---

**Document End**

This architecture design document will be updated as the system evolves. For questions or suggestions, please contact the development team.

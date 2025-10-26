# STRING Database Data Structure Analysis

**Analysis Date**: 2025-10-24
**STRING Version**: 12.0
**Organism**: Human (Taxonomy ID: 9606)
**Analysis Location**: `/data/scc/ag-gruber/GROUP/tgur/x/bioyoda_dev2/analysis/string_raw/`

## Executive Summary

STRING database provides protein-protein interaction data in a relational format with three main files:
1. **Protein Links** - The core interaction data (space-separated)
2. **Protein Aliases** - Identifier mappings to external databases (tab-separated)
3. **Protein Info** - Protein metadata and annotations (tab-separated)

**Key Statistics for Human (9606)**:
- **Proteins**: 19,699 unique proteins
- **Interactions**: 13,715,404 protein-protein links
- **Average score**: 268.6 (out of 1000)
- **UniProt mappings**: 88,155 mappings
- **HGNC mappings**: 19,203 mappings

## File 1: Protein Links (`9606.protein.links.v12.0.txt`)

### Format
- **Size**: 602 MB uncompressed
- **Format**: Space-separated values (NOT tab-separated!)
- **Encoding**: Plain text
- **Lines**: 13,715,405 (including header)

### Schema
```
protein1 protein2 combined_score
```

### Column Descriptions

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| protein1 | String | STRING protein ID (format: taxid.ENSP_ID) | `9606.ENSP00000000233` |
| protein2 | String | STRING protein ID (format: taxid.ENSP_ID) | `9606.ENSP00000356607` |
| combined_score | Integer | Confidence score (0-999) | `173` |

### Sample Data
```
protein1 protein2 combined_score
9606.ENSP00000000233 9606.ENSP00000356607 173
9606.ENSP00000000233 9606.ENSP00000427567 154
9606.ENSP00000000233 9606.ENSP00000253413 151
9606.ENSP00000000233 9606.ENSP00000493357 471
9606.ENSP00000000233 9606.ENSP00000324127 201
```

### Identifier Format
**Pattern**: `{taxonomy_id}.{ensembl_protein_id}`
- Taxonomy ID: Species identifier (9606 = Homo sapiens)
- Ensembl Protein ID: ENSP followed by 11 digits
- **Note**: These are STRING's internal identifiers based on Ensembl

### Score Distribution Analysis

**Total Interactions**: 13,715,404

| Confidence Level | Score Range | Count | Percentage |
|-----------------|-------------|--------|------------|
| High | ≥ 700 | 473,860 | 3.5% |
| Medium | 400-699 | 1,385,084 | 10.1% |
| Low | 150-399 | 11,856,460 | 86.4% |

**Average Score**: 268.6

**Score Distribution (Top)**:
- 999: 28,284 interactions (highest confidence)
- 998: 6,214 interactions
- 997: 4,318 interactions
- Very few interactions have scores > 700

**Observations**:
- Most interactions (86.4%) are low confidence (150-399)
- Only 3.5% are high confidence (≥700)
- Filtering at score ≥ 400 reduces dataset to ~14% of original
- Filtering at score ≥ 700 reduces dataset to ~3.5% of original

### Directionality
- Interactions appear to be **unidirectional** in the file
- Each pair (A,B) appears only once (not both A-B and B-A)
- For biobtree integration, we may need to create bidirectional xrefs

### Example: EGFR Protein
- **STRING ID**: `9606.ENSP00000275493`
- **UniProt AC**: P00533
- **Gene Symbol**: EGFR
- **Total Interactions**: 11,640
- **Sample Interactions**:
  - Score 640: `9606.ENSP00000011653` (high confidence partner)
  - Score 524: `9606.ENSP00000005257` (medium-high confidence)
  - Score 436: `9606.ENSP00000009530` (medium confidence)
  - Score 188: `9606.ENSP00000000233` (low confidence)

## File 2: Protein Aliases (`9606.protein.aliases.v12.0.txt`)

### Format
- **Size**: 191 MB uncompressed
- **Format**: Tab-separated values
- **Encoding**: Plain text
- **Lines**: 3,889,208 (including header)

### Schema
```
#string_protein_id	alias	source
```

### Column Descriptions

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| string_protein_id | String | STRING protein ID | `9606.ENSP00000000233` |
| alias | String | External identifier or name | `P84085` |
| source | String | Database/source of the alias | `UniProt_AC` |

### Sample Data
```
#string_protein_id	alias	source
9606.ENSP00000000233	2B6H	Ensembl_PDB
9606.ENSP00000000233	2B6H	UniProt_DR_PDB
9606.ENSP00000000233	381	Ensembl_HGNC_entrez_id
9606.ENSP00000000233	P84085	UniProt_AC
9606.ENSP00000000233	ARF5	Ensembl_HGNC_symbol
9606.ENSP00000000233	ARF5	Ensembl_UniProt
9606.ENSP00000000233	ARF5	UniProt_GN_Name
```

### Key Source Types for Biobtree Integration

| Source | Count (Human) | Description | Priority |
|--------|---------------|-------------|----------|
| UniProt_AC | 88,155 | UniProt accession (PRIMARY KEY!) | ⭐⭐⭐ |
| Ensembl_HGNC_symbol | 19,203 | HGNC gene symbols | ⭐⭐⭐ |
| UniProt_GN_Name | 19,699 | Gene names from UniProt | ⭐⭐ |
| Ensembl_UniProt | Many | UniProt IDs from Ensembl | ⭐⭐ |
| Ensembl_HGNC_entrez_id | ~19K | Entrez Gene IDs | ⭐ |
| KEGG_NAME | Variable | KEGG gene names | ⭐ |
| UniProt_DR_PDB | Many | PDB structure IDs | ⭐ |

### Mapping Strategy Insights

**For one STRING protein, we can have multiple aliases:**
- Example: `9606.ENSP00000000233` (ARF5 protein)
  - UniProt_AC: P84085, P26437, C9J1Z8, A4D0Z3
  - Gene symbols: ARF5
  - Entrez ID: 381
  - PDB structures: 2B6H
  - Protein names: "ADP-ribosylation factor 5"

**Multiple UniProt entries per STRING protein**:
- Some STRING proteins map to multiple UniProt accessions (isoforms, obsolete IDs)
- Need to decide: use primary UniProt_AC or all?

**Coverage**:
- 19,699 STRING proteins
- 88,155 UniProt_AC mappings (~4.5 average per protein!)
- Most proteins have 1-3 UniProt mappings
- Some have many (isoforms, obsolete IDs)

### Example: ARF5 Protein Aliases
```
STRING ID: 9606.ENSP00000000233
├── UniProt_AC: P84085 (primary)
├── UniProt_AC: P26437 (secondary)
├── UniProt_AC: C9J1Z8 (isoform?)
├── UniProt_AC: A4D0Z3 (isoform?)
├── Gene Symbol: ARF5
├── HGNC ID: HGNC:381
├── Entrez ID: 381
├── PDB: 2B6H
└── Description: "ADP-ribosylation factor 5"
```

## File 3: Protein Info (`9606.protein.info.v12.0.txt`)

### Format
- **Size**: 6.0 MB uncompressed
- **Format**: Tab-separated values
- **Encoding**: Plain text
- **Lines**: 19,700 (including header)

### Schema
```
#string_protein_id	preferred_name	protein_size	annotation
```

### Column Descriptions

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| string_protein_id | String | STRING protein ID | `9606.ENSP00000000233` |
| preferred_name | String | Preferred gene/protein name | `ARF5` |
| protein_size | Integer | Amino acid length | `180` |
| annotation | String | Functional annotation (long text) | "ADP-ribosylation factor 5; GTP-binding protein..." |

### Sample Data
```
#string_protein_id	preferred_name	protein_size	annotation
9606.ENSP00000000233	ARF5	180	ADP-ribosylation factor 5; GTP-binding protein involved in protein trafficking...
9606.ENSP00000000412	M6PR	277	Cation-dependent mannose-6-phosphate receptor; Transport of phosphorylated lysosomal enzymes...
9606.ENSP00000275493	EGFR	1210	Epidermal growth factor receptor; Receptor tyrosine kinase binding ligands...
```

### Observations
- **preferred_name**: Usually the gene symbol (ARF5, EGFR, etc.)
- **protein_size**: Useful for validation
- **annotation**: Rich functional description (often truncated with "[...]")
- Annotations are very detailed and valuable for display

## Relational Structure

### How Files Connect

```
┌─────────────────────────────────────────────────────────────────┐
│                    STRING Protein (Core Entity)                  │
│                  ID: 9606.ENSP00000000233                        │
└────────────┬────────────────────────────────────┬────────────────┘
             │                                    │
             │                                    │
     ┌───────▼──────────┐                ┌───────▼──────────┐
     │  Protein Info    │                │  Protein Aliases │
     │  (Metadata)      │                │  (Mappings)      │
     ├──────────────────┤                ├──────────────────┤
     │ preferred_name   │                │ P84085 (UniProt) │
     │ protein_size     │                │ ARF5 (HGNC)      │
     │ annotation       │                │ 381 (Entrez)     │
     └──────────────────┘                │ 2B6H (PDB)       │
                                         └──────────────────┘
             │
             │
     ┌───────▼──────────────────────────────────────────┐
     │         Protein Links (Interactions)              │
     │                                                   │
     │  9606.ENSP00000000233 ←→ 9606.ENSP00000356607   │
     │         (score: 173)                             │
     │                                                   │
     │  9606.ENSP00000000233 ←→ 9606.ENSP00000493357   │
     │         (score: 471)                             │
     │                                                   │
     │  ... 13.7M total interactions ...                │
     └───────────────────────────────────────────────────┘
```

### Key Relationships

1. **STRING ID → Metadata** (1:1)
   - Each STRING protein has ONE entry in protein.info
   - Provides preferred name, size, annotation

2. **STRING ID → Aliases** (1:N)
   - Each STRING protein has MANY aliases (avg ~200 per protein!)
   - Multiple mappings to same external database (e.g., multiple UniProt ACs)

3. **STRING ID → Interactions** (1:N)
   - Each STRING protein has MANY interaction partners
   - Human average: ~1,400 interactions per protein (13.7M / 19.7K)
   - But highly variable: some have 10, others have 11,000+ (like EGFR)

## Biobtree Adaptation Strategy

### Challenge: Relational Data → Graph/Key-Value Model

STRING data is inherently **relational**:
- Proteins (entities) with attributes
- Aliases (mappings) to external databases
- Interactions (edges) between proteins

Biobtree uses a **graph/key-value** model:
- Identifiers as keys
- Attributes stored per identifier
- Cross-references (xrefs) between identifiers

### Proposed Adaptation Approach

#### Option 1: Use UniProt as Primary Key (RECOMMENDED)
```
UniProt Accession (P84085)
├── STRING attributes stored here
│   ├── STRING_ID: 9606.ENSP00000000233
│   ├── preferred_name: ARF5
│   ├── protein_size: 180
│   ├── annotation: "..."
│   └── interactions: [list of partner UniProt IDs with scores]
└── Cross-references
    ├── STRING → 9606.ENSP00000000233
    └── Interaction xrefs → Partner UniProt IDs
```

**Pros**:
- UniProt already integrated in biobtree
- Users query by UniProt ID
- Natural fit with existing data model

**Cons**:
- Need to handle multiple UniProt ACs per STRING protein
- Some STRING proteins may lack UniProt mapping

#### Option 2: Use STRING ID as Primary Key
```
STRING ID (9606.ENSP00000000233)
├── Attributes
│   ├── preferred_name: ARF5
│   ├── protein_size: 180
│   └── annotation: "..."
├── Cross-references
│   ├── UniProt → P84085
│   ├── HGNC → ARF5
│   └── Interaction xrefs → Partner STRING IDs
└── Interactions stored as attributes
```

**Pros**:
- Direct representation of STRING data
- No ambiguity with multiple UniProt mappings
- Easier to process

**Cons**:
- Users need to map HGNC/UniProt → STRING ID first
- Adds new identifier type to biobtree
- More complex query chains

#### Option 3: Hybrid Approach (BEST FOR BIOBTREE!)
```
1. Store on UniProt entries:
   UniProt (P84085)
   └── attributes: STRING metadata
   └── xrefs: Interaction partners as UniProt IDs

2. Create text search links:
   "ARF5" (gene name) → P84085 (UniProt)
   "9606.ENSP00000000233" (STRING ID) → P84085 (UniProt)

3. Create bidirectional interaction xrefs:
   P84085 (UniProt_A) → Q12345 (UniProt_B) [score: 471]
   Q12345 (UniProt_B) → P84085 (UniProt_A) [score: 471]
```

**Pros**:
- Leverages existing UniProt infrastructure
- Searchable by gene name, STRING ID, or UniProt ID
- Bidirectional queries work naturally

**Cons**:
- Need to handle proteins without UniProt mapping
- Multiple UniProt IDs per STRING protein creates duplicates

### Recommended Implementation Strategy

**Phase 1: UniProt-Centric Storage**
1. Parse `protein.aliases.txt` to build STRING_ID → UniProt_AC mapping
2. For each UniProt entry in biobtree:
   - Add STRING_ID as attribute
   - Add preferred_name, protein_size, annotation as attributes
   - Store interaction partners as list with scores

**Phase 2: Create Cross-References**
3. For each interaction in `protein.links.txt`:
   - Map STRING_IDs to UniProt_ACs
   - Create xref: UniProt_A ↔ UniProt_B (bidirectional)
   - Store score as xref attribute

**Phase 3: Search Enhancement**
4. Create text-based search links:
   - preferred_name → UniProt_AC
   - STRING_ID → UniProt_AC

### Handling Edge Cases

**Case 1: STRING protein with multiple UniProt ACs**
- **Solution**: Pick primary UniProt_AC (first in aliases file?)
- **Alternative**: Store on ALL UniProt entries (creates redundancy)

**Case 2: STRING protein without UniProt mapping**
- **Solution**: Create STRING-specific entry
- **Identifier**: Use STRING_ID as fallback
- **Count**: Likely < 1% of proteins

**Case 3: Interaction partners without UniProt mapping**
- **Solution**: Skip interaction or store STRING_ID directly
- **Impact**: Minimal (most proteins have UniProt)

## Score Filtering Recommendations

Based on distribution analysis:

### Conservative (High Quality, Low Coverage)
- **Threshold**: ≥ 700
- **Interactions**: 473,860 (3.5% of total)
- **Use case**: High-confidence networks only
- **Avg interactions/protein**: ~24 per protein

### Balanced (RECOMMENDED)
- **Threshold**: ≥ 400
- **Interactions**: 1,858,944 (13.6% of total)
- **Use case**: Medium+ confidence
- **Avg interactions/protein**: ~94 per protein

### Comprehensive (High Coverage, More Noise)
- **Threshold**: ≥ 150
- **Interactions**: 13,715,404 (100% of dataset)
- **Use case**: Exploratory analysis
- **Avg interactions/protein**: ~696 per protein

**Recommendation**: Start with ≥ 400 for balanced quality/coverage

## Data Processing Estimates

### For Test Dataset (Score ≥ 400)
- **Proteins**: ~19,700
- **Interactions**: ~1.86M
- **Estimated size**: ~50 MB
- **Processing time**: ~5-10 minutes

### For Full Dataset (Score ≥ 150)
- **Proteins**: 19,700
- **Interactions**: 13.7M
- **Estimated size**: ~400 MB
- **Processing time**: ~30-60 minutes

## Key Insights for Implementation

### 1. Identifier Mapping is Critical
- Must build robust STRING_ID → UniProt_AC mapping
- Handle multiple UniProt IDs per STRING protein
- ~88K mappings for 19.7K proteins (avg 4.5 per protein)

### 2. Score Thresholds Matter
- Default to ≥ 400 for quality
- Make configurable in `conf/source.dataset.json`
- Document threshold choice clearly

### 3. Bidirectionality
- STRING file has A→B only once
- Biobtree needs both A→B and B→A for queries
- Must create symmetric xrefs

### 4. File Format Inconsistency
- **protein.links**: SPACE-separated (not tab!)
- **protein.aliases**: Tab-separated
- **protein.info**: Tab-separated
- Code must handle both delimiters

### 5. Memory Considerations
- 19.7K proteins manageable in memory
- 13.7M interactions may need streaming
- Aliases file (3.9M lines) should stream

## Next Steps

1. **Create Test Dataset** (`test_data/string/`)
   - Select ~500 well-known proteins (EGFR, BRCA1, TP53, etc.)
   - Extract their interactions (filtered ≥ 400)
   - Include all aliases for mapping
   - ~5K interactions, ~500 proteins, < 5 MB

2. **Implement STRING Processor** (`src/update/string.go`)
   - Follow `clinical_trials.go` pattern
   - Build STRING_ID → UniProt mapping
   - Process interactions with score filtering
   - Create bidirectional xrefs

3. **Define Configuration** (`conf/source.dataset.json`)
   - Add STRING dataset entry
   - Specify test data path
   - Set score threshold parameter

4. **Test Integration**
   - Build biobtree with test dataset
   - Verify cross-references work
   - Test query: `HGNC:EGFR >> uniprot >> string`
   - Benchmark performance

## Appendix: Useful Analysis Commands

```bash
# Count interactions per protein
awk '{print $1}' 9606.protein.links.v12.0.txt | sort | uniq -c | sort -rn | head -n 20

# Find high-confidence interactions
awk '$3 >= 700' 9606.protein.links.v12.0.txt | wc -l

# Map STRING ID to UniProt
grep "9606.ENSP00000275493" 9606.protein.aliases.v12.0.txt | grep "UniProt_AC"

# Find protein by gene name
grep -i "EGFR" 9606.protein.aliases.v12.0.txt | grep "Ensembl_HGNC_symbol"

# Get protein metadata
grep "9606.ENSP00000275493" 9606.protein.info.v12.0.txt
```

---

**Document Status**: Complete ✅
**Next Phase**: Design Adaptation Strategy & Create Test Dataset

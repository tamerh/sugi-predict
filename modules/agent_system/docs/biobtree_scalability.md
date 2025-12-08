# BioBTree Filtering Scalability Assessment

**Date:** 2024-12-08
**Context:** Evaluating BioBTree's ability to handle multi-agent workloads with filtering

## Architecture Analysis

### How BioBTree Filtering Works

BioBTree uses Google's CEL (Common Expression Language) for filtering via `github.com/google/cel-go`.

**Filter Execution Flow** (from `src/service/mapfilter.go`):

```
For each entry in chain:
  1. Lookup entry from LMDB database (s.getLmdbResult2)
  2. If filter exists:
     a. Check filter cache first (cacheKey = f_ + id + dataset + filter)
     b. If not cached: Parse → Check → Compile CEL program
     c. Evaluate CEL program against protobuf attributes
     d. Cache result
  3. Move to next entry
```

### Key Components

| Component | Operation | Complexity |
|-----------|-----------|------------|
| **CEL Compilation** | Parse → Check → Program | O(1) per unique filter (cached in query.Program) |
| **CEL Evaluation** | Eval() per entry | O(n) where n = entries to filter |
| **LMDB Lookups** | getLmdbResult2() | O(n) disk/memory reads |
| **Filter Cache** | filterResultCache | Helps with repeated queries |

## Performance Benchmarks

Measured on scc2 BioBTree server (2024-12-08), fresh cache:

| Query Type | Response Time | Notes |
|------------|---------------|-------|
| No filter | 15-77ms | Fast |
| `pChembl>7.0` (on activity) | ~300ms | Moderate |
| `highestDevelopmentPhase>2` (on molecule) | ~22s | **SLOW** |
| Logical operators (`&&`, `\|\|`) | Same as underlying filter | Not the bottleneck |

## Why Phase Filters are Slow (~22s)

Example chain:
```
JAK2 >> ensembl >> uniprot >> chembl_target_component >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule[phase>2]
```

The filter is applied at the **last step** (`chembl_molecule`). This means:

1. All intermediate mappings must complete first
2. Each `chembl_molecule` entry requires:
   - LMDB lookup to get full protobuf
   - CEL evaluation of `highestDevelopmentPhase>2`
3. For JAK2, this might involve 1000s of molecules to evaluate

**pChembl filter is faster** because it's applied at `chembl_activity`, which filters early and reduces downstream entries.

## Scalability Concerns for Multi-Agent System

### Current Performance Estimates

| Metric | Current | Required for Production |
|--------|---------|------------------------|
| Requests/sec (simple) | ~50-100 | 1000+ |
| Requests/sec (filtered) | ~1-5 | 100+ |
| Concurrent agents | 1 | 10-50 |

### Bottlenecks for Scaling

1. **CEL Evaluation is Sequential**: Each entry evaluated one-by-one
2. **No Query-Level Parallelization**: `xrefMapping` is single-threaded
3. **Filter Position Matters**: Late filters = more work
4. **LMDB Read Contention**: Multiple readers OK, but high volume may bottleneck
5. **Memory**: Each CEL evaluation loads full protobuf into memory

## Recommendations

### Short-term (Agent System Design)

#### 1. Prefer Early Filters

Apply filters on `chembl_activity` not `chembl_molecule`:

```bash
# Fast (~300ms): filter early
activity[pChembl>7.0] >> molecule

# Slow (~22s): filter late
activity >> molecule[phase>2]
```

#### 2. Use Caching Strategically

Results are cached - repeated queries are fast. Design agents to:
- Use consistent query patterns
- Warm up cache with common queries on startup

#### 3. Batch Queries

Combine multiple genes into one query:

```bash
# Good: 1 request
EGFR,BRAF,JAK2 >> ensembl >> uniprot >> ...

# Bad: 3 separate requests
EGFR >> ensembl >> ...
BRAF >> ensembl >> ...
JAK2 >> ensembl >> ...
```

#### 4. Species Filtering (Use with Caution)

**Tested 2024-12-08**: Filtering by human species at the ensembl level improves slow phase filter performance.

| Query | Time | Improvement |
|-------|------|-------------|
| EGFR all species (baseline) | 39ms | - |
| EGFR human only | 12ms | 3x faster |
| EGFR all species + phase>2 | **10,508ms** | - |
| EGFR human only + phase>2 | **4,004ms** | **2.6x faster (62% reduction)** |

```bash
# Faster but may miss data: human only
GENE >> ensembl[ensembl.genome=="homo_sapiens"] >> uniprot >> ... >> molecule[phase>2]

# Slower but complete: all species
GENE >> ensembl >> uniprot >> ... >> molecule[phase>2]
```

**Why it helps**: Human-only filtering reduces ensembl mappings (e.g., 2→1 for EGFR), which means fewer downstream entries to evaluate with the slow phase filter.

**⚠️ CAUTION for Drug Discovery**: Many drugs are tested on mouse/rat models before human trials. Filtering to human-only may miss:
- Preclinical drug candidates with mouse assay data
- Compounds tested only in animal models so far
- Valuable structure-activity relationship (SAR) data from model organisms

**Recommendation**:
- **Drug discovery queries**: Keep all species (default) to get complete drug data
- **ID mapping queries**: Human-only filter is safe if user only needs human identifiers
- **User explicitly requests**: Apply species filter only when user asks for specific organism

#### 5. Avoid Complex Filters When Possible

Simple comparison filters may be faster:

```bash
# Prefer this (if semantically equivalent)
phase>2

# Over this
phase==3 || phase==4
```

### Long-term (BioBTree Improvements)

If scaling beyond current limits is needed:

1. **Pre-computed Indexes**: Index common filter fields (phase, pChembl) for O(1) lookup
2. **Parallel CEL Evaluation**: Process multiple entries concurrently using goroutines
3. **Query Optimization**: Push filters earlier in chain automatically
4. **Result Streaming**: Return partial results as they're computed
5. **Dedicated Filter Cache**: Separate cache for filter results with larger capacity

## Capacity Planning

### For 10-50 Agents (~100 req/sec total)

Current BioBTree should handle this if:
- Use early filters (activity not molecule)
- Leverage caching (repeated queries)
- Batch queries where possible
- Avoid phase filters in hot paths

### For 1000+ req/sec

Would require:
- BioBTree optimizations (parallel evaluation, pre-indexing)
- Caching layer in front (Redis/Memcached)
- Query result pre-computation for common patterns
- Horizontal scaling (multiple BioBTree instances)

## Potential Solution: LLM Post-Filtering

### The Idea

Instead of slow BioBTree filters, retrieve all results quickly and let the LLM filter them.

```
BioBTree Filter:  JAK2 >> ... >> molecule[phase>2]     → 22 seconds
LLM Post-Filter:  JAK2 >> ... >> molecule (no filter)  → 77ms + LLM ~2s = ~2s total
```

### Comparison

| Aspect | BioBTree Filter | LLM Post-Filter |
|--------|-----------------|-----------------|
| **Response Time** | 22s (slow filters) | ~77ms + LLM ~2s |
| **Data Transfer** | Less data (filtered) | More data (all results) |
| **LLM Token Usage** | Low | Higher (process all results) |
| **Flexibility** | Limited to indexed attributes | Can filter on anything |
| **Accuracy** | Exact (database level) | Depends on LLM parsing |
| **Cost** | Server CPU | LLM API cost |

### When to Use LLM Post-Filtering

**YES - Use LLM filtering when:**
- BioBTree filter is slow (phase filters ~22s)
- Complex logic not supported by CEL
- Small result sets (<200 items)
- Need flexible/fuzzy filtering ("most promising candidates")

**NO - Keep BioBTree filtering when:**
- Filter is fast (pChembl ~300ms)
- Large result sets (1000s of items)
- Exact numerical filtering needed
- Token cost is a concern

### Hybrid Approach (Recommended)

```python
# Strategy based on filter type
if filter_on_activity:  # pChembl, bao, etc.
    # Fast at BioBTree level (~300ms)
    chain = "gene >> ... >> activity[pChembl>7.0] >> molecule"

elif filter_on_molecule:  # phase, type - SLOW
    # Do at LLM level instead
    chain = "gene >> ... >> activity >> molecule"  # No filter
    # LLM filters the ~150 results

elif complex_filter:  # semantic, multi-criteria
    # Must do at LLM level
    chain = "gene >> ... >> molecule"
    # LLM applies complex logic
```

### Implementation Sketch

```python
class DrugDiscoveryAgent:
    async def process_query(self, query: str):
        if self._needs_slow_filter(query):
            # Get all results without filter
            results = await self.biobtree_query(chain_without_filter)
            # LLM filters in post-processing
            filtered = await self.llm_filter(results, user_criteria)
            return filtered
        else:
            # Use fast BioBTree filter directly
            return await self.biobtree_query(chain_with_filter)

    def _needs_slow_filter(self, query: str) -> bool:
        slow_keywords = ["approved", "phase", "clinical"]
        return any(kw in query.lower() for kw in slow_keywords)
```

### Trade-off Summary

| Filter Type | BioBTree Time | LLM Post-Filter Time | Recommendation |
|-------------|---------------|----------------------|----------------|
| pChembl > 7.0 | ~300ms | ~2s | Use BioBTree |
| phase > 2 | ~22s | ~2s | Use LLM |
| phase == 4 | ~30s+ (timeout) | ~2s | Use LLM |
| Complex logic | Not supported | ~2-3s | Use LLM |

## Conclusion

The phase filter slowness is not a CEL issue per se - it's the combination of:

1. **Late-stage filtering** - lots of entries to evaluate
2. **Sequential evaluation** - one entry at a time
3. **Large dataset** - chembl_molecule has many entries

**Key Insight**: Filter position in the chain matters more than filter complexity. Always filter as early as possible in the chain to minimize downstream processing.

## References

- CEL-Go: https://github.com/google/cel-go
- BioBTree source: `biobtreev2/src/service/mapfilter.go`
- Filter execution: `execCelGo()` function (lines 951-1091)

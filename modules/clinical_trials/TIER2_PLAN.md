# Tier 2 Features Implementation Plan

## Overview

Tier 2 features focus on **high-impact clinical data** with moderate implementation complexity:
1. **Publications/References** - Link trials to published literature (PMIDs)
2. **Adverse Events** - Safety data for risk assessment

## Coverage Analysis (400 Test Trials)

Based on analysis of test data:

| Feature | Coverage | Complexity | Priority |
|---------|----------|------------|----------|
| **Publications** | 39.2% (157/400 trials) | Low | **High** |
| **Adverse Events** | 11.2% (45/400 trials) | Moderate | Medium |

**Recommendation**: Start with **Publications** due to:
- ✓ Higher coverage (39.2% vs 11.2%)
- ✓ Simpler structure (one-to-many, flat)
- ✓ High value (links to PubMed for cross-referencing)
- ✓ Easy to integrate with existing PubMed module

## Feature 1: Publications/References

### Data Structure

**AACT Table**: `study_references.txt`

**Fields**:
```
- nct_id: Trial identifier
- pmid: PubMed ID (links to PubMed abstracts)
- reference_type: BACKGROUND, RESULT, DERIVED
- citation: Full citation text
```

**Reference Types**:
- `BACKGROUND`: Background/related studies
- `RESULT`: Published results from this trial
- `DERIVED`: Analysis derived from trial data

### Implementation Plan

**1. Extraction** (download_and_extract.py)
```python
# Process study references (one-to-many)
references_dict = {}
if include_publications:
    references = self.load_table('study_references')
    if references is not None:
        references = references[references['nct_id'].isin(kept_nct_ids)]
        for nct_id, group in references.groupby('nct_id'):
            references_dict[nct_id] = []
            for _, row in group.iterrows():
                pmid = str(row.get('pmid', ''))
                if pmid and pmid != 'nan':
                    references_dict[nct_id].append({
                        'pmid': pmid,
                        'reference_type': str(row.get('reference_type', '')),
                        'citation': str(row.get('citation', ''))
                    })
```

**Output Structure**:
```json
{
  "nct_id": "NCT12345678",
  "publications": [
    {
      "pmid": "25256621",
      "reference_type": "BACKGROUND",
      "citation": "Bingham J, Clarke H, et al. Clin Orthop Relat Res. 2014"
    },
    {
      "pmid": "697948",
      "reference_type": "RESULT",
      "citation": "Brook I, Reza MJ, et al. Arthritis Rheum. 1978"
    }
  ]
}
```

**2. Processing** (process_trials.py)
- Add `publications` to all metadata chunks
- No changes to text chunking (publications are metadata only)

**3. Query Capabilities**
- Filter by trials with published results
- Cross-reference with PubMed abstracts (future: join queries)
- Find trials with multiple publications
- Separate background vs result publications

**Example Queries**:
- "Which trials have published results?"
- "Find trials with publications in high-impact journals"
- "Show trials with results published in the last 5 years"

### Implementation Effort

**Complexity**: Low (similar to sponsors/facilities)
**Files to Modify**:
- `download_and_extract.py` (~20 lines)
- `process_trials.py` (~10 lines)
- `Snakefile` (~1 line)

**Testing**:
- 157/400 test trials have publications (39.2%)
- Good coverage for validation

## Feature 2: Adverse Events

### Data Structure

**AACT Table**: `reported_events.txt`

**Fields**:
```
- nct_id: Trial identifier
- event_type: serious, other
- time_frame: When events were recorded
- organ_system: Body system affected
- adverse_event_term: Specific event name
- subjects_affected: Number of subjects
- subjects_at_risk: Total subjects in group
- event_count: Total occurrences
- description: Event description
```

### Challenges

**1. Low Coverage**: Only 11.2% of test trials (45/400)
- Many trials don't report detailed adverse events
- More common in completed trials with results

**2. Complex Structure**:
- Multiple events per trial
- Group-specific data (by study arm)
- Statistical aggregation needed

**3. Data Volume**:
- 10.9M total rows in AACT
- Large nested structures per trial

### Implementation Approaches

**Option A: Summary Only** (Recommended)
Extract high-level summary:
```json
{
  "adverse_events_summary": {
    "has_events": true,
    "serious_events_count": 5,
    "other_events_count": 12,
    "most_common": ["Nausea", "Headache", "Fatigue"]
  }
}
```
- ✓ Simpler implementation
- ✓ Smaller data size
- ✓ Good for filtering/searching
- ✗ Less detailed

**Option B: Full Detail**
Extract complete event data:
```json
{
  "adverse_events": [
    {
      "event_type": "serious",
      "organ_system": "Cardiac disorders",
      "term": "Myocardial infarction",
      "subjects_affected": 2,
      "subjects_at_risk": 100,
      "description": "..."
    }
  ]
}
```
- ✓ Complete data
- ✓ Enables detailed analysis
- ✗ Large data structures
- ✗ Complex queries

### Recommendation for Adverse Events

**Phase 1**: Skip for now (focus on Publications)
**Phase 2**: Implement summary version if needed
**Rationale**:
- Low coverage (11.2%) limits utility
- Complex structure requires more effort
- Publications provide more immediate value

## Implementation Timeline

### Phase 1: Publications (Recommended Next)
**Effort**: 2-3 hours
**Value**: High (cross-reference with PubMed)
**Coverage**: 39.2%

**Steps**:
1. Add publications extraction to `download_and_extract.py`
2. Update metadata in `process_trials.py`
3. Add `--include-publications` flag to Snakefile
4. Add test queries (e.g., "trials with published results")
5. Update fixtures and test validation
6. Test with 400-trial test set

### Phase 2: Adverse Events (Optional)
**Effort**: 4-6 hours
**Value**: Medium (limited coverage)
**Coverage**: 11.2%

**Decision Point**: Implement only if:
- Users specifically request safety data
- We focus on completed trials (higher coverage)
- We need summary-level safety filtering

## Benefits of Tier 2

### Publications
1. **Cross-referencing**: Link trials ↔ literature
2. **Evidence chain**: Find published evidence for interventions
3. **Quality indicator**: Trials with publications = completed/impactful
4. **Future integration**: Join with PubMed collection for unified search

**RAG Enhancement Opportunity** 🎯:
Since BioYoda has both Clinical Trials AND PubMed collections, publications enable intelligent cross-referencing:
- **Smart Context**: When answering about a trial, RAG can automatically fetch and include related PubMed articles via PMID
- **Evidence Chain**: "Show me trial NCT12345 AND its published results from PubMed"
- **Bidirectional**: Query trials → get PMIDs → fetch full PubMed abstracts in single RAG response
- **Enhanced Answers**: Combine trial protocol (from clinical_trials) with published outcomes (from pubmed_abstracts)
- **Implementation**: API layer can resolve PMIDs and merge contexts before LLM generation

Example RAG flow:
```
User: "What were the results of the diabetes trial NCT12345?"
→ Search clinical_trials for NCT12345
→ Extract PMIDs from publications field
→ Fetch those PMIDs from pubmed_abstracts collection
→ Combine trial metadata + published results
→ Generate comprehensive answer with both sources
```

### Adverse Events (if implemented)
1. **Safety filtering**: Find trials with good safety profiles
2. **Risk assessment**: Identify common side effects
3. **Clinical decision support**: Help clinicians/patients assess risks

## Comparison: Tier 1 vs Tier 2

| Aspect | Tier 1 (Completed) | Tier 2 Publications | Tier 2 Adverse Events |
|--------|-------------------|---------------------|---------------------|
| **Coverage** | 85-100% | 39.2% | 11.2% |
| **Complexity** | Low | Low | Moderate |
| **Value** | High | High | Medium |
| **Data Size** | Small | Small | Large |
| **Implementation** | 4 hours | 2-3 hours | 4-6 hours |
| **Status** | ✅ Done | ⏳ Recommended | ⏸️ Optional |

## Recommendation

**Start with Publications**:
1. Higher coverage (39.2% vs 11.2%)
2. Lower complexity (similar to Tier 1)
3. Higher immediate value (PubMed cross-referencing)
4. Natural next step after Tier 1

**Defer Adverse Events**:
- Wait for user demand
- Consider summary version first
- May not be worth the complexity given low coverage

## Next Steps

If proceeding with Publications:
1. Review this plan
2. Implement extraction following Tier 1 pattern
3. Add test queries for publications
4. Update documentation
5. Test with 400-trial reference set

---

**Document Version**: 1.0
**Date**: October 2025
**Status**: Planning phase

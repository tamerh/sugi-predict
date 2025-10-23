# Adverse Events Implementation Analysis

## Executive Summary

Based on analysis of the AACT database, adverse events data is available and can be extracted for clinical trials. This document provides a comprehensive analysis and implementation recommendations for Tier 2.

---

## Data Availability

### Source Tables

**1. `reported_events.txt`** (Main table)
- **Size**: ~11M rows total database (test: ~11M rows)
- **Unique trials**: ~55K trials have adverse events data
- **Coverage**: ~10% of all trials (554K total)

**Key Fields:**
```
- nct_id: Trial identifier
- event_type: 'serious' | 'other'
- adverse_event_term: Event name (e.g., "Headache", "Nausea")
- organ_system: Body system (e.g., "Cardiac disorders")
- subjects_affected: Count affected
- subjects_at_risk: Total in group
- event_count: Total occurrences
- time_frame: When recorded
- assessment: SYSTEMATIC_ASSESSMENT | NON_SYSTEMATIC_ASSESSMENT
- vocab: MedDRA version
```

**2. `reported_event_totals.txt`** (Summary table)
- **Size**: ~557K rows
- **Fields**: Deaths, serious adverse events aggregated by group

### Event Type Distribution

From sample analysis (100K events):
- **Other events**: 64% (non-serious)
- **Serious events**: 36%

### Most Common Adverse Events

Top 15 across all trials:
1. Headache (990 occurrences in sample)
2. Nausea (933)
3. Vomiting (822)
4. Diarrhoea (712)
5. Fatigue (687)
6. Constipation (655)
7. Dizziness (591)
8. Nasopharyngitis (557)
9. Pyrexia (548)
10. Urinary tract infection (545)
11. Cough (521)
12. Back pain (487)
13. Upper respiratory tract infection (463)
14. Arthralgia (457)
15. Abdominal pain (452)

### Organ Systems

27 unique organ systems:
- Infections and infestations (13.6%)
- Gastrointestinal disorders (12.3%)
- General disorders (8%)
- Nervous system disorders (7.5%)
- Respiratory disorders (6.7%)
- Investigations (5.7%)
- Musculoskeletal disorders (5.4%)
- Skin disorders (5.3%)
- Injury and procedural complications (4.8%)
- Metabolism and nutrition disorders (4.5%)

---

## Data Complexity Analysis

### Challenge 1: Volume Per Trial

**Example**: NCT01012258 has **216 event records**
- Different events per study arm/group
- Each event type tracked separately
- Includes both serious and other events

**Data explosion**:
- 554K trials × 200 avg events = **110M+ potential records**
- Test dataset: 400 trials → 10M+ event rows

### Challenge 2: Nested Structure

Events are grouped by:
1. **Trial** (nct_id)
2. **Study arm/group** (result_group_id, ctgov_group_code)
3. **Event type** (serious vs other)
4. **Time frame** (when measured)
5. **Individual events** (adverse_event_term)

Full structure requires preserving all levels:
```json
{
  "nct_id": "NCT123",
  "adverse_events": {
    "groups": [
      {
        "group_code": "EG000",
        "group_name": "Experimental Arm",
        "time_frame": "Up to 60 days",
        "events": [
          {
            "type": "serious",
            "organ_system": "Cardiac disorders",
            "term": "Myocardial infarction",
            "subjects_affected": 2,
            "subjects_at_risk": 100,
            "event_count": 2,
            "percentage": 2.0
          }
        ]
      }
    ]
  }
}
```

### Challenge 3: Metadata Bloat

**Storage Impact Estimates** (554K trials):

| Approach | Avg Size/Trial | Total Size | Increase |
|----------|----------------|------------|----------|
| **Current** | 1KB | ~554 MB | Baseline |
| **Full Events** | +5KB | +2.8 GB | +500% |
| **Summary Only** | +500 bytes | +277 MB | +50% |
| **Top-K Events** | +1KB | +554 MB | +100% |

---

## Implementation Options

### Option A: Summary Statistics Only ⭐ **RECOMMENDED**

**What to extract:**
- Count of serious events
- Count of other events
- Top 5-10 most common events
- Flag for "has safety data"

**Advantages:**
✅ Minimal storage overhead (+50% vs +500%)
✅ Fast to extract and process
✅ Enables key filtering ("trials with serious events")
✅ Good for safety screening

**Disadvantages:**
❌ Loses detailed event information
❌ Cannot analyze specific events in depth
❌ No per-group breakdowns

**Metadata Structure:**
```json
{
  "nct_id": "NCT123",
  "adverse_events_summary": {
    "has_events": true,
    "serious_events_count": 5,
    "other_events_count": 23,
    "total_subjects_at_risk": 200,
    "serious_events_percentage": 2.5,
    "common_events": [
      {"term": "Nausea", "count": 15, "percentage": 7.5},
      {"term": "Headache", "count": 12, "percentage": 6.0},
      {"term": "Fatigue", "count": 10, "percentage": 5.0}
    ],
    "organ_systems_affected": ["Gastrointestinal", "Nervous system"]
  }
}
```

**Use Cases:**
- "Find trials with low serious event rates"
- "Which trials reported nausea as common side effect?"
- "Trials with good safety profiles (< 5% serious events)"

---

### Option B: Top-K Events Detail

**What to extract:**
- Top 10 most common events (detailed)
- All serious events (detailed)
- Summary statistics

**Advantages:**
✅ Captures most important safety signals
✅ Manageable size (+100%)
✅ Good balance of detail vs overhead
✅ Keeps critical serious events

**Disadvantages:**
❌ Arbitrary cutoff (why 10?)
❌ May miss rare but important events
❌ Still loses per-group detail

**Metadata Structure:**
```json
{
  "nct_id": "NCT123",
  "adverse_events": {
    "summary": {
      "serious_count": 5,
      "other_count": 23,
      "total_events": 28
    },
    "serious_events": [
      {
        "term": "Myocardial infarction",
        "organ_system": "Cardiac disorders",
        "subjects_affected": 2,
        "subjects_at_risk": 100,
        "percentage": 2.0,
        "groups": ["Experimental", "Control"]
      }
    ],
    "top_common_events": [
      {
        "term": "Nausea",
        "organ_system": "Gastrointestinal",
        "subjects_affected": 15,
        "subjects_at_risk": 100,
        "percentage": 15.0
      }
    ]
  }
}
```

---

### Option C: Full Event Detail (NOT RECOMMENDED)

**What to extract:**
- All events
- All groups
- Complete structure

**Advantages:**
✅ Complete data
✅ Enables detailed analysis

**Disadvantages:**
❌ Massive storage (+500%)
❌ Slow to process
❌ Most data rarely used
❌ Overwhelms RAG context windows

**When to use:**
- Specialized safety database
- Separate collection for adverse events only
- Post-market surveillance system

---

## Recommended Implementation

### Phase 1: Summary Statistics (Immediate) ⭐

**Extraction Strategy:**

```python
# In download_and_extract.py

def extract_adverse_events_summary(nct_id: str, events_df: pd.DataFrame) -> dict:
    """
    Extract summary adverse events data for a trial.

    Returns lightweight summary suitable for filtering/RAG.
    """
    trial_events = events_df[events_df['nct_id'] == nct_id]

    if len(trial_events) == 0:
        return {
            'has_events': False,
            'serious_events_count': 0,
            'other_events_count': 0
        }

    # Count by type
    serious = trial_events[trial_events['event_type'] == 'serious']
    other = trial_events[trial_events['event_type'] == 'other']

    # Get unique events and affected subjects
    serious_terms = set(serious['adverse_event_term'].dropna())
    other_terms = set(other['adverse_event_term'].dropna())

    # Calculate total subjects at risk (max across groups)
    total_at_risk = trial_events['subjects_at_risk'].max()

    # Get most common events (top 5)
    event_counts = trial_events.groupby('adverse_event_term')['subjects_affected'].sum()
    top_events = event_counts.nlargest(5)

    common_events = []
    for term, count in top_events.items():
        if pd.notna(term):
            # Get organ system for this event
            organ_sys = trial_events[trial_events['adverse_event_term'] == term]['organ_system'].iloc[0]
            common_events.append({
                'term': str(term),
                'organ_system': str(organ_sys) if pd.notna(organ_sys) else '',
                'subjects_affected': int(count),
                'percentage': round(float(count) / total_at_risk * 100, 1) if total_at_risk > 0 else 0
            })

    # Get affected organ systems
    organ_systems = list(trial_events['organ_system'].dropna().unique())

    return {
        'has_events': True,
        'serious_events_count': len(serious_terms),
        'other_events_count': len(other_terms),
        'total_subjects_at_risk': int(total_at_risk) if pd.notna(total_at_risk) else 0,
        'common_events': common_events[:5],  # Top 5
        'organ_systems_affected': organ_systems[:10]  # Limit to 10
    }
```

**Integration Points:**

1. **Extraction** (`download_and_extract.py` lines ~600):
```python
# After publications processing
adverse_events_dict = {}
if include_adverse_events:
    reported_events = self.load_table('reported_events')
    if reported_events is not None:
        reported_events = reported_events[reported_events['nct_id'].isin(kept_nct_ids)]
        log_with_timestamp(f"Processing adverse events for {len(reported_events):,} event records")

        for nct_id in kept_nct_ids:
            adverse_events_dict[nct_id] = extract_adverse_events_summary(
                nct_id, reported_events
            )
```

2. **Add to trial data** (lines ~660):
```python
if nct_id in adverse_events_dict:
    study_data['adverse_events_summary'] = adverse_events_dict[nct_id]
else:
    study_data['adverse_events_summary'] = {'has_events': False}
```

3. **Config flag** (argparse):
```python
parser.add_argument("--include-adverse-events", action="store_true", default=True)
```

---

## Query Capabilities (Summary Approach)

### Filtering Examples

**1. Trials with low serious event rates:**
```json
POST /search
{
  "query": "diabetes treatment",
  "collections": ["clinical_trials"],
  "filters": {
    "adverse_events_summary.serious_events_count": {"$lte": 5}
  }
}
```

**2. Trials with specific side effects:**
```json
{
  "query": "cancer immunotherapy",
  "filters": {
    "adverse_events_summary.common_events.term": "Nausea"
  }
}
```

**3. Trials with safety data available:**
```json
{
  "filters": {
    "adverse_events_summary.has_events": true,
    "overall_status": "Completed"
  }
}
```

### RAG Context Example

When retrieving trial context for RAG:
```
Trial NCT123: Cancer Immunotherapy Study
Conditions: Melanoma
Interventions: Drug X
Status: Completed

Safety Profile:
- Serious adverse events: 3 events (2.5% of participants)
- Common side effects: Nausea (15%), Fatigue (12%), Headache (8%)
- Organ systems affected: Gastrointestinal, Nervous system
- Overall subjects at risk: 120

Publications: [PMID123, PMID456]
```

LLM can now answer:
- "What are the common side effects of this drug?"
- "Is this treatment safe?"
- "Which trials have the best safety profiles?"

---

## Performance Considerations

### Extraction Performance

**Current Pattern (Publications):**
- Load table once
- Group by nct_id
- Simple iteration
- **Time**: ~30 seconds for 400 trials

**Adverse Events (Summary):**
- Load table once (larger: 11M rows vs 500K)
- Filter to kept trials
- Group by nct_id + aggregate
- **Time**: ~2-5 minutes for 400 trials
- **Memory**: ~2GB for full table

**Optimization:**
```python
# Chunk processing for large tables
def load_table_chunked(self, table_name: str, chunksize: int = 100000):
    """Load large table in chunks to manage memory"""
    table_path = self.extracted_dir / f"{table_name}.txt"
    return pd.read_csv(table_path, sep='|', chunksize=chunksize, low_memory=False)

# Process in chunks
adverse_events_dict = {}
for chunk in self.load_table_chunked('reported_events'):
    chunk = chunk[chunk['nct_id'].isin(kept_nct_ids)]
    for nct_id in chunk['nct_id'].unique():
        if nct_id not in adverse_events_dict:
            adverse_events_dict[nct_id] = extract_adverse_events_summary(
                nct_id, chunk
            )
```

### Storage Impact

**Summary approach** (recommended):
- **Per trial**: ~500 bytes
- **400 trials**: ~200 KB
- **554K trials**: ~277 MB
- **Increase**: +50% metadata size
- **Qdrant**: Negligible impact (metadata is small vs vectors)

---

## Testing Strategy

### Test Coverage

1. **Extract test** (400 trials):
```bash
# Run extraction with adverse events
./bioyoda.sh test --modules clinical_trials

# Verify in chunks
python3 << EOF
import json
with open('test_out/raw_data/clinical_trials/chunked/trials_chunk_0001.json') as f:
    trials = json.load(f)

for trial in trials:
    if trial.get('adverse_events_summary', {}).get('has_events'):
        print(f"Trial {trial['nct_id']}: {trial['adverse_events_summary']}")
        break
EOF
```

2. **Validation queries**:
- Count trials with adverse events data
- Find trials with low serious event rates
- Search for specific side effects

3. **RAG test**:
```python
# Query: "What are the side effects of this diabetes drug?"
# Should retrieve trials with adverse_events_summary
# LLM should cite common_events data
```

---

## Migration Path

### Phase 1: Summary (Recommended Now)
- Implement summary extraction
- Add to metadata
- Enable filtering
- RAG-ready

### Phase 2: Enhanced Summary (If Needed)
- Add top-10 serious events detail
- Add event severity indicators
- Add time-to-event data

### Phase 3: Detailed (Future)
- Separate adverse events collection
- Full event detail for safety database
- Link to outcomes data

---

## Recommendation

✅ **Implement Option A: Summary Statistics**

**Reasons:**
1. Provides 80% of value with 20% of complexity
2. Enables key use cases (safety filtering, RAG context)
3. Manageable storage (+50% vs +500%)
4. Fast extraction and processing
5. Can upgrade to Option B later if needed

**Implementation Effort:** ~3-4 hours
- Extraction function: 1 hour
- Integration: 1 hour
- Testing: 1 hour
- Documentation: 1 hour

**Timeline:**
- Day 1: Implement extraction
- Day 2: Test and validate
- Day 3: Update docs and merge

---

## Alternative: Defer to Tier 3

**If summary is not valuable enough:**
- Wait for specific user requests
- Focus on other Tier 2 features
- Consider specialized safety database

**Current Tier 1+2 coverage:**
- ✅ Conditions (100% coverage)
- ✅ Sponsors (100%)
- ✅ Facilities (85%)
- ✅ Study Arms (95%)
- ✅ Publications (39%)
- ❓ Adverse Events (11% coverage, high complexity)

**Trade-off:** Low coverage (11%) may not justify implementation effort even with summary approach.

---

## Decision Point

**Question for stakeholders:**

Do you want:
1. **Summary adverse events now** (3-4 hours, +50% storage, limited detail)
2. **Full adverse events later** (8-10 hours, +500% storage, complete data)
3. **Skip adverse events** (focus on Tier 3 features with higher coverage)

**My recommendation:** Option 1 (Summary) - good balance of value and effort.

---

**Document Version:** 1.0
**Date:** October 23, 2025
**Author:** BioYoda Development Team

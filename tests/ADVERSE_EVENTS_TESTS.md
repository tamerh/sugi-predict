# Adverse Events Testing - Implementation Guide

## Overview

Test infrastructure updated to validate adverse events extraction and querying for clinical trials.

**Date**: October 23, 2025
**Status**: ✅ Complete and ready for testing

---

## Changes Made

### 1. Fixture Update Script (`tests/fixtures/clinical_trials/update_clinical_trials_fixtures.py`)

**Added adverse events tracking**:
- Counter for trials with adverse events
- Collection of common adverse event terms
- Statistics reporting for adverse events coverage
- Example queries for adverse events

**New statistics**:
```python
stats['with_adverse_events'] = 0  # Count of trials with AE data
common_adverse_events = Counter()  # Top adverse events across trials
```

**Sample output**:
```
Field Coverage:
  Sponsors:        384/400 (96.0%)
  Facilities:      340/400 (85.0%)
  Study Arms:      380/400 (95.0%)
  Conditions:      400/400 (100.0%)
  Interventions:   400/400 (100.0%)
  Publications:    157/400 (39.2%)
  Adverse Events:  45/400 (11.2%)

Top 10 Adverse Events:
  12x Nausea
  10x Headache
   9x Fatigue
   8x Diarrhea
  ...
```

**New example queries**:
- "Find trials with safety data and low serious event rates"
- "Which trials report {top_event} as a common side effect?"
- "Find completed trials with published results and safety data"

### 2. Test Queries (`tests/queries.txt`)

**Added 5 new adverse events queries**:

1. `"Find trials with safety data and low serious event rates."`
2. `"Which trials report nausea as a common side effect?"`
3. `"Show completed trials with adverse events data available."`
4. `"What are the common side effects in cardiovascular drug trials?"`
5. `"Find trials with good safety profiles and minimal adverse events."`

**Total queries**: 18 → 23 queries (5 new)

### 3. Query Validation Script (`tests/validate_queries.py`)

**Updated field coverage checking**:

```python
# Added adverse events counting
with_adverse_events = 0

for result in results:
    payload = result.get('payload', {})
    ae_summary = payload.get('adverse_events_summary', {})
    if ae_summary.get('has_events', False):
        with_adverse_events += 1
```

**Enhanced coverage reporting**:
```
Field Coverage:
  Sponsors:        90/100 (90.0%)
  Facilities:      85/100 (85.0%)
  Study Arms:      95/100 (95.0%)
  Conditions:      100/100 (100.0%)
  Interventions:   100/100 (100.0%)
  Publications:    40/100 (40.0%)
  Adverse Events:  11/100 (11.0%)  # NEW!
```

**Updated success messages**:
- ✅ All Tier 1 + Tier 2 fields present! (including Adverse Events)
- ✅ Tier 1 + Publications present!
- ⚠️ Adverse Events: No data in sample (expected ~11% coverage)

**Verbose output enhanced**:
```
Sample result with Tier 1+2 fields:
  NCT ID: NCT01234567
  Title: Diabetes Treatment Study...
  Sponsors: 2
  Facilities: 5
  Study Arms: 3
  Publications: 2
  Adverse Events: 5 serious, 23 other  # NEW!
```

---

## Usage

### Step 1: Update Test Fixtures

After extracting test data with adverse events:

```bash
# Run test extraction (includes adverse events)
./bioyoda.sh test --modules clinical_trials

# Update fixtures from test_out
python3 tests/fixtures/clinical_trials/update_clinical_trials_fixtures.py
```

**Expected output**:
```
================================================================================
TIER 1 FIELD COVERAGE ANALYSIS
================================================================================

Field Coverage:
  Sponsors:        384/400 (96.0%)
  Facilities:      340/400 (85.0%)
  Study Arms:      380/400 (95.0%)
  Conditions:      400/400 (100.0%)
  Interventions:   400/400 (100.0%)
  Publications:    157/400 (39.2%)
  Adverse Events:  45/400 (11.2%)    ← NEW!

Top 10 Adverse Events:
  12x Nausea
  10x Headache
   9x Fatigue
  ...

Example 6. Trial with Adverse Events Data:
   NCT: NCT01234567
   Title: Study of Drug X in Cancer Patients...
   Serious events: 5
   Other events: 23
   Top event: Nausea (15.0%)
   Query: "Find trials with safety data and low serious event rates"
```

### Step 2: Run Query Validation

```bash
# Run full test suite (includes adverse events queries)
./bioyoda.sh test

# Or run validation directly
python3 tests/validate_queries.py --verbose
```

**Expected results**:
```
================================================================================
SEARCH QUERY VALIDATION
================================================================================

Clinical Trials Queries (23 queries)
----------------------------------------

...

20. Query: Find trials with safety data and low serious event rates.
   Collections: clinical_trials
   ✓ PASS: 8 results
     Top: NCT:NCT01234567 (score: 0.782)

21. Query: Which trials report nausea as a common side effect?
   Collections: clinical_trials
   ✓ PASS: 5 results
     Top: NCT:NCT02345678 (score: 0.745)

...

Clinical Trials: 23/23 passed ✓
```

### Step 3: Check Field Coverage

After validation, check that adverse events are present:

```
================================================================================
CHECKING FIELD COVERAGE IN RESULTS
================================================================================

Sample size: 100 results

Field Coverage:
  Sponsors:        90/100 (90.0%)
  Facilities:      85/100 (85.0%)
  Study Arms:      95/100 (95.0%)
  Conditions:      100/100 (100.0%)
  Interventions:   100/100 (100.0%)
  Publications:    40/100 (40.0%)
  Adverse Events:  11/100 (11.0%)    ← Should be ~10-15%

✓ All Tier 1 + Tier 2 fields present! (including Adverse Events)
```

---

## Expected Coverage

### Adverse Events Coverage

**~11% of trials** have adverse events data:
- Only completed trials with results report adverse events
- Not all therapeutic areas require reporting
- Coverage varies by trial status and phase

**Coverage breakdown** (estimated):
- Completed Phase 3/4 trials: ~40%
- Completed Phase 2 trials: ~20%
- Recruiting/Active trials: ~5%
- Observational studies: ~2%

### Query Success Criteria

**Adverse events queries should**:
1. Return results (at least 1-2 trials)
2. Have reasonable scores (> 0.4)
3. Match trials that actually have AE data

**Note**: Low result counts are expected for AE queries due to 11% coverage.

---

## Test Scenarios

### Scenario 1: Basic Adverse Events Query

**Query**: "Show completed trials with adverse events data available"

**Expected**:
- 3-10 results (depending on fixture size)
- All results should have `adverse_events_summary.has_events = true`
- Score > 0.5

**Validation**:
```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show completed trials with adverse events data available",
    "collections": ["clinical_trials"],
    "limit": 5
  }' | jq '.results[].payload.adverse_events_summary'
```

### Scenario 2: Specific Side Effect Query

**Query**: "Which trials report nausea as a common side effect?"

**Expected**:
- 2-8 results
- Results should have "Nausea" in `adverse_events_summary.common_events`
- Score varies (0.4-0.7)

**Validation**:
```bash
# Check if results have nausea in common events
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Which trials report nausea as a common side effect",
    "collections": ["clinical_trials"]
  }' | jq '.results[].payload.adverse_events_summary.common_events[] | select(.term | contains("Nausea"))'
```

### Scenario 3: Safety Profile Query

**Query**: "Find trials with good safety profiles and minimal adverse events"

**Expected**:
- 5-15 results
- Results may or may not have AE data
- Should prioritize trials with low serious event counts

**Validation**:
```python
# Check that returned trials have reasonable safety profiles
import requests
response = requests.post('http://localhost:8000/search', json={
    'query': 'Find trials with good safety profiles and minimal adverse events',
    'collections': ['clinical_trials']
})

for result in response.json()['results']:
    ae = result['payload'].get('adverse_events_summary', {})
    if ae.get('has_events'):
        serious = ae.get('serious_events_count', 0)
        print(f"NCT {result['payload']['nct_id']}: {serious} serious events")
```

---

## Troubleshooting

### Issue 1: No results for adverse events queries

**Symptoms**:
```
Query: Find trials with safety data and low serious event rates.
✗ No results found
```

**Causes**:
1. Test fixtures don't have adverse events data
2. Adverse events not extracted
3. Qdrant collection missing metadata

**Solution**:
```bash
# Check if extraction included adverse events
jq '.[0].adverse_events_summary' test_out/raw_data/clinical_trials/chunked/trials_chunk_0001.json

# Re-extract with adverse events
rm -rf test_out/
./bioyoda.sh test --modules clinical_trials

# Regenerate fixtures
python3 tests/fixtures/clinical_trials/update_clinical_trials_fixtures.py
```

### Issue 2: Coverage is 0%

**Symptoms**:
```
Field Coverage:
  Adverse Events:  0/100 (0.0%)
```

**Causes**:
1. Test dataset has no completed trials
2. Adverse events extraction disabled
3. Metadata not passed to Qdrant

**Solution**:
```bash
# Check config
grep "include_adverse_events" config/test_config.yaml

# Check extraction flag in download_and_extract.py
grep "include_adverse_events" modules/clinical_trials/scripts/download_and_extract.py

# Check Qdrant payloads
curl http://localhost:6333/collections/clinical_trials/points/scroll | \
  jq '.result.points[0].payload.adverse_events_summary'
```

### Issue 3: Query scores are very low (< 0.3)

**Symptoms**:
```
Query: Which trials report nausea as a common side effect?
✓ PASS: 2 results
  Top: NCT:NCT01234567 (score: 0.285)  ← TOO LOW
```

**Causes**:
1. Query too specific for semantic search
2. Few trials have the specific adverse event
3. Model doesn't understand adverse events context well

**Solution**:
- Revise query to be more semantic: "trials with gastrointestinal side effects"
- Add more context to query: "clinical trials reporting nausea in completed studies"
- Consider filtering instead of pure semantic search

---

## Integration with Full Test Suite

### Test Flow

1. **Setup**: Copy fixtures → Extract data (with AE) → Process
2. **Insert**: Load to Qdrant (includes AE metadata)
3. **Validate Queries**: Run all 23 queries (including 5 AE queries)
4. **Check Coverage**: Verify AE field present in ~11% of results
5. **RAG Tests**: Verify LLM can cite adverse events data

### Expected Timeline

- **Fixture mode**: ~2-3 minutes (uses pre-extracted data)
- **Pipeline mode**: ~15-20 minutes (full extraction with AE processing)

### Success Criteria

✅ **All tests pass**:
- 23/23 search queries return results
- Adverse events coverage: 10-15% (expected)
- Field validation: All Tier 1+2 fields present
- RAG queries cite adverse events when relevant

---

## Query Design Guidelines

### Good Adverse Events Queries

✅ **"Find trials with low serious event rates"**
- Semantic, not exact match
- Focused on concept (safety)
- Works with or without AE data

✅ **"Which trials report nausea as a side effect?"**
- Specific but common adverse event
- Likely to match multiple trials
- Clear intent

✅ **"Show completed trials with safety data"**
- Broad enough to get results
- Specific to completed trials (more likely to have AE)
- Checks for data availability

### Poor Adverse Events Queries

❌ **"Find trials with exactly 5 serious adverse events"**
- Too specific (exact match)
- Unlikely to match any trial
- Better as a filter

❌ **"Which trials report Stevens-Johnson syndrome?"**
- Too rare (may have 0 matches in fixtures)
- Consider testing with more common events first
- Better for production queries

❌ **"List all adverse events for NCT01234567"**
- Direct lookup query (use API filtering)
- Not semantic search
- Use Qdrant filters instead

---

## Next Steps

1. ✅ Run test extraction with adverse events
2. ✅ Update fixtures with AE data
3. ✅ Run validation tests
4. ⏳ Review test results and adjust queries if needed
5. ⏳ Test RAG with adverse events context
6. ⏳ Document any edge cases or issues

---

## Files Modified

1. `tests/fixtures/clinical_trials/update_clinical_trials_fixtures.py` - AE tracking
2. `tests/queries.txt` - 5 new AE queries
3. `tests/validate_queries.py` - AE field validation
4. `tests/ADVERSE_EVENTS_TESTS.md` - This document

---

## References

- **Implementation**: `modules/clinical_trials/ADVERSE_EVENTS_IMPLEMENTATION.md`
- **Analysis**: `modules/clinical_trials/ADVERSE_EVENTS_ANALYSIS.md`
- **Test README**: `tests/README.md`
- **Fixtures README**: `tests/fixtures/README.md`

---

**Status**: ✅ Ready for testing
**Last Updated**: October 23, 2025

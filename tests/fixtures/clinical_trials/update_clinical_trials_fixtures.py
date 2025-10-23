#!/usr/bin/env python3
"""
Update clinical trials test fixtures from test_out directory.

This script:
1. Reads all chunks from test_out/raw_data/clinical_trials/chunked/
2. Analyzes Tier 1 field coverage (sponsors, facilities, study_arms)
3. Creates updated reference fixtures in tests/fixtures/clinical_trials/
   - sample_trials.json: All 400 trials from test run (with Tier 1 fields)
   - test_nct_ids.txt: List of all 400 NCT IDs
   - tier1_coverage_stats.json: Coverage statistics
4. Provides statistics and example queries for test development

Run this script after running: ./bioyoda.sh test --modules clinical_trials
"""

import json
import shutil
from pathlib import Path
from collections import Counter

def analyze_and_update_fixtures():
    """Analyze test_out chunks and update fixtures."""

    print("=" * 80)
    print("Clinical Trials Test Fixture Update")
    print("=" * 80)

    # Paths
    chunks_dir = Path("test_out/raw_data/clinical_trials/chunked")
    fixtures_dir = Path("tests/fixtures/clinical_trials")
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    if not chunks_dir.exists():
        print(f"\nERROR: Chunks directory not found: {chunks_dir}")
        print("Please run: ./bioyoda.sh test --modules clinical_trials")
        return False

    # Load all chunks
    print(f"\nLoading chunks from: {chunks_dir}")
    all_trials = []
    chunk_files = sorted(chunks_dir.glob("trials_chunk_*.json"))

    for chunk_file in chunk_files:
        with open(chunk_file) as f:
            trials = json.load(f)
            all_trials.extend(trials)
            print(f"  Loaded {len(trials)} trials from {chunk_file.name}")

    print(f"\nTotal trials: {len(all_trials)}")

    # Analyze Tier 1 field coverage
    print("\n" + "=" * 80)
    print("TIER 1 FIELD COVERAGE ANALYSIS")
    print("=" * 80)

    stats = {
        'total': len(all_trials),
        'with_sponsors': 0,
        'with_facilities': 0,
        'with_study_arms': 0,
        'with_conditions': 0,
        'with_interventions': 0,
    }

    sponsor_names = Counter()
    sponsor_classes = Counter()
    facility_cities = Counter()
    facility_countries = Counter()
    arm_types = Counter()

    for trial in all_trials:
        if trial.get('sponsors') and len(trial['sponsors']) > 0:
            stats['with_sponsors'] += 1
            for sponsor in trial['sponsors']:
                sponsor_names[sponsor.get('name', 'Unknown')] += 1
                sponsor_classes[sponsor.get('agency_class', 'Unknown')] += 1

        if trial.get('facilities') and len(trial['facilities']) > 0:
            stats['with_facilities'] += 1
            for facility in trial['facilities']:
                facility_cities[f"{facility.get('city', 'Unknown')}, {facility.get('state', '')}".strip(', ')] += 1
                facility_countries[facility.get('country', 'Unknown')] += 1

        if trial.get('study_arms') and len(trial['study_arms']) > 0:
            stats['with_study_arms'] += 1
            for arm in trial['study_arms']:
                arm_types[arm.get('type', 'Unknown')] += 1

        if trial.get('conditions') and len(trial['conditions']) > 0:
            stats['with_conditions'] += 1

        if trial.get('interventions') and len(trial['interventions']) > 0:
            stats['with_interventions'] += 1

    # Print statistics
    print(f"\nField Coverage:")
    print(f"  Sponsors:      {stats['with_sponsors']}/{stats['total']} ({stats['with_sponsors']/stats['total']*100:.1f}%)")
    print(f"  Facilities:    {stats['with_facilities']}/{stats['total']} ({stats['with_facilities']/stats['total']*100:.1f}%)")
    print(f"  Study Arms:    {stats['with_study_arms']}/{stats['total']} ({stats['with_study_arms']/stats['total']*100:.1f}%)")
    print(f"  Conditions:    {stats['with_conditions']}/{stats['total']} ({stats['with_conditions']/stats['total']*100:.1f}%)")
    print(f"  Interventions: {stats['with_interventions']}/{stats['total']} ({stats['with_interventions']/stats['total']*100:.1f}%)")

    print(f"\nTop 10 Sponsors:")
    for sponsor, count in sponsor_names.most_common(10):
        print(f"  {count:3d}x {sponsor}")

    print(f"\nSponsor Types:")
    for stype, count in sponsor_classes.most_common():
        print(f"  {count:3d}x {stype}")

    print(f"\nTop 10 Facility Cities:")
    for city, count in facility_cities.most_common(10):
        print(f"  {count:3d}x {city}")

    print(f"\nTop 10 Countries:")
    for country, count in facility_countries.most_common(10):
        print(f"  {count:3d}x {country}")

    print(f"\nStudy Arm Types:")
    for arm_type, count in arm_types.most_common():
        print(f"  {count:3d}x {arm_type}")

    # Find good examples for queries
    print("\n" + "=" * 80)
    print("EXAMPLE TRIALS FOR TEST QUERIES")
    print("=" * 80)

    # Example 1: Trial with NIH sponsor
    nih_trials = [t for t in all_trials if any('National Institutes of Health' in s.get('name', '') for s in t.get('sponsors', []))]
    if nih_trials:
        trial = nih_trials[0]
        print(f"\n1. NIH-Sponsored Trial:")
        print(f"   NCT: {trial['nct_id']}")
        print(f"   Title: {trial['brief_title'][:70]}")
        print(f"   Query: \"Find trials funded by National Institutes of Health\"")

    # Example 2: Trial in specific city
    if facility_cities:
        top_city = facility_cities.most_common(1)[0][0]
        city_trials = [t for t in all_trials if any(f"{f.get('city', '')}, {f.get('state', '')}".strip(', ') == top_city for f in t.get('facilities', []))]
        if city_trials:
            trial = city_trials[0]
            print(f"\n2. Location-Specific Trial:")
            print(f"   NCT: {trial['nct_id']}")
            print(f"   Title: {trial['brief_title'][:70]}")
            print(f"   Location: {top_city}")
            print(f"   Query: \"Which studies are conducted in {top_city}?\"")

    # Example 3: Trial with multiple arms
    multi_arm_trials = [t for t in all_trials if len(t.get('study_arms', [])) >= 2]
    if multi_arm_trials:
        trial = multi_arm_trials[0]
        print(f"\n3. Multi-Arm Trial:")
        print(f"   NCT: {trial['nct_id']}")
        print(f"   Title: {trial['brief_title'][:70]}")
        print(f"   Arms: {len(trial['study_arms'])} ({', '.join([a.get('type', 'Unknown') for a in trial['study_arms']])})")
        print(f"   Query: \"Show trials with experimental and placebo control arms\"")

    # Example 4: Industry-sponsored trial
    industry_trials = [t for t in all_trials if any(s.get('agency_class', '') == 'INDUSTRY' for s in t.get('sponsors', []))]
    if industry_trials:
        trial = industry_trials[0]
        sponsor_name = next((s['name'] for s in trial['sponsors'] if s.get('agency_class') == 'INDUSTRY'), 'Unknown')
        print(f"\n4. Industry-Sponsored Trial:")
        print(f"   NCT: {trial['nct_id']}")
        print(f"   Title: {trial['brief_title'][:70]}")
        print(f"   Sponsor: {sponsor_name}")
        print(f"   Query: \"Find industry-funded clinical trials\"")

    # Example 5: International trial
    intl_trials = [t for t in all_trials if len(set(f.get('country', '') for f in t.get('facilities', []))) > 1]
    if intl_trials:
        trial = intl_trials[0]
        countries = set(f.get('country', '') for f in trial.get('facilities', []))
        print(f"\n5. International Trial:")
        print(f"   NCT: {trial['nct_id']}")
        print(f"   Title: {trial['brief_title'][:70]}")
        print(f"   Countries: {len(countries)} ({', '.join(list(countries)[:3])})")
        print(f"   Query: \"Find multi-country clinical trials\"")

    # Save updated fixtures
    print("\n" + "=" * 80)
    print("UPDATING FIXTURES")
    print("=" * 80)

    # Save ALL trials as reference (all 400 from test run)
    sample_trials_file = fixtures_dir / "sample_trials.json"
    with open(sample_trials_file, 'w') as f:
        json.dump(all_trials, f, indent=2)
    print(f"\n✓ Updated: {sample_trials_file} ({len(all_trials)} trials - complete test dataset)")

    # Extract and save NCT IDs
    nct_ids_file = fixtures_dir / "test_nct_ids.txt"
    with open(nct_ids_file, 'w') as f:
        f.write("# Clinical Trials Test NCT IDs\n")
        f.write("# These are the first 400 trials processed during test runs\n")
        f.write(f"# Total: {len(all_trials)} trials (from test_trials_limit config)\n")
        f.write("#\n")
        for trial in all_trials:
            f.write(f"{trial['nct_id']}\n")
    print(f"✓ Updated: {nct_ids_file} ({len(all_trials)} NCT IDs)")

    # Save statistics
    stats_file = fixtures_dir / "tier1_coverage_stats.json"
    with open(stats_file, 'w') as f:
        json.dump({
            'coverage': stats,
            'top_sponsors': dict(sponsor_names.most_common(20)),
            'sponsor_classes': dict(sponsor_classes),
            'top_cities': dict(facility_cities.most_common(20)),
            'top_countries': dict(facility_countries.most_common(10)),
            'arm_types': dict(arm_types)
        }, f, indent=2)
    print(f"✓ Created: {stats_file}")

    print("\n" + "=" * 80)
    print("✓ Fixtures updated successfully!")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Review suggested queries above")
    print("2. Add relevant queries to tests/queries.txt")
    print("3. Update tests/validate_queries.py to check Tier 1 field coverage")
    print("4. Run: ./bioyoda.sh test")

    return True

if __name__ == "__main__":
    import sys
    success = analyze_and_update_fixtures()
    sys.exit(0 if success else 1)

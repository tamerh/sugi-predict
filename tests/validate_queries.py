#!/usr/bin/env python3
"""
BioYoda Query Validation

Simple script to validate search and RAG queries against test data.
Called by ./bioyoda.sh test after servers are started.

Usage:
    python tests2/validate_queries.py [--verbose]
    python tests2/validate_queries.py --search-only
    python tests2/validate_queries.py --rag-only
"""

import argparse
import requests
import json
import sys
from pathlib import Path
from typing import List, Dict, Optional


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


class QueryValidator:
    """Validates queries against BioYoda API"""

    def __init__(self, api_url: str = "http://localhost:8000", verbose: bool = False):
        self.api_url = api_url.rstrip('/')
        self.verbose = verbose
        self.results = {
            'ct_search_passed': 0,
            'ct_search_failed': 0,
            'pubmed_search_passed': 0,
            'pubmed_search_failed': 0,
            'rag_passed': 0,
            'rag_failed': 0,
            'rag_skipped': 0
        }

    def check_api_health(self) -> bool:
        """Check if API is running and healthy"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                health = response.json()
                if health['status'] == 'healthy':
                    print(f"{Colors.GREEN}✓{Colors.NC} API is healthy")
                    return True
                else:
                    print(f"{Colors.YELLOW}⚠{Colors.NC} API status: {health['status']}")
                    if not health.get('qdrant_connected'):
                        print(f"  {Colors.RED}✗{Colors.NC} Qdrant not connected")
                    if not health.get('model_loaded'):
                        print(f"  {Colors.RED}✗{Colors.NC} Model not loaded")
                    return False
            else:
                print(f"{Colors.RED}✗{Colors.NC} API returned status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print(f"{Colors.RED}✗{Colors.NC} Cannot connect to API at {self.api_url}")
            print(f"  Make sure API is running: ./bioyoda.sh api start --test")
            return False
        except Exception as e:
            print(f"{Colors.RED}✗{Colors.NC} Error checking API: {e}")
            return False

    def load_search_queries(self, query_type: str = "clinical_trials") -> List[str]:
        """
        Load search queries from file

        Args:
            query_type: "clinical_trials" or "pubmed"
        """
        if query_type == "pubmed":
            queries_file = Path(__file__).parent / "queries_pubmed.txt"
        else:
            queries_file = Path(__file__).parent / "queries.txt"

        if not queries_file.exists():
            print(f"{Colors.YELLOW}⚠{Colors.NC} {queries_file.name} not found at {queries_file}")
            return []

        queries = []
        for line in queries_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                # Remove quotes if present
                line = line.strip('"\'')
                queries.append(line)

        return queries

    def generate_rag_questions(self, search_queries: List[str]) -> List[str]:
        """Generate RAG questions from search queries"""
        # Take first 5 search queries and convert to questions
        rag_questions = []

        templates = [
            "What research has been done on {query}?",
            "Summarize findings related to {query}.",
            "What are the clinical implications of {query}?",
            "Explain the current understanding of {query}.",
            "What studies investigate {query}?"
        ]

        for i, query in enumerate(search_queries[:5]):
            template = templates[i % len(templates)]
            # Clean up the query if it's already a question
            cleaned_query = query.rstrip('?').strip()
            question = template.format(query=cleaned_query)
            rag_questions.append(question)

        return rag_questions

    def validate_search_query(self, query: str, index: int, collections: List[str] = None,
                              expected_nct: str = None, min_score: float = 0.4) -> bool:
        """
        Validate a single search query

        Args:
            query: Search query string
            index: Query index number
            collections: Collections to search (default: ["pubmed_abstracts", "clinical_trials"])
            expected_nct: Expected NCT ID that should be in top results (optional)
            min_score: Minimum score threshold for top result (lowered to 0.4 for flexibility)

        Returns:
            True if query passes validation, False otherwise
        """
        if collections is None:
            collections = ["pubmed_abstracts", "clinical_trials"]

        collection_str = ", ".join(collections)
        print(f"\n{index}. Query: {Colors.BLUE}{query}{Colors.NC}")
        print(f"   Collections: {collection_str}")
        if expected_nct:
            print(f"   Expected: {expected_nct} with score >= {min_score}")

        try:
            response = requests.post(
                f"{self.api_url}/search",
                json={
                    "query": query,
                    "collections": collections,
                    "limit": 10
                },
                timeout=30
            )

            if response.status_code == 200:
                results = response.json()
                total_results = results.get('total_results', 0)

                if total_results > 0:
                    top = results['results'][0] if results['results'] else None
                    top_score = top.get('score', 0) if top else 0

                    # Get top identifier
                    if top:
                        payload = top.get('payload', {})
                        if 'pmid' in payload:
                            top_id = f"PMID:{payload['pmid']}"
                            top_nct = None
                        elif 'nct_id' in payload:
                            top_id = f"NCT:{payload['nct_id']}"
                            top_nct = payload['nct_id']
                        else:
                            top_id = "N/A"
                            top_nct = None
                    else:
                        top_id = "N/A"
                        top_nct = None

                    # Validation checks
                    passed = True
                    messages = []

                    # Check 1: Score threshold
                    if top_score < min_score:
                        passed = False
                        messages.append(f"Low score: {top_score:.3f} < {min_score}")

                    # Check 2: Expected NCT in top results
                    if expected_nct:
                        found_in_top = False
                        for i, result in enumerate(results['results'][:5], 1):
                            payload = result.get('payload', {})
                            if payload.get('nct_id') == expected_nct:
                                found_in_top = True
                                if i == 1:
                                    messages.append(f"✓ {expected_nct} is #1")
                                else:
                                    passed = False
                                    messages.append(f"✗ {expected_nct} is #{i}, not #1")
                                break

                        if not found_in_top:
                            passed = False
                            messages.append(f"✗ {expected_nct} not in top 5")

                    # Print results
                    if passed:
                        print(f"   {Colors.GREEN}✓{Colors.NC} PASS: {total_results} results")
                        print(f"     Top: {top_id} (score: {top_score:.3f})")
                        for msg in messages:
                            print(f"     {msg}")
                    else:
                        print(f"   {Colors.YELLOW}⚠{Colors.NC} WARN: {total_results} results (validation issues)")
                        print(f"     Top: {top_id} (score: {top_score:.3f})")
                        for msg in messages:
                            print(f"     {msg}")

                    # Show top 3 in verbose mode
                    if self.verbose and results.get('results'):
                        for i, result in enumerate(results['results'][:3], 1):
                            payload = result.get('payload', {})
                            score = result.get('score', 0)

                            if 'pmid' in payload:
                                identifier = f"PMID:{payload['pmid']}"
                            elif 'nct_id' in payload:
                                identifier = f"NCT:{payload['nct_id']}"
                            else:
                                identifier = f"ID:{result.get('id', 'N/A')}"

                            print(f"       {i}. {identifier} (score: {score:.3f})")

                    return passed
                else:
                    print(f"   {Colors.RED}✗{Colors.NC} No results found")
                    return False
            else:
                error_msg = response.text[:200] if response.text else "Unknown error"
                print(f"   {Colors.RED}✗{Colors.NC} API error {response.status_code}: {error_msg}")
                return False

        except requests.exceptions.Timeout:
            print(f"   {Colors.RED}✗{Colors.NC} Request timed out (>30s)")
            return False
        except Exception as e:
            print(f"   {Colors.RED}✗{Colors.NC} Error: {e}")
            return False

    def check_tier1_coverage(self) -> None:
        """Check Tier 1+ field coverage in clinical trials results (Tier 1 + Publications)"""
        print("\n" + "="*80)
        print("FIELD COVERAGE CHECK (Clinical Trials)")
        print("="*80)
        print("\nChecking for Tier 1 (sponsors, facilities, study_arms) + Publications...")

        # Run a simple query to get sample results
        try:
            response = requests.post(
                f"{self.api_url}/search",
                json={
                    "query": "clinical trials",
                    "collections": ["clinical_trials"],
                    "limit": 20
                },
                timeout=30
            )

            if response.status_code != 200:
                print(f"{Colors.YELLOW}⚠{Colors.NC} Could not fetch results for coverage check")
                return

            results = response.json().get('results', [])
            if not results:
                print(f"{Colors.YELLOW}⚠{Colors.NC} No results to check")
                return

            # Count field coverage
            total = len(results)
            with_sponsors = 0
            with_facilities = 0
            with_study_arms = 0
            with_conditions = 0
            with_interventions = 0
            with_publications = 0
            with_adverse_events = 0

            for result in results:
                payload = result.get('payload', {})

                if payload.get('sponsors') and len(payload['sponsors']) > 0:
                    with_sponsors += 1
                if payload.get('facilities') and len(payload['facilities']) > 0:
                    with_facilities += 1
                if payload.get('study_arms') and len(payload['study_arms']) > 0:
                    with_study_arms += 1
                if payload.get('conditions') and len(payload['conditions']) > 0:
                    with_conditions += 1
                if payload.get('interventions') and len(payload['interventions']) > 0:
                    with_interventions += 1
                if payload.get('publications') and len(payload['publications']) > 0:
                    with_publications += 1
                # Check adverse events
                ae_summary = payload.get('adverse_events_summary', {})
                if ae_summary.get('has_events', False):
                    with_adverse_events += 1

            # Print coverage stats
            print(f"\nSample size: {total} results")
            print(f"\nField Coverage:")
            print(f"  Sponsors:        {with_sponsors}/{total} ({with_sponsors/total*100:.1f}%)")
            print(f"  Facilities:      {with_facilities}/{total} ({with_facilities/total*100:.1f}%)")
            print(f"  Study Arms:      {with_study_arms}/{total} ({with_study_arms/total*100:.1f}%)")
            print(f"  Conditions:      {with_conditions}/{total} ({with_conditions/total*100:.1f}%)")
            print(f"  Interventions:   {with_interventions}/{total} ({with_interventions/total*100:.1f}%)")
            print(f"  Publications:    {with_publications}/{total} ({with_publications/total*100:.1f}%)")
            print(f"  Adverse Events:  {with_adverse_events}/{total} ({with_adverse_events/total*100:.1f}%)")

            # Show a sample result with all fields
            if self.verbose:
                print(f"\nSample result with Tier 1+2 fields:")
                for result in results:
                    payload = result.get('payload', {})
                    if (payload.get('sponsors') and payload.get('facilities') and
                        payload.get('study_arms')):
                        print(f"  NCT ID: {payload.get('nct_id', 'N/A')}")
                        print(f"  Title: {payload.get('brief_title', 'N/A')[:60]}")
                        print(f"  Sponsors: {len(payload.get('sponsors', []))}")
                        print(f"  Facilities: {len(payload.get('facilities', []))}")
                        print(f"  Study Arms: {len(payload.get('study_arms', []))}")
                        print(f"  Publications: {len(payload.get('publications', []))}")
                        ae_summary = payload.get('adverse_events_summary', {})
                        if ae_summary.get('has_events'):
                            print(f"  Adverse Events: {ae_summary.get('serious_events_count', 0)} serious, {ae_summary.get('other_events_count', 0)} other")
                        else:
                            print(f"  Adverse Events: No data")
                        break

            # Check if fields are present
            tier1_ok = with_sponsors > 0 and with_facilities > 0 and with_study_arms > 0
            publications_ok = with_publications > 0
            adverse_events_ok = with_adverse_events > 0

            if tier1_ok and publications_ok and adverse_events_ok:
                print(f"\n{Colors.GREEN}✓{Colors.NC} All Tier 1 + Tier 2 fields present! (including Adverse Events)")
            elif tier1_ok and publications_ok:
                print(f"\n{Colors.GREEN}✓{Colors.NC} Tier 1 + Publications present!")
                if not adverse_events_ok:
                    print(f"  {Colors.YELLOW}⚠{Colors.NC} Adverse Events: No data in sample (expected ~11% coverage)")
            elif tier1_ok:
                print(f"\n{Colors.GREEN}✓{Colors.NC} Tier 1 fields present!")
                if not publications_ok:
                    print(f"  {Colors.YELLOW}⚠{Colors.NC} Publications field present but no data in sample")
                if not adverse_events_ok:
                    print(f"  {Colors.YELLOW}⚠{Colors.NC} Adverse Events: No data in sample (expected ~11% coverage)")
            else:
                print(f"\n{Colors.RED}✗{Colors.NC} Some fields are missing!")
                if with_sponsors == 0:
                    print(f"  Missing: sponsors")
                if with_facilities == 0:
                    print(f"  Missing: facilities")
                if with_study_arms == 0:
                    print(f"  Missing: study_arms")
                if with_publications == 0:
                    print(f"  Missing: publications")

        except Exception as e:
            print(f"{Colors.YELLOW}⚠{Colors.NC} Error checking Tier 1 coverage: {e}")

    def validate_rag_query(self, question: str, index: int) -> Optional[bool]:
        """
        Validate a single RAG query

        Returns:
            True if passes, False if fails, None if skipped (RAG not available)
        """
        print(f"\n{index}. Question: {Colors.BLUE}{question}{Colors.NC}")

        try:
            response = requests.post(
                f"{self.api_url}/ask",
                json={
                    "question": question,
                    "collections": ["pubmed_abstracts", "clinical_trials"],
                    "top_k": 3,
                    "temperature": 0.1
                },
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                answer = result.get('answer', '')
                sources = result.get('sources', [])

                if answer and len(sources) > 0:
                    print(f"   {Colors.GREEN}✓{Colors.NC} Generated answer ({len(answer)} chars)")
                    print(f"     Sources: {len(sources)}")

                    # Show citations
                    if self.verbose:
                        citations = [s.get('id', 'N/A') for s in sources]
                        print(f"     Citations: {', '.join(citations)}")
                        print(f"     Answer preview: {answer[:150]}...")
                    else:
                        citations = [s.get('id', 'N/A') for s in sources[:3]]
                        print(f"     Citations: {', '.join(citations)}")

                    # Check validation if available
                    validation = result.get('validation', {})
                    if validation and validation.get('warning'):
                        print(f"     {Colors.YELLOW}⚠{Colors.NC} {validation['warning']}")

                    return True
                else:
                    print(f"   {Colors.RED}✗{Colors.NC} No answer or sources generated")
                    return False

            elif response.status_code == 503:
                print(f"   {Colors.YELLOW}⚠{Colors.NC} RAG not configured (skipping)")
                return None
            else:
                error_msg = response.text[:200] if response.text else "Unknown error"
                print(f"   {Colors.RED}✗{Colors.NC} API error {response.status_code}: {error_msg}")
                return False

        except requests.exceptions.Timeout:
            print(f"   {Colors.RED}✗{Colors.NC} Request timed out (>120s)")
            return False
        except Exception as e:
            print(f"   {Colors.RED}✗{Colors.NC} Error: {e}")
            return False

    def run_search_validation(self) -> bool:
        """Run all search query validations"""
        print("\n" + "="*80)
        print("SEARCH QUERY VALIDATION")
        print("="*80)

        all_passed = True

        # Test Clinical Trials queries
        ct_queries = self.load_search_queries("clinical_trials")
        if ct_queries:
            print(f"\n{Colors.BLUE}Clinical Trials Queries{Colors.NC} ({len(ct_queries)} queries)")
            print("-" * 40)

            for i, query in enumerate(ct_queries, 1):
                if self.validate_search_query(query, i, collections=["clinical_trials"]):
                    self.results['ct_search_passed'] += 1
                else:
                    self.results['ct_search_failed'] += 1

            # CT Summary
            total_ct = self.results['ct_search_passed'] + self.results['ct_search_failed']
            passed_ct = self.results['ct_search_passed']

            print(f"\n{'-'*40}")
            print(f"Clinical Trials: {passed_ct}/{total_ct} passed", end="")
            if passed_ct == total_ct:
                print(f" {Colors.GREEN}✓{Colors.NC}")
            else:
                print(f" {Colors.RED}✗{Colors.NC}")
                all_passed = False
            print(f"{'-'*40}")
        else:
            print(f"\n{Colors.YELLOW}No clinical trials queries found{Colors.NC}")

        # Test PubMed queries
        pubmed_queries = self.load_search_queries("pubmed")
        if pubmed_queries:
            print(f"\n{Colors.BLUE}PubMed Queries{Colors.NC} ({len(pubmed_queries)} queries)")
            print("-" * 40)

            for i, query in enumerate(pubmed_queries, 1):
                if self.validate_search_query(query, i, collections=["pubmed_abstracts"]):
                    self.results['pubmed_search_passed'] += 1
                else:
                    self.results['pubmed_search_failed'] += 1

            # PubMed Summary
            total_pubmed = self.results['pubmed_search_passed'] + self.results['pubmed_search_failed']
            passed_pubmed = self.results['pubmed_search_passed']

            print(f"\n{'-'*40}")
            print(f"PubMed: {passed_pubmed}/{total_pubmed} passed", end="")
            if passed_pubmed == total_pubmed:
                print(f" {Colors.GREEN}✓{Colors.NC}")
            else:
                print(f" {Colors.RED}✗{Colors.NC}")
                all_passed = False
            print(f"{'-'*40}")
        else:
            print(f"\n{Colors.YELLOW}No PubMed queries found{Colors.NC}")

        # Overall search summary
        total_search = (self.results['ct_search_passed'] + self.results['ct_search_failed'] +
                       self.results['pubmed_search_passed'] + self.results['pubmed_search_failed'])
        passed_search = self.results['ct_search_passed'] + self.results['pubmed_search_passed']

        print(f"\n{'='*80}")
        print(f"Overall Search Results: {passed_search}/{total_search} passed", end="")
        if all_passed:
            print(f" {Colors.GREEN}✓{Colors.NC}")
        else:
            print(f" {Colors.RED}✗{Colors.NC}")
        print(f"{'='*80}")

        # Check Tier 1 field coverage
        self.check_tier1_coverage()

        return all_passed

    def run_rag_validation(self) -> bool:
        """Run RAG query validations"""
        print("\n" + "="*80)
        print("RAG QUERY VALIDATION")
        print("="*80)

        # Generate RAG questions from both clinical trials and PubMed queries
        ct_queries = self.load_search_queries("clinical_trials")
        pubmed_queries = self.load_search_queries("pubmed")

        all_search_queries = ct_queries + pubmed_queries
        rag_questions = self.generate_rag_questions(all_search_queries)

        if not rag_questions:
            print(f"{Colors.YELLOW}No RAG questions to test{Colors.NC}")
            return True

        print(f"\nTesting {len(rag_questions)} RAG questions (from both CT and PubMed queries)...")

        for i, question in enumerate(rag_questions, 1):
            result = self.validate_rag_query(question, i)
            if result is True:
                self.results['rag_passed'] += 1
            elif result is False:
                self.results['rag_failed'] += 1
            else:  # None = skipped
                self.results['rag_skipped'] += 1
                # If first query is skipped, all will be, so break
                if i == 1:
                    print(f"\n{Colors.YELLOW}RAG not available - skipping remaining RAG tests{Colors.NC}")
                    break

        # Summary
        if self.results['rag_skipped'] > 0:
            print(f"\n{'-'*80}")
            print(f"RAG Results: Skipped (RAG not configured)")
            print(f"{'-'*80}")
            return True  # Don't fail if RAG not available
        else:
            total = self.results['rag_passed'] + self.results['rag_failed']
            passed = self.results['rag_passed']

            print(f"\n{'-'*80}")
            print(f"RAG Results: {passed}/{total} passed", end="")
            if passed == total:
                print(f" {Colors.GREEN}✓{Colors.NC}")
            else:
                print(f" {Colors.RED}✗{Colors.NC}")
            print(f"{'-'*80}")

            return self.results['rag_failed'] == 0

    def print_final_summary(self):
        """Print final test summary"""
        print("\n" + "="*80)
        print("FINAL RESULTS")
        print("="*80)

        # Search breakdown
        ct_total = self.results['ct_search_passed'] + self.results['ct_search_failed']
        pubmed_total = self.results['pubmed_search_passed'] + self.results['pubmed_search_failed']
        search_total = ct_total + pubmed_total
        search_passed = self.results['ct_search_passed'] + self.results['pubmed_search_passed']

        if ct_total > 0:
            print(f"Clinical Trials Search: {self.results['ct_search_passed']}/{ct_total} passed")
        if pubmed_total > 0:
            print(f"PubMed Search:          {self.results['pubmed_search_passed']}/{pubmed_total} passed")
        if search_total > 0:
            print(f"Total Search:           {search_passed}/{search_total} passed")

        # RAG
        if self.results['rag_skipped'] > 0:
            print(f"RAG:                    Skipped (not configured)")
        else:
            rag_total = self.results['rag_passed'] + self.results['rag_failed']
            if rag_total > 0:
                print(f"RAG:                    {self.results['rag_passed']}/{rag_total} passed")

        # Overall
        total_passed = search_passed + self.results['rag_passed']
        total_failed = (self.results['ct_search_failed'] + self.results['pubmed_search_failed'] +
                       self.results['rag_failed'])
        total_tests = total_passed + total_failed

        print(f"\n{'='*80}")
        print(f"TOTAL: {total_passed}/{total_tests} passed")

        if total_failed == 0:
            print(f"\n{Colors.GREEN}✓ All tests passed!{Colors.NC}")
        else:
            print(f"\n{Colors.RED}✗ {total_failed} test(s) failed{Colors.NC}")

        print("="*80 + "\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Validate BioYoda search and RAG queries",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--api-url',
        default='http://localhost:8000',
        help='API URL (default: http://localhost:8000)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output'
    )

    parser.add_argument(
        '--search-only',
        action='store_true',
        help='Only run search validation'
    )

    parser.add_argument(
        '--rag-only',
        action='store_true',
        help='Only run RAG validation'
    )

    args = parser.parse_args()

    # Initialize validator
    validator = QueryValidator(api_url=args.api_url, verbose=args.verbose)

    print("\n" + "="*80)
    print("BIOYODA QUERY VALIDATION")
    print("="*80)
    print(f"API URL: {args.api_url}")
    print()

    # Check API health
    if not validator.check_api_health():
        print(f"\n{Colors.RED}API not available - exiting{Colors.NC}\n")
        sys.exit(1)

    # Run validations
    search_passed = True
    rag_passed = True

    if not args.rag_only:
        search_passed = validator.run_search_validation()

    if not args.search_only:
        rag_passed = validator.run_rag_validation()

    # Print summary
    validator.print_final_summary()

    # Exit with failure if any tests failed
    if not (search_passed and rag_passed):
        sys.exit(1)


if __name__ == "__main__":
    main()

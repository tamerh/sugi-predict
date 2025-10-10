#!/usr/bin/env python3
"""
BioYoda Search CLI

Simple command-line tool to search biomedical literature using BioYoda API.

Usage:
    # Simple search
    ./bioyoda_search.py "CRISPR gene editing"

    # Search specific collection
    ./bioyoda_search.py "cancer treatment" --collection pubmed_abstracts

    # Limit results
    ./bioyoda_search.py "Alzheimer disease" --limit 5

    # Multi-collection search
    ./bioyoda_search.py "COVID-19 vaccine" --collection pubmed_abstracts clinical_trials

    # Interactive mode
    ./bioyoda_search.py --interactive
"""
import argparse
import requests
import sys
import json
from typing import List, Optional
from datetime import datetime


class BioYodaSearchCLI:
    """CLI interface for BioYoda Search API"""

    def __init__(self, api_url: str = "http://localhost:8000"):
        """Initialize CLI with API URL"""
        self.api_url = api_url.rstrip('/')
        self.check_api_health()

    def check_api_health(self):
        """Check if API is running and healthy"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                health = response.json()
                if health['status'] != 'healthy':
                    print(f"⚠️  API is {health['status']}")
                    if not health['qdrant_connected']:
                        print("   Qdrant is not connected!")
                    if not health['model_loaded']:
                        print("   Model is not loaded!")
            else:
                print(f"⚠️  API returned status code {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"❌ Error: Cannot connect to API at {self.api_url}")
            print("   Make sure the API is running:")
            print("   ./bioyoda.sh api start")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error checking API health: {e}")
            sys.exit(1)

    def search(
        self,
        query: str,
        collections: Optional[List[str]] = None,
        limit: int = 10,
        verbose: bool = False
    ) -> dict:
        """
        Perform search query

        Args:
            query: Search query string
            collections: List of collections to search (default: all)
            limit: Number of results per collection
            verbose: Show detailed information

        Returns:
            Search results dictionary
        """
        if collections is None:
            collections = ["pubmed_abstracts", "clinical_trials"]

        payload = {
            "query": query,
            "collections": collections,
            "limit": limit
        }

        try:
            response = requests.post(
                f"{self.api_url}/search",
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                error = response.json() if response.headers.get('content-type') == 'application/json' else response.text
                print(f"❌ Search failed (HTTP {response.status_code})")
                print(f"   {error}")
                return None

        except requests.exceptions.Timeout:
            print("❌ Search timed out (>30s)")
            return None
        except Exception as e:
            print(f"❌ Search error: {e}")
            return None

    def display_results(self, results: dict, verbose: bool = False):
        """
        Display search results in a readable format

        Args:
            results: Search results dictionary
            verbose: Show detailed information
        """
        if not results:
            return

        print("\n" + "="*80)
        print(f"Query: '{results['query']}'")
        print(f"Found {results['total_results']} results in {results['search_time_ms']:.2f}ms")
        print(f"Results per collection: {results['results_per_collection']}")
        print("="*80 + "\n")

        if results['total_results'] == 0:
            print("No results found.")
            return

        for idx, result in enumerate(results['results'], 1):
            # Extract common fields
            score = result['score']
            collection = result['collection']
            payload = result['payload']

            # Get source-specific fields
            if 'pmid' in payload:
                source_id = f"PMID: {payload['pmid']}"
            elif 'nct_id' in payload:
                source_id = f"NCT ID: {payload['nct_id']}"
            else:
                source_id = f"ID: {result['id']}"

            # Get text content
            text = payload.get('chunk_text', payload.get('text', 'No text available'))

            # Display result
            print(f"{idx}. [{collection}] {source_id}")
            print(f"   Score: {score:.4f}")

            # Show text preview (first 300 chars)
            if len(text) > 300:
                preview = text[:300] + "..."
            else:
                preview = text

            # Clean up text for display
            preview = preview.replace('\n', ' ').strip()
            print(f"   {preview}")

            if verbose:
                print(f"\n   Full payload:")
                for key, value in payload.items():
                    if key != 'chunk_text':  # Don't repeat full text
                        print(f"      {key}: {value}")

            print()

    def list_collections(self):
        """List available collections"""
        try:
            response = requests.get(f"{self.api_url}/collections", timeout=5)
            if response.status_code == 200:
                collections = response.json()

                print("\n" + "="*80)
                print("Available Collections")
                print("="*80 + "\n")

                for coll in collections:
                    print(f"📚 {coll['display_name']} ({coll['name']})")
                    print(f"   {coll['description']}")
                    print(f"   Documents: {coll['points_count']:,}")
                    print(f"   Status: {coll['status']}")
                    print(f"   Vector size: {coll['vector_size']}")
                    print()

            else:
                print(f"❌ Failed to list collections (HTTP {response.status_code})")

        except Exception as e:
            print(f"❌ Error listing collections: {e}")

    def interactive_mode(self):
        """Interactive search mode"""
        print("\n" + "="*80)
        print("BioYoda Search - Interactive Mode")
        print("="*80)
        print("\nCommands:")
        print("  search <query>     - Search all collections")
        print("  pubmed <query>     - Search PubMed only")
        print("  trials <query>     - Search Clinical Trials only")
        print("  collections        - List available collections")
        print("  help               - Show this help")
        print("  quit / exit        - Exit interactive mode")
        print("\nType your search query or command:")
        print()

        while True:
            try:
                user_input = input("bioyoda> ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("Goodbye!")
                    break

                if user_input.lower() == 'help':
                    print("\nCommands:")
                    print("  search <query>     - Search all collections")
                    print("  pubmed <query>     - Search PubMed only")
                    print("  trials <query>     - Search Clinical Trials only")
                    print("  collections        - List available collections")
                    print("  quit / exit        - Exit\n")
                    continue

                if user_input.lower() == 'collections':
                    self.list_collections()
                    continue

                # Parse command
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                query = parts[1] if len(parts) > 1 else ""

                if command == 'search':
                    if query:
                        results = self.search(query)
                        self.display_results(results)
                    else:
                        print("Usage: search <query>")

                elif command == 'pubmed':
                    if query:
                        results = self.search(query, collections=["pubmed_abstracts"])
                        self.display_results(results)
                    else:
                        print("Usage: pubmed <query>")

                elif command == 'trials':
                    if query:
                        results = self.search(query, collections=["clinical_trials"])
                        self.display_results(results)
                    else:
                        print("Usage: trials <query>")

                else:
                    # Treat entire input as search query
                    results = self.search(user_input)
                    self.display_results(results)

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="BioYoda Search CLI - Search biomedical literature",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple search
  %(prog)s "CRISPR gene editing"

  # Search specific collection
  %(prog)s "cancer treatment" --collection pubmed_abstracts

  # Limit results
  %(prog)s "Alzheimer disease" --limit 5

  # Interactive mode
  %(prog)s --interactive

  # List collections
  %(prog)s --list-collections
        """
    )

    parser.add_argument(
        'query',
        nargs='?',
        help='Search query string'
    )

    parser.add_argument(
        '--collection',
        '-c',
        nargs='+',
        help='Collection(s) to search (default: all)'
    )

    parser.add_argument(
        '--limit',
        '-l',
        type=int,
        default=10,
        help='Number of results per collection (default: 10)'
    )

    parser.add_argument(
        '--api-url',
        default='http://localhost:8000',
        help='API URL (default: http://localhost:8000)'
    )

    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Show detailed results'
    )

    parser.add_argument(
        '--interactive',
        '-i',
        action='store_true',
        help='Interactive mode'
    )

    parser.add_argument(
        '--list-collections',
        action='store_true',
        help='List available collections'
    )

    parser.add_argument(
        '--json',
        action='store_true',
        help='Output raw JSON results'
    )

    args = parser.parse_args()

    # Initialize CLI
    cli = BioYodaSearchCLI(api_url=args.api_url)

    # List collections
    if args.list_collections:
        cli.list_collections()
        return

    # Interactive mode
    if args.interactive:
        cli.interactive_mode()
        return

    # Require query for non-interactive mode
    if not args.query:
        parser.print_help()
        sys.exit(1)

    # Perform search
    results = cli.search(
        query=args.query,
        collections=args.collection,
        limit=args.limit,
        verbose=args.verbose
    )

    if results:
        if args.json:
            # Output raw JSON
            print(json.dumps(results, indent=2))
        else:
            # Display formatted results
            cli.display_results(results, verbose=args.verbose)


if __name__ == "__main__":
    main()

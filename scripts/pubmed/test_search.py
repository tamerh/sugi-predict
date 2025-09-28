#!/usr/bin/env python3
"""
Terminal-based FAISS Search Client for BioYoda
Tests the PubMed FAISS index and metadata directly without needing a web server.
"""

import os
import json
import faiss
import numpy as np
import argparse
from sentence_transformers import SentenceTransformer
from datetime import datetime
from typing import List, Dict, Tuple

class BioYodaSearchClient:
    def __init__(self, index_path: str, metadata_path: str, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize the search client with FAISS index and metadata."""
        self.model_name = model_name
        self.index_path = index_path
        self.metadata_path = metadata_path

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading model: {model_name}")
        self.model = SentenceTransformer(model_name)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading FAISS index: {index_path}")
        self.index = faiss.read_index(index_path)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading metadata: {metadata_path}")
        with open(metadata_path, 'r') as f:
            self.metadata = json.load(f)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Ready! Index contains {self.index.ntotal:,} vectors")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Metadata contains {len(self.metadata):,} entries")

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Perform semantic search on the FAISS index."""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Searching for: '{query}'")

        # Encode the query
        query_vector = self.model.encode([query])[0]
        query_vector = query_vector.reshape(1, -1).astype('float32')

        # Search the index
        distances, indices = self.index.search(query_vector, top_k)

        results = []
        for i in range(min(top_k, len(indices[0]))):
            idx = int(indices[0][i])
            distance = float(distances[0][i])

            # Get metadata for this result
            metadata_key = str(idx)
            if metadata_key in self.metadata:
                metadata_item = self.metadata[metadata_key]

                # Convert L2 distance to similarity score (0-1, higher is better)
                similarity = 1 / (1 + distance)

                results.append({
                    'rank': i + 1,
                    'pmid': metadata_item['pmid'],
                    'similarity': similarity,
                    'distance': distance,
                    'text': metadata_item['chunk_text']
                })
            else:
                print(f"Warning: No metadata found for index {idx}")

        return results

    def display_results(self, results: List[Dict], show_full_text: bool = False):
        """Display search results in a formatted way."""
        if not results:
            print("No results found.")
            return

        print(f"\n{'='*80}")
        print(f"Found {len(results)} results:")
        print(f"{'='*80}")

        for result in results:
            print(f"\n[{result['rank']}] PMID: {result['pmid']}")
            print(f"    Similarity: {result['similarity']:.4f} | Distance: {result['distance']:.4f}")

            # Extract title and abstract
            text = result['text']
            if text.startswith("Title: "):
                parts = text.split("\nAbstract: ", 1)
                title = parts[0].replace("Title: ", "")
                abstract = parts[1] if len(parts) > 1 else ""

                print(f"    Title: {title}")

                if show_full_text:
                    print(f"    Abstract: {abstract}")
                else:
                    # Show first 200 chars of abstract
                    preview = abstract[:200] + "..." if len(abstract) > 200 else abstract
                    print(f"    Abstract: {preview}")
            else:
                preview = text[:300] + "..." if len(text) > 300 else text
                print(f"    Text: {preview}")

            print("-" * 80)

    def interactive_search(self):
        """Start an interactive search session."""
        print(f"\n{'='*60}")
        print("BioYoda Interactive Search")
        print(f"{'='*60}")
        print("Commands:")
        print("  - Enter a search query to find relevant papers")
        print("  - 'help' for more options")
        print("  - 'quit' or 'exit' to quit")
        print(f"{'='*60}")

        while True:
            try:
                query = input("\n🔍 Search query: ").strip()

                if query.lower() in ['quit', 'exit', 'q']:
                    print("Goodbye!")
                    break

                if query.lower() == 'help':
                    print("\nAvailable commands:")
                    print("  search <query>      - Search for papers")
                    print("  full <query>        - Search with full text display")
                    print("  top10 <query>       - Show top 10 results")
                    print("  stats               - Show index statistics")
                    print("  help                - Show this help")
                    print("  quit/exit           - Exit the program")
                    continue

                if query.lower() == 'stats':
                    print(f"\nIndex Statistics:")
                    print(f"  Total vectors: {self.index.ntotal:,}")
                    print(f"  Vector dimension: {self.index.d}")
                    print(f"  Metadata entries: {len(self.metadata):,}")
                    print(f"  Model: {self.model_name}")
                    continue

                if not query:
                    continue

                # Parse commands
                show_full = False
                top_k = 5

                if query.startswith('full '):
                    show_full = True
                    query = query[5:]
                elif query.startswith('top10 '):
                    top_k = 10
                    query = query[6:]

                if not query.strip():
                    print("Please enter a search query.")
                    continue

                # Perform search
                results = self.search(query, top_k)
                self.display_results(results, show_full_text=show_full)

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="BioYoda Terminal Search Client")
    parser.add_argument("--index", "-i",
                       default="../../results_all-MiniLM-L6-v2/pubmed/master_pubmed_merge3.index",
                       help="Path to FAISS index file")
    parser.add_argument("--metadata", "-m",
                       default="../../results_all-MiniLM-L6-v2/pubmed/master_metadata_mergee3.json",
                       help="Path to metadata JSON file")
    parser.add_argument("--model",
                       default="all-MiniLM-L6-v2",
                       help="Sentence transformer model name")
    parser.add_argument("--query", "-q",
                       help="Single query to search (non-interactive mode)")
    parser.add_argument("--top-k", "-k", type=int, default=5,
                       help="Number of results to return")
    parser.add_argument("--full-text", "-f", action="store_true",
                       help="Show full text in results")

    args = parser.parse_args()

    # Check if files exist
    if not os.path.exists(args.index):
        print(f"Error: Index file not found: {args.index}")
        return 1

    if not os.path.exists(args.metadata):
        print(f"Error: Metadata file not found: {args.metadata}")
        return 1

    try:
        # Initialize client
        client = BioYodaSearchClient(args.index, args.metadata, args.model)

        if args.query:
            # Single query mode
            results = client.search(args.query, args.top_k)
            client.display_results(results, show_full_text=args.full_text)
        else:
            # Interactive mode
            client.interactive_search()

    except Exception as e:
        print(f"Error initializing client: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
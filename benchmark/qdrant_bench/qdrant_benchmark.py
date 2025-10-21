#!/usr/bin/env python3
"""
Simple Qdrant Performance Benchmark Script
Tests search performance with different configurations
"""

import sys
import time
import json
import argparse
from pathlib import Path
from typing import List, Dict
import requests

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient


# Test queries - mix of simple and complex
TEST_QUERIES = [
    "CRISPR gene editing",
    "Alzheimer disease treatment",
    "COVID-19 vaccine efficacy",
    "cancer immunotherapy",
    "diabetes type 2 management",
    "heart failure biomarkers",
    "antibiotic resistance mechanisms",
    "neural network deep learning",
    "protein folding structure",
    "RNA sequencing analysis"
]


def load_model(model_name: str):
    """Load embedding model"""
    print(f"Loading model: {model_name}...")
    start = time.time()
    model = SentenceTransformer(model_name)
    print(f"Model loaded in {time.time() - start:.2f}s")
    return model


def benchmark_search(
    qdrant_url: str,
    collection_name: str,
    model: SentenceTransformer,
    queries: List[str],
    limit: int = 10,
    ef: int = None,
    timeout: int = 180
) -> Dict:
    """Run benchmark searches"""

    client = QdrantClient(url=qdrant_url, timeout=timeout)

    # Get collection info
    try:
        collection_info = client.get_collection(collection_name)

        # Get vector counts (use points_count as primary, fall back to vectors_count)
        vectors_count = 0
        indexed_vectors_count = 0

        if hasattr(collection_info, 'points_count') and collection_info.points_count:
            vectors_count = collection_info.points_count
        elif hasattr(collection_info, 'vectors_count') and collection_info.vectors_count:
            vectors_count = collection_info.vectors_count

        if hasattr(collection_info, 'indexed_vectors_count') and collection_info.indexed_vectors_count:
            indexed_vectors_count = collection_info.indexed_vectors_count
        else:
            # If no indexed_vectors_count, assume all are indexed when status is green
            if collection_info.status == "green":
                indexed_vectors_count = vectors_count

        # Get collection status
        status = collection_info.status

        # Get segments count
        segments_count = 0
        if hasattr(collection_info, 'segments_count'):
            segments_count = collection_info.segments_count
        elif hasattr(collection_info, 'points_count'):
            # Try to get from collection config
            try:
                segments_count = len(collection_info.payload_schema) if hasattr(collection_info, 'payload_schema') else 0
            except:
                segments_count = 0

        # Color code status
        status_color = {
            'green': '\033[0;32m',
            'yellow': '\033[1;33m',
            'red': '\033[0;31m',
            'grey': '\033[0;90m'
        }.get(status.lower(), '')
        reset_color = '\033[0m'

        print(f"\nCollection: {collection_name}")
        print(f"Status: {status_color}{status.upper()}{reset_color}")
        print(f"Vectors: {vectors_count:,} (indexed: {indexed_vectors_count:,})")
        if segments_count > 0:
            print(f"Segments: {segments_count}")
        print(f"Timeout: {timeout}s")
        if ef:
            print(f"HNSW ef: {ef}")

        # Store collection metadata
        collection_metadata = {
            "status": status,
            "vectors_count": vectors_count,
            "indexed_vectors_count": indexed_vectors_count,
            "segments_count": segments_count,
        }
    except Exception as e:
        print(f"Error getting collection info: {e}")
        return {"error": str(e)}

    results = []
    total_time = 0

    print(f"\nRunning {len(queries)} test queries...")
    print("-" * 60)

    for i, query in enumerate(queries, 1):
        try:
            # Encode query
            encode_start = time.time()
            query_vector = model.encode(query).tolist()
            encode_time = time.time() - encode_start

            # Search
            search_start = time.time()

            # Build search params
            search_params = None
            if ef is not None:
                from qdrant_client.models import SearchParams
                search_params = SearchParams(hnsw_ef=ef, exact=False)

            search_results = client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                search_params=search_params
            )

            search_time = time.time() - search_start
            total_time_query = encode_time + search_time
            total_time += total_time_query

            # Print result
            print(f"{i}. '{query[:50]}...'")
            print(f"   Encode: {encode_time*1000:.0f}ms | Search: {search_time*1000:.0f}ms | Total: {total_time_query*1000:.0f}ms")
            print(f"   Top score: {search_results[0].score:.3f}")

            results.append({
                "query": query,
                "encode_time_ms": encode_time * 1000,
                "search_time_ms": search_time * 1000,
                "total_time_ms": total_time_query * 1000,
                "top_score": search_results[0].score,
                "results_count": len(search_results)
            })

        except Exception as e:
            print(f"{i}. '{query[:50]}...' - ERROR: {e}")
            results.append({
                "query": query,
                "error": str(e)
            })

    # Summary
    print("-" * 60)
    avg_time = total_time / len(queries) if results else 0
    successful = len([r for r in results if "error" not in r])

    print(f"\nSummary:")
    print(f"  Successful: {successful}/{len(queries)}")
    print(f"  Average time: {avg_time*1000:.0f}ms")
    print(f"  Total time: {total_time:.2f}s")

    return {
        "collection": collection_name,
        "collection_status": collection_metadata["status"],
        "vectors_count": collection_metadata["vectors_count"],
        "indexed_vectors_count": collection_metadata["indexed_vectors_count"],
        "segments_count": collection_metadata["segments_count"],
        "queries": len(queries),
        "successful": successful,
        "average_time_ms": avg_time * 1000,
        "total_time_s": total_time,
        "ef": ef,
        "limit": limit,
        "timeout": timeout,
        "results": results
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark Qdrant search performance")
    parser.add_argument("--qdrant-url", default="http://localhost:6333", help="Qdrant server URL")
    parser.add_argument("--collection", default="pubmed_abstracts", help="Collection name")
    parser.add_argument("--model", default="pritamdeka/S-BioBERT-snli-multinli-stsb", help="Embedding model")
    parser.add_argument("--limit", type=int, default=10, help="Results per query")
    parser.add_argument("--ef", type=int, help="HNSW ef parameter (default: Qdrant default)")
    parser.add_argument("--timeout", type=int, default=180, help="Client timeout in seconds")
    parser.add_argument("--queries", nargs="+", help="Custom queries (default: use built-in)")
    parser.add_argument("--output", help="Output JSON file for results")

    args = parser.parse_args()

    # Load model
    model = load_model(args.model)

    # Use custom or default queries
    queries = args.queries if args.queries else TEST_QUERIES

    # Run benchmark
    print(f"\n{'='*60}")
    print(f"QDRANT SEARCH BENCHMARK")
    print(f"{'='*60}")

    results = benchmark_search(
        qdrant_url=args.qdrant_url,
        collection_name=args.collection,
        model=model,
        queries=queries,
        limit=args.limit,
        ef=args.ef,
        timeout=args.timeout
    )

    # Save results
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {output_path}")

    # Exit code based on success
    if results.get("error"):
        sys.exit(1)

    avg_time = results.get("average_time_ms", 0)
    if avg_time > 10000:  # > 10 seconds
        print("\n⚠️  SLOW: Average query time > 10s")
        sys.exit(1)
    elif avg_time > 5000:  # > 5 seconds
        print("\n⚠️  MODERATE: Average query time > 5s")
        sys.exit(0)
    else:
        print("\n✓ FAST: Average query time < 5s")
        sys.exit(0)


if __name__ == "__main__":
    main()

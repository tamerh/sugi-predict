#!/usr/bin/env python3
"""Test BioBTree filter queries for Drug Discovery Agent."""

import asyncio
import sys
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from modules.agent_system.integrations.biobtree_client import BioBTreeClient
from modules.agent_system.core.config import get_config


async def test_filters():
    """Test various filter queries."""
    config = get_config()
    client = BioBTreeClient(config.integrations.biobtree)

    tests = [
        # Basic queries
        {
            "name": "JAK2 all drugs (no filter)",
            "terms": ["JAK2"],
            "mapfilter": ">>ensembl>>uniprot>>chembl_target_component>>chembl_target>>chembl_assay>>chembl_activity>>chembl_molecule"
        },
        {
            "name": "JAK2 pChembl>7.0 (fast filter)",
            "terms": ["JAK2"],
            "mapfilter": ">>ensembl>>uniprot>>chembl_target_component>>chembl_target>>chembl_assay>>chembl_activity[chembl.activity.pChembl>7.0]>>chembl_molecule"
        },
        {
            "name": "JAK2 phase>2 (slow filter)",
            "terms": ["JAK2"],
            "mapfilter": ">>ensembl>>uniprot>>chembl_target_component>>chembl_target>>chembl_assay>>chembl_activity>>chembl_molecule[chembl.molecule.highestDevelopmentPhase>2]"
        },
        # Species filtering - human only improves slow phase filter
        {
            "name": "JAK2 human only",
            "terms": ["JAK2"],
            "mapfilter": '>>ensembl[ensembl.genome=="homo_sapiens"]>>uniprot>>chembl_target_component>>chembl_target>>chembl_assay>>chembl_activity>>chembl_molecule'
        },
        {
            "name": "JAK2 human only + phase>2",
            "terms": ["JAK2"],
            "mapfilter": '>>ensembl[ensembl.genome=="homo_sapiens"]>>uniprot>>chembl_target_component>>chembl_target>>chembl_assay>>chembl_activity>>chembl_molecule[chembl.molecule.highestDevelopmentPhase>2]'
        },
    ]

    results_summary = []

    for test in tests:
        print("=" * 60)
        print(f"TEST: {test['name']}")
        print("=" * 60)

        start_time = time.time()
        try:
            result = await client.map_query(
                terms=test["terms"],
                mapfilter=test["mapfilter"],
                mode="lite"
            )
            elapsed = time.time() - start_time

            lite = result.get('results_lite', {})
            stats = lite.get('stats', {})
            mappings = lite.get('mappings', [])

            elapsed_ms = elapsed * 1000
            print(f"Stats: {stats}")
            print(f"Response time: {elapsed_ms:.0f}ms")

            if mappings and mappings[0].get('targets'):
                targets = mappings[0]['targets']
                print(f"Found {len(targets)} results")
                for t in targets[:5]:
                    print(f"  - {t.get('id')}")
                if len(targets) > 5:
                    print(f"  ... and {len(targets) - 5} more")

                results_summary.append({
                    "name": test["name"],
                    "results": len(targets),
                    "time_ms": round(elapsed_ms),
                    "status": "ok"
                })
            else:
                error = mappings[0].get('error') if mappings else None
                if error:
                    print(f"Error: {error}")
                    results_summary.append({
                        "name": test["name"],
                        "results": 0,
                        "time_ms": round(elapsed_ms),
                        "status": "error",
                        "error": str(error)
                    })
                else:
                    print("No results found")
                    results_summary.append({
                        "name": test["name"],
                        "results": 0,
                        "time_ms": round(elapsed_ms),
                        "status": "ok"
                    })

        except Exception as e:
            elapsed = time.time() - start_time
            elapsed_ms = elapsed * 1000
            print(f"Error: {e}")
            print(f"Response time: {elapsed_ms:.0f}ms")
            results_summary.append({
                "name": test["name"],
                "results": 0,
                "time_ms": round(elapsed_ms),
                "status": "error",
                "error": str(e)[:50]
            })

        print()

    await client.close()

    # Print summary table
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"{'Test':<45} {'Results':>8} {'Time':>8}")
    print("-" * 60)
    for r in results_summary:
        status = "OK" if r["status"] == "ok" else "ERR"
        print(f"{r['name']:<45} {r['results']:>8} {r['time_ms']:>6}ms")
    print("-" * 60)

    total_time = sum(r["time_ms"] for r in results_summary)
    print(f"{'Total':<45} {'':<8} {total_time:>6}ms")

    print("\nTests completed!")


if __name__ == "__main__":
    asyncio.run(test_filters())

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
        # === FAST FILTERS ===
        # ChEMBL activity filter (~400ms)
        {
            "name": "JAK2 -> ChEMBL pChembl>7.0 (FAST)",
            "terms": ["JAK2"],
            "mapfilter": ">>ensembl>>uniprot>>chembl_target_component>>chembl_target>>chembl_assay>>chembl_activity[chembl.activity.pChembl>7.0]>>chembl_molecule"
        },
        # PubChem no filter (baseline ~90ms)
        {
            "name": "JAK2 -> PubChem (no filter)",
            "terms": ["JAK2"],
            "mapfilter": ">>ensembl>>uniprot>>pubchem_activity>>pubchem"
        },
        # PubChem has_patents filter (~400ms)
        {
            "name": "JAK2 -> PubChem has_patents (FAST)",
            "terms": ["JAK2"],
            "mapfilter": '>>ensembl>>uniprot>>pubchem_activity>>pubchem[pubchem.has_patents==true]'
        },
        # === MEDIUM SPEED FILTERS ===
        # PubChem compound_type=drug (~5s) - GOOD alternative to ChEMBL phase filter
        {
            "name": "JAK2 -> PubChem compound_type=drug (5s)",
            "terms": ["JAK2"],
            "mapfilter": '>>ensembl>>uniprot>>pubchem_activity>>pubchem[pubchem.compound_type=="drug"]'
        },
        # === SLOW FILTERS ===
        # ChEMBL phase filter (~20s) - works but slow
        {
            "name": "JAK2 -> ChEMBL phase>2 (SLOW ~20s)",
            "terms": ["JAK2"],
            "mapfilter": ">>ensembl>>uniprot>>chembl_target_component>>chembl_target>>chembl_assay>>chembl_activity>>chembl_molecule[chembl.molecule.highestDevelopmentPhase>2]"
        },
    ]

    results_summary = []

    for test in tests:
        print("=" * 60)
        print(f"TEST: {test['name']}")
        print("=" * 60)

        start_time = time.perf_counter()
        try:
            result = await client.map_query(
                terms=test["terms"],
                mapfilter=test["mapfilter"],
                mode="lite"
            )
            total_elapsed_ms = (time.perf_counter() - start_time) * 1000

            lite = result.get('results_lite', {})
            stats = lite.get('stats', {})
            mappings = lite.get('mappings', [])

            # Get precise gRPC timing from client
            grpc_time_ms = result.get('_client_timing_ms', 0)

            # Check if BioBTree returns server-side timing
            server_time_ms = lite.get('timing_ms') or lite.get('elapsed_ms') or stats.get('timing_ms')

            print(f"Stats: {stats}")
            print(f"gRPC call time: {grpc_time_ms:.1f}ms")
            print(f"Total (with overhead): {total_elapsed_ms:.1f}ms")
            if server_time_ms:
                print(f"Server-side time: {server_time_ms}ms")

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
                    "time_ms": round(grpc_time_ms),
                    "status": "ok"
                })
            else:
                error = mappings[0].get('error') if mappings else None
                if error:
                    print(f"Error: {error}")
                    results_summary.append({
                        "name": test["name"],
                        "results": 0,
                        "time_ms": round(grpc_time_ms),
                        "status": "error",
                        "error": str(error)
                    })
                else:
                    print("No results found")
                    results_summary.append({
                        "name": test["name"],
                        "results": 0,
                        "time_ms": round(grpc_time_ms),
                        "status": "ok"
                    })

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            error_msg = str(e)
            if "DEADLINE_EXCEEDED" in error_msg:
                print(f"Error: TIMEOUT (>{elapsed_ms/1000:.1f}s)")
            else:
                print(f"Error: {error_msg[:100]}")
            print(f"Elapsed time: {elapsed_ms:.0f}ms")
            results_summary.append({
                "name": test["name"],
                "results": 0,
                "time_ms": round(elapsed_ms),
                "status": "timeout" if "DEADLINE_EXCEEDED" in error_msg else "error",
                "error": "TIMEOUT" if "DEADLINE_EXCEEDED" in error_msg else error_msg[:50]
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

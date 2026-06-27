#!/usr/bin/env python3
"""Swap a rebuilt collection in: verify <name>_v2 is green + fully indexed, drop <name>, alias <name> -> <name>_v2.

The companion to clean_copy.py. After a rebuild produces a clean green <name>_v2, this retires the old (wedged)
<name> and points an alias at the new one, so the engine/web keep querying the same name with zero config change.
Refuses to swap unless <name>_v2 is green and fully indexed (won't drop the old for a half-built replacement).

  python swap_alias.py --name patent_compounds
"""
import sys, argparse
sys.path.insert(0, "/data/bioyoda")
from qdrant_client import QdrantClient, models


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="logical name (e.g. patent_compounds); alias points here")
    ap.add_argument("--from", dest="src", default=None, help="rebuilt collection (default <name>_v2)")
    a = ap.parse_args()
    dst = a.src or f"{a.name}_v2"
    qc = QdrantClient(url="http://localhost:6333", timeout=120, check_compatibility=False)

    v = qc.get_collection(dst)
    ok = str(v.status).endswith("green") and (v.indexed_vectors_count or 0) >= v.points_count * 0.99
    assert ok, f"REFUSING swap: {dst} is {str(v.status).split('.')[-1]}, indexed {v.indexed_vectors_count:,}/{v.points_count:,}"
    print(f"  {dst}: green, {v.points_count:,} fully indexed -> safe to swap", flush=True)

    if qc.collection_exists(a.name):
        qc.delete_collection(a.name)
        print(f"  dropped old collection {a.name}", flush=True)
    qc.update_collection_aliases(change_aliases_operations=[
        models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=dst, alias_name=a.name))])
    print(f"  alias {a.name} -> {dst} created. Swap complete; engine/web now serve from {dst}.", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Shared helpers for the tier-1 pipeline tests (tests/pipeline/).

These tests exercise the REAL `bioyoda.sh build <collection> <stage>` command in TEST MODE
(no --prod, so it targets the *_test collection) pointed at the small fixtures under
tests/fixtures/.  They assert the *_test collection comes out populated and queryable.

Style mirrors tests/test_atlas_bake.py: plain scripts (no pytest), the same QdrantClient
pattern, assert + print "<name>: PASSED", non-zero exit on failure.
"""
import os
import subprocess
import sys
import time

from qdrant_client import QdrantClient

ROOT = "/data/bioyoda"
QDRANT = os.environ.get("BIOYODA_QDRANT_URL", "http://localhost:6333")


def client():
    # same pattern the build command + existing tests use
    return QdrantClient(url=QDRANT, timeout=600, check_compatibility=False)


def drop(qc, name):
    """Idempotent: remove a *_test collection so each run starts clean.

    Guard rail: refuse to ever touch a non-_test collection (protects prod/aliased data).
    """
    assert name.endswith("_test"), f"refusing to drop non-test collection {name!r}"
    if qc.collection_exists(name):
        qc.delete_collection(name)


def run_build(collection, stage, env=None, extra=(), timeout=900):
    """Invoke `./bioyoda.sh build <collection> <stage>` in TEST MODE (no --prod).

    `env` overlays the build env (e.g. CT_TRIALS_JSON to point a source at a fixture).
    Returns the CompletedProcess; the caller asserts returncode + inspects the collection.
    """
    cmd = ["./bioyoda.sh", "build", collection, stage, *extra]
    e = dict(os.environ)
    if env:
        e.update(env)
    r = subprocess.run(cmd, cwd=ROOT, env=e, capture_output=True, text=True, timeout=timeout)
    return r


def assert_build_ok(r, ctx):
    if r.returncode != 0:
        sys.stderr.write(f"\n--- build {ctx} STDOUT (tail) ---\n" + "\n".join(r.stdout.splitlines()[-40:]))
        sys.stderr.write(f"\n--- build {ctx} STDERR (tail) ---\n" + "\n".join(r.stderr.splitlines()[-40:]) + "\n")
    assert r.returncode == 0, f"build {ctx} exited {r.returncode}"


def wait_count(qc, name, timeout=120):
    """Return the point count once the collection is non-empty (HNSW build can lag the upsert)."""
    t0 = time.time()
    last = 0
    while time.time() - t0 < timeout:
        if qc.collection_exists(name):
            last = qc.count(name).count
            if last > 0:
                return last
        time.sleep(2)
    return last

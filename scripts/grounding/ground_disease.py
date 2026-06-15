#!/usr/bin/env python3
"""Ground free-text disease/condition strings to MONDO CURIEs — fast, deterministic,
CPU-only, dependency-light. The grounding-as-payload feature: attach canonical ontology
IDs to BioYoda's (predictive) hits so a prediction is traceable to ground truth.

Uses the MONDO SemSQL SQLite that oaklib downloads to ~/.data/oaklib/mondo.db. Builds an
in-memory {normalized label/synonym -> MONDO id} index (~1s, ~93k keys), then O(1) lookups
with light normalization + a few morphological fallbacks. No network, no LLM, no GPU.

  from scripts.grounding.ground_disease import DiseaseGrounder
  g = DiseaseGrounder()
  g.ground("Hepatocellular Carcinoma")  -> ("MONDO:0007256", "hepatocellular carcinoma")
"""
import os, re, sqlite3
from functools import lru_cache

MONDO_DB = os.environ.get("MONDO_DB", os.path.expanduser("~/.data/oaklib/mondo.db"))
_WS = re.compile(r"\s+")


_QUAL_TAIL = re.compile(r"\s*,?\s*\(?(unspecified|nos|disorder|disease|condition|finding)\)?$")


def _norm(s):
    # Treat hyphens as spaces and drop apostrophes so "triple-negative" == "triple negative"
    # and "Crohn's" == "crohns" — applied to BOTH index keys and queries for consistency.
    s = s.replace("-", " ").replace("'", "")
    return _WS.sub(" ", s.strip().lower())


def _variants(s):
    """Light morphological/qualifier variants to improve recall without fuzzy matching."""
    n = _norm(s)
    yield n
    # strip a trailing qualifier like ", unspecified" / "(disorder)"
    stripped = _QUAL_TAIL.sub("", n).strip()
    if stripped and stripped != n:
        yield stripped
    if n.endswith("s"):
        yield n[:-1]                      # carcinomas -> carcinoma


class DiseaseGrounder:
    def __init__(self, db_path=MONDO_DB):
        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"MONDO db not found at {db_path}. Run once: python -c "
                f"\"from oaklib import get_adapter; get_adapter('sqlite:obo:mondo')\"")
        self.db_path = db_path
        self.idx = {}
        self.labels = {}
        con = sqlite3.connect(db_path)
        # labels first (authoritative), then exact synonyms (don't overwrite a label key)
        for subj, val in con.execute(
                "SELECT subject,value FROM statements WHERE predicate='rdfs:label' "
                "AND subject LIKE 'MONDO:%' AND value IS NOT NULL"):
            self.labels[subj] = val
            self.idx.setdefault(_norm(val), subj)
        for subj, val in con.execute(
                "SELECT subject,value FROM statements WHERE predicate='oio:hasExactSynonym' "
                "AND subject LIKE 'MONDO:%' AND value IS NOT NULL"):
            self.idx.setdefault(_norm(val), subj)
        con.close()

    @lru_cache(maxsize=100000)
    def ground(self, text):
        """Return (MONDO_id, label) or (None, None)."""
        if not text:
            return (None, None)
        for v in _variants(text):
            mid = self.idx.get(v)
            if mid:
                return (mid, self.labels.get(mid))
        return (None, None)

    def ground_many(self, terms):
        """Map a list of condition strings -> deduped list of MONDO ids (unmatched dropped)."""
        out = []
        for t in terms or []:
            mid, _ = self.ground(t)
            if mid and mid not in out:
                out.append(mid)
        return out


if __name__ == "__main__":
    import sys
    g = DiseaseGrounder()
    print(f"MONDO index: {len(g.idx):,} keys, {len(g.labels):,} classes")
    for t in (sys.argv[1:] or ["Hepatocellular Carcinoma", "Triple Negative Breast Cancer",
                               "Type 2 Diabetes", "Crohn's Disease", "COVID-19"]):
        print(f"  {t!r} -> {g.ground(t)}")

#!/usr/bin/env python3
"""Canonicalize raw SureChEMBL patent-assignee strings for display + grouping.

The raw strings are messy ("AMIRA PHARMACEUTICALS, INC. (US)", "Amira Pharmaceuticals, Inc. (US)",
"AMIRA PHARMACEUTICALS INC" ...). This collapses the formatting variants to one name by dropping the
trailing country code and legal-form suffixes and title-casing. It does NOT merge semantic aliases or
abbreviations (e.g. "Du Pont" vs "E I Du Pont De Nemours") -- those go in ALIASES, a small curated map
for the top filers, extended as needed. Step toward the priority-date / family enrichment (EPO OPS).
"""
import re

_LEGAL = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "llc", "lp",
          "llp", "plc", "ag", "gmbh", "mbh", "sa", "nv", "kg", "kgaa", "ab", "oy", "oyj", "spa", "bv",
          "pty", "pte", "srl", "aps", "as", "kk", "ulc", "pc", "pllc", "sas", "sl", "lda", " aps"}

# Curated aliases for variants the rules can't merge (abbreviations / spelling). Keys are canon() output.
ALIASES = {
    "E I Du Pont De Nemours": "Du Pont",
    "Du Pont De Nemours": "Du Pont",
    "Amira Phamaceuticals": "Amira Pharmaceuticals",   # common SureChEMBL typo
}


def canon(raw):
    """Raw assignee string -> a clean, display-ready canonical name ('' for empty)."""
    if not raw:
        return ""
    s = re.sub(r"\s*\([A-Za-z]{2}\)\s*$", "", raw)              # trailing country code "(US)"
    s = re.sub(r"[._,]", " ", s).replace("&", " and ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    toks = s.split()
    changed = True
    while changed and toks:                                     # strip trailing legal forms + dangling "and"
        changed = False
        if toks[-1].lower() in _LEGAL:
            toks.pop(); changed = True
        elif toks[-1].lower() == "and":
            toks.pop(); changed = True
    out = " ".join(toks).title()
    return ALIASES.get(out, out)

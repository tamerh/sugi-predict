#!/usr/bin/env python3
"""EPO OPS (Open Patent Services) enrichment: priority date, filing date, normalized applicant per patent.

SureChEMBL gives a PUBLICATION date (lags the real invention by ~18mo to years) + raw assignee strings.
EPO OPS adds the PRIORITY date (the true earliest claim), the FILING date, and the normalized applicant.

Credentials: config/epo.json {"consumer_key","consumer_secret"} (gitignored) or env EPO_KEY/EPO_SECRET.
The free tier is quota-limited, so results CACHE to work/epo_cache/<epodoc>.json and enrichment is meant to be
LAZY (on view), not a bulk 40M-patent job. EPO's JSON nests inconsistently (dict-or-list, text under "$"),
so the parser is defensive.

  from modules.patents.epo_enrich import enrich
  enrich("US-20260146232-A1")   -> {"priority_date","filing_date","applicants",...}  or None on miss
  python epo_enrich.py US-20260146232-A1 EP-0564409-A1    # CLI test
"""
import os, sys, json, base64, time, re, urllib.request, urllib.error, pathlib

ROOT = pathlib.Path(os.environ.get("BIOYODA_ROOT") or pathlib.Path(__file__).resolve().parents[2])  # /data/bioyoda
CONFIG = ROOT / "config" / "epo.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from modules.paths import WORK as _WORK          # honors config.yaml base_dir (e.g. out_prod/work)
    CACHE = pathlib.Path(_WORK) / "epo_cache"
except Exception:
    CACHE = ROOT / "work" / "epo_cache"              # legacy fallback
OPS = "https://ops.epo.org/3.2"
_tok = {"value": None, "exp": 0.0}


def _creds():
    k, s = os.environ.get("EPO_KEY"), os.environ.get("EPO_SECRET")
    if k and s:
        return k, s
    if CONFIG.exists():
        c = json.load(open(CONFIG))
        return c["consumer_key"], c["consumer_secret"]
    raise RuntimeError("EPO creds missing: set EPO_KEY/EPO_SECRET or create config/epo.json")


def _token():
    """OAuth2 client-credentials token, cached until ~1 min before expiry (tokens last ~20 min)."""
    if _tok["value"] and time.time() < _tok["exp"] - 60:
        return _tok["value"]
    k, s = _creds()
    auth = base64.b64encode(f"{k}:{s}".encode()).decode()
    r = urllib.request.Request(f"{OPS}/auth/accesstoken", data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    d = json.load(urllib.request.urlopen(r, timeout=30))
    _tok.update(value=d["access_token"], exp=time.time() + int(d.get("expires_in", 1200)))
    return _tok["value"]


# --- defensive EPO-JSON helpers (nodes are dict-or-list; scalar text lives under "$") ---
def _L(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def _T(d):
    if isinstance(d, dict):
        return d.get("$", "")
    if isinstance(d, list):
        return _T(d[0]) if d else ""
    return d or ""


def _dates(node):
    """Recursively collect every YYYYMMDD date string under a node (robust to single/list nesting)."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            out += ([_T(x) for x in _L(v)] if k == "date" else _dates(v))
    elif isinstance(node, list):
        for x in node:
            out += _dates(x)
    return [d for d in out if isinstance(d, str) and len(d) >= 8 and d[:8].isdigit()]


def _to_epodoc(patent):
    """'US-20260146232-A1' -> 'US20260146232' (strip dashes + trailing kind code for the lookup)."""
    e = str(patent).replace("-", "").upper()
    return re.sub(r"[A-Z]\d?$", "", e)


def _fmt(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d and len(d) >= 8 else d


def enrich(patent, force=False):
    """{priority_date, filing_date, applicants, family_id, publication_date} for a patent number, or None on miss.
    Caches hits AND misses to work/epo_cache/<epodoc>.json so we never re-spend quota on the same patent."""
    epodoc = _to_epodoc(patent)
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"{epodoc}.json"
    if cf.exists() and not force:
        c = json.load(open(cf))
        return None if "error" in c else c
    try:
        r = urllib.request.Request(
            f"{OPS}/rest-services/published-data/publication/epodoc/{epodoc}/biblio",
            headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"})
        data = json.load(urllib.request.urlopen(r, timeout=30))
    except urllib.error.HTTPError as e:
        if e.code == 404:                       # genuine not-found: cache a permanent miss
            json.dump({"error": 404}, open(cf, "w"))
        return None                             # quota (403/429), 5xx, etc.: transient, do NOT cache (retry later)
    except Exception:                           # missing creds, network (URLError), timeout: transient, do NOT cache
        return None
    try:
        ed = data["ops:world-patent-data"]["exchange-documents"]["exchange-document"]
        ed = ed[0] if isinstance(ed, list) else ed
        b = ed["bibliographic-data"]
        pri = sorted(set(_dates(b.get("priority-claims"))))
        fil = sorted(set(_dates(b.get("application-reference"))))
        pub = sorted(set(_dates(b.get("publication-reference"))))
        apps = _L(b.get("parties", {}).get("applicants", {}).get("applicant"))
        names = [_T(a.get("applicant-name", {}).get("name")) for a in apps
                 if isinstance(a, dict) and a.get("@data-format") == "epodoc"]
        out = {
            "priority_date": _fmt(pri[0]) if pri else None,      # earliest priority = the true claim date
            "filing_date": _fmt(fil[0]) if fil else None,
            "publication_date": _fmt(pub[0]) if pub else None,
            "applicants": list(dict.fromkeys(n for n in names if n)),
            "family_id": ed.get("@family-id"),
        }
    except Exception as e:                                       # unexpected structure -> cache a miss, don't crash callers
        json.dump({"error": f"parse:{e}"}, open(cf, "w"))
        return None
    json.dump(out, open(cf, "w"))
    return out


def enrich_state(patent):
    """(data_or_None, resolved): resolved=True when we have a definitive answer (real data or a genuine
    not-found, both cached); False when a transient failure (quota/network) left nothing cached, so the
    caller should retry on a later view rather than treat it as a permanent miss. Never raises."""
    cf = CACHE / f"{_to_epodoc(patent)}.json"
    try:
        data = enrich(patent)        # may do one live call; caches only real data or a genuine 404
    except Exception:
        return None, False
    return data, cf.exists()         # after enrich, a cache file exists iff the answer is definitive


if __name__ == "__main__":
    import sys
    for p in (sys.argv[1:] or ["US-20260146232-A1", "EP-0564409-A1"]):
        print(f"{p:24s} -> {enrich(p)}")

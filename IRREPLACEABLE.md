# ⚠️ IRREPLACEABLE DATA — DO NOT DELETE OR REGENERATE-FROM-SCRATCH

Some data in this repo **cannot be re-downloaded** because the upstream source is gone,
or can only be rebuilt at enormous compute cost. This file is the canonical record of
what those assets are, why they matter, and how they're protected.

## The irreplaceable assets

| Asset | Path | Why irreplaceable |
|---|---|---|
| **Mined USPTO historical text** | `raw_data/patents/historical_uspto/` (11 G, 3,534 JSON + `uspto_historical.parquet`, 519,117 patents w/ abstracts, 2001→2025-12-23) | Sourced from the personal GitHub repo `eloyfelix.github.io/uspto-chem`, which is **no longer maintained**. This local copy is likely one of few surviving copies. Gap past 2025-12-23 is fillable only via manual CAPTCHA download (USPTO bulk XML). |
| **AACT clinical-trials raw** | `raw_data/clinical_trials/` (21 G, `aact_flat_files_20251227.zip` + extracted) | The AACT download endpoint that produced this was already broken (DigitalOcean link gone). CT text now comes from BioBTree's `trials.json` instead. |
| **Live Qdrant database** | `qdrant/` (615 G, 5 collections) | Regenerable only at **GPU-weeks** of cost (embedding 28.9M pubmed + 38.6M patents_text + 30.9M compounds + 574K esm2 + 554K CT). Effectively irreplaceable in practice. |

Regenerable-but-expensive (lower priority): `work/data/processed` embeddings (rebuild = days),
other `raw_data/*` (pubmed/uniprot/surechembl — re-downloadable from live sources).

## Protections in place

1. **Offsite backup (gdrive).** The two irreplaceable raw sets are copied to
   `gdrive:bioyoda/raw_data/{patents/historical_uspto,clinical_trials}` via rclone
   (`scripts/commands/sync.sh`; manual backup log under `work/logs/sync/`). This is the
   only layer that survives a full local `rm -rf` or disk failure — **keep it current.**
   (Before 2026-06-13 only the 143 MB parquet was on gdrive, NOT the 11 G of raw JSONs.)
2. **Read-only.** `raw_data/patents/historical_uspto` and `raw_data/clinical_trials` are
   `chmod -R a-w` (blocks accidental overwrite + casual `rm`; to edit: `chmod -R u+w <path>`).
3. **Delete-guard.** `bioyoda.sh clean` (and any caller of `assert_deletable` in
   `scripts/lib/common.sh`) refuses to delete anything under `raw_data/`, `qdrant/`, or
   `snapshots/`, and refuses empty/`/`/`/data`/repo-root targets (stops the
   `rm -rf "$unset_var/data/.."` → `rm -rf /data/..` class of accident).
4. **(Optional, needs root) hard immutability.** For true `rm -rf`-proofing on this ext4
   volume, run as root:
   ```
   sudo chattr -R +i /data/bioyoda/raw_data/patents/historical_uspto
   sudo chattr -R +i /data/bioyoda/raw_data/clinical_trials
   ```
   To modify later: `sudo chattr -R -i <path>` first. (ext4 has no native snapshots, so
   chattr is the only local mechanism that blocks even `rm -rf`.)

## Folder layout (post 2026-06-13 reorg)

```
raw_data/   ← ALL inputs, consolidated (was split across out/ + snapshots/)
work/       ← pipeline working outputs (was "out"); data/ state/ logs/; raw_data -> ../raw_data symlink
qdrant/     ← LIVE serving DB (was snapshots/qdrant_latest)
snapshots/  ← published/archival bundles ONLY
```

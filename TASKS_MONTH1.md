# BioYoda: Month 1 Task Breakdown

Detailed task breakdown for parallel execution. Use this to assign work to Claude or track your own progress.

---

## Task Legend

| Symbol | Meaning |
|--------|---------|
| `[C]` | Claude can do this |
| `[U]` | User must do this |
| `[C/U]` | Collaborative |
| `[blocked]` | Has dependencies |
| `parallel:X` | Can run parallel with task X |

---

## Repository Structure

| Repo | Purpose | Create |
|------|---------|--------|
| `bioyoda` | Backend (current) | Exists |
| `bioyoda-web` | SvelteKit frontend | Week 3 |
| (optional) `bioyoda-infra` | Docker, deployment | Week 2 or in main |

---

## Week 1: Product Polish

### 1.1 Response Formatting [C]
Convert raw JSON to professional markdown reports.

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.1.1 Create `ResponseFormatter` class | [C] | 2h | - |
| 1.1.2 Drug discovery report template | [C] | 2h | - |
| 1.1.3 Evidence path sections (collapsible) | [C] | 1h | - |
| 1.1.4 Drug tables with phase badges | [C] | 1h | - |
| 1.1.5 Summary statistics section | [C] | 1h | - |
| 1.1.6 Integrate into agent response | [C] | 1h | 1.1.1 done |
| 1.1.7 Test with 3 diseases | [C/U] | 1h | 1.1.6 done |

**Output:** `modules/agent_system/formatters/disease_report.py`

---

### 1.2 Drug Name Resolution [C]
Prefer common names over IUPAC/ChEMBL IDs.

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.2.1 Audit current `_get_best_drug_name()` | [C] | 30m | parallel:1.1 |
| 1.2.2 Add altNames priority ranking | [C] | 1h | - |
| 1.2.3 Fallback chain: common → brand → IUPAC | [C] | 1h | - |
| 1.2.4 Cache resolved names | [C] | 30m | - |
| 1.2.5 Test with known drugs (aspirin, imatinib) | [C] | 30m | - |

**Output:** Updated `disease_drug_tool.py`

---

### 1.3 Export Functionality [C]
CSV and JSON export for all results.

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.3.1 Create `ExportService` class | [C] | 1h | parallel:1.1,1.2 |
| 1.3.2 CSV export (drugs, genes, pathways) | [C] | 1h | - |
| 1.3.3 JSON export (structured, full data) | [C] | 30m | - |
| 1.3.4 Excel export (optional, openpyxl) | [C] | 1h | - |
| 1.3.5 Add to agent tool response | [C] | 30m | - |

**Output:** `modules/agent_system/services/export.py`

---

### 1.4 Error Handling [C]
Graceful failures with clear messages.

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.4.1 Audit current error paths | [C] | 1h | parallel:1.1,1.2,1.3 |
| 1.4.2 Create custom exception classes | [C] | 30m | - |
| 1.4.3 User-friendly error messages | [C] | 1h | - |
| 1.4.4 Partial result handling (some paths fail) | [C] | 1h | - |
| 1.4.5 Logging improvements | [C] | 30m | - |

**Output:** `modules/agent_system/core/exceptions.py`

---

### 1.5 Showcase Analyses [C/U]
3 disease analyses for demos and paper.

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.5.1 Run Glioblastoma full analysis | [C] | 30m | blocked:1.1 |
| 1.5.2 Run Type 2 Diabetes full analysis | [C] | 30m | parallel:1.5.1 |
| 1.5.3 Run NSCLC full analysis | [C] | 30m | parallel:1.5.1 |
| 1.5.4 Save outputs (JSON + markdown) | [C] | 30m | - |
| 1.5.5 Review and validate results | [U] | 1h | - |
| 1.5.6 Document interesting findings | [C/U] | 1h | - |

**Output:** `data/showcase/` directory with saved analyses

---

### 1.6 Paper Tasks (Parallel Track) [C/U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.6.1 Paper outline (sections, flow) | [C] | 1h | parallel:all |
| 1.6.2 Abstract draft (250 words) | [C] | 1h | blocked:1.6.1 |
| 1.6.3 Methods: BioBTree architecture text | [C] | 2h | parallel:1.6.2 |
| 1.6.4 Methods: 9-path drug discovery text | [C] | 2h | parallel:1.6.3 |
| 1.6.5 Create architecture diagram (mermaid) | [C] | 1h | parallel:1.6.3 |
| 1.6.6 Create flowchart diagram (mermaid) | [C] | 1h | parallel:1.6.4 |
| 1.6.7 User review and feedback | [U] | 2h | blocked:1.6.1-6 |

**Output:** `paper/` directory with drafts

---

### 1.7 Reproducibility & Data Provenance [C]
Full traceability of data versions for regulatory compliance and scientific reproducibility.

#### 1.7.1 BioBTree Manifest System [C]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.7.1.1 Design manifest.json schema | [C] | 1h | parallel:1.1-1.5 |
| 1.7.1.2 Auto-capture git commit/tag during build | [C] | 1h | - |
| 1.7.1.3 Extract dataset versions from source URLs | [C] | 2h | - |
| 1.7.1.4 Calculate checksums for source files | [C] | 1h | - |
| 1.7.1.5 Record build timestamp and duration | [C] | 30m | - |
| 1.7.1.6 Generate manifest.json in output dir | [C] | 1h | - |
| 1.7.1.7 Add record counts per dataset | [C] | 1h | - |

**Output:** `biobtreev2/scripts/generate_manifest.py` or integrate into `gen.sh`

**manifest.json fields:**
```json
{
  "biobtree_version": "tag or v0.0.0-dev",
  "biobtree_commit": "full sha",
  "biobtree_branch": "main",
  "build_timestamp": "ISO8601",
  "build_duration_seconds": 3600,
  "build_host": "hostname",
  "datasets": {
    "<dataset_name>": {
      "version": "extracted or unknown",
      "source_url": "original URL",
      "source_file": "local filename",
      "checksum_sha256": "hash of source",
      "download_date": "ISO8601",
      "record_count": 12345,
      "local_copy": true/false
    }
  }
}
```

---

#### 1.7.2 Dataset Version Detection [C]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.7.2.1 UniProt version from filename/URL | [C] | 30m | parallel:1.7.1 |
| 1.7.2.2 ChEMBL version from filename | [C] | 30m | - |
| 1.7.2.3 PubChem version (date-based) | [C] | 30m | - |
| 1.7.2.4 DrugBank version from file | [C] | 30m | - |
| 1.7.2.5 Reactome version detection | [C] | 30m | - |
| 1.7.2.6 EFO/Mondo version detection | [C] | 30m | - |
| 1.7.2.7 SureChEMBL/Patents version | [C] | 30m | - |
| 1.7.2.8 Fallback: use download date if no version | [C] | 30m | - |

**Output:** `biobtreev2/scripts/version_detection.py`

---

#### 1.7.3 Source File Archiving [C]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.7.3.1 Define size threshold (e.g., <10MB) | [C] | 15m | parallel:1.7.1,1.7.2 |
| 1.7.3.2 Create sources/ archive directory | [C] | 15m | - |
| 1.7.3.3 Copy small source files during build | [C] | 1h | - |
| 1.7.3.4 Compress archived sources (gzip) | [C] | 30m | - |
| 1.7.3.5 Record archive status in manifest | [C] | 30m | - |
| 1.7.3.6 Add .gitignore for large archives | [C] | 15m | - |

**Small files to archive:** config files, mapping files, ontology subsets, version files

**Large files (skip):** UniProt XML, PubChem SDF, ChEMBL SQL dumps

---

#### 1.7.4 BioYoda API Version Metadata [C]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.7.4.1 Load BioBTree manifest.json at startup | [C] | 30m | parallel:1.7.1-3 |
| 1.7.4.2 Track Qdrant collection build dates | [C] | 1h | - |
| 1.7.4.3 Add `data_versions` to API responses | [C] | 1h | - |
| 1.7.4.4 Create `/v1/versions` endpoint | [C] | 30m | - |
| 1.7.4.5 Add version info to export files | [C] | 30m | - |

**API response addition:**
```json
{
  "results": { ... },
  "metadata": {
    "query_id": "uuid",
    "timestamp": "ISO8601",
    "data_versions": {
      "biobtree": "v2.1.0 (a1b2c3d4)",
      "biobtree_build": "2025-01-15",
      "qdrant_pubmed": "2025-01-10",
      "qdrant_clinical_trials": "2025-01-10",
      "qdrant_patents": "2025-01-05"
    }
  }
}
```

---

#### 1.7.5 Reproducibility Documentation [C]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 1.7.5.1 Document manifest.json format | [C] | 30m | blocked:1.7.1 |
| 1.7.5.2 Add reproducibility section to README | [C] | 30m | - |
| 1.7.5.3 Create REPRODUCIBILITY.md guide | [C] | 1h | - |
| 1.7.5.4 Add to paper methods section | [C] | 30m | - |

**Output:** `REPRODUCIBILITY.md` in both biobtree and bioyoda repos

---

## Week 2: API & Infrastructure

### 2.1 Hetzner Server Setup [U]
Physical server provisioning and hardening.

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 2.1.1 Order Hetzner AX52 | [U] | 30m | - |
| 2.1.2 Initial OS setup (Ubuntu 22.04) | [U] | 1h | blocked:2.1.1 |
| 2.1.3 SSH key setup, disable password | [U] | 30m | - |
| 2.1.4 UFW firewall config | [U] | 30m | - |
| 2.1.5 fail2ban setup | [U] | 30m | - |
| 2.1.6 Install Docker + Docker Compose | [U] | 30m | - |

**Note:** Server ordering has lead time. Do this first thing Week 2.

---

### 2.2 Cloudflare Setup [U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 2.2.1 Add domain to Cloudflare | [U] | 15m | parallel:2.1 |
| 2.2.2 Update nameservers at registrar | [U] | 15m | - |
| 2.2.3 DNS records (A, CNAME) | [U] | 15m | blocked:2.1.2 |
| 2.2.4 SSL mode: Full (Strict) | [U] | 5m | - |
| 2.2.5 Generate origin certificate | [U] | 15m | - |
| 2.2.6 Enable WAF rules | [U] | 15m | - |
| 2.2.7 Configure rate limiting | [U] | 15m | - |

---

### 2.3 Business Registration (Germany) [U]
Gewerbeanmeldung for legal compliance.

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 2.3.1 Gewerbeanmeldung at local Gewerbeamt | [U] | 1h | parallel:2.1,2.2 |
| 2.3.2 Receive Finanzamt questionnaire (1-2 weeks) | [U] | - | - |
| 2.3.3 Fill out, elect Kleinunternehmerregelung | [U] | 30m | - |
| 2.3.4 Set up Stripe with Steuer-ID | [U] | 30m | blocked:2.3.1 |

**Cost:** ~€30 registration fee
**Note:** Do Gewerbeanmeldung early Week 2 - Finanzamt response takes 1-2 weeks.

---

### 2.4 Docker Configuration [C]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 2.4.1 Create `docker-compose.yml` | [C] | 2h | parallel:2.1,2.2,2.3 |
| 2.4.2 Dockerfile for FastAPI | [C] | 1h | - |
| 2.4.3 Dockerfile for BioBTree | [C] | 30m | - |
| 2.4.4 Qdrant container config | [C] | 30m | - |
| 2.4.5 Postgres container config | [C] | 30m | - |
| 2.4.6 Volume mounts for data persistence | [C] | 30m | - |
| 2.4.7 Environment variables / secrets | [C] | 30m | - |
| 2.4.8 Caddyfile for reverse proxy | [C] | 1h | - |
| 2.4.9 Health check endpoints | [C] | 30m | - |

**Output:** `infrastructure/` directory

---

### 2.5 GitHub Actions CI/CD [C]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 2.5.1 Create deploy workflow | [C] | 1h | parallel:2.4 |
| 2.5.2 SSH key secrets setup | [U] | 15m | - |
| 2.5.3 Build and push to server | [C] | 1h | - |
| 2.5.4 Zero-downtime deploy script | [C] | 1h | - |
| 2.5.5 Test full deployment | [C/U] | 1h | blocked:2.1,2.2,2.4 |

**Output:** `.github/workflows/deploy.yml`

---

### 2.6 FastAPI Development [C]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 2.6.1 Project structure setup | [C] | 1h | parallel:2.1-2.5 |
| 2.6.2 Pydantic models (request/response) | [C] | 2h | - |
| 2.6.3 `/v1/drug-discovery` endpoint | [C] | 2h | - |
| 2.6.4 `/v1/id-mapping` endpoint | [C] | 1h | parallel:2.6.3 |
| 2.6.5 `/v1/protein-similarity` endpoint | [C] | 1h | parallel:2.6.3 |
| 2.6.6 `/v1/compound-similarity` endpoint | [C] | 1h | parallel:2.6.3 |
| 2.6.7 JWT authentication middleware | [C] | 2h | - |
| 2.6.8 API key generation/validation | [C] | 1h | - |
| 2.6.9 Rate limiting middleware | [C] | 1h | - |
| 2.6.10 Usage logging to Postgres | [C] | 1h | - |
| 2.6.11 OpenAPI customization | [C] | 30m | - |
| 2.6.12 Integration tests | [C] | 2h | - |

**Output:** `api/` directory (or `bioyoda-api/` repo)

---

### 2.7 Paper Tasks Week 2 [C/U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 2.7.1 Complete methods section | [C] | 2h | parallel:2.1-2.6 |
| 2.7.2 Run 3 disease analyses (final) | [C] | 1h | blocked:Week1 |
| 2.7.3 Document analysis outputs | [C] | 1h | - |
| 2.7.4 Compare to DrugBank/ChEMBL | [C] | 2h | - |
| 2.7.5 Results section draft | [C] | 3h | blocked:2.7.2-4 |

---

## Week 3: Frontend & Business

### 3.1 SvelteKit Project Setup [U/C]
New repo: `bioyoda-web`

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 3.1.1 Create GitHub repo | [U] | 5m | - |
| 3.1.2 SvelteKit init with TypeScript | [U] | 15m | - |
| 3.1.3 Tailwind CSS setup | [C] | 30m | - |
| 3.1.4 Skeleton UI / shadcn-svelte | [C] | 30m | - |
| 3.1.5 Project structure (routes, lib, components) | [C] | 1h | - |
| 3.1.6 API client service | [C] | 1h | - |
| 3.1.7 Environment config (API URL) | [C] | 15m | - |

---

### 3.2 Frontend Core Features [C/U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 3.2.1 Layout component (nav, footer) | [C] | 1h | blocked:3.1 |
| 3.2.2 Query input component | [C] | 2h | - |
| 3.2.3 Disease autocomplete | [C] | 1h | - |
| 3.2.4 Parameter controls (checkboxes, sliders) | [C] | 1h | - |
| 3.2.5 Loading/progress indicator | [C] | 1h | - |
| 3.2.6 Results container | [C] | 1h | - |
| 3.2.7 Evidence path cards (collapsible) | [C] | 2h | - |
| 3.2.8 Drug table component (sortable) | [C] | 2h | - |
| 3.2.9 Similarity results display | [C] | 1h | - |
| 3.2.10 Export buttons (CSV, JSON) | [C] | 1h | - |
| 3.2.11 Error handling / error states | [C] | 1h | - |
| 3.2.12 Mobile responsive | [C] | 2h | - |

---

### 3.3 Landing Page [C]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 3.3.1 Hero section (tagline, CTA) | [C] | 1h | parallel:3.2 |
| 3.3.2 Features section (4 key differentiators) | [C] | 1h | - |
| 3.3.3 How it works section | [C] | 1h | - |
| 3.3.4 Pricing section | [C] | 1h | - |
| 3.3.5 Demo/screenshot section | [C] | 1h | blocked:3.2 |
| 3.3.6 Footer (links, legal) | [C] | 30m | - |

---

### 3.4 Auth & Payments [C/U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 3.4.1 Login/signup pages | [C] | 2h | parallel:3.2,3.3 |
| 3.4.2 JWT token handling (client) | [C] | 1h | - |
| 3.4.3 Protected routes | [C] | 1h | - |
| 3.4.4 Stripe account setup | [U] | 30m | parallel:all |
| 3.4.5 Stripe Checkout integration | [C] | 2h | blocked:3.4.4 |
| 3.4.6 Subscription status display | [C] | 1h | - |
| 3.4.7 Usage dashboard (queries used) | [C] | 1h | - |

---

### 3.5 Frontend Deployment [C/U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 3.5.1 SvelteKit adapter-static or adapter-node | [C] | 30m | blocked:3.2 |
| 3.5.2 Dockerfile for frontend | [C] | 30m | - |
| 3.5.3 Add to docker-compose.yml | [C] | 15m | - |
| 3.5.4 GitHub Actions for frontend | [C] | 1h | - |
| 3.5.5 Test full deployment | [U] | 1h | - |

---

### 3.6 Marketing Assets [C/U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 3.6.1 Blog post draft | [C] | 2h | parallel:3.2 |
| 3.6.2 Blog post review/edit | [U] | 1h | blocked:3.6.1 |
| 3.6.3 Demo video script | [C] | 30m | parallel:3.6.1 |
| 3.6.4 Record demo video | [U] | 1h | blocked:3.2 |
| 3.6.5 LinkedIn company page | [U] | 30m | parallel:all |
| 3.6.6 Prepare outreach emails | [C] | 1h | parallel:3.6.1 |

---

### 3.7 Paper Tasks Week 3 [C/U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 3.7.1 Introduction section | [C] | 2h | parallel:3.1-3.6 |
| 3.7.2 Discussion section | [C] | 2h | - |
| 3.7.3 Create figures (final) | [C] | 2h | - |
| 3.7.4 Format for bioRxiv | [C] | 1h | - |
| 3.7.5 User review full draft | [U] | 3h | blocked:3.7.1-4 |

---

## Week 4: Beta Launch

### 4.1 Beta User Acquisition [U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 4.1.1 List 20 potential beta users | [U] | 1h | - |
| 4.1.2 Send outreach emails (10) | [U] | 1h | - |
| 4.1.3 LinkedIn messages (10) | [U] | 1h | - |
| 4.1.4 Post on relevant forums | [U] | 1h | - |
| 4.1.5 Onboard accepted users | [U] | ongoing | - |

---

### 4.2 Feedback & Fixes [C/U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 4.2.1 Set up feedback channel (email/Discord) | [U] | 30m | - |
| 4.2.2 Triage incoming issues | [U] | ongoing | - |
| 4.2.3 Fix critical bugs | [C/U] | as needed | - |
| 4.2.4 Document feedback themes | [C] | 1h | - |
| 4.2.5 Prioritize Month 2 backlog | [C/U] | 2h | - |

---

### 4.3 Launch Announcements [U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 4.3.1 LinkedIn post | [U] | 30m | - |
| 4.3.2 Twitter/X post | [U] | 15m | - |
| 4.3.3 Bioinformatics subreddit | [U] | 30m | - |
| 4.3.4 Hacker News (optional) | [U] | 15m | - |

---

### 4.4 Paper Finalization [C/U]

| Subtask | Owner | Effort | Parallel |
|---------|-------|--------|----------|
| 4.4.1 Incorporate user feedback if relevant | [C] | 1h | - |
| 4.4.2 Final proofread | [U] | 2h | - |
| 4.4.3 Submit to bioRxiv | [U] | 1h | - |

---

## Parallelization Summary

### What Claude Can Work On In Parallel

While you're doing server setup (Week 2), Claude can:
- Write all Docker configs
- Write FastAPI endpoints
- Write paper sections
- Draft blog post

While you're doing frontend (Week 3), Claude can:
- Write component code for you to integrate
- Prepare marketing content
- Finalize paper

### Maximum Parallel Tracks

| Track | Owner | Week 1 | Week 2 | Week 3 | Week 4 |
|-------|-------|--------|--------|--------|--------|
| **Backend** | [C] | Formatting, exports | FastAPI, Docker | - | Bug fixes |
| **Infra** | [U] | - | Hetzner, Cloudflare | Deploy frontend | Monitor |
| **Frontend** | [U] | - | - | SvelteKit | Iterate |
| **Paper** | [C] | Outline, methods | Results | Intro, discussion | Submit |
| **Business** | [U] | - | - | Stripe, marketing | Beta users |

---

## Quick Reference: Give These to Claude

Copy-paste these to start tasks:

**Week 1:**
```
"Create ResponseFormatter class for drug discovery results.
Convert JSON to markdown with tables, collapsible sections,
and summary statistics. See disease_drug_tool.py for data structure."
```

```
"Create ExportService class with CSV and JSON export for
drug discovery results. Support drugs, genes, and pathways tables."
```

```
"Write paper outline and abstract for BioYoda. Focus on
multi-database drug discovery, 9-path approach, and 3 disease
case studies. Keep proprietary details out."
```

**Week 2:**
```
"Create docker-compose.yml for: FastAPI (port 8000),
Qdrant (6333), Postgres (5432), BioBTree (9001), Caddy.
Include volume mounts for data persistence."
```

```
"Create FastAPI project with 4 endpoints: drug-discovery,
id-mapping, protein-similarity, compound-similarity.
JWT auth, rate limiting, usage logging to Postgres."
```

**Week 3:**
```
"Create SvelteKit components: QueryInput (disease autocomplete),
ResultsDisplay (collapsible evidence paths), DrugTable (sortable),
ExportButtons. Use Tailwind CSS."
```

**Reproducibility:**
```
"Create manifest.json generation for BioBTree builds. Track:
git commit/tag, build timestamp, dataset versions (UniProt, ChEMBL,
PubChem, etc.), source file checksums. Auto-detect versions from
filenames/URLs. Archive small source files (<10MB) in sources/ dir."
```

```
"Add data_versions metadata to all BioYoda API responses. Load
BioBTree manifest.json at startup. Track Qdrant collection build
dates. Create /v1/versions endpoint showing all data provenance."
```

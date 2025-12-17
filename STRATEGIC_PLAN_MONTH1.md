# BioYoda: 1-Month Launch Plan

## Positioning

**BioYoda: AI Drug Discovery Co-Pilot**

Find drugs, targets, and competitive compounds in minutes instead of weeks. Multi-database evidence synthesis powered by AI reasoning.

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Frontend** | SvelteKit + Tailwind + Skeleton UI | Expert familiarity, fast, professional |
| **Backend API** | FastAPI (Python) | Async, auto OpenAPI docs, Python ecosystem |
| **Agent System** | Custom Python + LLM | BioBTree + Qdrant + Gemini/Claude |
| **Edge/Security** | Cloudflare (Free) | DDoS, CDN, WAF, hide origin IP |
| **Infrastructure** | Hetzner Dedicated (AX52) | €80/mo vs $500+/mo cloud, predictable |
| **Deployment** | Docker Compose + Caddy | Uniform ops, future scaling (not for deps - binaries are self-contained) |
| **CI/CD** | GitHub Actions | Push-to-deploy |

### Monthly Infrastructure Cost

| Service | Cost | Notes |
|---------|------|-------|
| Hetzner AX52 | ~€80 | Dedicated server |
| Hetzner Storage Box | ~€3 | Backups |
| Cloudflare | $0 | Free tier sufficient |
| Domain | ~€1 | Annual, amortized |
| UptimeRobot | $0 | Free tier |
| **Total** | **~€85/mo** | vs $500+/mo cloud |

### Data Processing (Separate from Serving)

**Important distinction:**
- **Serving** (Hetzner AX52): BioBTree queries, Qdrant search, API - always up, stable
- **Processing**: Build BioBTree, generate embeddings - batch, resource-heavy, periodic

**Processing resources:**

| Timeframe | Resource | Use Case |
|-----------|----------|----------|
| Month 1 | University HPC | BioBTree rebuild, ESM-2 embeddings (GPU) |
| Month 2+ | Google Colab Pro / Hetzner / Laptop | Smaller updates, Morgan FP |

**Processing workloads:**
- BioBTree rebuild: CPU + memory intensive
- ESM-2 protein embeddings (573K): Needs GPU
- Morgan fingerprints (30.8M): CPU intensive

**Data flow:** Processing server → rsync/push → Production server

### Deployment Architecture

```
                         Internet
                            │
                            ▼
┌─────────────────────────────────────────────────────┐
│                    Cloudflare                       │
│   • SSL termination     • CDN (static assets)       │
│   • DDoS protection     • WAF (attack blocking)     │
│   • Rate limiting       • Bot protection            │
│   • Hide origin IP      • Analytics                 │
└─────────────────────────┬───────────────────────────┘
                          │ (Cloudflare Origin Cert)
                          ▼
┌─────────────────────────────────────────────────────┐
│               Hetzner AX52 Server                   │
│                                                     │
│   Caddy (reverse proxy, origin SSL)                 │
│   ├── bioyoda.com      → SvelteKit (static)         │
│   ├── api.bioyoda.com  → FastAPI (:8000)            │
│   └── health checks                                 │
│                                                     │
│   Docker Compose                                    │
│   ├── sveltekit        (Node, static build)         │
│   ├── fastapi          (Python 3.11, uvicorn)       │
│   ├── biobtree         (gRPC :9001)                 │
│   ├── qdrant           (vectors :6333)              │
│   └── postgres         (users, API keys)            │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Dual Track: Product + Preprint

**Strategy:** Limited beta and preprint in parallel. Preprint provides pharma credibility; beta feedback improves paper quality.

```
Week 1: Product polish (formatting, exports)  |  Outline + methods draft
Week 2: API + Hetzner infrastructure          |  Methods + results draft
Week 3: SvelteKit frontend + business setup   |  Finalize paper
Week 4: Beta launch (5-10 users)              |  Submit to bioRxiv
Month 2: Wider launch with preprint credibility
```

---

## Preprint Plan

**Target:** bioRxiv submission end of Month 1

**Paper structure:**
1. Introduction - AI in drug discovery, multi-database challenge
2. Methods - BioBTree architecture, 9-path drug discovery, similarity search
3. Results - 3 disease case studies (Glioblastoma, T2 Diabetes, NSCLC)
4. Validation - Comparison to known drugs, manual workflow time
5. Discussion - Limitations, future directions

**Keep proprietary:** LLM prompts, agent code, chain templates, fine-tuning data

**Journal target (submit Month 2):** Bioinformatics, NAR Web Server, or Briefings in Bioinformatics

---

## Week 1: Product Polish

**Goal:** Make current capabilities production-ready

| Task | Days | Notes |
|------|------|-------|
| Response formatting (markdown reports with tables) | 2 | Critical - raw JSON looks unprofessional |
| Drug name resolution (prefer common names) | 1 | Use altNames ranking already implemented |
| Export functionality (CSV, JSON) | 1 | Users need to take data elsewhere |
| Error handling improvements | 1 | Graceful failures, clear messages |
| 3 showcase disease analyses | 1 | Glioblastoma, T2 Diabetes, NSCLC |

**Paper tasks (parallel):**
- [ ] Paper outline and abstract draft
- [ ] Methods section: BioBTree architecture diagram
- [ ] Methods section: 9-path drug discovery flowchart

**Deliverables:**
- [ ] Professional-looking disease reports
- [ ] Saved showcase outputs for demos
- [ ] Paper outline complete

---

## Week 2: API & Infrastructure

**Goal:** Deploy to Hetzner, enable programmatic access

### Infrastructure (Hetzner + Cloudflare)

**Why Hetzner:** Predictable costs (~€80/mo vs $500+/mo cloud), no egress fees, sufficient for launch scale.

**Why Cloudflare:** Free DDoS protection, CDN, WAF - security layer you can't monitor 24/7 as solo founder.

**Server:** Hetzner AX52 (AMD Ryzen 7 5800X, 64GB RAM, 2x1TB NVMe)

| Task | Hours | Notes |
|------|-------|-------|
| Server order + initial OS setup | 2 | Ubuntu 22.04 LTS |
| Security hardening (SSH keys, UFW, fail2ban) | 2 | No password auth |
| Docker + Docker Compose setup | 2 | All services containerized |
| Cloudflare setup (DNS, SSL mode, WAF rules) | 1 | Full (Strict) SSL, orange cloud |
| Cloudflare origin certificate + Caddy | 1 | 15-year cert, no renewal needed |
| Caddy reverse proxy config | 1 | Route to services |
| GitHub Actions CI/CD | 3 | Push to deploy |
| Monitoring (UptimeRobot, healthchecks) | 2 | Free tier sufficient |
| Backup to Hetzner Storage Box | 1 | Automated daily |

### API Development

| Task | Days | Notes |
|------|------|-------|
| FastAPI REST wrapper | 1.5 | 4 endpoints: drug-discovery, id-mapping, protein-sim, compound-sim |
| API key authentication | 0.5 | Simple key generation and validation |
| Rate limiting | 0.5 | Prevent abuse, enable tiered access |
| OpenAPI/Swagger docs | - | Auto-generated from FastAPI |
| Usage logging | 0.5 | Track queries per user |

**Paper tasks (parallel):**
- [ ] Methods section complete
- [ ] Results: Run 3 disease analyses, document outputs
- [ ] Results: Compare findings to known drug databases

**Deliverables:**
- [ ] Hetzner server running all services
- [ ] Cloudflare protecting origin (DDoS, WAF, CDN)
- [ ] Working API at `api.bioyoda.com/v1/`
- [ ] CI/CD pipeline (push → deploy)
- [ ] API documentation (auto-generated OpenAPI)
- [ ] Methods + Results draft

---

## Week 3: Frontend & Business

**Goal:** Professional web interface and monetization setup

### SvelteKit Frontend

**Stack:** SvelteKit + Tailwind CSS + Skeleton UI (or shadcn-svelte)

| Task | Days | Notes |
|------|------|-------|
| SvelteKit project setup | 0.5 | Tailwind, component library, deploy config |
| Query interface | 1 | Disease/gene input, parameter controls |
| Results display | 1.5 | Tables, cards, collapsible evidence paths |
| Export functionality | 0.5 | CSV, JSON download buttons |
| Landing page (same app) | 1 | Positioning, features, pricing, demo link |

### Business Setup

| Task | Days | Notes |
|------|------|-------|
| Stripe integration | 1 | Subscription payments |
| Blog post: "Finding drugs for glioblastoma with AI" | 0.5 | Show real results, explain methodology |
| Demo video (5 min) | 0.5 | Screen recording with narration |
| LinkedIn company page | 0.5 | Professional presence |
| Outreach to 10 beta users | 0.5 | Personal emails, LinkedIn messages |

**Pricing Tiers:**

| Tier | Price | Limits |
|------|-------|--------|
| Free | $0 | 10 queries/month, no similarity search |
| Researcher | $99/mo | 100 queries, protein similarity |
| Professional | $499/mo | 500 queries, all features |
| Enterprise | Custom | Unlimited, API, support |

**Paper tasks (parallel):**
- [ ] Introduction section
- [ ] Discussion section draft
- [ ] Figures: Architecture diagram, results tables

**Deliverables:**
- [ ] SvelteKit app deployed (query UI + landing page)
- [ ] Payment flow working
- [ ] Published blog post
- [ ] Demo video on YouTube/Loom
- [ ] Full paper draft

---

## Week 4: Beta Launch

**Goal:** Get real users and feedback

| Task | Days | Notes |
|------|------|-------|
| Beta user onboarding | Ongoing | 5-10 target users |
| Fix critical issues | 2-3 | Based on real usage |
| Collect testimonials | 1 | Even short quotes help |
| Social announcements | 1 | LinkedIn, Twitter, forums |
| Customer support setup | 0.5 | Email or Discord |
| Plan Month 2 roadmap | 1 | Based on feedback |

**Beta User Sources:**
1. LinkedIn pharma/biotech connections
2. Bioinformatics Reddit/forums
3. Academic collaborators
4. Twitter biotech community
5. Cold outreach to biotech startups

**Deliverables:**
- [ ] 5-10 active beta users
- [ ] Documented feedback
- [ ] At least 1 paying customer
- [ ] Month 2 priorities defined

---

## Success Metrics

| Metric | Target |
|--------|--------|
| API uptime | >99% |
| Query response time | <60s |
| Beta users | 5-10 |
| Paying customers | 1-3 |
| Email signups | 50+ |

---

## What NOT To Do This Month

- Add new agents (variant analysis, etc.)
- Build complex enterprise features
- Over-engineer the UI (functional > perfect)
- Write comprehensive documentation
- Open source anything
- Optimize for massive scale
- Set up Kubernetes or complex orchestration

**Focus:** Sell what you have, not build what you might need.

---

## Key Differentiators to Highlight

1. **30.8M Patent Compounds** - Competitive intelligence no one else has
2. **9-Path Drug Discovery** - Most comprehensive evidence gathering
3. **30-Second Analysis** - Speed vs weeks of manual work
4. **Deterministic + AI** - Accurate data with intelligent reasoning
5. **Full Reproducibility** - Every result traceable to exact data versions

---

## Reproducibility & Data Provenance

**Vision:** Every query result can be reproduced exactly. Users know precisely which data versions produced their findings - critical for regulatory submissions and scientific publications.

**Why This Matters:**
- Pharma companies need audit trails for regulatory submissions
- Academic users need reproducibility for publications
- Differentiates from black-box AI tools
- Builds trust with enterprise customers

### BioBTree Reproducibility

Track and store:
| Item | Storage | Notes |
|------|---------|-------|
| BioBTree git commit/tag | `manifest.json` | Exact code version used |
| Build timestamp | `manifest.json` | When data was generated |
| Dataset versions | `manifest.json` | Per-source version info |
| Source file checksums | `manifest.json` | MD5/SHA256 of inputs |
| Small source files | `sources/` | Local copy if <10MB |

**manifest.json example:**
```json
{
  "biobtree_version": "v2.1.0",
  "biobtree_commit": "a1b2c3d",
  "build_timestamp": "2025-01-15T10:30:00Z",
  "datasets": {
    "uniprot": {
      "version": "2025_01",
      "source_url": "https://ftp.uniprot.org/...",
      "checksum": "sha256:abc123...",
      "record_count": 573000
    },
    "chembl": {
      "version": "34",
      "source_url": "https://ftp.ebi.ac.uk/...",
      "checksum": "sha256:def456..."
    }
  }
}
```

### BioYoda Query Reproducibility

Each query response includes:
```json
{
  "query_id": "uuid",
  "timestamp": "2025-01-15T14:22:00Z",
  "data_versions": {
    "biobtree": "v2.1.0 (a1b2c3d)",
    "qdrant_pubmed": "2025-01-10",
    "qdrant_patents": "2025-01-05"
  },
  "results": { ... }
}
```

### Implementation Priority

| Phase | Task | Notes |
|-------|------|-------|
| Month 1 | BioBTree manifest.json generation | During build process |
| Month 1 | Version info in API responses | Simple metadata field |
| Month 2 | Source file archiving (small files) | <10MB threshold |
| Month 2 | Query result archiving | Optional, for enterprise |

---

## Technical Debt to Track (Fix Later)

- Missing SMILES for some ChEMBL entries (CHEMBL25)
- PubChem synonyms/drug_names empty
- SureChEMBL ID lookup slow (needs payload index)
- No efo→reactome or efo→uniprot links in BioBTree
- Gene names not enriching in protein similarity results

---

## Month 2+ Preview

Based on Month 1 learnings, likely priorities:

**Infrastructure:**
- Data processing setup (post-university HPC transition)
- Evaluate: Google Colab Pro (~$10/mo) vs Hetzner CPU server (~€40/mo)
- Document BioBTree/Qdrant update pipeline

**Features:**
- Variant Analysis Agent
- Literature search integration
- Batch processing (100 genes at once)
- Antibody dataset (pending BioBTree link)
- Custom PDF reports

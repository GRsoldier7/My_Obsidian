---
name: biohacking-data-pipeline
description: |
  Architect and build automated data pipelines for biohacking, health, and supplement data using Python + PostgreSQL. Guides the full pipeline lifecycle: finding and evaluating data sources (APIs, web scraping, public datasets), designing normalized database schemas, writing ingestion scripts with scheduling and error handling, and building data validation/quality checks. Use when the user mentions biohacking data, health databases, supplement databases, blood work data, biomarker tracking, automated data collection, ETL pipelines for health data, API integrations for health/wellness services, or building a data-driven health product. Also trigger for scheduled ingestion (daily runs, cron jobs), lab/bloodwork APIs, or health schema design.
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: product
  adjacent-skills: database-design, cloud-migration-playbook, testing-strategy
  source-repo: GRsoldier7/My_AI_Skills
---

# Biohacking Data Pipeline Architect

## Three Decision Lenses

1. **Data quality over quantity** — bad health advice is worse than no tool at all
2. **Schema for evolution** — design for data types you can't predict today
3. **Production-readiness from start** — logging, error handling, retry, idempotency

## Core Data Domains

- **Supplements & Compounds:** profiles, interactions, efficacy evidence (Examine.com, PubMed, PubChem)
- **Biomarkers & Lab Work:** reference ranges (age/sex-adjusted), biomarker relationships, lab panels
- **Protocols & Stacks:** evidence-based stacks, dosing protocols, contraindications
- **User Health Data:** blood work imports, symptom tracking, supplement logs, wearable data

## Pipeline Architecture Pattern

```
Extract → Validate → Transform → Load → Verify → Log

Extract:   Pull from source, handle pagination, rate limiting, auth
           Always capture raw response before any transformation

Validate:  Check plausibility (Vitamin D > 100,000 IU = likely unit error)
           Required fields present? Duplicates? Schema match?

Transform: Clean, normalize, standardize units (mg vs mcg vs IU)

Load:      Upsert with ON CONFLICT DO UPDATE (idempotent!)

Verify:    Row counts, NULLs in required fields, referential integrity

Log:       Records extracted, validated, loaded, rejected (with reasons)
```

## Database Design Principles

```sql
-- Provenance pattern (NON-NEGOTIABLE for health data)
ALTER TABLE supplements ADD COLUMN source_id INTEGER REFERENCES data_sources(source_id);
ALTER TABLE supplements ADD COLUMN source_record_id TEXT;
ALTER TABLE supplements ADD COLUMN ingested_at TIMESTAMPTZ DEFAULT NOW();

-- Temporal versioning
CREATE UNIQUE INDEX idx_biomarker_current
  ON biomarker_values(user_id, biomarker_id)
  WHERE valid_until IS NULL;
```

## Scheduling Options (in order of recommendation)

1. **Prefect or Dagster** — dashboard, retry logic, dependency management, cloud-ready
2. **APScheduler** — lightweight Python, good for <4 pipelines
3. **Cron + Python** — simplest, minimal observability (graduation target: option 1 or 2)

## API Integration Rules

- Rate limiting with exponential backoff + jitter — non-negotiable
- Cache aggressively (supplement data doesn't change hourly)
- Store raw API responses alongside transformed data (API death insurance)
- Web scraping: check robots.txt, 2-3 second delays, store raw HTML

## Anti-Patterns

1. **Loading Without Provenance:** Every external data table MUST have source_id, source_name, ingested_at
2. **Skipping Validate:** Physiologically impossible values will enter the system silently
3. **Non-Idempotent Pipelines:** Running twice must produce same database state — use upsert, not insert

## Quality Gates
- [ ] Every external table has source_id, source_name, ingested_at provenance columns
- [ ] Pipeline follows full Extract → Validate → Transform → Load → Verify → Log pattern
- [ ] Pipeline is idempotent: re-running produces same result without duplicates
- [ ] Rate limiting with exponential backoff for all API integrations
- [ ] Validation catches physiologically implausible values with rejection logging
- [ ] Schedule configured and tested

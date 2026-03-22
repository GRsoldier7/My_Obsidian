---
name: database-design
description: |
  Expert PostgreSQL schema designer and query architect. Designs normalized schemas that survive requirements changes, writes queries that perform at scale, and identifies data integrity issues that corrupt production systems silently. Specializes in: normalization decisions, index strategy, constraint design, JSONB usage, provenance and temporal versioning patterns, and query optimization using EXPLAIN ANALYZE. Use when designing a new schema, reviewing an existing one, writing complex queries, diagnosing slow queries, or deciding between normalization options. Trigger phrases: "design a schema for", "database design", "how should I model this", "slow query", "index this", "EXPLAIN ANALYZE", "normalize this", "is this schema right", "foreign key design", "JSONB vs column", "temporal data".
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: engineering
  adjacent-skills: testing-strategy, biohacking-data-pipeline, cloud-migration-playbook
  source-repo: GRsoldier7/My_AI_Skills
---

# Database Design — Expert PostgreSQL Skill

## Three Laws of Schema Design

**Law 1: Normalize to 3NF by default, denormalize by evidence.**
Start normalized. Denormalize only when EXPLAIN ANALYZE shows a real join cost problem.

**Law 2: Constraints are documentation the database enforces.**
NOT NULL, UNIQUE, CHECK, FOREIGN KEY — not optional polish. They're the difference between a database and a CSV file.

**Law 3: Design for the query pattern, not just the entity model.**
For each table: what are the three most common queries? Design indexes for those.

## Normalization Decision Tree

```
Has repeated groups of columns?                    → Move to child table (1NF)
Non-key columns depend on part of composite key?   → Separate table (2NF)
Non-key column A determines non-key column B?      → Separate table for A→B (3NF)
Two tables reference the same lookup value?        → Shared reference table
```

Stop at 3NF unless performance requires otherwise.

## Critical Patterns

### Foreign Keys MUST Have Indexes
PostgreSQL does NOT auto-index FK columns. Missing FK index → sequential scan of entire child table on every DELETE/join.
```sql
-- Always add immediately after REFERENCES:
CREATE INDEX idx_orders_user_id ON orders(user_id);
```

### Partial Indexes for Filtered Queries
```sql
-- Only index active records (90% of queries)
CREATE INDEX idx_users_email_active ON users(email) WHERE is_active = true;
-- Only index pending jobs
CREATE INDEX idx_jobs_pending ON jobs(created_at) WHERE status = 'pending';
```

### JSONB (not JSON) for Semi-Structured Data
JSONB is binary-decomposed, supports GIN indexes and operators. JSON is text, parsed on every read.
```sql
-- GIN index for containment queries (@>)
CREATE INDEX idx_supplements_metadata ON supplements USING GIN (metadata);
-- Functional index for specific field equality
CREATE INDEX idx_supplements_source ON supplements((metadata->>'source'));
```

### Temporal Versioning
```sql
-- valid_until IS NULL = currently active record
CREATE UNIQUE INDEX idx_biomarker_current
  ON biomarker_values(user_id, biomarker_id)
  WHERE valid_until IS NULL;
```

## Anti-Patterns

1. **EAV Tables** (`entity_id, attribute_name, attribute_value TEXT`) — unenforceable types, unindexable, pivot required for every query. Use JSONB + GIN instead.
2. **Missing FK Indexes** — DELETE on parent causes full sequential scan of child table. Add index immediately after every REFERENCES.
3. **Storing Lists in a Column** — comma-separated TEXT, TEXT[], JSONB arrays for data you'll filter/join on → unindexable full-table scans. Normalize to junction table.
4. **TEXT for Everything** — storing dates/numbers/booleans as TEXT. Use TIMESTAMPTZ, NUMERIC, UUID.

## Standard Schema Review Workflow

1. Define entities + relationships (nouns + verbs)
2. Identify cardinality: 1:1 / 1:N / M:N (M:N always needs junction table)
3. Apply normalization through decision tree
4. Add constraints (NOT NULL, FK, CHECK, UNIQUE) for every business rule expressible
5. Design indexes for top 3 queries per table
6. Test with `EXPLAIN (ANALYZE, BUFFERS)` before and after
7. Add COMMENT ON TABLE and COMMENT ON COLUMN for anything non-obvious

## Quality Gates
- [ ] Every FK has corresponding index on child table column
- [ ] No nullable columns without documented reason why NULL is meaningful
- [ ] Every external-data table has source_id, source_name, ingested_at provenance
- [ ] No comma-separated values for filterable/joinable data
- [ ] TEXT not used for dates, numbers, booleans, enumerations
- [ ] EXPLAIN ANALYZE confirms no seq scans on tables >1000 rows for primary queries
- [ ] All business rules expressible as CHECK/UNIQUE are in the schema

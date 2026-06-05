# P1 Integrity Layer — Implementation Session — 2026-05-03

**Branch:** `polish/prod-ready`
**Commits (chronological):** `f3f8325`, `641011d`, `cd66a20`, `2024dba`, `c8e7013`, `de46db2`
**Outcome:** Steps 1–7 of the ADR-0005 rollout sequence landed. Step 6c is operator action (LXC deployment + workflow reactivation). Step 8 is a future checkpoint.

---

## What landed

### `f3f8325` — Step 1: ADR-0005 design
[docs/adr/0005-brain-dump-state-machine-and-receipts.md](../adr/0005-brain-dump-state-machine-and-receipts.md) (482 lines).
- 6-state machine (`empty | has_content | scanning | extracted | partial | error`)
- 8-field canonical frontmatter
- Content-addressed extraction receipts at `99_System/extraction-receipts/<source>-<YYYYMMDD>-<sha8>.json`
- Pre-reset archive at `99_System/archive/brain-dumps/<YYYY-MM-DD>/<file>`
- Per-section gated reset
- 16-test plan, 8-step rollout, P2 future-proofing notes
- One architectural fork flagged for Aaron's sign-off (n8n shell-out vs JSON-fixture parity)

### `641011d` — Step 2: pure-functions kernel + tests
[tools/bd_integrity.py](../../tools/bd_integrity.py) (370 lines, no I/O):
- `compute_content_hash` (sha256, NFC, LF, retention-block stripped)
- `parse_frontmatter` / `serialize_frontmatter` (canonical-field-ordered)
- `migrate_frontmatter` (idempotent, preserves unknown legacy fields)
- `is_body_effectively_empty` (template + retention detection — fixed mid-step to match `is_section_empty`)
- `receipt_path` / `archive_path` (content-addressed)
- `compute_summary` / `build_receipt` / `decide_final_status`
- `make_retention_block` (Obsidian callout, wikilink to receipt)
- `next_state` (state machine)
- `apply_reset` (gated transform — verified sections cleared, failed retained)

[tests/test_brain_dump_integrity.py](../../tests/test_brain_dump_integrity.py) (25 tests, all green first run).
Covers ADR tests 3, 6, 11, 13, 15, 16 plus receipt/state/serialization scaffolding.

### `cd66a20` — Step 3: migration script
[scripts/migrate_brain_dump_frontmatter.py](../../scripts/migrate_brain_dump_frontmatter.py) (218 lines).
Dry-run by default, idempotent, per-file before/after delta.

### `2024dba` — Step 4: Python processor wired to gated path
[tools/process_brain_dump.py](../../tools/process_brain_dump.py) `process_file()` rewritten end-to-end.

Per-file flow: read → parse FM → compute hash → empty? → archive → extract → build receipt → write receipt → gated reset → write source.

`--no-reset` preserved as heartbeat-only safety net.

**Deliberate ADR deviation:** `scanning` state is logical-only during a run, NOT persisted to disk. A crashed run leaves the file in its prior state and re-picks it on retry; receipts are content-addressed so this is idempotent. Eliminates ADR rule R3 (stale-lock recovery) — doesn't need the audit check.

Bug fix during integration: `bdi.is_body_effectively_empty` didn't strip `=this.field` placeholders, `*Tags:` lines, or `Format:` lines, causing it to disagree with the existing `is_section_empty`. Brought up to parity. Migration script + live processor now agree on every file.

### `c8e7013` — Step 7: receipt audit script
[scripts/audit_extraction_receipts.py](../../scripts/audit_extraction_receipts.py) (362 lines).
6 rules (R1, R2, R4, R5, R6, R7). R3 dropped (see ADR deviation above).
Live audit reported 22 pre-migration findings → 0 post-migration. Working as designed.

### `de46db2` — Steps 5 + 6 + 6b: migration applied, n8n thin-scheduler refactor, LXC runbook
- Paused n8n workflow `1SiacuC68kFgYayV` via API.
- Ran migration with `--apply` on all 11 brain-dump sources. 11/11 succeeded. Audit clean.
- Rewrote `workflows/n8n/brain-dump-processor-v2.json` from ~17 nodes to 7. n8n is now a thin scheduler that runs Python and emails the digest. Python is the single logic kernel.
- [docs/runbook-deploy-python-to-lxc.md](../runbook-deploy-python-to-lxc.md) — what the LXC (CT-202) needs and how to verify.

---

## Verification snapshots

| Check | Pre-session | End of session |
|---|---|---|
| pytest | 202 pass, 1 skip | **230 pass, 1 skip** |
| Workflow audits | 4/4 green | 4/4 green |
| Live extraction-receipts audit | (script didn't exist) | 0 findings (clean) |
| Brain-dump source frontmatter | non-canonical, missing 5 fields | canonical 8-field across all 11 sources |
| n8n brain-dump-processor-v2 status | active (UTC-adjusted cron, hardcoded `reset_applied`) | **paused** pending LXC deploy + reactivation |
| `99_System/extraction-receipts/` | doesn't exist | will populate on first run after LXC deploy |
| `99_System/archive/brain-dumps/` | doesn't exist | will populate on first run after LXC deploy |

---

## Operator action items (step 6c)

1. Read [docs/runbook-deploy-python-to-lxc.md](../runbook-deploy-python-to-lxc.md).
2. SSH to LXC CT-202. Verify Python 3.12+ + install `boto3 openai python-dotenv`.
3. Mount or rsync the repo to `${OHO_REPO_PATH:-/opt/oho}`.
4. Ensure `.env` is present at `${OHO_REPO_PATH}/.env`.
5. Smoke test: `python3 -u tools/process_brain_dump.py --dry-run` — verify stdout JSON valid.
6. Reactivate workflow: `curl -X POST -H "X-N8N-API-KEY: $N8N_API_KEY" http://192.168.1.121:5678/api/v1/workflows/1SiacuC68kFgYayV/activate`.
7. Trigger a manual run from n8n UI; verify digest email + receipt + archive land correctly.

Until step 6c completes, manual `python3 tools/process_brain_dump.py` on the Mac continues to work with full P1 gates.

---

## Backlog / future steps

- **Step 4b** — orchestrator-level integration tests (ADR tests 1, 2, 4, 5, 7, 8, 12, 14). Mock-S3-based. Worth doing post-deployment when we have real receipts to compare against. Not blocking.
- **Step 8** — `--no-reset` deprecation decision. Default: keep as documented escape hatch. Re-evaluate after ≥7 days of clean live runs.
- **Vault-health-report integration** — shell out from `vault-health-report.json` to `audit_extraction_receipts.py` and surface findings in the weekly email. Small. Useful.
- **P2 (threaded tasks) design** — design-first per Aaron's directive. Spec lands as a future ADR before any code. See [project_p2_threaded_tasks_spec.md](../../../../../Users/aarondeyoung/.claude/projects/-Volumes-home----AI-Scripts-Automations-Projects-Projects-Repos-ObsidianHomeOrchestrator/memory/project_p2_threaded_tasks_spec.md) memory.

---

## Lessons (durable)

1. **Receipt-as-the-gate beats `bool reset_applied`.** Computing reset success from a verifiable artifact eliminates the entire class of "pipeline lies in its own log" bugs. The static-analysis test (Test 8 in ADR) makes the literal `reset_applied: true|false` physically impossible to ship in JS code.
2. **Content-addressed receipt paths make idempotency free.** Same body → same receipt key → re-runs overwrite in place. No GC needed for orphans across short windows. This was a small ADR detail with outsized correctness benefit.
3. **Logical-only states are a feature.** Persisting `scanning` to disk would have created a stale-lock failure mode that requires audit-level recovery. By keeping `scanning` in-memory only, the system has fewer states it can corruptedly inhabit.
4. **Two implementations is the bug.** Every duplicate of "the same logic in JS and Python" is a divergence waiting to happen. The 2026-05-03 hardcoded `reset_applied: true` was exactly this. Step 6's thin-scheduler architecture deletes the duplicate.
5. **Migration scripts must be dry-run-default + idempotent.** The migration ran twice during this session (a "would-do" preview pass and an `--apply` pass). Same input both times → identical output (proven by the test). This is what makes a manual one-shot script safe to run again if interrupted.

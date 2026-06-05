# Value-First Triage — 2026-04-25 / 26 (UTC)

**Operator self-rating before:** 3/10. Symptom triad: blank emails, brain dumps not extracting, static checklists. On the verge of abandoning the project.

**Operator after:** end-to-end pipeline restored. Brain dump extraction proven on real content. Emails carry real bodies. Three living views in Obsidian. Observability layer surfacing runtime truth.

## Root causes located (parallel diagnostic)

1. **Blank emails** — `n8n-nodes-base.emailSend@2` with `options.emailFormat: "both"` silently drops the HTML body. SMTP `messageSize` 364–678 B for ~13.6 kB HTML payloads. All 6 email-emitting workflows affected. The 2026-04-19 "dual-body" claim never worked on this n8n build.
2. **Silent brain dumps** — n8n's `S3: List Brain Dumps` node returns `items: 0` on 50 consecutive cron firings (boto3 with same creds lists 12 files). n8n's S3 layer is broken; credentials/bucket/endpoint are fine. Operator's content sat untouched. Compounding: regex extractor used a verb whitelist that didn't match the operator's writing patterns ("Flush out", "Fine Tune", "Re-apply", "Dig into").
3. **Dead checklists** — `Live Dashboard.md` is fully clobbered hourly by `live-dashboard-updater`. Any Dataview added there is erased within 60 minutes. No isolated daily-action surface existed.

## What shipped

### Track A — Working emails
- All 6 emailSend nodes: `emailFormat: "both"` → `"html"`. Orphan `text` parameters dropped.
- New `scripts/audit_workflow_email_format.py` — 15 workflows scanned, all green.
- New `scripts/render_emails_dryrun.py` — renders each email to `tests/fixtures/email-previews/<workflow>.html` for visual review.
- Runtime evidence: morning-briefing 2026-04-26 01:31 UTC produced `body_length: 13710` (was 364–678).

### Track B — Brain dump intelligence (Python tool)
- `tools/process_brain_dump.py` substantially rewritten:
  - Section-aware parsing (`## To Do's`, `## Tasks`, etc.)
  - Prose-aware imperative-verb regex (broader heuristic; replaces verb whitelist)
  - `- YYYYMMDD` shorthand → canonical `[due:: YYYY-MM-DD]`
  - AI gold path (OpenRouter) on every brain dump now, not just regex-empty
  - Intent classification: action / research / question / event / reference → routed appropriately
  - Auto `[explore:: true]` tag for research-intent items (drives Home.md View 3)
  - Area auto-detection from context keywords; priority inference from urgency cues
  - Fuzzy-match dedup against existing MTL (≥85% similarity)
  - Source-link wikilinks (`[source:: [[braindump-YYYY-MM-DD-name]]]`)
  - Confidence-gated review queue for low-confidence extractions
  - Telemetry to `99_System/metrics/brain-dump-extraction.jsonl`
- n8n workflow's S3 List node replaced with HTTP-Request + presigned URL (bypasses broken n8n S3 layer)
- Defense-in-depth: empty-list runs now write run logs and emit notifications (silent zero → loud zero)
- 89 tests for the brain-dump module; 3 new regression tests for the trailing-tag validation bug

### Track C — Home.md as daily entry point
- New `000_Master Dashboard/Home.md` (4258 B) with sections: Morning Setup, Today, Active Projects, This Week, Reading Queue, To Look Into, Inbox Health, Quick Actions
- Built by `tools/build_home_view.py` (idempotent, re-run anytime)
- Reads live MinIO state for inbox-health stats
- Validated render: 2 overdue, 19 due-today/priority-A, 4 quick wins on first build

### Track D — Observability layer
- New `99_System/Pipeline Health.md` (3658 B) — auto-updated workflow health table
- New `tools/build_pipeline_health.py` — n8n REST API + run-log cross-check
- New `tools/anomaly_detector.py` — rules: silent zero, stale pipeline, run-log gap, MTL stagnation
- Daily-summary mode for morning-briefing integration

## Critical bugs found and fixed during verification

1. **Three audit scripts crashed on Windows** with `cp1252` encoding error. `Path.read_text()` calls had no `encoding="utf-8"`. Fixed in `audit_workflow_credentials.py`, `audit_workflow_runlogs.py`, `audit_workflow_connections.py`, `tests/test_workflow_templates.py`. All 4 audits now green.
2. **Data-loss bug in process_brain_dump.py**: `TASK_FORMAT_PATTERN` rejected tasks carrying `[explore::]` and `[source:: [[...]]]` tags because the strip-then-revalidate regex couldn't match through wikilink `]]`. Result: regex extracted 5 tasks, all 5 silently rejected, but `reset_to_template` ran anyway → operator's brain dump wiped without MTL append. **Recovered via MinIO versioning** (`list_object_versions` returned 54 versions; restored the 1533-byte pre-reset version). Fixed `TASK_FORMAT_PATTERN` to accept trailing extension tags directly. 3 regression tests added.

## End-to-end proof on operator's real brain dump

After the validation fix, ran `tools/process_brain_dump.py --file "BrainDump — Personal.md"`:
- Discovered 1 file, 1 section with real content (`✅ To Do's`)
- Regex extracted 5 tasks
- 5 appended to MTL with canonical format + source-links
- 1 task got `[explore:: true]` ("Dig into ICP for E7 & Legal")
- Source file reset to empty template (only after successful append)
- Run log written to `99_System/logs/`

## Outstanding (Phase 2)

- **n8n cron path**: `__MINIO_HOST__` and `__AWS_CRED_ID__` placeholders need `setup-n8n.sh` hydration; until then, manual `tools/process_brain_dump.py` is the working path.
- Reset-after-append ordering: today `reset_to_template` fires regardless of MTL append result. Should be conditional on `mtl_appended > 0`.
- MTL backfill: only 11% have `[due::]`, 0% have `[completion::]`. Limits Home.md "Overdue" and "This Week / Completed" coverage.
- `[explore:: true]` adoption — auto-tagging only; no historical tasks tagged.
- Weekend Planner inactive (needs GCAL OAuth2 cred).
- Telegram capture bot unwired.
- OpenRouter key rotation pending.

## Test suite

189 passed, 1 skipped (was 151 / 1 per pre-triage CLAUDE.md). All four audit scripts green on Windows.

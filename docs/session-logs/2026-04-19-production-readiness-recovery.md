# Production Readiness Recovery — 2026-04-19

**Branch:** `polish/prod-ready` | **Commits:** `d860b87`, `b0b7dc5`, `15f4902` (+ final docs/audit commit)
**Duration:** One session, inline execution with checkpoints.

---

## Root cause of the 10-day silence

Brain-dump and article ingestion had been idle since 2026-04-10. Live diagnosis (run before any code change) established:

- `curl --max-time 5 http://192.168.1.240:9000/minio/health/live` → exit code 7 (connection refused).
- Host 192.168.1.240 pings fine (0.127 ms RTT). Container, not network.
- `scripts/health_check.py` reported `minio: FAIL`. `n8n: PASS`.
- Article-processor errors in the execution log were `ECONNREFUSED 192.168.1.240:9000` cascading into the global error handler → the "blank email" Aaron was seeing was the error-handler email, HTML-only, rendering poorly in some clients.

Root cause: **MinIO container on the Windows MiniPC was down.** Aaron restarted it. Post-restart `health_check.py` passed on all 4 checks — critically, `brain_dumps: 11 brain dump file(s) found`. Content was intact the whole time; the pipeline just couldn't read it.

The Codex recovery plan (`Obsid.md`) was directionally correct (conflated skip reasons, HTML-only emails) but had misdiagnosed the ingestion-path gap — there was no missing data, just a missing socket.

## What landed

Four commits on `polish/prod-ready`, each independently revertible:

### `d860b87` — stabilize: land MTL-append parity, weekend-planner registration, GCAL placeholder
Five uncommitted files shipped as-is so the hardening diff stays reviewable:
- `tools/process_brain_dump.py`: new `append_tasks_to_mtl()` — CLI parity with n8n's append-to-MTL stage. Reads MTL, dedups against existing task descriptions, appends new ones under a `## Brain Dump Capture — YYYY-MM-DD` header.
- `workflows/n8n/brain-dump-processor-v2.json`: added Read MTL → Append Tasks → Write MTL stage (93 lines).
- `scripts/setup-n8n.sh`: register weekend-planner workflow + hydrate `__GCAL_CRED_ID__` placeholder.
- `workflows/n8n/article-processor.json`, `vault-health-report.json`: minor tweaks.

### `b0b7dc5` — test(workflows): add production-hardening assertions (red)
Five new assertions in `tests/test_workflow_templates.py`, all failing against the then-current tree (13 failures total with parametrization):
- `test_scheduled_workflows_wire_error_workflow` — parametrized over 12 scheduled workflows.
- `test_email_nodes_have_text_fallback` — enforces text multipart when emailFormat is html/both.
- `test_minio_download_nodes_have_continue_on_fail` — branching-before-fail-loud.
- `test_skip_reasons_use_canonical_enum` — `{source_prefix_empty, minio_offline, queue_missing, queue_empty, no_new_items}`.
- `test_morning_briefing_runs_after_brain_dump` — UTC cron-minutes comparison.

### `15f4902` — harden(workflows): dual-body emails, errorWorkflow wired, cron decoupled
Made all 5 assertions green without touching preserved patterns:
- **errorWorkflow** `jIOFmhr37mXEhlHz` wired on 10 workflows that were missing it (2 had empty string, 8 had no field). `daily-note-creator-v2` and `weekend-planner` already wired.
- **Dual-body emails** (`emailFormat: "both"` + `text` fallback) on the 6 email nodes that were HTML-only:
  - `error-handler`: `Format Error` now emits `textBody`; `Email: Error Alert` reads it.
  - `morning-briefing`: inline expression referencing overdue/today/capture counts.
  - `overdue-task-alert-v2`, `weekly-digest-v2`, `vault-health-report`, `system-health-monitor`: concise inline summaries from existing Code-node outputs.
- **`article-processor/S3: Read Article Queue`**: `continueOnFail: true` (was missing — this is why MinIO outage fired the global error handler instead of letting the workflow branch cleanly).
- **`morning-briefing` cron** shifted from `0 12 * * *` → `30 12 * * *` (7:00 → 7:30 CDT). Previously the briefing ran in the same slot as the brain-dump processor, so "yesterday's captures" was perpetually one day stale. Now 30 min after brain-dump finishes, 30 min before `overdue-task-alert-v2` at 8:00 CDT — no collision.

### Final docs+audit commit
- `scripts/audit_workflow_runlogs.py` — enforces the skip_reason enum + `status: "skipped"` always carrying a reason. Mirrors the test assertion; prevents the "10 days of no_work logs" failure mode from recurring.
- `CLAUDE.md`: corrected S3 cred family from `aws` → `s3` (was doc drift; the auditor is the truth); updated morning-briefing row to reflect 7:30 CDT; added the three audit scripts to the Scripts table; new `## NotebookLM` subsection marking `d056e9d5-...` as authoritative and `a428969b-...` as superseded.
- `docs/session-logs/2026-04-12-full-memory-snapshot.md`: added a SUPERSEDED banner at the top pointing at the new notebook ID.
- This session log.
- NotebookLM sources refreshed via CLI (external state, not committed).

## Preserved patterns (did NOT touch)

- `executionOrder: "v1"` on every workflow — v0 re-executes upstream nodes on multi-input nodes, which is what created double-sends of the weekly digest in a prior session.
- Binary reads via `await this.helpers.getBinaryDataBuffer(0, 'data')` — the filesystem-v2 storage mode rule from the 2026-04-12 snapshot.
- Email-as-dead-end topology — `audit_workflow_connections.py` enforces it; `test_email_nodes_do_not_feed_log_nodes` regression-guards it.
- S3 credential family = `s3` everywhere, never mixed with `aws`.

## Verification

| Check | Result |
|-------|--------|
| `scripts/health_check.py --json` | all 4 green (minio, n8n, vault_files=4/4, brain_dumps=11) |
| `pytest -q` | 151 pass, 1 skip |
| `scripts/audit_workflow_credentials.py` | exit 0 |
| `scripts/audit_workflow_connections.py` | exit 0 |
| `scripts/audit_workflow_runlogs.py` | exit 0 |
| `python3 -c "json.loads(...)"` across all 15 workflow JSONs | all parse |

## Deferred

- Full article-processor skip branch (IF node → Build Skip Log → dedicated S3 write + email). Current fix (`continueOnFail` + silent empty-queue fallthrough) meets the assertion but is less observable than the plan's full recommendation. Land in a follow-up when there's a concrete skip event to harvest as a test fixture.
- Brain-dump `skip_reason` split between `minio_offline` vs `source_prefix_empty`. Code path exists (`_noFiles` flag) but doesn't distinguish the cause yet. With MinIO now healthy and `continueOnFail` on the List node would capture the offline case — not yet wired. Same follow-up as above.
- Live deploy to n8n pending Aaron's confirmation of which deploy path to use: `scripts/setup-n8n.sh` (repo-canonical, tested) vs `/tmp/deploy_workflows.py` (memory-snapshot-recommended, hardcoded cred IDs, not in repo).

## NotebookLM

Sources pushed post-commit to `d056e9d5-64d9-4f64-aa94-faff603de835`:
- `docs/session-logs/2026-04-12-full-memory-snapshot.md` (with the new superseded banner)
- `docs/session-logs/2026-04-19-production-readiness-recovery.md` (this file)

Prior sources all dated 2026-04-03 — a 2+ week gap now closed.

## Commit sequence

```
15f4902 harden(workflows): dual-body emails, errorWorkflow wired, cron decoupled
b0b7dc5 test(workflows): add production-hardening assertions (red)
d860b87 stabilize: land MTL-append parity, weekend-planner registration, GCAL placeholder
be12a7c feat(phase1+2): fix daily note creator, archive tasks, add weekend planner   (pre-existing baseline)
```

Plus the final docs+audit commit that includes this log.

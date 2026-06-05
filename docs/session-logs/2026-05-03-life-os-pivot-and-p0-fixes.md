# Life-OS Pivot + P0 Recovery — 2026-05-03

**Branch:** `polish/prod-ready` | **Commit:** `2b518b1`
**Duration:** One session, inline execution. Auto mode.

---

## Reframe — pipeline → Life OS

Aaron explicitly reframed the project: **OHO is a personal Life Operating System across 8 domains, not a brain-dump pipeline.** Task-level comments/threading is an explicit ask. This reframe drives the v1.0 roadmap (P1→P7) committed to memory.

## Root cause of the 11-day silence

Brain-dump n8n cron had been writing 276-byte "skipped" stubs every day since 2026-04-22 while 11 brain-dump files (10 with content, 1 placeholder) sat in MinIO. Two compounding bugs:

1. **Cron fired 5–6 hours late.** Crons were UTC-adjusted from a pre-`settings.timezone` era, then `timezone: America/Chicago` was added later — double-applying the offset. Brain-dump fired at noon Chicago, not 7AM. Same for morning-briefing, overdue-alert, weekly-digest, vault-health.
2. **List step failed auth, was mislabeled `source_prefix_empty`.** The list node was an HTTP+SigV4 request bound to `__AWS_CRED_ID__` placeholder, which `setup-n8n.sh` falls back to leaving literal when `AWS_CRED_ID` env var is missing. Auth failed every day, caught by `continueOnFail`, and the no-work fallback labeled it `source_prefix_empty` — same shape as a legitimately empty inbox.

Codex's recovery plan correctly named both classes of bug. What it understated: the `source_prefix_empty` mislabel was the load-bearing piece — without it, an alert would have fired daily. The `audit_workflow_runlogs.py` enum-canary existed exactly to prevent this; it just hadn't been extended with `minio_auth_error` yet.

## What landed in `2b518b1`

### Cron timezone reconciliation (5 workflows)
`brain-dump-processor-v2` `0 7 * * *` · `morning-briefing` `30 7 * * *` · `overdue-task-alert-v2` `0 8 * * *` · `weekly-digest-v2` `0 18 * * 0` · `vault-health-report` `0 20 * * 0`. All run in `America/Chicago`. Article-processor was correct (already had both 8AM + 7PM local triggers).

### MinIO list path rewritten
Replaced HTTP+SigV4 list + XML parser in [brain-dump-processor-v2.json](workflows/n8n/brain-dump-processor-v2.json) with a single `n8n-nodes-base.s3` `list` node bound to the existing `MinIO S3` (`s3` family) credential. Same pattern `vault-health-report` already uses. Eliminates an entire class of credential-family-mixing bugs.

### Truthful skip_reason
Added `minio_auth_error` and `minio_list_failed` to the canonical enum in [scripts/audit_workflow_runlogs.py](scripts/audit_workflow_runlogs.py) and [tests/test_workflow_templates.py](tests/test_workflow_templates.py). The new no-work builder distinguishes `_listFailed` (→ `minio_auth_error`) from authenticated-empty (→ `source_prefix_empty`) so silent-failure-as-empty can never recur.

### Backlog drain in safe mode
Added `--no-reset` flag to [tools/process_brain_dump.py](tools/process_brain_dump.py). Ran it: 5 new tasks (3 Home, 2 Personal) appended to MTL with `[source:: [[…]]]` backrefs. Source brain-dump files left intact pending P1's safe-reset gates.

### NotebookLM ID reconciliation
CLAUDE.md called `d056e9d5-…` authoritative — that notebook does not exist in the user's account. The "superseded" `a428969b-…` actually still holds 9 historical session-log sources. Made `a428969b-…` authoritative; recorded `844aa6a1-…` Working Memory as a sidecar; flagged `d056e9d5-…` as a phantom in CLAUDE.md.

### Dead placeholder removal
Removed `__AWS_CRED_ID__` and `__MINIO_HOST__` from [scripts/setup-n8n.sh](scripts/setup-n8n.sh). They had no remaining consumers.

## Lessons (durable)

1. **n8n cron + workflow-level timezone**: when `settings.timezone` is set, cron is local time. Don't UTC-adjust. Test this in `tests/test_workflow_templates.py`.
2. **Credential family rule**: `n8n-nodes-base.s3` ↔ `s3`; `n8n-nodes-base.httpRequest` SigV4 ↔ `aws`. Never mix. If a list step needs auth that's not already wired, switch to native `s3` — don't add an `aws` cred.
3. **Audit regex caveat**: `_SKIP_REASON_RE` only matches `skip_reason: 'literal'`. Computed values bypass it. Use spread to keep literals visible: `{ skip_reason: 'foo', ...baseLog }`.
4. **NotebookLM verify discipline**: before trusting any documented notebook ID, run `~/.notebooklm-venv/bin/notebooklm list --json`. Memory snapshots can hold IDs for notebooks that never existed or got deleted.
5. **`--no-reset` safe drain**: when the cron path is broken AND source files exist, drain values without touching sources. Reset only after gates land.

## Roadmap (committed to project memory)

| Phase | Theme | Status |
|---|---|---|
| **P0** | Stop the bleed | ✅ shipped |
| **P1** | Safe reset — state machine + extraction receipts + raw-source archive + `last_checked`/`last_processed` + truthful run logs | NEXT — non-negotiable, boring, hard to break |
| **P2** | Threaded tasks (stable `task_id` not slugs) | Design after P1 (spec covers IDs, migration, dedup, backlinks, completion sync, audit) |
| **P3** | Capture-from-anywhere (Telegram, email, voice) | After P1 + likely P2 |
| **P4** | Decision-ready briefings | After P3 |
| **P5** | Review rituals | After P4 |
| **P6** | Domain-aware UX | After P5 |
| **P7** | Insight loop / AI coach | Last |

**Hard rules from Aaron 2026-05-03:**
- P1 closes the integrity layer before any expansion. No capture surfaces, no insights, no domain UX while P1 is open.
- P2 is design-first; spec before code.
- "Insight v0" stays read-only and non-blocking if it ever ships, after P1 (and probably P2).

## Verification

- 4 workflow audits: ✅ (credentials, runlogs, connections, email-format)
- pytest: ✅ 202 passed, 1 skipped
- MTL post-drain: 2 new "Brain Dump Capture — 2026-05-03" blocks (3 + 2 tasks)
- Source brain-dump files: untouched (verified via `--no-reset`)

## Next session

Begin P1 design. `docs/adr/2026-05-XX-brain-dump-state-machine-and-receipts.md`. Code change comes after the spec.

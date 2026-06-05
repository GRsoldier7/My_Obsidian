# ADR-0005: Brain-Dump Pipeline Integrity Layer — State Machine, Receipts, Gated Reset

**Date:** 2026-05-03
**Status:** Accepted — live cutover completed 2026-05-04; 7-day stability
window open before marking Implemented
**Deciders:** Aaron DeYoung
**Supersedes:** the implicit "always-reset" behavior of [tools/process_brain_dump.py](../../tools/process_brain_dump.py) and [workflows/n8n/brain-dump-processor-v2.json](../../workflows/n8n/brain-dump-processor-v2.json) (both pre-2026-05-03)

---

## Context

The 2026-05-03 P0 commit (`2b518b1`) recovered the brain-dump pipeline from 11 days of silent skipped runs but did not close the integrity layer. Today the pipeline still has structural problems:

1. **Reset is unconditional.** [tools/process_brain_dump.py:1471–1475](../../tools/process_brain_dump.py#L1471) clears extracted sections regardless of whether downstream writes (MTL append, articles queue, notes, review queue) actually verified.
2. **`reset_applied: true` is asserted, not computed.** The n8n workflow's "Build Output Files" Code node hardcodes the field; the Python path treats it similarly. A failed MTL write produces a run log claiming reset was applied.
3. **Source data has no archive before clearing.** Recovery currently depends on MinIO bucket versioning. That works, but it isn't the pipeline's own contract.
4. **`last_processed` advances on every successful read of the file.** It cannot distinguish "we successfully scanned it" from "we successfully extracted and durably wrote outputs."
5. **Crash mid-run leaves no trace.** If the workflow dies between extraction and reset, the next run can't tell what was already done.

Aaron's 2026-05-03 directive (saved as feedback memory `feedback_p1_integrity_first.md`):

> P1 is non-negotiable, boring, hard to break. While P1 is open: no new capture surfaces, no insights/coach scripts, no domain UX scope.

This ADR defines the integrity layer that P1 must deliver. P2 (threaded tasks) and P3 (capture-from-anywhere) compose on top of this; they do not modify it.

---

## Decision

Introduce four coordinated mechanisms, all centred on a single principle: **the receipt is the authority. Nothing else asserts what was done.**

1. **State machine** for each brain-dump source file, persisted in frontmatter. Six states: `empty | has_content | scanning | extracted | partial | error`.
2. **Frontmatter contract** with eight canonical fields including `content_hash`, `last_checked`, `last_processed`, `last_processed_hash`, and `last_receipt`.
3. **Extraction receipt** — a per-file-per-run JSON in `99_System/extraction-receipts/`, content-addressed by sha256. Records the archive write, every per-section write target, and a verified bool on each. The receipt is written *before* any source clearing and read back from MinIO to drive the gate.
4. **Per-section gated reset** — a section clears only if its receipt entry is `verified: true`. Failed sections stay; a retention block at the top of the file documents what was held back and why.

The Python processor (`tools/process_brain_dump.py`) and the n8n workflow share
one logic kernel: `tools/bd_integrity.py`. n8n calls a dedicated OHO HTTP runner
sidecar, and that runner shells out to Python for the integrity-critical work
(state transition, receipt build, frontmatter update, gate decision) instead of
re-implementing it in JavaScript. This eliminates the JS/Python divergence that
caused the P0 hardcoded `reset_applied: true` bug.

---

## State Machine

Persisted in frontmatter `status:` field.

| From          | To             | Condition                                                                                                                           |
| ------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `empty`       | `has_content`  | Body non-empty AND `current_hash != last_processed_hash`. Detected on the next scan after a user edit.                              |
| `has_content` | `scanning`     | A run starts processing this file. `last_checked` updated, `content_hash` captured.                                                 |
| `scanning`    | `extracted`    | Archive verified AND receipt verified AND every section's receipt entry has `verified: true`. All sections cleared, `last_processed` and `last_processed_hash` advance. |
| `scanning`    | `partial`      | Archive verified AND receipt verified, but at least one section has `verified: false`. Verified sections cleared; failed sections retained with a retention block. `last_processed` does NOT advance. |
| `scanning`    | `error`        | Pre-extraction failure (file read, parse, or archive write failed). No reset. No receipt finalized.                                 |
| `partial`     | `scanning`     | Next run re-picks the file. Only the un-verified sections are retried.                                                              |
| `error`       | `scanning`     | Same — eligible for re-pick.                                                                                                        |
| `extracted`   | `empty`        | Implicit: after a successful reset, the body is empty, so the next scan moves it to `empty`.                                         |
| `empty`       | `has_content`  | User edits the file again.                                                                                                          |

**Work-eligible states for a scheduled run:** `has_content`, `partial`, `error`. `scanning` is a transient lock — see "Crash recovery" below. `empty` is skipped.

```
                       ┌──────────────────────────┐
                       │           empty          │
                       └─────────────┬────────────┘
                                     │  user edits → hash changes
                                     ▼
                       ┌──────────────────────────┐
                       │       has_content        │◀──────┐
                       └─────────────┬────────────┘       │
                                     │  run starts        │
                                     ▼                     │
                       ┌──────────────────────────┐       │  retry
                       │         scanning         │───────┤
                       └────┬──────────┬─────────┘       │
                            │          │                 │
              all verified  │          │  some failed    │
                            ▼          ▼                 │
                ┌─────────────┐  ┌──────────────┐        │
                │  extracted  │  │   partial    │────────┤
                └──────┬──────┘  └──────────────┘        │
                       │                                 │
                       │  body now empty                 │
                       └──────────► empty                │
                                                         │
                            ┌────────────────┐           │
                            │      error     │───────────┘
                            └────────────────┘
                              ▲
                              │ pre-extraction failure
                              └─ from scanning
```

---

## Frontmatter Schema (Canonical)

Every file in `00_Inbox/brain-dumps/` has exactly this frontmatter. Field order is fixed.

```yaml
---
domain: personal                  # existing — kept (display name, free-form)
area: personal                    # existing — kept (8-domain enum)
status: empty                     # state-machine value
content_hash: sha256:3a9c2f1b...  # sha256 of normalized body (excludes frontmatter + retention block)
last_checked: 2026-05-04T07:00:14Z      # ISO-8601 UTC. Set every authenticated read.
last_processed: 2026-05-03T07:00:42Z    # ISO-8601 UTC. Set ONLY on `extracted` transition.
last_processed_hash: sha256:b2e8f4...   # the content_hash that was successfully processed.
last_receipt: extraction-receipts/Faith-20260503-3a9c2f1b.json   # null if never processed.
last_partial_reasons: []          # array of {section, reason, dt}; populated only when status: partial
---
```

**Update rules:**

- `last_checked` — every authenticated read. Heartbeat. Updated even when status stays `empty`.
- `content_hash` — recomputed every scan from the **normalized** body (frontmatter stripped, retention block stripped, then sha256). Stored even when `empty`.
- `last_processed` + `last_processed_hash` — written **only** when reaching `extracted`. Never on `partial`, never on `error`.
- `last_receipt` — pointer updated on `extracted` AND `partial` (a partial run produces a receipt).
- `last_partial_reasons` — cleared on `extracted`. Populated only when `status: partial`.
- `status` — written by the state-machine transition function in `bd_integrity.py`. Never hand-edited by individual writers.

**Why hash, not date, for "user edited":** comparing `current_hash != last_processed_hash` is unambiguous across timezones, partial states, and clock skew. Date comparison is not.

---

## Receipt Schema

One JSON per run-per-source, at `99_System/extraction-receipts/<source-stem>-<YYYYMMDD>-<sha8>.json`.

`<sha8>` is the first 8 hex of `content_hash`. This makes the receipt path content-addressed: same content → same receipt path; idempotent re-runs overwrite in place; orphans don't accumulate.

The filename stem is normalized only through
`tools.bd_integrity.slug_for_filename()`. Audits and future receipt-aware tools
must use that same helper rather than carrying their own slug logic. The
2026-05-04 audit false positive on `BrainDump — Home.md` came from a duplicate
normalizer that produced `BrainDump--Home` while the writer produced
`BrainDump-Home`.

```json
{
  "schema_version": 1,
  "source": {
    "key": "00_Inbox/brain-dumps/Faith.md",
    "filename": "Faith.md",
    "content_hash": "sha256:3a9c2f1b...",
    "size_bytes": 4823
  },
  "run": {
    "workflow": "brain-dump-processor",
    "run_id": "2026-05-04T07:00:14.219Z-Faith.md",
    "started_at": "2026-05-04T07:00:14Z",
    "finished_at": "2026-05-04T07:00:42Z",
    "executor": "python",
    "no_reset": false
  },
  "archive": {
    "key": "99_System/archive/brain-dumps/2026-05-04/Faith.md",
    "etag": "\"a1b2...\"",
    "size_bytes": 4823,
    "verified": true
  },
  "sections": [
    {
      "section": "✅ To Do's",
      "section_type": "tasks",
      "items_extracted": 3,
      "writes": [
        {
          "target": "mtl",
          "key": "10_Active Projects/Active Personal/!!! MASTER TASK LIST.md",
          "items": 3,
          "etag": "\"e4f5...\"",
          "size_bytes": 41203,
          "verified": true
        },
        {
          "target": "processed_file",
          "key": "00_Inbox/processed/2026-05-04-Faith-tasks.md",
          "items": 3,
          "etag": "\"f1a2...\"",
          "size_bytes": 612,
          "verified": true
        }
      ],
      "verified": true
    },
    {
      "section": "📰 Articles & Resources to Follow Up On",
      "section_type": "articles",
      "items_extracted": 1,
      "writes": [
        {
          "target": "articles_queue",
          "key": "00_Inbox/articles-to-process.md",
          "items": 1,
          "etag": null,
          "size_bytes": 0,
          "verified": false,
          "error": "head_object 503"
        }
      ],
      "verified": false
    }
  ],
  "summary": {
    "all_sections_verified": false,
    "verified_sections": ["✅ To Do's"],
    "failed_sections": ["📰 Articles & Resources to Follow Up On"],
    "reset_applied_count": 1,
    "final_status": "partial"
  }
}
```

Each `writes[*]` entry MAY include an optional `task_ids: [...]` field starting in P2. P1 ignores that field.

---

## Gate Semantics — When Is a Section "Safe to Clear"?

A section S in source F is safe to clear if and only if all four conditions hold:

1. The pre-reset archive `99_System/archive/brain-dumps/<YYYY-MM-DD>/<F>` exists and was head_object-verified (`receipt.archive.verified == true`).
2. The receipt JSON for this run was written to MinIO and head_object-verified.
3. The receipt's section entry for S has `verified: true`.
4. Every `writes[*]` entry inside that section has `verified: true` (head_object after PUT returned `ContentLength` matching the body sent, ETag captured).

If any of (1)–(4) fails for a section, that section's body stays. A retention block at the top of the file records the reason. The frontmatter `status` becomes `partial` and `last_partial_reasons` is populated.

`reset_applied_count` in the run log is **computed** by counting `writes_per_section` where `section.verified == true`. The shape `reset_applied: true|false` is removed from the log entirely. A static-analysis test (see "Test Plan") greps every n8n Code node for the string literals `reset_applied: true` and `reset_applied: false`; both must be absent.

### Crash Recovery

If the workflow crashes between archive write and receipt write, the source file still has `status: scanning` and `last_checked` is now stale. The work-eligible set excludes `scanning`, so the next run skips it — but a stale-lock detector in the audit script flags any `status: scanning` whose `last_checked` is more than 1 hour old, reverts it to its prior status (read from the most recent receipt), and the file becomes work-eligible again.

If the workflow crashes between receipt write and section clearing, the receipt exists with all `verified: true` flags, but the source still has its content. The next run reads the receipt, sees that all sections were verified, completes the clearing, and transitions to `extracted`. The receipt's content-addressed path means the rerun produces the same receipt key — overwrite in place, no orphan.

---

## Retention Block Format

When `status: partial`, prepend a single block immediately after the closing `---` of frontmatter, before the H1 title:

```markdown
> [!warning] Retention notice — 2026-05-04
> The following sections were NOT cleared because their downstream writes failed:
> - **📰 Articles & Resources to Follow Up On** — articles_queue write failed (head_object 503)
>
> Receipt: [[99_System/extraction-receipts/Faith-20260504-3a9c2f1b]]
> The next scheduled run will retry these sections automatically.
```

Format chosen because:
- Obsidian renders `> [!warning]` as a callout — visible to the user in the vault.
- Wikilink to receipt opens it directly in Obsidian.
- Block is fenced by blank lines so the body-hash normalization can strip it cleanly.

The `_strip_yaml_frontmatter` helper in `process_brain_dump.py` is extended to also strip the retention block (regex: `^> \[!warning\] Retention notice.*?(?=\n## |\n# |\Z)`) before computing `content_hash`. The retention block does NOT itself trigger `has_content` on the next scan.

---

## Truthful Run Log

`RunLog` (Python dataclass + n8n log-builder shape) gains:

```python
@dataclass
class RunLog:
    # ... existing fields ...
    receipts_written: int = 0
    files_by_state: dict = field(default_factory=lambda: {
        "empty": 0, "has_content": 0, "scanning": 0,
        "extracted": 0, "partial": 0, "error": 0
    })
    files_extracted: list = field(default_factory=list)
    files_partial:   list = field(default_factory=list)   # [{file, reasons}]
    files_error:     list = field(default_factory=list)   # [{file, error}]
    archive_writes_pass: int = 0
    archive_writes_fail: int = 0
    reset_summary: dict = field(default_factory=lambda: {
        "files_reset_full": 0,        # all sections cleared
        "files_reset_partial": 0,     # some sections cleared, some retained
        "files_reset_skipped": 0,     # no sections safe to clear
    })
```

The `reset_applied: bool` field is removed entirely. Replaced by `reset_summary` which is computed from receipts.

### New skip_reasons

Added to the canonical enum in BOTH [scripts/audit_workflow_runlogs.py](../../scripts/audit_workflow_runlogs.py) and [tests/test_workflow_templates.py](../../tests/test_workflow_templates.py):

- `archive_write_failed` — pre-reset archive failed; whole run aborted before any clear.
- `receipt_write_failed` — receipt PUT or its head_object failed; abort before reset.
- `state_lock_stale` — file was `scanning` with stale `last_checked`; recovery path took it.
- `content_hash_unchanged` — `last_processed_hash == current_hash` and status was `empty`; nothing to do.

Existing seven stay: `source_prefix_empty`, `minio_offline`, `minio_auth_error`, `minio_list_failed`, `queue_missing`, `queue_empty`, `no_new_items`.

---

## Audit Script — `scripts/audit_extraction_receipts.py`

Fail-fast. Runs in CI and as part of `vault-health-report`. Rules:

1. **Every reset event has a receipt.** For each run log in the last 14 days, every entry in `reset_summary.files_reset_full` and `reset_summary.files_reset_partial` MUST point to a receipt that exists in MinIO AND whose `summary.final_status` matches what the run log claimed.
2. **Every receipt's referenced source either exists or has an archive.** Orphans surfaced.
3. **No source has `status: scanning` with `last_checked` older than 1 hour.** Stale lock = audit fail.
4. **No source has `status: partial` older than 7 days.** Stale partial = unattended failure.
5. **No source has `status: extracted` AND non-empty extractable sections.** Should be impossible — defense in depth.
6. **Frontmatter completeness.** Every brain-dump source has all 8 canonical fields. Missing fields = drift = fail.
7. **content_hash sanity.** When `status: empty`, recomputing hash on the body must match `content_hash`.

Exit non-zero if any rule fails. Prints actionable findings: file, rule, what to do.

---

## Test Plan — Red Tests First

All tests added to `tests/test_brain_dump_integrity.py` (new file). Each MUST be red before implementation lands.

| # | Test | What it catches |
|---|------|-----------------|
| 1 | `test_mtl_append_failure_does_not_reset_section` | MTL head_object fails ⇒ tasks section stays, retention block added, status=partial. |
| 2 | `test_articles_queue_failure_does_not_reset_articles_section` | Articles write fails ⇒ articles section retained, tasks section still clears. |
| 3 | `test_partial_success_writes_retention_block_with_reasons` | Retention block format + `last_partial_reasons` populated. |
| 4 | `test_receipt_write_failure_refuses_all_clears` | Receipt PUT or head_object fails ⇒ no section clears. status=error. |
| 5 | `test_archive_write_failure_aborts_run_before_extraction` | Archive head_object fails ⇒ run aborts. No downstream writes attempted. |
| 6 | `test_canary_full_roundtrip_python` | Synthetic dump with known content → all writes verify → reset full → frontmatter shows status=empty, last_processed set, last_processed_hash matches. |
| 7 | `test_n8n_python_parity_via_jsonfixture` | Same canary fixture through Python and the n8n runner boundary produces the same receipt JSON shape. |
| 8 | `test_reset_applied_literal_absent_from_jscode` | Static-analysis: greps every n8n Code node for `reset_applied: true` and `reset_applied: false` literals. Both must be absent. |
| 9 | `test_skip_reason_enum_in_sync` | Existing pattern + 4 new skip_reasons present in both audit script and test enum. |
| 10 | `test_stale_scanning_lock_recovers` | File with status=scanning and last_checked > 1h: audit reverts to prior status from last receipt. |
| 11 | `test_content_hash_excludes_retention_block` | Adding a retention block does not change content_hash. |
| 12 | `test_no_reset_flag_writes_no_receipt_no_clear` | `--no-reset`: writes downstream targets but does NOT write a receipt and does NOT clear sections. status stays `has_content`. last_checked DOES update. |
| 13 | `test_idempotent_rerun_same_hash_writes_same_receipt_path` | Same content twice ⇒ same receipt key, overwritten in place, no orphan. |
| 14 | `test_receipt_etag_drift_invalidates_section_clear` | Receipt's recorded ETag for MTL no longer matches a fresh head_object at clear-time ⇒ refuse clear (something else overwrote MTL between write and verify). |
| 15 | `test_frontmatter_migration_idempotent` | Running the migration script twice on the same source file produces identical frontmatter. |
| 16 | `test_partial_to_extracted_clears_retention_block` | A partial-then-successful retry transitions cleanly: retention block removed, last_partial_reasons cleared. |

---

## n8n Parity Strategy — Single Source of Truth

The n8n workflow does NOT re-implement the gate in JavaScript.

**Logic kernel — `tools/bd_integrity.py`** (new module). Owns:
- State machine transitions
- Frontmatter read/write/normalize
- `content_hash` computation (with retention-block stripping)
- Receipt build + write + verify
- Per-section gate decision
- Retention block generation
- Reset writer (consumes receipt, returns new file body)

`tools/process_brain_dump.py` imports from `bd_integrity.py`.

**n8n call site:** the workflow uses an HTTP Request node:

```text
POST http://oho-runner:8080/process-brain-dump
Authorization: Bearer <OHO_RUNNER_TOKEN>
```

The runner is a FastAPI sidecar on the same Docker network as n8n. It exposes
only `/health` and `/process-brain-dump`; it accepts no arbitrary command
parameter. The fixed subprocess is:

```bash
python3 -u tools/process_brain_dump.py
```

with `cwd=/opt/oho`, environment loaded from `/opt/oho/.env`, a 180-second
timeout, a single-run lock, and bearer-token auth. n8n parses the runner's
`stdout_json` field and branches to success / no-work / error email paths.

Email policy after the 2026-05-04 cutover:

- `top_status == "success"` sends the digest email.
- `top_status == "no_work"` ends silently. The MinIO run log and receipt audit
  are the heartbeat; empty-day email is noise.
- `top_status in {"parse_error", "partial_or_error"}` sends the error notice.

**Why HTTP runner instead of pure-JS reimplementation:**
1. The integrity layer's correctness is load-bearing. Two implementations means two places to fix bugs and two places to drift. The 2026-05-03 hardcoded `reset_applied: true` bug came from exactly this pattern.
2. n8n 2.x does not activate workflows containing `n8n-nodes-base.executeCommand`, and n8n runs in Docker, isolated from the LXC host filesystem.
3. A sidecar preserves the single Python logic kernel without putting Python or `/opt/oho` inside the n8n container.
4. The runner contract is narrow: one endpoint, one fixed command, bearer auth, timeout, and a concurrency lock.
5. The HTTP boundary composes with future P2/P3 runner endpoints without depending on n8n's restricted node surface.

**Rejected 2026-05-04:** direct `executeCommand`. It failed activation on n8n
2.18.5 with `Unrecognized node type: n8n-nodes-base.executeCommand`, and the
n8n container also could not see `/opt/oho`.

**Recommendation:** ship the HTTP runner. The decision to keep TWO
implementations is what got us into this mess.

---

## Migration Plan — The 11 Existing Brain-Dump Files

Manual one-shot script `scripts/migrate_brain_dump_frontmatter.py`. Idempotent.

For each file in `00_Inbox/brain-dumps/`:

1. Read current frontmatter (today's files have `domain`, `area`, `last_processed`, `status` — older fields tolerated).
2. Compute `content_hash` from current normalized body.
3. Determine initial state:
   - Body empty ⇒ `status: empty`, `last_processed_hash: <current_hash>` (so the file isn't immediately re-picked as "edited since last processed").
   - Body non-empty ⇒ `status: has_content`, `last_processed_hash: null`, `last_processed: null`. Next scheduled run will pick it up.
4. Set `last_checked: <now-UTC>`, `last_receipt: null`, `last_partial_reasons: []`.
5. Preserve any unknown legacy fields (forward-compat).
6. Verified PUT.
7. Emit a per-file before/after migration report.

**Safety:**
- `--dry-run` flag default — must explicitly opt into writes.
- Run with the cron paused (or outside the 7AM CDT window).
- Versioning is on in MinIO; rollback path is `s3.list_object_versions(Prefix=key)`.
- Idempotent: re-running computes the same hash, no-ops.

---

## Rollout Sequence

Strictly ordered. Each step is a separate commit; each is independently revertible.

1. **ADR + design memo lands** (this document) — no behavior change.
2. **`tools/bd_integrity.py` module + tests 1–6, 11, 13, 15, 16** land. No integration with the live processor yet. All tests must be red, then green.
3. **`scripts/migrate_brain_dump_frontmatter.py` lands** — dry-run only by default. Tested via fixtures.
4. **Wire `process_brain_dump.py` to use `bd_integrity.py`.** The Python path goes live with gates. Tests 1–5, 6, 12 cover the live behavior. The `--no-reset` flag is preserved as the safety net.
5. **Run the migration on the 11 stranded files** during a manual window with cron paused.
6. **Wire n8n to the OHO runner** via HTTP Request. Test 7 (parity) and Test 8
   (no `reset_applied` literal) cover this. Re-deploy only this workflow via
   `scripts/deploy_n8n_workflow.py`; `scripts/setup-n8n.sh` is broader than this
   cutover.
7. **`scripts/audit_extraction_receipts.py` lands** + integrates into `vault-health-report`. Tests 9, 10, 14 cover audit logic.
8. **Deprecate the `--no-reset` safety net.** Once gates are proven (≥ 7 days of clean runs, no audit findings), remove the flag — or keep it as a documented escape hatch. Decide at that checkpoint, not now.

Each step lands its own commit. The branch (`polish/prod-ready` until P1 ships, then a fresh branch for P2) accumulates them. CI must pass after every commit.

---

## Out of Scope

Explicit list. None of these belong in P1:

- **P2 task threading / stable `task_id`.** Receipts have an OPTIONAL `task_ids: [...]` field per write entry that P2 will populate. P1 ignores it.
- **P3 capture-from-anywhere** (Telegram, email-forward, voice→text). P3 must use the same template generator as the migration script — that's a P3 prerequisite, not a P1 deliverable.
- **Insight loop / coach emails / domain-aware UX.** Forbidden until P1 closes.
- **Per-task reset granularity below the section level.** Explicitly rejected. Section-level reset is the boring choice.
- **Cross-file dedup beyond what `append_tasks_to_mtl` already does.**
- **Compacting `99_System/archive/brain-dumps/` over time.** Archive grows slowly (one file per source per processed-day). Revisit at v2.0.
- **Refactoring `tools/process_brain_dump.py`** beyond what's required to call into `bd_integrity.py`. The 1551-line file gets a surgical split, not a rewrite.

---

## Future-Proofing for P2

The `extract → write → verify → receipt → gate` boundary is task-agnostic. P2 plugs into it as additional write-targets, not a new state machine.

When P2 lands and tasks get stable IDs in `30_Tasks/<area>/`:

- Each `writes[*]` entry in the receipt gains an OPTIONAL `task_ids: [...]` field listing canonical IDs created by that write.
- The state machine is unchanged.
- The frontmatter is unchanged.
- The audit script gains one optional check: every `task_id` claimed in a receipt resolves to an existing `30_Tasks/.../task-X.md`.
- The retention block format is unchanged.
- The gate semantics are unchanged.

P1 should not paint us into a corner with task identity. It does not.

---

## Risks and Mitigations

| Risk                                                                  | Mitigation                                                                                                            |
| --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Runner call from n8n adds latency / failure surface.                  | Dedicated sidecar with fixed command, auth, timeout, concurrency lock, and n8n retry rule. Test 7 fixture-asserts shapes; Test 5 covers crash mid. |
| Migration corrupts existing source frontmatter.                       | `--dry-run` default; per-file before/after report; MinIO versioning is on; idempotent re-run.                         |
| Receipt accumulates over time (one per file per processed-day).       | At v2.0, add a compaction step: zip receipts older than 90 days under `_archive/`. Out of scope for P1.               |
| Hash normalization edge case (frontmatter quote styles, line endings) | `bd_integrity.py` enforces canonical normalization (UTF-8 NFC, LF endings, frontmatter stripped, retention stripped). Tested.  |
| Stale `scanning` lock blocks a file indefinitely.                     | Audit rule 3 (1-hour staleness) recovers automatically. Tested by Test 10.                                            |
| n8n re-implements the gate in JS again "to avoid the runner."         | Test 8 (static-analysis) makes that physically impossible to ship — `reset_applied: true|false` literals fail CI.     |

---

## Decisions Inside This ADR That I'm Making (No Aaron Sign-off Needed)

Per `feedback_cadence.md`: routine decisions inside an approved plan are mine to make.

- Receipt path is content-addressed (`<source>-<date>-<sha8>.json`).
- State machine has exactly 6 states, no more.
- Stale-lock threshold is 1 hour.
- `last_processed` advances ONLY on `extracted`.
- Retention block is an Obsidian callout, not a comment block.
- `--no-reset` flag stays in P1 as safety net; deprecation decision happens at step 8 of rollout, not now.

## Step 6 Deployment Decision

The original Step 6 deployment-surface decision was direct n8n
`Execute Command` versus keeping a JS-only reimplementation. The accepted
2026-05-04 decision is now:

- **n8n calls the dedicated OHO runner over HTTP.**
- The runner shells out to Python as the single logic kernel.
- n8n never re-implements the integrity gate in JavaScript.
- Direct `Execute Command` is rejected for brain-dump processing on n8n 2.x.

That preserves the core ADR decision — one Python implementation — while
matching the live n8n 2.x Docker runtime.

---

## Status Transitions for This ADR

- **Proposed** — Aaron reviews this document. No code lands until status is `Accepted`.
- **Accepted** — current. P1 code and live cutover are complete; the 7-day stability window is open.
- **Implemented** — when steps 2–7 of the rollout have landed and CI is green for ≥ 7 days. ADR status updated to reflect.
- **Superseded** — if a future ADR changes the integrity model. Receipts migrate via a `schema_version` bump.

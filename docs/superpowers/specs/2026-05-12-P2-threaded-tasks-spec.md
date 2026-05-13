# P2 — Threaded Tasks Design Spec

**Date:** 2026-05-12
**Phase:** P2 of the Life Orchestrator v1.0 Roadmap
**Status:** DESIGN — pre-implementation. This file is the working spec.
**Promotion path:** before any P2 code lands, this document MUST be promoted to
`docs/adr/0007-threaded-tasks.md` (Status: Accepted). The implementation rollout
itself MUST NOT begin until ADR-0005 / P1+P1.5 / ADR-0006 have run clean in prod
for ≥ 7 consecutive days (no audit findings, no `partial` stragglers > 7 days).
The current soak window opened with `a1bd438` and the deployment runbook in
[docs/runbook-deploy-python-to-lxc.md](../../runbook-deploy-python-to-lxc.md).
**Author:** Polychronos planning team — Aaron DeYoung approver
**Supersedes when implemented:** the pre-2026-05-12 implicit "task = MTL line"
identity model used by [tools/process_brain_dump.py § append_tasks_to_mtl](../../../tools/process_brain_dump.py)
(lines 830–891) and the description-only dedup in that same function.

---

## TL;DR

Today an OHO task is a string in `!!! MASTER TASK LIST.md`. It has no
durable identity. Re-extraction relies on lowercased-prefix dedup against
the existing MTL. If Aaron edits the wording, the task is "new again."
If he splits one item into two, history disappears. If a task is completed
in MTL and then re-captured Tuesday morning, the dedup may or may not
catch it depending on how it was reworded.

P2 introduces **stable per-task identity**. A task gains an immutable
`task_id`, a backing file under `30_Tasks/<area>/`, and a thread of
history (captures, splits, merges, blocks, completions, reopens).
The MTL becomes a Dataview-friendly *view* over the backing files, not
the source of truth for identity. Bidirectional sync keeps the magical
Obsidian-checkbox UX intact while making the system robust to edits,
re-captures, re-extractions, splits, merges, and human off-script changes.

This is the largest design lift in v1.0. It is intentionally design-first
because a mistake in the identity model is the kind of mistake you cannot
walk back without a painful migration.

---

## 1. Goal & Magical Moment

**Goal:** Every captured intention becomes a first-class, threaded,
addressable, auditable entity for the lifetime of Aaron's Life OS.

**Magical Moment v1 — "the Tuesday→Thursday split":** Aaron brain-dumps
on Tuesday: "Decide on hip surgery." Wednesday he edits the MTL line to
"Decide on hip surgery — talk to Christy first." Thursday in a brain
dump he says "Call Dr. Garcia about hip + read the imaging notes." The
P2 system recognises the Thursday capture is *related to* the Tuesday
task, prompts a split into two child tasks (`t-2026w19-a3f1` "Talk to
Christy" / `t-2026w19-c08b` "Call Dr. Garcia"), keeps both linked to the
original parent (`t-2026w19-92ab`), and the parent's backing file shows
the full thread: captured → edited → split → status:done when both
children close. Weekly review surfaces this as one decision-thread, not
three orphan lines.

**Magical Moment v2 — "the conversation, not the list":** Sunday weekly
review opens the Decisions Dashboard. Each thread is rendered as a card:
parent task, its split children, source brain dumps, completion timestamps.
Aaron asks "what did I decide about the hip?" — one click on the thread
reveals every capture, every edit, every split, with timestamps. The
Life OS is not a flat task list — it is a *conversation* with himself
over weeks.

**Magical Moment v3 — "manual edits never destroy history":** Aaron
edits an MTL line on his phone (Remotely-Save → MinIO) while a
brain-dump processor run is mid-flight on the LXC. The task identity
survives because identity is in the wikilink, not the description text.
The next audit pass detects the description drift, syncs the backing
file, and surfaces no false-duplicate.

---

## 2. ID Scheme

### 2.1 Decision

```
task_id := "t-" <iso-year> "w" <iso-week-2digit> "-" <4-hex>
example:  t-2026w19-a3f1
```

- `t-` prefix is a hard literal — every task ID starts with `t-`. This
  reserves the namespace cleanly for future ID kinds (`p-` projects,
  `n-` notes, `d-` decisions) if we ever want them.
- `<iso-year>w<iso-week>` is the ISO-8601 week-of-year of capture. Two
  digits, zero-padded.
- `<4-hex>` is 16 random bits from `secrets.token_hex(2)` generated at
  capture time. **Never reused** across the lifetime of the vault.

### 2.2 Why this shape

| Property | Choice rationale |
|----------|------------------|
| **Sortability** | Lexicographically sorts by week of capture. `t-2026w19-…` precedes `t-2026w20-…`. Useful in file listings, audits, weekly review. |
| **Human readability** | A glance at `t-2026w19-a3f1` tells Aaron "captured in week 19 of 2026." Beats a pure UUID for vault navigation. |
| **Collision math** | 16 bits = 65,536 slots per week. Birthday-bound on collision = √65,536 ≈ 256 captures/week. Aaron averages ~30 tasks/week peak; collision probability per task ≤ 0.05%. Collisions are detected at write time (see § 13 audit) and resolved by regenerating the suffix — never silently. |
| **Filesystem-safe** | Lowercase hex + hyphens. No glyphs Obsidian/MinIO/MacOS Smart Mail systems mangle. Survives copy/paste across iMessage, SMS, Telegram. |
| **No timestamp inside the ID** | Capture time lives in the YAML frontmatter, not the ID. Keeps the ID short and stable even if the wall-clock is off. |
| **Not a UUIDv4** | UUIDs are 36 chars; visually noisy; not sortable; carry no human signal. We're optimising for human + Dataview, not external systems. |
| **Not monotonic** | Monotonic counters require central allocation. The brain-dump processor, the Telegram capture surface (future P3), and a future Mac-native quick-capture must all generate IDs without coordination. |

### 2.3 Where stored

- **Authoritative:** the backing file's filename (`30_Tasks/<area>/t-2026w19-a3f1.md`) AND its YAML frontmatter `id:` field.
- **Mirror:** every MTL line for an open task ends with `[id:: t-2026w19-a3f1]` (a Dataview inline field) and links to the backing file via `[[t-2026w19-a3f1|description]]`.
- **Receipts:** ADR-0005 receipts gain a `writes[*].task_ids: [...]` field listing IDs created/touched by each write. This is the audit chain back to the brain dump.

### 2.4 Generation contract

```python
def new_task_id(now: datetime | None = None) -> str:
    """Return a brand-new task_id. Caller MUST verify uniqueness against the
    30_Tasks/ directory before writing — collisions regenerate.
    """
```

Implementation lives in `tools/task_id.py`. Pure function, easy to unit test.

---

## 3. Backing File Shape

### 3.1 Path

```
30_Tasks/<area>/<task_id>.md
```

`<area>` is one of the 8 canonical areas:
`faith family business consulting work health home personal`. The area
folder is part of the path, NOT replicated in frontmatter as a string —
the path is the source of truth for area; if Aaron moves a file from
`30_Tasks/health/` to `30_Tasks/personal/`, the next audit reconciles
the frontmatter to match the path. (Path > frontmatter for area; see
§ 8 reconciliation rules.)

### 3.2 Frontmatter (canonical, ordered)

```yaml
---
id: t-2026w19-a3f1
schema_version: 1
status: active           # captured|triaged|active|in_progress|blocked|done|archived|split|merged
priority: A              # A|B|C|null
area: health             # mirrors the parent folder; reconciliation source of truth = folder
due: 2026-05-30          # ISO date, optional
created_at: 2026-05-12T07:00:42Z
updated_at: 2026-05-12T07:00:42Z
completed_at: null       # ISO timestamp; set when status=done
description_hash: sha256:b14c…  # over the canonical description text
source:
  brain_dump: 00_Inbox/brain-dumps/Health.md
  receipt: 99_System/extraction-receipts/Health-20260512-3a9c2f1b.json
  section: "✅ To Do's"
  line_range: [42, 42]          # inclusive 1-indexed line numbers at extraction time
  origin_hash: sha256:9f2c…     # hash of the source brain-dump span — see § 7
parent: null                    # task_id of parent if this is a child of split
children: []                    # task_ids of children if this was split
related: []                     # peer task_ids — manual or audit-discovered
blocked_by: []                  # task_ids this task is waiting on
blocks: []                      # task_ids waiting on this task
tags: []                        # free-form Obsidian tags, optional
explore: false                  # opt-in curiosity flag
---
```

Field rules:

| Field | Mutability | Owner |
|-------|------------|-------|
| `id` | Immutable | Generator |
| `schema_version` | Bump only via migration | Migration tool |
| `status` | Mutable by state-machine transitions only | `tools/task_state.py` |
| `priority` | Mutable by user (Obsidian) or extractor | Either; reconciliation: last-write-wins by `updated_at` |
| `area` | Mutable by moving the file | Folder = truth |
| `due` | Mutable | User or extractor |
| `created_at` | Immutable after creation | Generator |
| `updated_at` | Touched on every change | Whoever writes |
| `completed_at` | Set once at status→done; reset to null on reopen | State machine |
| `description_hash` | Recomputed on every description write | Writer |
| `source.*` | Immutable after first set | Extractor |
| `parent` / `children` | Mutable only via split/merge ops | State machine |
| `related` | User or audit | Either |
| `blocked_by` / `blocks` | User or audit | Either |
| `tags` | User | User |
| `explore` | User or extractor | Either |

### 3.3 Body conventions

```markdown
# Decide on hip surgery — talk to Christy first

> [!summary]+ At a glance
> - Area: `health` · Priority: `A` · Due: `2026-05-30`
> - Status: `active` since 2026-05-12T07:00:42Z
> - Source: [[00_Inbox/brain-dumps/Health|Health brain dump]] line 42

## Description

Decide on hip surgery — talk to Christy first.

## Notes

_(free-form — Aaron writes here)_

## Thread / Audit Log

- **2026-05-12 07:00 UTC** · captured · from `Health.md` line 42 · receipt `Health-20260512-3a9c2f1b`
- **2026-05-13 14:22 UTC** · description edited via MTL · `"Decide on hip surgery"` → `"Decide on hip surgery — talk to Christy first"`
- **2026-05-14 09:01 UTC** · split into [[t-2026w19-c08b]] (Call Dr. Garcia) and [[t-2026w19-d4e3]] (Read imaging notes)

## Related

- Parent: _(none)_
- Children: [[t-2026w19-c08b]] · [[t-2026w19-d4e3]]
- Blocked by: _(none)_
- Blocks: _(none)_
```

Body sections are **conventional, not enforced**. The audit script
only requires frontmatter validity. The state-machine writer
appends to `## Thread / Audit Log` automatically; humans can write
anywhere in `## Notes`.

### 3.4 Sample rendered file

The full sample above is the canonical sample. Tests assert that a
freshly-created task from a brain-dump extraction produces a file
byte-equal to a golden fixture in `tests/fixtures/threaded_tasks/`.

---

## 4. MTL Line Shape

### 4.1 New canonical bullet

**Today (P1.5):**
```
- [ ] Decide on hip surgery [area:: health] [priority:: A] [due:: 2026-05-30]
```

**P2:**
```
- [ ] [[30_Tasks/health/t-2026w19-a3f1|Decide on hip surgery]] [id:: t-2026w19-a3f1] [area:: health] [priority:: A] [due:: 2026-05-30]
```

### 4.2 Dataview compatibility

All existing Dataview queries used by the Command Center (see
[tools/build_command_center.py § render_ready_to_act etc.](../../../tools/build_command_center.py)) keep working
unchanged because they key on:

- the open-checkbox state (`!completed`)
- the inline fields `area`, `priority`, `due`
- the `explore` flag

Two new fields become queryable:
- `id` — `WHERE id = "t-2026w19-a3f1"` for direct addressability
- `[[wikilink]]` — Dataview already renders the wikilink as the task text

The `parse_mtl_open` parser in `build_command_center.py` gains one
additional field per task:

```python
TASK_ID_RE = re.compile(r"\[id::\s*(t-\d{4}w\d{2}-[0-9a-f]{4})\]")
```

The existing description regex must strip both `[id::…]` AND the wikilink
to render plain text. A pure-function test
(`tests/test_command_center.py::test_parse_mtl_open_handles_threaded_line`)
covers this.

### 4.3 Mixed-format tolerance

During migration and forever after, the parser MUST accept both shapes
(P1 inline-only and P2 wikilink+id). Aaron may legitimately add a
hand-typed task that has no backing file yet — that's a `triaged-pending`
state we handle in § 5.

---

## 5. State Machine

### 5.1 States

```
                         ┌──────────────┐
                         │   captured   │  ← raw extraction; not yet triaged
                         └──────┬───────┘
                                │  AI triage / user review (§ P3-aware: optional)
                                ▼
                         ┌──────────────┐
                         │   triaged    │  ← assigned area + priority; ready to do
                         └──────┬───────┘
                                │  user opens / picks up
                                ▼
                         ┌──────────────┐
                         │    active    │  ◀─────────────┐
                         └─────┬────────┘                │
                ┌──────────────┼──────────────┐          │
                │              │              │          │
                ▼              ▼              ▼          │
        ┌──────────────┐ ┌──────────┐ ┌──────────────┐   │
        │ in_progress  │ │ blocked  │ │   split      │   │
        └──────┬───────┘ └────┬─────┘ └──────────────┘   │
               │ done         │ unblocked                │
               ▼              └──────────────────────────┘
        ┌──────────────┐
        │     done     │
        └──────┬───────┘
               │ user reopens                  ┌──────────────┐
               ├──────────────────────────────►│   merged     │  (target of merge op)
               │                               └──────────────┘
               ▼
        ┌──────────────┐
        │   archived   │  ← swept out of active filesystem; readable via audit
        └──────────────┘
```

### 5.2 Transitions

| From | Event | To | Trigger | Audit-log line |
|------|-------|----|---------| ---------------|
| (none) | `task.create` | `captured` | Brain-dump extractor | `captured · from <source> · receipt <key>` |
| `captured` | `task.triage` | `triaged` | Extractor (regex confidence ≥ high) OR user review | `triaged · area=<a> priority=<p>` |
| `captured` | `task.send_to_review` | `captured` | Extractor (low confidence) | (no transition; lands in review queue instead) |
| `triaged` | `task.activate` | `active` | First MTL surfacing OR user opens | `activated` |
| `active` | `task.start` | `in_progress` | User adds `🚧` tag OR manual | `started` |
| `active` / `in_progress` | `task.block` | `blocked` | User OR `blocked_by` populated | `blocked by <ids/reason>` |
| `blocked` | `task.unblock` | `active` | All `blocked_by` resolved OR user | `unblocked` |
| `active` / `in_progress` / `blocked` | `task.complete` | `done` | `[x]` in MTL OR `status: done` in YAML | `completed at <ts>` |
| `done` | `task.reopen` | `active` | `[ ]` in MTL OR `status: active` in YAML | `reopened at <ts>` |
| `done` | `task.archive` | `archived` | Archive job (manual or scheduled) | `archived to <path>` |
| `active` / `in_progress` | `task.split` | `split` (parent) + new `triaged` children | Operator command | `split into <child_ids>` |
| any | `task.merge` | `merged` (loser) + updated `active` (winner) | Operator command | `merged into <winner_id>` |
| any (esp. captured/triaged) | `task.resurrect` | `captured` | Audit detects re-capture matching an archived task | `resurrected from archive of <old_id>` |

### 5.3 Triggers

- **Cron**: brain-dump processor (`captured` creation), archive sweep (`done`→`archived` after N days completed, default 30).
- **Webhook / runner**: future P3 quick-add surfaces also call `task.create`.
- **Audit reconciliation**: `tools/audit_threaded_tasks.py` detects MTL ↔ backing-file drift and emits transitions (`task.complete`, `task.reopen`) idempotently.
- **Operator CLI**: `python3 -m tools.tasks <op>` for split/merge/archive. These are the only "manual" transitions humans run by hand.

### 5.4 Audit log entries

Every transition appends one line to the `## Thread / Audit Log`
section of the backing file AND emits a JSON line to
`99_System/logs/task-events-<YYYY-MM-DD>.jsonl`:

```json
{"ts":"2026-05-14T09:01:00Z","event":"task.split","actor":"operator","id":"t-2026w19-a3f1","children":["t-2026w19-c08b","t-2026w19-d4e3"]}
```

The JSONL is the audit's primary input; the markdown log is the human's view.

---

## 6. Migration Plan

### 6.1 Estimate

The MTL today contains the canonical task lines used by the Command
Center. Reading from MinIO at design time isn't required for the spec
itself; the audit run-log indicates several hundred open tasks at peak.
We design for **up to 2,000 lines** in MTL, of which up to 1,500 might
be open tasks at migration time. The migration script handles unbounded
input but logs warnings above 2,500 lines and prints an estimated wall-clock.

### 6.2 Script

`scripts/migrate_mtl_to_threaded.py`.

Three phases, each idempotent and reversible:

**Phase A — Plan (dry-run by default):**

1. Read MTL from MinIO.
2. Parse every `- [ ]` / `- [x]` line.
3. For each line:
   - Determine canonical description (strip inline fields, lowercase, NFC, trim).
   - Compute `description_hash`.
   - Generate proposed `task_id` (ISO week of *today*, 4-hex random).
   - Detect "obvious twins" — lines with identical description_hash within
     the same area. Flag as merge candidates; do not create duplicates.
   - Detect `Brain Dump Capture — YYYY-MM-DD (<src>)` section headers and
     attribute child tasks back to that brain dump as `source.brain_dump`.
4. Write a plan JSON: `99_System/state/p2-migration-plan-<ts>.json` with
   every proposed file path, frontmatter, and MTL line replacement.
5. Print a human-readable summary: total tasks, by area, by priority,
   estimated file count, twin merges.

**Phase B — Apply (explicit `--apply`):**

1. For each planned task, write `30_Tasks/<area>/<task_id>.md` (verified PUT).
2. Re-write MTL with new line shape. Single verified PUT — atomic from
   Obsidian's view.
3. Write `99_System/state/p2-migration-result-<ts>.json` recording every
   file created with its ETag.

**Phase C — Verify:**

1. Run `scripts/audit_threaded_tasks.py` (see § 13). MUST exit 0.
2. Run a no-op brain-dump processor pass with `--dry-run` to confirm
   the threaded extractor still recognises everything.

### 6.3 Rollback

- MinIO bucket versioning is ON. Every PUT in the migration is a new
  version. Rollback is `s3 list-object-versions` then revert MTL to its
  pre-migration version and delete the `30_Tasks/` files written in this
  migration run (their keys are recorded in the result JSON).
- `scripts/migrate_mtl_to_threaded.py --rollback <result-json>` automates
  this. Tested end-to-end on a synthetic fixture in CI.

### 6.4 Safety rails

- Cron paused during migration (`scripts/n8n_pause_workflow.py brain-dump-processor`).
- Telegram capture webhook (future) gated behind a feature flag.
- Migration runs from a maintenance window note appended to the
  Command Center: "Migration in progress; auto-rebuild paused."
- `--dry-run` is the default. `--apply` is the only flag that writes.
- Idempotent: re-running `--apply` against an already-migrated MTL is a
  no-op (existing files are detected via path-then-hash check).

---

## 7. Dedup Algorithm

The fundamental dedup question: "is this capture the same task as something I already have?"

### 7.1 Layered identity

Dedup proceeds through three layers, in order. Any positive match short-circuits later layers.

**Layer 1 — `origin_hash` exact match.**
The brain-dump extractor computes `origin_hash = sha256(<source_file_relpath>|<section_name>|<line_range_text>)`
where `line_range_text` is the NFC-normalized, whitespace-collapsed text of
the source span. If the same `origin_hash` is already in any task's
`source.origin_hash`, the capture is the **same source span re-extracted** —
this run is a re-execution of a prior extraction. No new task; the existing
task's `source.receipt` may be updated to point at the newer receipt if
desired (idempotent).

**Layer 2 — `description_hash` exact match within area.**
After normalizing the captured description (NFC, lowercase, collapse
whitespace, strip inline fields), `description_hash` is computed. If any
*open* task in the same `area` has the same `description_hash`, the
capture is a **re-statement** — append a thread entry to the existing
task ("re-captured from <source>") and do not create a new file.

**Layer 3 — fuzzy match within area, gated.**
Using the existing `fuzzy_dedup_filter` in `tools/process_brain_dump.py`
(threshold 0.85) over open tasks in the same area, if a candidate is
"close-enough," route the new capture to the **review queue** with both
candidates linked. Aaron decides: merge, keep as related, or accept as new.
Never silently drops.

### 7.2 Recognising "same task captured twice from different brain dumps"

Layer 2 handles this when the wording is identical. Layer 3 handles it
when the wording drifted. The review queue is the human-in-the-loop for
the ambiguous case — and it's the only place where the system asks for
input rather than guessing.

### 7.3 Archived-task resurrection

If a Layer-1 or Layer-2 match hits an **archived** task, the dedup
emits `task.resurrect`: the archived task moves back to `captured` with
a new thread entry "resurrected from archive of <old_id> via <source>".
The `task_id` is preserved (we never reuse IDs, but we also never
fragment history). The audit log records that resurrection.

### 7.4 Cross-area near-duplicates

Explicitly out of scope for automatic dedup. A brain-dump capture in
the `health` area and a hand-typed line in `personal` with similar text
are *kept separate* — area boundaries are real to Aaron. The audit
script flags cross-area near-duplicates for the weekly review (informational
only).

---

## 8. Manual-Edit Resilience

Aaron edits MTL bullet text directly without touching the backing file.
This MUST be safe.

### 8.1 Reconciliation rules

Run after every brain-dump processor pass AND on demand via
`scripts/audit_threaded_tasks.py --reconcile`.

For every `[id:: t-…]` line in MTL:

1. **ID resolves to a backing file?**
   - Yes → continue.
   - No → emit `orphan_mtl_line` finding. Backing file may have been
     deleted by hand. Action: flag in the "Needs your eyes" inbox
     (see § 8.3).

2. **Description in MTL matches `description_hash` of backing file?**
   - Yes → no-op.
   - No → MTL is the more recent source of truth IF
     `mtl_line_last_write` (best estimate: ETag of MTL) is more recent
     than backing file's `updated_at`. Then update backing file:
     - new `description` (replace `## Description` body)
     - new `description_hash`
     - `updated_at` = now
     - audit-log entry: "description edited via MTL"
   - If clocks/ETags can't decide (rare): rule is **YAML wins** for
     structured fields (`area`, `priority`, `due`) and **MTL wins** for
     description text. Surface the conflict to "Needs your eyes."

3. **Checkbox state mismatch?**
   - MTL `[x]` + backing `status` ∉ {done, archived} → emit
     `task.complete` (`completed_at` = now or MTL line's daily-note context).
   - MTL `[ ]` + backing `status` == done → emit `task.reopen`.

4. **Inline fields mismatch (area / priority / due)?**
   - The folder of the backing file wins for **area**. If MTL says
     `[area:: faith]` but backing file is in `30_Tasks/health/`, the
     backing file's folder wins; MTL line is rewritten on next render.
   - For **priority** and **due**, MTL wins — these are the fields
     Aaron most often tweaks inline.

5. **No matching MTL line at all for an active backing file?**
   - Means MTL got out-of-sync. The next Command Center rebuild
     regenerates the MTL section from backing files (see § 12 render
     pipeline). MTL is regenerated from the source of truth weekly
     during the Sunday digest in a "compaction" pass.

### 8.2 The "Needs your eyes" inbox

A single file: `00_Inbox/review-queue.md` already exists. P2 adds a
sub-section `## Threaded Task Reconciliation` rendered at the top:

```markdown
## Threaded Task Reconciliation

- [ ] **Conflict — t-2026w19-a3f1** — MTL says priority=B, backing file says priority=A. Both updated within 60s. Pick one.
- [ ] **Orphan — t-2026w19-zzzz** — MTL references this ID but no backing file exists. Restore from archive or delete the MTL line.
- [ ] **Near-duplicate** — "Call doctor" (existing `t-2026w19-c08b`) vs new capture "Call Dr. Garcia about hip" (proposed `t-2026w20-…`). Merge, link, or keep separate.
```

These appear in the Command Center "❓ Needs Review" section
unchanged — the existing Command Center renderer already pipes
`review-queue.md` to that section.

### 8.3 Conflict UX principle

The system never silently overwrites. Any time both MTL and backing
file changed since the last reconciliation, BOTH are preserved and
Aaron gets the deciding vote. The vote is a human task — surfacing in
the review queue is the conflict UX.

---

## 9. Backlinks

P2 makes the vault a proper graph. The minimum link surface:

| From | To | Form | Purpose |
|------|----|----- |---------|
| Task backing file | Source brain dump | `source.brain_dump` field + body link | Trace any task back to its origin |
| Task backing file | Source receipt | `source.receipt` field + body link | Audit chain |
| Task backing file | Parent task (if split-child) | `parent` field + body wikilink | Thread navigation |
| Task backing file | Child tasks | `children` field + body wikilinks | Thread navigation |
| Task backing file | Blocked-by tasks | `blocked_by` field + body wikilinks | Critical path |
| Task backing file | Related project page | Auto-discovered if MTL is in a project section | Project rollup |
| Task backing file | Daily note where completed | New line in daily note: `- ✅ [[t-…\|description]] @ HH:MM` | Completion audit |
| MTL line | Task backing file | Wikilink in the bullet | Click-through to detail |
| Daily note | Tasks completed today | Auto-section appended by the state machine | Daily review |
| Brain dump (pre-archive) | Tasks extracted | The brain dump's archive note in `99_System/archive/brain-dumps/<date>/` gets a `## Tasks extracted` section listing the new task_ids | Reverse trace |
| Project page (`10_Active Projects/...`) | Threaded tasks in that project | Dataview query on `id` or area; new in P2 | Project boards keep working |

Backlink writes are part of the same atomic verified-PUT loop as the
task creation itself; failures route through the same receipt gate
(ADR-0005 § "Gate Semantics") so a task isn't considered "created"
until at least the backing file + MTL line both verified. Daily-note
and brain-dump-archive backlinks are best-effort: failure logs a
warning and the audit reconciles on its next pass.

---

## 10. Completion Sync

### 10.1 Bidirectional rule

Completion can originate from either side:
- **MTL side:** Aaron checks `[x]` in MTL (probably on phone via Obsidian mobile).
- **Backing-file side:** Aaron sets `status: done` in the backing file's frontmatter, or via the operator CLI.

### 10.2 Precedence

When both changed since the last sync:

1. If MTL line is `[x]` AND backing `status: done` → no conflict; ensure `completed_at` is set.
2. If MTL line is `[ ]` AND backing `status: done` → recently-reopened-via-MTL wins → `task.reopen`. Clear `completed_at`.
3. If MTL line is `[x]` AND backing `status` ∉ {done, archived} → `task.complete`. Set `completed_at` to:
   - The `[completion:: YYYY-MM-DD]` inline field if present in the MTL line, ELSE
   - The daily-note date where the line currently sits if discoverable, ELSE
   - `now()` as fallback.

### 10.3 `[completion::]` auto-population

When `task.complete` fires, the MTL line is rewritten in place to
append `[completion:: <date>]` if missing. The state-machine writer
owns this rewrite; the line is verified-PUT as part of the same atomic
write as the backing-file status change.

This solves the current 0% completion-field population problem in MTL
(noted in CLAUDE.md "Pending" section) **for newly-completed tasks
post-P2**. A separate one-time backfill (out of P2 scope) handles the
historical lines if Aaron wants it.

### 10.4 Failure mode: half-completed

If MTL write succeeds but backing-file write fails (or vice versa),
the next reconciliation pass detects the mismatch and retries.
`completed_at` is idempotent — re-running `task.complete` with the
same target state is a no-op. The audit reports any half-completed
state lasting > 1 hour as a finding.

---

## 11. Splits and Merges

### 11.1 Split

**Operator command:**
```bash
python3 -m tools.tasks split t-2026w19-a3f1 \
  --child "Talk to Christy about hip surgery" \
  --child "Call Dr. Garcia about hip imaging"
```

**Effects:**
- Parent: `status → split`, `children = [<new_id_1>, <new_id_2>]`, audit log.
- Each child: created as new file with `parent = t-2026w19-a3f1`, status `triaged`, area inherited from parent, `source.brain_dump` = parent's source, audit log "split from parent t-…"
- MTL: parent line removed (or hidden via `status: split` filter — see § 12), each child gets a new line.

**Reversible?** No, but recoverable: `python3 -m tools.tasks unsplit t-2026w19-a3f1` reverts if children have not been edited. If children have been edited, unsplit refuses and surfaces the divergence.

### 11.2 Merge

**Operator command:**
```bash
python3 -m tools.tasks merge t-2026w19-c08b --into t-2026w19-a3f1
```

**Effects:**
- Loser (`t-2026w19-c08b`): `status → merged`, body gains a "merged into [[t-2026w19-a3f1]]" notice, audit log.
- Winner: gains a thread entry "merged from t-2026w19-c08b at <ts>", inherits union of `related`, `blocked_by`, `blocks`, `tags` (deduped).
- MTL: loser's line removed; winner's line unchanged unless description was updated.

**Conflict handling:** the operator command refuses to merge if the loser's `status` is `done` AND the winner's is open (would lose completion timestamp). Force-merge requires `--force`.

### 11.3 Audit trail invariant

For any task that has ever been split or merged, the `## Thread / Audit Log`
section and the `99_System/logs/task-events-*.jsonl` files together let
the audit script reconstruct the full lineage. The audit asserts:
- Every `merged` task has its `merged_into` target existing.
- Every `split` task has all `children` existing.
- Every child has `parent` pointing back to a task whose `children` list
  contains it (bidirectional consistency).

---

## 12. Archive Flow

### 12.1 When

A `done` task moves to `archived` automatically **30 days after `completed_at`**.
Scheduled job: weekly, runs Sunday 9PM CDT (slot `:53`, free per
CLAUDE.md cron-slot constraint). Manual archive any time via
`python3 -m tools.tasks archive <id>` or `python3 -m tools.tasks archive --before 2026-04-01`.

### 12.2 Where

`99_System/archive/tasks/<YYYY>/<area>/<task_id>.md`.

The file is moved (PUT to new key, verified, DELETE old key only after
verified) atomically. Backing-file YAML adds `archived_at: <ts>`.

### 12.3 Dataview continuity

Dataview queries in the Command Center scope `FROM "10_Active Projects" OR "00_Inbox"`
— they don't need to change. The archive area is intentionally
excluded so the Command Center stays focused on the *now*. A separate
`99_System/Task Archive Index.md` page renders Dataview tables for
historical lookup; it's read-only and rebuilt by the same Sunday job
that runs archival.

### 12.4 Command-center hiding

The Command Center re-renders open-tasks Dataview every hour. Archived
tasks (`status: archived` AND in `99_System/archive/tasks/`) never
appear there. The `## 🗂 By Life Area` query LIMIT 60 already caps the
display; archival also keeps the by-area scan fast.

---

## 13. Audit Script — `scripts/audit_threaded_tasks.py`

Fail-fast. Runs every hour as part of `live-dashboard-updater` (`:03`
slot) and as part of `vault-health-report` weekly. Exit non-zero on any
finding.

### 13.1 Rules

| # | Rule | Severity |
|---|------|----------|
| 1 | Every `30_Tasks/<area>/<task_id>.md` file has valid canonical frontmatter (all required fields present, valid enums). | FAIL |
| 2 | Every `task_id` in a filename matches the `id:` field. | FAIL |
| 3 | Every task's `area` field equals its parent folder name. | FAIL — auto-reconcile (folder wins) |
| 4 | No duplicate `task_id` across the entire vault. | FAIL |
| 5 | Every `parent` reference resolves to an existing task whose `children` list contains us. | FAIL |
| 6 | Every `child` reference resolves to an existing task whose `parent` is us. | FAIL |
| 7 | Every `blocked_by` reference resolves. | FAIL |
| 8 | Every MTL `[id:: …]` resolves to an existing backing file. | FAIL — emit "orphan_mtl_line" + add to review queue |
| 9 | No backing file with `status` ∈ {`captured`, `triaged`, `active`, `in_progress`, `blocked`} is missing from MTL. | FAIL — auto-regenerate MTL line |
| 10 | No backing file with `status` ∈ {`done`, `archived`, `split`, `merged`} is present in MTL. | FAIL — auto-remove MTL line |
| 11 | `description_hash` matches the canonical-normalized description body. | FAIL — recompute on next write |
| 12 | No task with `status: scanning`-equivalent transient state > 1 hour old. (Lock detector, mirrors ADR-0005 rule 3.) | FAIL |
| 13 | Every receipt with `task_ids` lists IDs that resolve. | FAIL |
| 14 | No collision detected (two tasks with same `description_hash` in same area and same `source.origin_hash`). | FAIL |
| 15 | `completed_at` set iff `status: done`. `archived_at` set iff `status: archived`. | FAIL |
| 16 | No cross-area near-duplicates within 0.90 fuzzy match. | WARN |
| 17 | No `merged` task whose `merged_into` target is itself `merged` (no merge chains; resolve transitively). | FAIL — auto-flatten |

### 13.2 Output

```text
$ python3 scripts/audit_threaded_tasks.py
Scanning 30_Tasks/ (1,243 files) ...
Scanning MTL (847 open lines) ...
Cross-checking receipts (last 14 days, 32 receipts) ...

FAIL: 2 findings
  [orphan_mtl_line] MTL line "Drink more water [id:: t-2026w19-zz99]" — no backing file. Action: deleted by hand? Add to review queue or delete line.
  [bidirectional] t-2026w20-7c1a has child t-2026w20-3d4e, but t-2026w20-3d4e parent is t-2026w20-other. Action: fix one direction.

WARN: 1 finding
  [cross_area_near_dup] t-2026w19-a3f1 (health: "Decide on hip surgery") vs t-2026w19-b2c5 (personal: "Decide on hip"). Fuzzy 0.91. Consider merging.

Exit 1.
```

---

## 14. Performance

### 14.1 Targets

| Operation | Target (p50 / p95) | Today's baseline |
|-----------|---------------------|------------------|
| Brain-dump processor pass (typical: 8 sources, 30 tasks) | 8s / 20s | ~5s / ~12s today (no threaded writes) |
| Command Center rebuild (hourly) | 2s / 5s | ~1.5s today |
| `scripts/audit_threaded_tasks.py` full pass at 1,500 open + 5,000 archived | 8s / 15s | n/a |
| Dataview "By Life Area" query in Obsidian Mac | < 500ms | ~200ms today |
| Task creation (one task: backing file + MTL line + receipts update) | < 1.5s incl. verified-PUT | n/a |

### 14.2 Strategy

**Now:** flat markdown + Dataview is enough. Brain-dump processor and
Command Center both already read MTL once per pass and traverse it
linearly; that scales to ~10K lines comfortably.

**Optional shadow index — `99_System/index/tasks.sqlite`.**
- Built incrementally by every state-machine write (single-writer, the
  brain-dump processor + operator CLI both go through the same Python
  kernel).
- Rebuilt-from-truth nightly (Sunday 8PM CDT, slot `:53` reused with
  archival job) as belt-and-braces.
- **Optional in v2.0:** not required for v1.0. Add when Dataview queries
  exceed 1s on Obsidian Mac or when audit > 30s.
- Schema: one table `tasks(id PK, area, priority, due, status, parent,
  description_hash, created_at, updated_at, completed_at, archived_at)`,
  plus `task_links(from_id, to_id, kind)` for relationships. Indexes on
  `(area, status)`, `(due)`, `(parent)`.
- Even when present, MTL + backing-file markdown remain the source of
  truth. SQLite is a derived view, deletable any time.

### 14.3 Bounded growth

`30_Tasks/<area>/` cardinality is the constraint. At ~30 captures/week
and ~30-day archive cycle, the *active* footprint is ~120 open tasks
plus ~100 completed-not-yet-archived per area, max. Most areas will
have far fewer. The archive grows ~1,500 files/year — fine for
MinIO + macOS Finder + Obsidian.

---

## 15. Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| **Partial write — backing file PUT but MTL append failed.** | Receipt records `verified: false` for the MTL write target. ADR-0005 gate retains the source brain-dump section, so the next run re-extracts → Layer-1 `origin_hash` dedup catches it → existing backing file gets a thread entry, MTL append re-attempted. | Automatic via gate. |
| **Partial write — MTL appended but backing file PUT failed.** | Audit rule 8 surfaces "MTL line with no backing file" within 1 hour. | Auto-create backing file from the MTL line content + a placeholder source, or, if Aaron prefers, delete the MTL line and recapture. |
| **S3 / MinIO inconsistency** (read-your-write delay). | `s3_put_verified` already does head_object after PUT. If ContentLength mismatches body length, the write is marked unverified. | Existing primitive; P2 reuses unchanged. |
| **Obsidian sync conflict via Remotely-Save.** | Remotely-Save produces `<filename>.<timestamp>.conflict.md` files. | Audit script detects `*.conflict.md` under `30_Tasks/` and surfaces them in the review queue. Aaron picks the winner; the other is moved to `99_System/conflicts/`. |
| **Human deletes a backing file.** | Audit rule 8 (orphan MTL line) finds it. | Surface to review queue: restore from MinIO version history or accept the deletion (also delete the MTL line). |
| **Human edits a backing file's `id:` field by hand.** | Audit rule 2 (id field ≠ filename) fails. | Audit refuses to auto-fix; surfaces conflict — the ID is load-bearing for backlinks. Aaron picks the correct ID, audit rewrites both directions. |
| **Operator CLI killed mid-split.** | Audit rule 5/6 (bidirectional refs) catches the partial state. | Auto-recovery: any child without a parent whose `children` lists it is reverted to `triaged` and parent split is rolled back. |
| **Clock skew between Mac and LXC.** | `updated_at` comparisons in § 8 reconciliation. | Tolerance: 5 minutes. Within tolerance, structured-field changes go YAML-wins, description goes MTL-wins. |
| **Receipt audit (ADR-0005) finds a task_id claim that doesn't resolve.** | Existing audit pass. | Rule 13. Either the receipt is stale or the file got deleted; surface. |
| **MinIO outage during brain-dump processor pass.** | ADR-0005 gate already retains the source. No task created at all. | Existing behavior; P2 adds nothing new here. |
| **A task is captured twice from two different brain dumps in the same run.** | Layer-1 origin_hash differs (different sources) but Layer-2 description_hash matches → auto-link as `related`, only ONE backing file created. Audit confirms. | Built-in by dedup algorithm. |

---

## 16. Acceptance Criteria

P2 is "done" when **all** of the following are true:

1. Every newly-captured task creates exactly one backing file under `30_Tasks/<area>/`.
2. Every backing file passes audit rule 1–17 (rule 16 may WARN, all others must pass).
3. MTL contains exactly one line per `status ∈ {captured, triaged, active, in_progress, blocked}` task and zero lines for other statuses.
4. The full migration from pre-P2 MTL completes against the live vault with zero data loss (every original line is either represented in a backing file or surfaced in review queue with a reason).
5. Aaron can check `[x]` in MTL on his phone and the backing file flips to `status: done` within the next cron tick (≤ 1 hour).
6. Aaron can set `status: done` in a backing file and the MTL line flips to `[x]` within the next reconciliation pass.
7. Re-running the brain-dump processor on yesterday's already-extracted brain dump produces **zero** new tasks (Layer-1 origin_hash dedup proven).
8. A split operation produces three valid backing files (parent + 2 children) with full bidirectional refs, in ≤ 2s.
9. `scripts/audit_threaded_tasks.py` runs against the live vault in ≤ 15s p95 with 1,500 open tasks.
10. Command Center renders in ≤ 5s p95 with 1,500 open tasks.
11. The Sunday weekly digest renders threaded tasks as cards (parent + child rollup), not flat lines.
12. No regression in ADR-0005 receipts: every brain-dump receipt's `writes[*].task_ids` resolves; integrity audit stays green for 7 days post-P2.
13. The operator CLI exposes all of: `create`, `triage`, `split`, `merge`, `archive`, `unsplit`, `restore`, `move-area`. Each has `--dry-run`.
14. `tools/bd_integrity.py` and the new `tools/task_state.py` are the single source of truth; the n8n runner shells out to Python (no JS reimplementation).
15. Every state-machine transition is covered by at least one pytest test. ≥ 95% line coverage on `tools/task_state.py` and `tools/task_id.py`.

---

## 17. Risks + Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Identity model bug → task duplicates flood the vault.** | Low (with three dedup layers) | High (manual cleanup of hundreds of files) | Migration ships `--dry-run` default; first 7 days post-cut have audit running every 15 minutes (not every hour) with email alerts on duplicates. Rollback path is documented. |
| **Description-hash drift from Unicode/whitespace edge cases.** | Medium | Medium | Reuse `tools/bd_integrity.py` normalization (NFC, LF, strip). Test fixture covers smart quotes, em-dash, NBSP, BOM. |
| **Manual edits create unrecoverable conflicts.** | Medium | Low (surfaced, not silent) | "Needs your eyes" inbox catches everything. Audit refuses to auto-resolve any conflict it can't prove the resolution of. |
| **Migration takes > 30 minutes and disrupts a workday.** | Low | Medium | Migration runs during a maintenance window (Sunday morning); `--dry-run` plan executes in ≤ 10s on current vault size; `--apply` is bounded by network and parallelizable. |
| **Dataview performance regression on Obsidian Mac.** | Medium | Medium | Bounded LIMIT in queries (LIMIT 60 in by-area). SQLite shadow index is the fallback. Performance gate is part of acceptance criteria. |
| **n8n / runner divergence creeps back.** | Low | High | Single Python kernel (mirrors ADR-0005 decision). Static-analysis test greps n8n Code nodes for forbidden literals (`task_id`, `[id::`, etc., when they appear standalone in JS). |
| **Future P3 capture surface bypasses the kernel.** | Medium | High | P3 design must call the same `tools/task_state.py::create_task()` function (or its HTTP endpoint on the OHO runner). Audit detects any task created without a receipt — those are forbidden. |
| **Aaron disagrees with a design choice and we ship anyway.** | Low | High | "Controversial choices" section at top of return summary forces explicit user sign-off before the spec is promoted to ADR-0007. |

---

## 18. Dependencies

| Dependency | Reason | Status |
|------------|--------|--------|
| P1 + P1.5 + ADR-0006 stable for ≥ 7 days in prod. | The integrity layer must be load-bearing before P2 composes on top. | Open (soak window opened with `a1bd438`). |
| `tools/bd_integrity.py` schema_version 1 stable. | P2 receipts gain `task_ids` field on existing schema; no schema bump. | Stable. |
| MinIO bucket versioning ON. | Migration rollback path. | Confirmed (CLAUDE.md). |
| Command Center renders backing-file-aware sections. | Renderer needs `parse_mtl_open` to handle threaded line shape. | Renderer changes are part of P2 lane (d) below. |
| Receipt audit (`scripts/audit_extraction_receipts.py`) green. | We extend its job rather than fork audit. | Currently green. |
| Operator CLI scaffolding (`python3 -m tools.tasks`). | New surface; P2 introduces it. | Built as part of P2 lane (a). |

---

## 19. Parallel Sub-Lanes

P2 decomposes into 5 lanes that ship in this order but overlap on
implementation:

### (a) Kernel — `tools/task_id.py` + `tools/task_state.py`

- `new_task_id()`, `normalize_description()`, `description_hash()`
- `TaskFile` dataclass + frontmatter parse/serialize (extend `bd_integrity.py`'s YAML helper to the larger frontmatter shape)
- `apply_transition()` pure-function state machine
- `dedup_layered()` — Layer 1/2/3 algorithm
- Pure functions; ≥ 95% coverage; all 17 audit-rule edge cases as fixtures.
- **Effort:** L (1–2 wks)

### (b) Migration — `scripts/migrate_mtl_to_threaded.py`

- Plan / Apply / Verify / Rollback phases.
- Test fixture: synthesised MTL with twin-rows, completed lines, exotic Unicode.
- Test: golden migration of a 100-line fixture MTL → exact file tree match.
- **Effort:** M (3–5 days)

### (c) Audit — `scripts/audit_threaded_tasks.py`

- 17 rules + JSON report + human report
- Wire into `live-dashboard-updater` and `vault-health-report`
- **Effort:** M (3–5 days)

### (d) Command-Center Renderer Update — `tools/build_command_center.py`

- `parse_mtl_open` accepts both pre-P2 and P2 shapes.
- New section: `## 🧵 Threaded — Open Threads` rendering parent → children rollup (Dataview cannot render hierarchy cleanly; this is a `dataviewjs` block reading `parent`/`children` fields).
- "By Life Area" filter excludes `status ∈ {split, merged, done, archived}`.
- **Effort:** M (3–5 days)

### (e) Brain-Dump Processor Wiring + Operator CLI + Runner Endpoint

- `tools/process_brain_dump.py::append_tasks_to_mtl` becomes a thin
  shim over `task_state.create_task()` and `task_state.dedup_layered()`.
- New `python3 -m tools.tasks {create|triage|split|merge|archive|unsplit|restore|move-area}` CLI.
- New runner endpoints: `POST /tasks/split`, `POST /tasks/merge`, `POST /tasks/archive` (auth + lock + 30s timeout each).
- **Effort:** L (1–2 wks)

### (f) Tests + Documentation

- Cross-lane integration tests in `tests/test_threaded_tasks_e2e.py`.
- Operator runbook in `docs/runbook-threaded-tasks.md` (split/merge/archive recipes).
- ADR-0007 promotion of this spec.
- **Effort:** M (3–5 days)

---

## 20. Effort Summary

XL overall. Breakdown:

| Lane | Effort | Notes |
|------|--------|-------|
| (a) Kernel | L | 1–2 weeks |
| (b) Migration | M | 3–5 days |
| (c) Audit | M | 3–5 days |
| (d) Command Center | M | 3–5 days |
| (e) Processor + CLI + Runner | L | 1–2 weeks |
| (f) Tests + Docs | M | 3–5 days |
| **Total** | **~4–6 weeks** | Sequential by lane order with overlap in (c)/(d) running parallel to (e). |

---

## 21. Verification — TDD Strategy

Every lane lands red tests first. Examples (not exhaustive):

```python
# tests/test_task_id.py

def test_new_task_id_format():
    tid = new_task_id()
    assert re.fullmatch(r"t-\d{4}w\d{2}-[0-9a-f]{4}", tid)

def test_new_task_id_unique_in_1000_draws():
    ids = {new_task_id() for _ in range(1000)}
    assert len(ids) == 1000

def test_new_task_id_collision_detection_regenerates(tmp_path, monkeypatch):
    existing = {"t-2026w19-a3f1"}
    monkeypatch.setattr(secrets, "token_hex", side_effect=["a3f1", "b2c5"])
    tid = new_task_id_avoiding(existing, ...)
    assert tid == "t-2026w19-b2c5"

# tests/test_task_state.py

def test_layer1_origin_hash_match_short_circuits():
    existing = sample_task(origin_hash="sha256:abc...")
    cand = candidate(origin_hash="sha256:abc...")
    result = dedup_layered([cand], existing_open=[existing], existing_archived=[])
    assert result.action == "merge_into_existing"
    assert result.target_id == existing.id

def test_layer3_fuzzy_match_routes_to_review():
    existing = sample_task(description="Decide on hip surgery", area="health")
    cand = candidate(description="Decide on hip", area="health")  # 0.87 fuzzy
    result = dedup_layered([cand], existing_open=[existing], existing_archived=[])
    assert result.action == "to_review"

def test_archived_match_emits_resurrect():
    archived = sample_task(description_hash="sha256:xyz", status="archived")
    cand = candidate(description_hash="sha256:xyz")
    result = dedup_layered([cand], existing_open=[], existing_archived=[archived])
    assert result.action == "resurrect"
    assert result.target_id == archived.id

def test_split_parent_status_transition():
    parent = active_task()
    parent_after, children = apply_split(parent, descriptions=["A", "B"])
    assert parent_after.status == "split"
    assert {c.parent for c in children} == {parent.id}
    assert set(parent_after.children) == {c.id for c in children}

def test_mtl_checked_box_completes_backing_file():
    backing = active_task()
    mtl_line = f"- [x] [[{backing.path}|{backing.description}]] [id:: {backing.id}] [area:: health]"
    reconciled = reconcile_one(backing, mtl_line=mtl_line)
    assert reconciled.status == "done"
    assert reconciled.completed_at is not None

# tests/test_migrate.py

def test_migration_dry_run_against_golden_mtl(snapshot):
    plan = run_migration(read_fixture("mtl_100_lines.md"), apply=False)
    snapshot.assert_match(plan)  # plan JSON byte-equal to golden

def test_migration_apply_is_idempotent(s3_stub):
    run_migration_apply(s3_stub, mtl_text=read_fixture("mtl_100_lines.md"))
    state_after_first = snapshot_s3(s3_stub)
    run_migration_apply(s3_stub, mtl_text=read_fixture("mtl_100_lines.md"))
    state_after_second = snapshot_s3(s3_stub)
    assert state_after_first == state_after_second

# tests/test_audit_threaded.py

@pytest.mark.parametrize("rule", AUDIT_RULES)
def test_audit_rule_has_failing_fixture(rule):
    vault = load_synthetic_vault(rule.fixture_name)
    findings = audit(vault)
    assert rule.id in {f.rule_id for f in findings}
```

`tests/test_threaded_tasks_e2e.py` covers the full Tuesday→Thursday split
scenario end-to-end against a MinIO mock.

---

## 22. Open Questions

The following design choices are explicit asks for Aaron's call before
this spec is promoted to ADR-0007. Listed in priority order.

1. **Is `t-` the right prefix?** Alternative considered: no prefix
   (just `2026w19-a3f1.md`). Adding `t-` wastes 2 chars on every file
   but reserves the namespace for future `p-` (project), `d-` (decision)
   IDs. Recommendation: keep `t-`. Decision: ____.

2. **Auto-archive at 30 days post-completion?** Alternatives: never,
   60 days, 90 days, manual-only. Trade-off is archive volume in the
   active filesystem vs. recency in weekly review. Recommendation:
   30 days, configurable via env var. Decision: ____.

3. **Should `task.complete` from MTL touch the daily note?** It would
   add a `- ✅ [[t-…]] @ HH:MM` line to today's daily note for every
   completion. Pro: rich daily-note history. Con: daily note grows
   noisy with checkbox events. Recommendation: yes — it composes with
   the P4/P5 review rituals. Decision: ____.

4. **Operator CLI surface or Obsidian UI?** Split/merge/archive could
   eventually be Obsidian-native (a plugin command palette). For v1
   we're shipping a Python CLI. Future plugin out of scope. Decision:
   confirm Python CLI is acceptable v1.

5. **Sunday weekly digest format change?** Current digest is flat task
   summary; P2 unlocks rendering as **thread cards**. Big UX change.
   Recommendation: ship behind a feature flag for the first 2 weeks,
   default-on after. Decision: ____.

6. **`schema_version: 1` bump policy?** When P3/P4 add fields, do we
   bump or just add nullable fields? Recommendation: nullable fields
   stay at v1; structural breaks bump to v2 + migration. Decision: ____.

7. **Fuzzy threshold for Layer 3?** Today's `fuzzy_dedup_filter` uses
   0.85. Threaded duplicates likely want a higher bar (more
   restrictive, fewer false-merges) — 0.92? Recommendation: 0.90 for
   route-to-review, 0.85 stays as the silent in-section dedup we have
   today. Decision: ____.

8. **Where does the `## Thread / Audit Log` cap?** A long-running task
   could accrue dozens of entries. Recommendation: no cap, but the
   audit log is collapsible (`>` callout) in the body so it doesn't
   dominate the file. Decision: ____.

9. **Cross-area near-duplicate auto-link?** § 7.4 keeps them separate;
   audit only WARNs. Aaron might want `related` populated automatically
   for cross-area near-twins. Recommendation: opt-in via
   `enable_cross_area_relate: bool` config. Decision: ____.

10. **First MTL line for a brand-new task — should it default `status:
    triaged` or `status: captured` (so Aaron has to triage)?** Today
    everything regex-extracted lands as ready-to-do. The state machine
    distinguishes; the default routing matters. Recommendation:
    high-confidence regex → `triaged`, low-confidence → `captured` (lands
    in review queue). Decision: ____.

---

_End of spec. Promote to `docs/adr/0007-threaded-tasks.md` before any P2 code lands._

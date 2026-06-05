# SinkInputContract — design (A4)

**Status:** Proposed · **Date:** 2026-05-29 · **Drives:** top-down-plan §5 A4 · **Companion:** [ADR-0008 Cross-host comms](../../adr/0008-cross-host-comms.md), [ADR-0009 Threaded tasks](../../adr/0009-threaded-tasks.md), [task-backing-file.v1.yaml](../../schemas/task-backing-file.v1.yaml) (template)

This spec defines the contract layer between OHO's pipeline producers and its 4 sinks. It does NOT cover the Phase C threaded-task backing file (that's already locked in ADR-0009 + the YAML schema linked above). Scope is the two at-rest contracts that lack formal schemas today: the brain-dump summary state file and the per-workflow run-log JSON.

## 1 · Problem (verified by parallel investigators 2026-05-29)

| Sink | Reads from | Drift surface today |
|---|---|---|
| `workflows/n8n/morning-briefing.json` | MTL regex + `99_System/logs/brain-dump-processor-<DATE>.json` | dual-source; pulls `tasks_extracted` ∪ `task_count` (naming drift) |
| `workflows/n8n/live-dashboard-updater.json` | MTL regex | single-source; bound to MTL parse |
| `workflows/n8n/weekly-digest-v2.json` | MTL regex + North Star markdown | dual-source; North Star orphan-read |
| `tools/build_command_center.py` | MTL regex + `99_System/state/last-brain-dump-summary.json` + brain-dump logs + extraction receipts | **four sources, zero formal schemas**; the loosest sink in the repo |

Bonus consumers also feel the drift: `vault-health-report` (S3 list), `build_health_dashboard` (every run-log JSON across all workflows).

### Current contract discipline

- `tools/process_brain_dump.RunLog` (L138-L184) — typed `@dataclass` with 24 fields, `asdict()`-serialised → `99_System/logs/brain-dump-processor-<DATE>.json`. Typed at write-time but **NO at-rest schema documentation; consumers read by string-key**.
- `tools/process_brain_dump.build_operator_summary` (L1026) — returns an **inline 12-field dict** with NO dataclass and NO schema. Written to `99_System/state/last-brain-dump-summary.json`. **Loosest contract in the pipeline.**
- `tools/bd_integrity.build_receipt` — pure-function locked shape (TIGHT; out of scope for this spec).
- `tools/bd_integrity.CANONICAL_FRONTMATTER_FIELDS` — 8-field tuple enforced by `audit_extraction_receipts.py` rule 6 (TIGHT; out of scope).

## 2 · Decision

Adopt a **family of two locked contracts**, mirroring the `task-backing-file.v1.yaml` pattern (versioned YAML + Python dataclass + audit-enforced):

| Contract | Producer | Schema | Python type |
|---|---|---|---|
| `BrainDumpSummary` v1 | `process_brain_dump.build_operator_summary` | `docs/schemas/brain-dump-summary.v1.yaml` (NEW) | `tools/sink_contracts.BrainDumpSummary` (NEW `@dataclass(frozen=True)`) |
| `RunLogEntry` v1 | every workflow that writes `99_System/logs/<wf>-<DATE>.json` | `docs/schemas/run-log-entry.v1.yaml` (NEW) | `tools/sink_contracts.RunLogEntry` (NEW; common-fields base; workflow-specific subclasses) |

Both contracts:
- Carry `schema_version: int` and `schema: str` fields (matches `task-backing-file.v1.yaml` head).
- Follow ADR-0009 **additive-only evolution** — field additions OK at any time, removals require version bump.
- Follow ADR-0008 **forward-compat** — consumers tolerate unknown fields without failing.
- Are **enforced at rest** by a new `scripts/audit_sink_contracts.py` (in `make audit-all`).

**Phase C `BackingFileMeta` is explicitly out of scope** — it already exists at `task-backing-file.v1.yaml` and is governed by ADR-0009. Including it here would duplicate work that the Phase C critical path will land.

## 3 · Schema design

### 3.1 `brain-dump-summary.v1.yaml` (new)

Field set comes directly from the current `build_operator_summary` return (verified by investigator):

```yaml
schema_version: 1
schema: oho.brain-dump-summary.v1

required_fields:
  run_finished_at:
    type: string
    format: iso-8601-utc
    description: When the brain-dump-processor run completed.
  run_started_at:
    type: string
    format: iso-8601-utc
  status:
    type: string
    enum: [success, skipped, error]
  tasks_written:
    type: integer
    minimum: 0
  review_added:
    type: integer
    minimum: 0
  articles_queued:
    type: integer
    minimum: 0
  files_extracted:
    type: array
    items: { type: string }   # bare filenames, no path
  files_partial:
    type: array
    items:
      type: object
      required: [file, reasons]
      properties:
        file: { type: string }
        reasons: { type: array, items: { type: string } }
  files_error:
    type: array
    items:
      type: object
      required: [file, error]
      properties:
        file: { type: string }
        error: { type: string }
  files_by_state:
    type: object
    description: Counts keyed by bd_integrity.VALID_STATES.
    properties:
      empty: { type: integer, minimum: 0 }
      has_content: { type: integer, minimum: 0 }
      scanning: { type: integer, minimum: 0 }
      extracted: { type: integer, minimum: 0 }
      partial: { type: integer, minimum: 0 }
      error: { type: integer, minimum: 0 }
  reset_summary:
    type: object
    required: [files_reset_full, files_reset_partial, files_reset_skipped]
  top_added_tasks:
    type: array
    description: First 10 tasks from new_tasks_added, parsed + sorted A→B→C.
    items:
      type: object
      required: [area, priority, desc]
      properties:
        area: { type: string, enum: [faith, family, business, consulting, work, health, home, personal] }
        priority: { type: string, enum: [A, B, C] }
        desc: { type: string }
  total_added_tasks:
    type: integer
    minimum: 0

optional_fields:
  # Forward-compat slot. Consumers must tolerate unknown keys; producers may add
  # new fields as long as they are additive. Removals require a schema_version bump.

invariants:
  - status == "success" implies tasks_written >= 0 (already enforced by producer; restated here for the contract)
  - len(files_extracted) + len(files_partial) + len(files_error) == sum of (extracted, partial, error) keys in files_by_state
  - status == "skipped" requires a skip_reason field (forward-compat: producer adds; audit will flag if missing once added)
```

### 3.2 `run-log-entry.v1.yaml` (new)

Common-fields base, derived from `tools/process_brain_dump.RunLog` dataclass minus workflow-specific tails. Workflow-specific subclasses extend with additional named fields.

```yaml
schema_version: 1
schema: oho.run-log-entry.v1

required_fields:
  workflow:
    type: string
    description: Stable workflow identifier (matches filename stem of n8n JSON).
  run_date:
    type: string
    format: yyyy-mm-dd
  started_at:
    type: string
    format: iso-8601-utc
  finished_at:
    type: string
    format: iso-8601-utc
  duration_ms:
    type: integer
    minimum: 0
  status:
    type: string
    enum: [success, skipped, error]

conditional_fields:
  # When status == "skipped"
  skip_reason:
    type: string
    enum: [
      minio_auth_error, minio_list_failed,
      empty_inbox, no_active_files,
      missing_credential, fetch_failure,
      already_processed_today, ai_unavailable,
      rate_limited, dry_run
    ]
    required_when: status == "skipped"

optional_fields:
  # Producer-specific extensions. Each producer documents its own additive
  # fields in a doc comment at the top of its writer function.
  # Forward-compat: consumers must tolerate unknown keys.

invariants:
  - status == "skipped" requires skip_reason (already enforced by audit_workflow_runlogs; restated)
  - finished_at >= started_at (chronological order)
  - duration_ms == int((finished_at - started_at).total_seconds() * 1000) ± 50ms tolerance
```

## 4 · `tools/sink_contracts.py` (new)

Single module. ~150 LOC. Public surface:

```python
from dataclasses import dataclass, field, asdict
from typing import Any

SCHEMA_VERSION_SUMMARY = 1
SCHEMA_NAME_SUMMARY = "oho.brain-dump-summary.v1"

@dataclass(frozen=True)
class TopAddedTask:
    area: str
    priority: str
    desc: str

@dataclass(frozen=True)
class FilePartial:
    file: str
    reasons: list[str]

@dataclass(frozen=True)
class FileError:
    file: str
    error: str

@dataclass(frozen=True)
class BrainDumpSummary:
    schema_version: int
    schema: str
    run_finished_at: str
    run_started_at: str
    status: str
    tasks_written: int
    review_added: int
    articles_queued: int
    files_extracted: list[str]
    files_partial: list[FilePartial]
    files_error: list[FileError]
    files_by_state: dict[str, int]
    reset_summary: dict[str, int]
    top_added_tasks: list[TopAddedTask]
    total_added_tasks: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BrainDumpSummary":
        # Tolerant: unknown keys ignored (ADR-0008 forward-compat).
        # Missing required keys raise KeyError (clean caller signal).
        ...

SCHEMA_VERSION_RUNLOG = 1
SCHEMA_NAME_RUNLOG = "oho.run-log-entry.v1"

@dataclass(frozen=True)
class RunLogEntry:
    schema_version: int
    schema: str
    workflow: str
    run_date: str
    started_at: str
    finished_at: str
    duration_ms: int
    status: str
    skip_reason: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)  # producer-specific extensions
```

Both `from_dict` methods drop unknown keys silently (forward-compat); `to_dict` round-trips clean.

## 5 · Producer refactor

### 5.1 `process_brain_dump.build_operator_summary` → returns `BrainDumpSummary`

The function already builds the dict; the refactor replaces inline `return {...}` with `return BrainDumpSummary(...)`. The writer (`write_operator_summary`) calls `.to_dict()` before `json.dumps`. Zero net field change — the at-rest JSON is identical except for the two new top-level keys `schema_version: 1` + `schema: "oho.brain-dump-summary.v1"`.

### 5.2 `process_brain_dump.RunLog` → wraps `RunLogEntry`

The existing `RunLog` dataclass keeps its rich field set (24 fields). The serialiser splits common fields into `RunLogEntry` proper + everything-else into the `extras` dict. Writer emits the same JSON shape with two new top-level keys. Consumers that read `tasks_extracted` etc. continue to work — those fields land under `extras`.

This preserves backward compatibility for n8n Code-node readers that already grep specific field names.

## 6 · `scripts/audit_sink_contracts.py` (new)

Walks `99_System/state/last-brain-dump-summary.json` + every `99_System/logs/*-<DATE>.json` in MinIO. Validates:

- `schema_version: 1` + `schema: <correct-name>` present.
- All required fields present + correct type.
- `status == "skipped"` carries `skip_reason` from the canonical enum.
- Invariants from §3.1 + §3.2.

Fail-fast on first violation in `--strict` mode; warn-and-continue by default. Exit codes match the existing audit family: 0 clean, 1 violations, 2 I/O failure. Lives in `make audit-all`.

Default scan window: last 14 days of run-logs (same as `build_health_dashboard`). Tunable via `--days <N>`.

## 7 · Migration plan

Three atomic commits, in order:

1. **Schema land** — add `docs/schemas/brain-dump-summary.v1.yaml` + `docs/schemas/run-log-entry.v1.yaml`. No code consumers yet. Audit skipped. Net: 2 new docs.

2. **Module land** — add `tools/sink_contracts.py` with both dataclasses + `from_dict` / `to_dict`. Unit tests in `tests/test_sink_contracts.py` round-trip canonical fixtures. No producer wired yet.

3. **Producer refactor** — switch `build_operator_summary` to return `BrainDumpSummary`; switch `RunLog` writer to route through `RunLogEntry`. New JSON at rest carries `schema_version: 1` + `schema: <name>`. Existing consumers tolerate (they read by string-key, ignore unknown keys).

4. **Audit land** — `scripts/audit_sink_contracts.py` + wire into `make audit-all`. First run is informational (count anomalies, no fail) on logs older than the migration. New logs validate.

After commit 4, the contract is enforced at every PR + every weekly run. Future field additions in producers automatically pass; removals trigger schema_version bump.

## 8 · Non-goals

- **No new dependencies.** Pure stdlib (dataclass, json). No pydantic, no jsonschema-py (the audit script reads the YAML schema declaratively but enforces invariants in Python).
- **No Phase C backing-file scope.** ADR-0009 owns that schema; this spec must NOT define `BackingFileMeta`.
- **No runtime validation in producers.** Validation runs at the audit gate, not in the producer's hot path. Producers trust the contract; if they emit malformed payloads, the next audit catches it before the next PR.
- **No breaking change to existing n8n Code-node readers.** All current field names stay; only two new top-level keys (`schema_version`, `schema`) are added. Consumers that ignore unknown keys (all of them) keep working.

## 9 · Test plan

| Test | Scope |
|---|---|
| `tests/test_sink_contracts.py::test_brain_dump_summary_round_trip` | dataclass → dict → dataclass identity |
| `tests/test_sink_contracts.py::test_brain_dump_summary_tolerates_unknown_keys` | forward-compat (ADR-0008) |
| `tests/test_sink_contracts.py::test_run_log_entry_extras_passthrough` | producer-specific fields land in `extras` |
| `tests/test_sink_contracts.py::test_from_dict_missing_required_raises_keyerror` | clean failure signal |
| `tests/test_audit_sink_contracts.py::test_real_repo_clean_or_documented` | sanity: live state validates after migration |
| `tests/test_audit_sink_contracts.py::test_missing_schema_version_fails` | enforcement positive case |
| `tests/test_audit_sink_contracts.py::test_skip_reason_required_when_status_skipped` | invariant case |
| `tests/test_process_brain_dump.py` (existing) | unchanged; producer refactor should not break |

Estimated test count: +8 to +12 (depending on edge cases).

## 10 · Open questions

1. **Does `RunLogEntry.extras` belong in the schema YAML at all, or only in the Python dataclass?** Recommend: schema YAML treats `extras` as the "tolerated unknown fields" zone (no enum), Python dataclass exposes it as the explicit catch-all. Forward-compat preserved either way.

2. **Should the `top_added_tasks` Q2 Rock-area enum live in the schema or be open string?** Recommend: pin to the 8 canonical areas (matches CLAUDE.md's NEVER deviate rule). New area would require schema version bump — that's a feature, not a bug.

3. **Migration order vs audit gating** — migrating producers BEFORE the audit lands means at-rest data has mixed shapes for ~1 day during rollout. Acceptable per ADR-0008 forward-compat rule (consumers tolerate unknown), but worth noting.

4. **Does the n8n cron schedule for the new audit need a slot?** Recommend: piggy-back on the existing weekly `vault-health-report` Sunday 8PM run, not a new cron slot (Aaron's slot-protection rule from CLAUDE.md).

## 11 · Estimated cost

- Spec writing: ~3h (this doc)
- Schema files: ~1h
- `sink_contracts.py` + tests: ~3h
- Producer refactor: ~2h
- Audit script + tests: ~3h
- Documentation update (CURRENT-STATE.md + NEXT-STEPS.md): ~30min

**Total ~12h implementation after this spec is approved.**

## 12 · Sources

- Parallel cavecrew-investigator runs 2026-05-29 (sink mapping, bd_integrity surface, contract pattern survey).
- `docs/superpowers/2026-05-27-FOUNDATION-AUDIT-AND-TOP-DOWN-PLAN.md` §5 A4.
- `docs/adr/0008-cross-host-comms.md` (envelope forward-compat).
- `docs/adr/0009-threaded-tasks.md` (additive-only evolution).
- `docs/schemas/task-backing-file.v1.yaml` (template for versioned YAML).
- `tools/process_brain_dump.py` L138-L184 (RunLog), L1026-L1066 (build_operator_summary).
- `tools/bd_integrity.py` (frontmatter + receipt contracts; out of scope but adjacent).

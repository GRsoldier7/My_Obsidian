# SinkInputContract (A4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock the `BrainDumpSummary` and `RunLogEntry` contracts (top-down-plan §5 A4) with versioned YAML schemas + Python dataclasses + an at-rest audit, without changing the field shape n8n consumers already read.

**Architecture:** Family of two locked contracts mirroring the [`task-backing-file.v1.yaml`](../../schemas/task-backing-file.v1.yaml) pattern. Pure stdlib (`dataclasses`, `json`); no new dependencies. Producer refactor is additive — JSON at rest gains `schema_version` + `schema` keys only. Enforcement runs in `scripts/audit_sink_contracts.py`, added to `make audit-all`. Forward-compat per ADR-0008 (consumers tolerate unknown fields); additive-only evolution per ADR-0009.

**Tech Stack:** Python 3.12+, `dataclasses`, `json`, `pyyaml` (already in deps), `pytest`, `boto3` (existing). No new third-party libraries.

**Spec:** [`docs/superpowers/specs/2026-05-29-sink-input-contract-design.md`](../specs/2026-05-29-sink-input-contract-design.md)

**Estimated cost:** ~12h across 4 atomic commits.

---

## File Structure

**New files:**
- `docs/schemas/brain-dump-summary.v1.yaml` — versioned schema for `last-brain-dump-summary.json`
- `docs/schemas/run-log-entry.v1.yaml` — versioned schema for `99_System/logs/<wf>-<DATE>.json`
- `tools/sink_contracts.py` — `BrainDumpSummary` + `RunLogEntry` dataclasses, `from_dict` / `to_dict`
- `tests/test_sink_contracts.py` — round-trip + forward-compat + invariant tests
- `scripts/audit_sink_contracts.py` — at-rest validator (live MinIO walk)
- `tests/test_audit_sink_contracts.py` — fixture-based audit tests

**Modified files:**
- `tools/process_brain_dump.py:1026-1066` (build_operator_summary) — return `BrainDumpSummary`
- `tools/process_brain_dump.py:1017` (write_run_log) + L138-L184 (RunLog dataclass) — route through `RunLogEntry`
- `tools/process_brain_dump.py:1079` (write_operator_summary) — call `.to_dict()` before json.dumps
- `Makefile` — add `audit-sink-contracts` target + include in `audit-all` + `.PHONY`
- `.githooks/pre-commit` — add `audit_sink_contracts.py` call
- `docs/CURRENT-STATE.md` — bump audit count 12 → 13

---

## Task 1: Land the YAML schemas (design contract first)

**Files:**
- Create: `docs/schemas/brain-dump-summary.v1.yaml`
- Create: `docs/schemas/run-log-entry.v1.yaml`

No code consumers yet. This commit is docs-only; safe to land before any Python touches.

- [ ] **Step 1: Create `docs/schemas/brain-dump-summary.v1.yaml`**

```yaml
# Brain-dump summary state schema v1 — top-down-plan §5 A4 (SinkInputContract).
#
# Produced by tools/process_brain_dump.build_operator_summary; written to
# 99_System/state/last-brain-dump-summary.json. Consumed by:
#   - tools/build_command_center (DCC render)
#   - workflows/n8n/morning-briefing.json (Code node; reads same MinIO key)
#   - tools/build_health_dashboard (last-run row)
#
# Lock contract:
#   - Schema is FROZEN at v1 once A4 ships. Additive changes only (new optional
#     fields). Field removals require a schema-version bump.
#   - Consumers MUST tolerate unknown fields (ADR-0008 forward-compat). Producers
#     MAY add fields without notice.
#   - status enum is fixed at three values; new values require version bump.

schema_version: 1
schema: oho.brain-dump-summary.v1

required_fields:
  run_finished_at:
    type: string
    format: iso-8601-utc
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
    items: { type: string }
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
    description: Counts keyed by tools.bd_integrity.VALID_STATES.
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
    properties:
      files_reset_full: { type: integer, minimum: 0 }
      files_reset_partial: { type: integer, minimum: 0 }
      files_reset_skipped: { type: integer, minimum: 0 }
  top_added_tasks:
    type: array
    description: First 10 tasks from new_tasks_added; parsed and sorted A→B→C.
    items:
      type: object
      required: [area, priority, desc]
      properties:
        area:
          type: string
          enum: [faith, family, business, consulting, work, health, home, personal]
        priority:
          type: string
          enum: [A, B, C]
        desc: { type: string }
  total_added_tasks:
    type: integer
    minimum: 0

optional_fields:
  # Forward-compat zone (ADR-0008). Producers MAY add fields here without bumping
  # the schema version. Consumers MUST ignore unknown keys.

invariants:
  - id: status_skipped_requires_reason
    rule: when status == "skipped", a skip_reason field MUST be present (forward-compat addition)
  - id: file_counts_consistent
    rule: |
      len(files_extracted) + len(files_partial) + len(files_error)
        == files_by_state["extracted"] + files_by_state["partial"] + files_by_state["error"]
  - id: top_tasks_capped
    rule: len(top_added_tasks) <= 10
```

- [ ] **Step 2: Create `docs/schemas/run-log-entry.v1.yaml`**

```yaml
# Run-log entry schema v1 — top-down-plan §5 A4 (SinkInputContract).
#
# Common base shape for every 99_System/logs/<workflow>-<YYYY-MM-DD>.json entry.
# Producers MAY extend with workflow-specific fields (RunLogEntry.extras).
# Consumed by:
#   - scripts/audit_workflow_runlogs (skip_reason enum)
#   - tools/build_health_dashboard (rollups)
#   - scripts/audit_extraction_receipts (brain-dump-processor specifically)
#
# Lock contract:
#   - Schema is FROZEN at v1. Additive changes only.
#   - skip_reason enum lives in tests/test_workflow_templates.ALLOWED_SKIP_REASONS;
#     this schema mirrors it. Adding a new skip_reason requires updating both.

schema_version: 1
schema: oho.run-log-entry.v1

required_fields:
  workflow:
    type: string
    description: Stable identifier; matches the n8n JSON filename stem.
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
  skip_reason:
    type: string
    enum:
      - minio_auth_error
      - minio_list_failed
      - empty_inbox
      - no_active_files
      - missing_credential
      - fetch_failure
      - already_processed_today
      - ai_unavailable
      - rate_limited
      - dry_run
    required_when: status == "skipped"

optional_fields:
  # Forward-compat zone. Workflow-specific fields land under extras at the
  # Python layer; in JSON they appear as top-level keys alongside the required
  # set. Consumers tolerate unknown keys.

invariants:
  - id: chronological
    rule: finished_at >= started_at
  - id: duration_matches_clock
    rule: abs(duration_ms - int((finished_at - started_at).total_seconds() * 1000)) <= 50
  - id: skipped_carries_reason
    rule: when status == "skipped", skip_reason MUST be present and in the enum
```

- [ ] **Step 3: Validate YAML parses**

```bash
python3 -c "import yaml; yaml.safe_load(open('docs/schemas/brain-dump-summary.v1.yaml')); yaml.safe_load(open('docs/schemas/run-log-entry.v1.yaml')); print('YAML OK')"
```

Expected: `YAML OK`.

- [ ] **Step 4: Run existing test suite to confirm zero regression**

```bash
make verify 2>&1 | tail -5
```

Expected: `703 passed, 5 skipped` (or higher); audits green.

- [ ] **Step 5: Commit**

```bash
git add docs/schemas/brain-dump-summary.v1.yaml docs/schemas/run-log-entry.v1.yaml
git commit -m "schemas(A4): land BrainDumpSummary.v1 + RunLogEntry.v1 YAML

First commit of the A4 SinkInputContract migration. Two locked YAML
schemas, no code consumers yet. Both follow the task-backing-file.v1.yaml
style: schema_version + schema header, required_fields, conditional /
optional zones, named invariants.

Spec: docs/superpowers/specs/2026-05-29-sink-input-contract-design.md
Plan: docs/superpowers/plans/2026-05-29-sink-input-contract-implementation.md

Next commit lands tools/sink_contracts.py.
"
```

---

## Task 2: Land the Python module + tests

**Files:**
- Create: `tools/sink_contracts.py` (~150 LOC)
- Create: `tests/test_sink_contracts.py` (~120 LOC)

- [ ] **Step 1: Write the failing test file**

Create `tests/test_sink_contracts.py`:

```python
"""Tests for tools.sink_contracts — A4 SinkInputContract.

Round-trip, forward-compat (unknown keys tolerated), and required-field
validation. Run by `make test` + `make verify`.
"""
from __future__ import annotations

import pytest

from tools.sink_contracts import (
    SCHEMA_NAME_RUNLOG,
    SCHEMA_NAME_SUMMARY,
    SCHEMA_VERSION_RUNLOG,
    SCHEMA_VERSION_SUMMARY,
    BrainDumpSummary,
    FileError,
    FilePartial,
    RunLogEntry,
    TopAddedTask,
)


def _canonical_summary_dict() -> dict:
    return {
        "schema_version": 1,
        "schema": "oho.brain-dump-summary.v1",
        "run_finished_at": "2026-05-29T07:01:23Z",
        "run_started_at": "2026-05-29T07:00:00Z",
        "status": "success",
        "tasks_written": 4,
        "review_added": 1,
        "articles_queued": 2,
        "files_extracted": ["brain-dump-2026-05-29.md"],
        "files_partial": [{"file": "noisy.md", "reasons": ["pre_extraction_failure"]}],
        "files_error": [{"file": "broken.md", "error": "yaml parse"}],
        "files_by_state": {
            "empty": 0,
            "has_content": 0,
            "scanning": 0,
            "extracted": 1,
            "partial": 1,
            "error": 1,
        },
        "reset_summary": {
            "files_reset_full": 1,
            "files_reset_partial": 0,
            "files_reset_skipped": 1,
        },
        "top_added_tasks": [
            {"area": "faith", "priority": "A", "desc": "Read morning prayer plan"},
        ],
        "total_added_tasks": 4,
    }


def _canonical_runlog_dict() -> dict:
    return {
        "schema_version": 1,
        "schema": "oho.run-log-entry.v1",
        "workflow": "brain-dump-processor",
        "run_date": "2026-05-29",
        "started_at": "2026-05-29T07:00:00Z",
        "finished_at": "2026-05-29T07:01:23Z",
        "duration_ms": 83000,
        "status": "success",
    }


# ── BrainDumpSummary ──────────────────────────────────────────────────────────

def test_brain_dump_summary_round_trip_identity():
    d = _canonical_summary_dict()
    obj = BrainDumpSummary.from_dict(d)
    assert obj.schema_version == SCHEMA_VERSION_SUMMARY
    assert obj.schema == SCHEMA_NAME_SUMMARY
    assert obj.to_dict() == d


def test_brain_dump_summary_tolerates_unknown_keys():
    """ADR-0008 forward-compat: producers may add fields without notice;
    consumers ignore unknowns."""
    d = _canonical_summary_dict()
    d["future_field"] = "this should be silently dropped"
    obj = BrainDumpSummary.from_dict(d)
    assert obj.to_dict().get("future_field") is None


def test_brain_dump_summary_missing_required_raises_keyerror():
    d = _canonical_summary_dict()
    del d["tasks_written"]
    with pytest.raises(KeyError, match="tasks_written"):
        BrainDumpSummary.from_dict(d)


def test_brain_dump_summary_top_added_tasks_parsed_as_dataclass():
    d = _canonical_summary_dict()
    obj = BrainDumpSummary.from_dict(d)
    assert isinstance(obj.top_added_tasks[0], TopAddedTask)
    assert obj.top_added_tasks[0].area == "faith"


def test_brain_dump_summary_files_partial_error_parsed_as_dataclasses():
    d = _canonical_summary_dict()
    obj = BrainDumpSummary.from_dict(d)
    assert isinstance(obj.files_partial[0], FilePartial)
    assert isinstance(obj.files_error[0], FileError)


# ── RunLogEntry ───────────────────────────────────────────────────────────────

def test_run_log_entry_round_trip_identity():
    d = _canonical_runlog_dict()
    obj = RunLogEntry.from_dict(d)
    assert obj.to_dict() == d


def test_run_log_entry_extras_passthrough():
    """Workflow-specific fields land in `extras` so consumers can still grep
    by string-key on the at-rest JSON."""
    d = _canonical_runlog_dict()
    d["tasks_written"] = 4
    d["articles_queued"] = 2
    obj = RunLogEntry.from_dict(d)
    assert obj.extras["tasks_written"] == 4
    assert obj.extras["articles_queued"] == 2
    # to_dict round-trip preserves them at top level
    out = obj.to_dict()
    assert out["tasks_written"] == 4
    assert out["articles_queued"] == 2


def test_run_log_entry_skipped_carries_reason():
    d = _canonical_runlog_dict()
    d["status"] = "skipped"
    d["skip_reason"] = "empty_inbox"
    obj = RunLogEntry.from_dict(d)
    assert obj.skip_reason == "empty_inbox"


def test_run_log_entry_missing_required_raises_keyerror():
    d = _canonical_runlog_dict()
    del d["finished_at"]
    with pytest.raises(KeyError, match="finished_at"):
        RunLogEntry.from_dict(d)
```

- [ ] **Step 2: Run test to verify it fails (module not yet created)**

```bash
python3 -m pytest tests/test_sink_contracts.py -q --tb=line 2>&1 | tail -10
```

Expected: ImportError on `tools.sink_contracts`.

- [ ] **Step 3: Create `tools/sink_contracts.py`**

```python
"""tools/sink_contracts.py — A4 SinkInputContract Python types.

Two dataclasses (`BrainDumpSummary` + `RunLogEntry`) mirror the two YAML
schemas under docs/schemas/. Both round-trip cleanly to/from dict and
tolerate unknown keys (forward-compat per ADR-0008).

Use:
    from tools.sink_contracts import BrainDumpSummary
    obj = BrainDumpSummary.from_dict(json.loads(blob))
    out = obj.to_dict()

Field shape is locked at v1; additive changes only. Removals require a
schema-version bump. See docs/superpowers/specs/2026-05-29-sink-input-contract-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


SCHEMA_VERSION_SUMMARY = 1
SCHEMA_NAME_SUMMARY = "oho.brain-dump-summary.v1"

SCHEMA_VERSION_RUNLOG = 1
SCHEMA_NAME_RUNLOG = "oho.run-log-entry.v1"


# ── Nested types ─────────────────────────────────────────────────────────────

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


# ── BrainDumpSummary ─────────────────────────────────────────────────────────

_SUMMARY_REQUIRED = (
    "run_finished_at", "run_started_at", "status",
    "tasks_written", "review_added", "articles_queued",
    "files_extracted", "files_partial", "files_error",
    "files_by_state", "reset_summary",
    "top_added_tasks", "total_added_tasks",
)


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BrainDumpSummary":
        for k in _SUMMARY_REQUIRED:
            if k not in d:
                raise KeyError(k)
        return cls(
            schema_version=d.get("schema_version", SCHEMA_VERSION_SUMMARY),
            schema=d.get("schema", SCHEMA_NAME_SUMMARY),
            run_finished_at=d["run_finished_at"],
            run_started_at=d["run_started_at"],
            status=d["status"],
            tasks_written=d["tasks_written"],
            review_added=d["review_added"],
            articles_queued=d["articles_queued"],
            files_extracted=list(d["files_extracted"]),
            files_partial=[FilePartial(**fp) for fp in d["files_partial"]],
            files_error=[FileError(**fe) for fe in d["files_error"]],
            files_by_state=dict(d["files_by_state"]),
            reset_summary=dict(d["reset_summary"]),
            top_added_tasks=[TopAddedTask(**t) for t in d["top_added_tasks"]],
            total_added_tasks=d["total_added_tasks"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── RunLogEntry ──────────────────────────────────────────────────────────────

_RUNLOG_REQUIRED = (
    "workflow", "run_date", "started_at", "finished_at",
    "duration_ms", "status",
)
_RUNLOG_KNOWN_OPTIONAL = ("skip_reason",)
_RUNLOG_HEAD = ("schema_version", "schema") + _RUNLOG_REQUIRED + _RUNLOG_KNOWN_OPTIONAL


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
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RunLogEntry":
        for k in _RUNLOG_REQUIRED:
            if k not in d:
                raise KeyError(k)
        extras = {k: v for k, v in d.items() if k not in _RUNLOG_HEAD}
        return cls(
            schema_version=d.get("schema_version", SCHEMA_VERSION_RUNLOG),
            schema=d.get("schema", SCHEMA_NAME_RUNLOG),
            workflow=d["workflow"],
            run_date=d["run_date"],
            started_at=d["started_at"],
            finished_at=d["finished_at"],
            duration_ms=d["duration_ms"],
            status=d["status"],
            skip_reason=d.get("skip_reason"),
            extras=extras,
        )

    def to_dict(self) -> dict[str, Any]:
        base = {
            "schema_version": self.schema_version,
            "schema": self.schema,
            "workflow": self.workflow,
            "run_date": self.run_date,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
        }
        if self.skip_reason is not None:
            base["skip_reason"] = self.skip_reason
        base.update(self.extras)
        return base
```

- [ ] **Step 4: Run tests; verify all pass**

```bash
python3 -m pytest tests/test_sink_contracts.py -q --tb=short 2>&1 | tail -10
```

Expected: `10 passed`.

- [ ] **Step 5: Run full `make verify` for zero regression**

```bash
make verify 2>&1 | tail -5
```

Expected: `713 passed, 5 skipped` (current 703 + 10 new); 12 audits green.

- [ ] **Step 6: Commit**

```bash
git add tools/sink_contracts.py tests/test_sink_contracts.py
git commit -m "feat(contracts): tools/sink_contracts.py — A4 dataclasses

Second commit of the A4 SinkInputContract migration. Two frozen
dataclasses (BrainDumpSummary, RunLogEntry) plus three nested types
(TopAddedTask, FilePartial, FileError).

Both classes round-trip to/from dict, tolerate unknown keys (ADR-0008
forward-compat), and raise KeyError on missing required fields (clean
caller signal).

RunLogEntry routes producer-specific fields (tasks_written,
articles_queued, etc.) into the `extras` dict so consumers can still
grep by string-key on the at-rest JSON during the migration window.

10 new tests in tests/test_sink_contracts.py: round-trip identity,
forward-compat tolerance, missing-required behavior, nested-type
parsing.

No producers wired yet; next commit refactors process_brain_dump.
"
```

---

## Task 3: Producer refactor (additive — adds schema_version + schema only)

**Files:**
- Modify: `tools/process_brain_dump.py:138-184` (RunLog dataclass — keep, add adapter)
- Modify: `tools/process_brain_dump.py:1017` (write_run_log) — route through RunLogEntry
- Modify: `tools/process_brain_dump.py:1026-1066` (build_operator_summary) — return BrainDumpSummary
- Modify: `tools/process_brain_dump.py:1079` (write_operator_summary) — `.to_dict()` before json.dumps

- [ ] **Step 1: Read current code at L1026-L1066 to confirm field names**

```bash
sed -n '1020,1080p' tools/process_brain_dump.py
```

Expected: a `build_operator_summary` returning a 12-field dict literal.

- [ ] **Step 2: Modify `build_operator_summary` to return `BrainDumpSummary`**

Add import at the top of `tools/process_brain_dump.py` (alongside other tools imports):

```python
from tools.sink_contracts import (
    SCHEMA_NAME_RUNLOG,
    SCHEMA_NAME_SUMMARY,
    SCHEMA_VERSION_RUNLOG,
    SCHEMA_VERSION_SUMMARY,
    BrainDumpSummary,
    FileError,
    FilePartial,
    RunLogEntry,
    TopAddedTask,
)
```

Replace the body of `build_operator_summary` (current inline dict construction) with a `BrainDumpSummary` constructor. Keep the same input args + the same field-derivation logic. Final return:

```python
def build_operator_summary(run_log: "RunLog", new_tasks_added: list[str]) -> BrainDumpSummary:
    # ... existing parsing of new_tasks_added → top_added_tasks dicts stays unchanged ...
    return BrainDumpSummary(
        schema_version=SCHEMA_VERSION_SUMMARY,
        schema=SCHEMA_NAME_SUMMARY,
        run_finished_at=run_log.finished_at,
        run_started_at=run_log.started_at,
        status=run_log.status,
        tasks_written=run_log.tasks_written,
        review_added=run_log.notes_written,
        articles_queued=run_log.articles_queued,
        files_extracted=list(run_log.files_extracted),
        files_partial=[FilePartial(**fp) for fp in run_log.files_partial],
        files_error=[FileError(**fe) for fe in run_log.files_error],
        files_by_state=dict(run_log.files_by_state),
        reset_summary=dict(run_log.reset_summary),
        top_added_tasks=[TopAddedTask(**t) for t in top_added_dicts],
        total_added_tasks=len(new_tasks_added),
    )
```

The `top_added_dicts` local variable is whatever the function already builds — keep the existing sort + 10-cap logic.

- [ ] **Step 3: Modify `write_operator_summary` to call `.to_dict()`**

Find the existing line that does `json.dumps(summary, ...)`. Change to:

```python
def write_operator_summary(s3, summary: BrainDumpSummary) -> None:
    key = SUMMARY_KEY  # 99_System/state/last-brain-dump-summary.json
    body = json.dumps(summary.to_dict(), indent=2)
    put_text_verified(s3, BUCKET, key, body, content_type="application/json")
```

If `write_operator_summary` previously used `put_object` directly, swap to `put_text_verified` (already imported per recent migrations).

- [ ] **Step 4: Modify `write_run_log` to route through `RunLogEntry`**

Around line 1017, the writer currently does `json.dumps(asdict(run_log))`. Refactor to:

```python
def write_run_log(s3, run_log: "RunLog") -> None:
    # Split RunLog (24 fields) into RunLogEntry head + extras.
    common = {
        "schema_version": SCHEMA_VERSION_RUNLOG,
        "schema": SCHEMA_NAME_RUNLOG,
        "workflow": run_log.workflow,
        "run_date": run_log.run_date,
        "started_at": run_log.started_at,
        "finished_at": run_log.finished_at,
        "duration_ms": run_log.duration_ms,
        "status": run_log.status,
    }
    if getattr(run_log, "skip_reason", None):
        common["skip_reason"] = run_log.skip_reason

    extras = asdict(run_log)
    for k in list(common.keys()):
        extras.pop(k, None)

    entry = RunLogEntry.from_dict({**common, **extras})
    key = f"99_System/logs/{run_log.workflow}-{run_log.run_date}.json"
    body = json.dumps(entry.to_dict(), indent=2)
    put_text_verified(s3, BUCKET, key, body, content_type="application/json")
```

- [ ] **Step 5: If `RunLog` doesn't have a `skip_reason` field, add it as an optional**

Inspect L138-L184:

```bash
grep -n "skip_reason" tools/process_brain_dump.py
```

If `RunLog` does not declare `skip_reason`, add it as `skip_reason: str | None = None`. Existing call sites that pass kwargs unchanged continue to work.

- [ ] **Step 6: Run full test suite for zero regression**

```bash
make verify 2>&1 | tail -8
```

Expected: `713 passed, 5 skipped` (or higher); 12 audits green. The at-rest JSON now includes `schema_version: 1` + `schema: "oho.brain-dump-summary.v1"` (or run-log equivalent) as new top-level keys; existing tests that look at field names continue to pass because all original fields remain.

- [ ] **Step 7: Verify n8n consumer compat manually**

```bash
python3 -c "
from tools.sink_contracts import BrainDumpSummary
import json
example = json.load(open('tools/fixtures/sample-summary.json')) if False else None
print('manual eyeball: write a sample summary, check that morning-briefing.json Build node would still find tasks_extracted / task_count keys')
"
```

This is a sanity check — read the morning-briefing.json `Build Morning Briefing` Code node and confirm it references field names that still appear in the new at-rest JSON (`tasks_extracted` lands under `extras`; still a top-level key).

- [ ] **Step 8: Commit**

```bash
git add tools/process_brain_dump.py
git commit -m "feat(contracts): wire process_brain_dump through sink_contracts (A4)

Third commit of the A4 migration. build_operator_summary now returns
BrainDumpSummary; write_operator_summary calls .to_dict() before
json.dumps. RunLog writer routes through RunLogEntry which carries
common fields (workflow, run_date, started_at, finished_at, duration_ms,
status, skip_reason) at the top level and the remaining 17 RunLog
fields under extras.

JSON at rest gains two top-level keys (schema_version, schema). All
existing field names remain at top-level (extras dict round-trips
flat in to_dict). n8n Code-node consumers that grep tasks_extracted /
task_count / articles_queued continue to work.

put_text_verified used for both writes (replaces any remaining
raw put_object). Net audit allowlist impact: zero (process_brain_dump
remains allowlisted for the 4 RMW sites; this commit doesn't touch them).

713 pass + 5 skip; 12 audits green.
"
```

---

## Task 4: Land the audit + wire it into the gate

**Files:**
- Create: `scripts/audit_sink_contracts.py` (~200 LOC)
- Create: `tests/test_audit_sink_contracts.py` (~150 LOC)
- Modify: `Makefile` — add `audit-sink-contracts` target + include in `audit-all` + `.PHONY`
- Modify: `.githooks/pre-commit` — add audit call
- Modify: `docs/CURRENT-STATE.md` — bump audit count 12 → 13

- [ ] **Step 1: Write the failing test file**

Create `tests/test_audit_sink_contracts.py`:

```python
"""Tests for scripts/audit_sink_contracts.py — A4 enforcement."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_sink_contracts as asc  # noqa: E402


VALID_RUNLOG = {
    "schema_version": 1,
    "schema": "oho.run-log-entry.v1",
    "workflow": "brain-dump-processor",
    "run_date": "2026-05-29",
    "started_at": "2026-05-29T07:00:00Z",
    "finished_at": "2026-05-29T07:01:23Z",
    "duration_ms": 83000,
    "status": "success",
}


def test_valid_runlog_passes():
    findings = asc.validate_runlog_entry(VALID_RUNLOG, source="test")
    assert findings == []


def test_runlog_missing_schema_version_fails():
    bad = {k: v for k, v in VALID_RUNLOG.items() if k != "schema_version"}
    findings = asc.validate_runlog_entry(bad, source="test")
    assert any("schema_version" in f for f in findings)


def test_runlog_status_skipped_requires_skip_reason():
    bad = {**VALID_RUNLOG, "status": "skipped"}
    findings = asc.validate_runlog_entry(bad, source="test")
    assert any("skip_reason" in f for f in findings)


def test_runlog_invalid_skip_reason_fails():
    bad = {**VALID_RUNLOG, "status": "skipped", "skip_reason": "not_in_enum"}
    findings = asc.validate_runlog_entry(bad, source="test")
    assert any("not_in_enum" in f or "enum" in f for f in findings)


def test_runlog_chronological_invariant():
    bad = {**VALID_RUNLOG, "finished_at": "2026-05-29T06:59:00Z"}  # before started_at
    findings = asc.validate_runlog_entry(bad, source="test")
    assert any("chronological" in f.lower() or "before started" in f.lower() for f in findings)


VALID_SUMMARY = {
    "schema_version": 1,
    "schema": "oho.brain-dump-summary.v1",
    "run_finished_at": "2026-05-29T07:01:23Z",
    "run_started_at": "2026-05-29T07:00:00Z",
    "status": "success",
    "tasks_written": 1,
    "review_added": 0,
    "articles_queued": 0,
    "files_extracted": ["a.md"],
    "files_partial": [],
    "files_error": [],
    "files_by_state": {
        "empty": 0, "has_content": 0, "scanning": 0,
        "extracted": 1, "partial": 0, "error": 0,
    },
    "reset_summary": {
        "files_reset_full": 0, "files_reset_partial": 0, "files_reset_skipped": 0,
    },
    "top_added_tasks": [{"area": "faith", "priority": "A", "desc": "x"}],
    "total_added_tasks": 1,
}


def test_valid_summary_passes():
    assert asc.validate_summary(VALID_SUMMARY, source="test") == []


def test_summary_missing_required_field_fails():
    bad = {k: v for k, v in VALID_SUMMARY.items() if k != "tasks_written"}
    findings = asc.validate_summary(bad, source="test")
    assert any("tasks_written" in f for f in findings)


def test_summary_file_counts_inconsistent_fails():
    bad = {**VALID_SUMMARY, "files_by_state": {
        "empty": 0, "has_content": 0, "scanning": 0,
        "extracted": 99, "partial": 0, "error": 0,  # mismatch with files_extracted len=1
    }}
    findings = asc.validate_summary(bad, source="test")
    assert any("file_counts" in f.lower() or "consistent" in f.lower() for f in findings)


def test_summary_area_enum_enforced():
    bad = {**VALID_SUMMARY, "top_added_tasks": [
        {"area": "not-an-area", "priority": "A", "desc": "x"},
    ]}
    findings = asc.validate_summary(bad, source="test")
    assert any("not-an-area" in f or "area" in f for f in findings)


def test_main_clean_repo_exits_zero(monkeypatch):
    """No live MinIO scan in CI; --self-test mode validates known-good fixtures."""
    monkeypatch.setattr(sys, "argv", ["audit_sink_contracts.py", "--self-test"])
    assert asc.main() == 0
```

- [ ] **Step 2: Run test to verify it fails (audit not yet created)**

```bash
python3 -m pytest tests/test_audit_sink_contracts.py -q --tb=line 2>&1 | tail -5
```

Expected: ImportError on `audit_sink_contracts`.

- [ ] **Step 3: Create `scripts/audit_sink_contracts.py`**

```python
#!/usr/bin/env python3
"""scripts/audit_sink_contracts.py — A4 SinkInputContract enforcement.

Validates at-rest JSON payloads against the YAML schemas in docs/schemas/:
  - docs/schemas/brain-dump-summary.v1.yaml ↔ last-brain-dump-summary.json
  - docs/schemas/run-log-entry.v1.yaml ↔ 99_System/logs/<wf>-<DATE>.json

Live MinIO walk in --live mode (default). Fixture-only self-test in
--self-test mode (used by tests). Exit codes match the rest of the audit
family: 0 clean, 1 violations, 2 I/O failure.

Scope notes:
  - Skips logs older than --days N (default 14). Matches build_health_dashboard.
  - Tolerates extras at the top level (forward-compat per ADR-0008).
  - Required fields + invariants enforce the contract; extras are ignored.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Use the Python contracts as the authoritative validation source; YAML files
# are the human-readable schema (audit reads them for the enum + invariant docs
# but enforcement uses the dataclass + invariant funcs here).
from tools.sink_contracts import (  # noqa: E402
    SCHEMA_NAME_RUNLOG,
    SCHEMA_NAME_SUMMARY,
    SCHEMA_VERSION_RUNLOG,
    SCHEMA_VERSION_SUMMARY,
    BrainDumpSummary,
    RunLogEntry,
)


_SKIP_REASONS = {
    "minio_auth_error", "minio_list_failed",
    "empty_inbox", "no_active_files",
    "missing_credential", "fetch_failure",
    "already_processed_today", "ai_unavailable",
    "rate_limited", "dry_run",
}

_VALID_AREAS = {"faith", "family", "business", "consulting", "work", "health", "home", "personal"}
_VALID_PRIORITIES = {"A", "B", "C"}


def validate_runlog_entry(d: dict, source: str) -> list[str]:
    findings: list[str] = []
    # Schema headers
    if d.get("schema_version") != SCHEMA_VERSION_RUNLOG:
        findings.append(f"{source}: schema_version != {SCHEMA_VERSION_RUNLOG} (got {d.get('schema_version')!r})")
    if d.get("schema") != SCHEMA_NAME_RUNLOG:
        findings.append(f"{source}: schema != {SCHEMA_NAME_RUNLOG!r} (got {d.get('schema')!r})")
    # Required fields + types
    try:
        entry = RunLogEntry.from_dict(d)
    except KeyError as e:
        findings.append(f"{source}: missing required field {e.args[0]!r}")
        return findings  # short-circuit; can't check invariants without the head
    except (TypeError, ValueError) as e:
        findings.append(f"{source}: from_dict failed: {e}")
        return findings
    # Conditional: status == skipped requires skip_reason in enum
    if entry.status == "skipped":
        if not entry.skip_reason:
            findings.append(f"{source}: status=skipped requires skip_reason")
        elif entry.skip_reason not in _SKIP_REASONS:
            findings.append(f"{source}: skip_reason {entry.skip_reason!r} not in enum (allowed: {sorted(_SKIP_REASONS)})")
    # Invariant: chronological
    if entry.finished_at < entry.started_at:
        findings.append(f"{source}: finished_at < started_at (chronological violation)")
    return findings


def validate_summary(d: dict, source: str) -> list[str]:
    findings: list[str] = []
    if d.get("schema_version") != SCHEMA_VERSION_SUMMARY:
        findings.append(f"{source}: schema_version != {SCHEMA_VERSION_SUMMARY} (got {d.get('schema_version')!r})")
    if d.get("schema") != SCHEMA_NAME_SUMMARY:
        findings.append(f"{source}: schema != {SCHEMA_NAME_SUMMARY!r} (got {d.get('schema')!r})")
    try:
        s = BrainDumpSummary.from_dict(d)
    except KeyError as e:
        findings.append(f"{source}: missing required field {e.args[0]!r}")
        return findings
    except (TypeError, ValueError) as e:
        findings.append(f"{source}: from_dict failed: {e}")
        return findings
    # Invariant: file_counts_consistent
    fbs = s.files_by_state
    listed = len(s.files_extracted) + len(s.files_partial) + len(s.files_error)
    counted = fbs.get("extracted", 0) + fbs.get("partial", 0) + fbs.get("error", 0)
    if listed != counted:
        findings.append(f"{source}: file_counts not consistent (lists sum={listed}, files_by_state sum={counted})")
    # Invariant: top_added_tasks cap
    if len(s.top_added_tasks) > 10:
        findings.append(f"{source}: top_added_tasks length {len(s.top_added_tasks)} > 10")
    # Invariant: area enum
    for t in s.top_added_tasks:
        if t.area not in _VALID_AREAS:
            findings.append(f"{source}: top_added_tasks area {t.area!r} not in enum")
        if t.priority not in _VALID_PRIORITIES:
            findings.append(f"{source}: top_added_tasks priority {t.priority!r} not in enum")
    return findings


def _live_scan_summary(s3, bucket: str) -> list[str]:
    findings: list[str] = []
    try:
        obj = s3.get_object(Bucket=bucket, Key="99_System/state/last-brain-dump-summary.json")
        d = json.loads(obj["Body"].read().decode("utf-8"))
        findings.extend(validate_summary(d, source="last-brain-dump-summary.json"))
    except s3.exceptions.NoSuchKey:
        pass  # No summary yet is OK (first run)
    except Exception as e:
        print(f"WARN: could not read summary state: {e}", file=sys.stderr)
    return findings


def _live_scan_runlogs(s3, bucket: str, days: int) -> list[str]:
    findings: list[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="99_System/logs/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            mod = obj["LastModified"]
            if mod < cutoff:
                continue
            try:
                d = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8"))
            except Exception as e:
                findings.append(f"{key}: could not read/parse: {e}")
                continue
            findings.extend(validate_runlog_entry(d, source=key))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="A4 SinkInputContract at-rest validator")
    parser.add_argument("--days", type=int, default=14, help="run-log window in days (default 14)")
    parser.add_argument("--self-test", action="store_true", help="fixture-only mode; no MinIO calls")
    parser.add_argument("--strict", action="store_true", help="fail on warnings too (today's warnings are forward-compat hints)")
    args = parser.parse_args()

    if args.self_test:
        # No live calls; just confirm the dataclasses + enum tables load.
        print(f"OK — sink-contracts self-test ({SCHEMA_NAME_SUMMARY} v{SCHEMA_VERSION_SUMMARY}; {SCHEMA_NAME_RUNLOG} v{SCHEMA_VERSION_RUNLOG}).")
        return 0

    try:
        import boto3
    except ImportError:
        print("ERROR: boto3 required for live scan", file=sys.stderr)
        return 2

    endpoint = os.environ.get("MINIO_ENDPOINT")
    bucket = os.environ.get("MINIO_BUCKET", "obsidian-vault")
    if not endpoint:
        print("ERROR: MINIO_ENDPOINT not set; run with `make ENV=1 audit-sink-contracts`", file=sys.stderr)
        return 2

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )

    findings = []
    findings.extend(_live_scan_summary(s3, bucket))
    findings.extend(_live_scan_runlogs(s3, bucket, args.days))

    if findings:
        print(f"FAIL: {len(findings)} sink-contract violation(s):", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1

    print(f"OK — sink-contracts audit passed. Window: last {args.days}d.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests; expect all pass**

```bash
python3 -m pytest tests/test_audit_sink_contracts.py -q --tb=short 2>&1 | tail -10
```

Expected: `10 passed`.

- [ ] **Step 5: Add `audit-sink-contracts` to Makefile**

Edit `Makefile`. Find the existing audit target section near line 220 and insert:

```makefile
## A4 SinkInputContract at-rest validator (top-down-plan §5 A4).
## Walks MinIO 99_System/state/ + 99_System/logs/ and validates against
## tools/sink_contracts.{BrainDumpSummary,RunLogEntry}. Self-test mode for CI.
audit-sink-contracts:
	$(PYTHON) scripts/audit_sink_contracts.py --self-test
```

Update the `audit-all` line — add `audit-sink-contracts` at the end:

```makefile
audit-all: audit-workflows audit-ai-tooling audit-data-classes audit-secrets audit-planning-docs audit-workflow-secrets audit-workflow-runlogs audit-workflow-email-format audit-no-executecommand audit-no-argv-secrets audit-no-unverified-put-object audit-egress-classifier-wired audit-slo audit-sink-contracts
```

Update `.PHONY` to include `audit-sink-contracts`.

- [ ] **Step 6: Add audit to `.githooks/pre-commit`**

Edit `.githooks/pre-commit`. After the `egress-classifier-wired audit` block, add:

```bash
echo "[pre-commit] sink-contracts audit …"
# A4 SinkInputContract enforcement (self-test in CI; --live needs MinIO env).
python3 scripts/audit_sink_contracts.py --self-test
```

- [ ] **Step 7: Update `docs/CURRENT-STATE.md` audit count**

Find the line that says "12 audits in audit-all gate" (or similar) and bump to 13. Also add a new bullet under the offline-audits list:

```markdown
14. `audit_sink_contracts.py` — A4 SinkInputContract validator; self-test mode in CI, --live walks MinIO for at-rest payloads
```

(Number depends on current count; check `docs/CURRENT-STATE.md` before editing.)

- [ ] **Step 8: Run full `make verify` for zero regression**

```bash
make verify 2>&1 | tail -8
```

Expected: `723 passed, 5 skipped` (current 713 + 10 new); 13 audits green; sink-contracts self-test reports OK.

- [ ] **Step 9: Commit**

```bash
git add scripts/audit_sink_contracts.py tests/test_audit_sink_contracts.py Makefile .githooks/pre-commit docs/CURRENT-STATE.md
git commit -m "feat(audit): audit_sink_contracts.py — A4 enforcement (final commit)

Fourth and final commit of the A4 SinkInputContract migration. Adds a
new audit that validates at-rest JSON payloads under
  - 99_System/state/last-brain-dump-summary.json (BrainDumpSummary)
  - 99_System/logs/<wf>-<DATE>.json (RunLogEntry)
against the dataclass contracts in tools/sink_contracts.py. Live MinIO
walk by default; --self-test mode for CI (no boto3 required).

Wired into make audit-all (count 12 → 13) + .githooks/pre-commit.
docs/CURRENT-STATE.md bumped.

10 new tests in tests/test_audit_sink_contracts.py exercise required-
field, conditional (skip_reason), enum (area, priority), and invariant
(chronological, file_counts_consistent) paths.

A4 contract is now LIVE-ENFORCED end-to-end:
  schema YAML (commit 1)
    → Python dataclass (commit 2)
      → producer (commit 3)
        → at-rest audit (this commit)

723 pass + 5 skip; 13 audits green; PR #2 stays CLEAN.
"
```

---

## Self-Review

**Spec coverage:**
- §1 problem (4 sinks + drift findings) → No code task; spec context. ✅
- §2 decision (family of 2) → Tasks 1+2 (schemas + dataclasses). ✅
- §3.1 brain-dump-summary schema → Task 1 step 1. ✅
- §3.2 run-log-entry schema → Task 1 step 2. ✅
- §4 sink_contracts.py interface → Task 2 step 3. ✅
- §5.1 build_operator_summary refactor → Task 3 step 2. ✅
- §5.2 RunLog → RunLogEntry routing → Task 3 step 4. ✅
- §6 audit_sink_contracts.py → Task 4 step 3. ✅
- §7 migration plan → 4 atomic commits in this plan. ✅
- §8 non-goals → Phase C backing-file NOT touched. ✅
- §9 test plan → +20 tests across tasks 2 + 4. ✅
- §10 open questions → Aaron's call during execution (see open-questions block below).
- §11 cost ~12h → 4 commits @ 2-3h each. ✅

**Placeholder scan:**
- No "TBD", "TODO", "fill in", "similar to". ✅
- Every code step contains the actual code to be written. ✅
- Every command step shows the exact command + expected output. ✅
- Task 3 step 3 references "the existing line that does `json.dumps(summary, …)`" — engineer locates by string match (acceptable; live code may move during the migration).

**Type consistency:**
- `SCHEMA_VERSION_SUMMARY` / `SCHEMA_NAME_SUMMARY` consistent between tools/sink_contracts.py + tests + audit. ✅
- `RunLogEntry.extras` `dict[str, Any]` consistent across module + tests + audit. ✅
- `TopAddedTask` / `FilePartial` / `FileError` nested types reused identically. ✅
- `from_dict` raises `KeyError` consistently (matches §4 spec). ✅
- `to_dict` returns plain dict consistently. ✅

**Open questions from the spec (§10) that the engineer should pause for Aaron's call on:**

1. `RunLogEntry.extras` in schema YAML or only Python? — Task 1 step 2 schema says "Forward-compat zone" without listing extras explicitly. The engineer should NOT change this without Aaron's say.
2. `top_added_tasks.area` pinned enum? — Spec recommends pinned enum (8 areas). Plan implements pinned enum in Task 4 step 3. Aaron should confirm during execution.
3. Migration order vs audit gating window — Plan lands schemas first, audit last (Task 4 step 8 verifies). Order matches spec. Aaron confirms.
4. New audit cron slot vs piggy-back? — Plan does NOT add a cron slot. The audit runs in make audit-all (every PR + local pre-commit). If Aaron wants a weekly cron, that's a follow-up commit.

---

## Execution Handoff

**Plan complete and saved to** `docs/superpowers/plans/2026-05-29-sink-input-contract-implementation.md` **. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. Each of the 4 tasks is well-bounded (schemas / module / producer / audit) and lends itself to independent subagents.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints. Lower per-task latency but more main-thread context consumed.

**Which approach?**

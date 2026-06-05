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
            files_partial=[
                FilePartial(file=fp["file"], reasons=list(fp["reasons"]))
                for fp in d["files_partial"]
            ],
            files_error=[
                FileError(file=fe["file"], error=fe["error"])
                for fe in d["files_error"]
            ],
            files_by_state=dict(d["files_by_state"]),
            reset_summary=dict(d["reset_summary"]),
            top_added_tasks=[
                TopAddedTask(area=t["area"], priority=t["priority"], desc=t["desc"])
                for t in d["top_added_tasks"]
            ],
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

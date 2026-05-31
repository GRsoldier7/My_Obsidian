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


def test_brain_dump_summary_tolerates_unknown_keys_in_nested_types():
    """ADR-0008 forward-compat applies at every level. A producer adding a new
    field to a files_partial entry MUST NOT crash existing consumers."""
    d = _canonical_summary_dict()
    d["files_partial"] = [
        {"file": "noisy.md", "reasons": ["pre_extraction_failure"], "first_seen_at": "2026-05-30T00:00:00Z"},
    ]
    d["files_error"] = [
        {"file": "broken.md", "error": "yaml parse", "stack_trace": "irrelevant"},
    ]
    d["top_added_tasks"] = [
        {"area": "faith", "priority": "A", "desc": "x", "tag": "future-extension"},
    ]
    obj = BrainDumpSummary.from_dict(d)  # must not raise
    assert obj.files_partial[0].file == "noisy.md"
    assert obj.files_error[0].error == "yaml parse"
    assert obj.top_added_tasks[0].desc == "x"
    # to_dict should NOT carry the unknown nested keys (they were dropped by from_dict)
    out = obj.to_dict()
    assert "first_seen_at" not in out["files_partial"][0]
    assert "stack_trace" not in out["files_error"][0]
    assert "tag" not in out["top_added_tasks"][0]


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
    out = obj.to_dict()
    assert out["tasks_written"] == 4
    assert out["articles_queued"] == 2


def test_run_log_entry_skipped_carries_reason():
    d = _canonical_runlog_dict()
    d["status"] = "skipped"
    d["skip_reason"] = "empty_inbox"
    obj = RunLogEntry.from_dict(d)
    assert obj.skip_reason == "empty_inbox"


def test_run_log_entry_skip_reason_and_extras_combined_round_trip():
    """Round-trip identity when status=skipped (skip_reason set) AND producer-
    specific fields (extras) are present simultaneously."""
    d = _canonical_runlog_dict()
    d["status"] = "skipped"
    d["skip_reason"] = "empty_inbox"
    d["tasks_written"] = 0
    d["articles_queued"] = 0
    obj = RunLogEntry.from_dict(d)
    assert obj.skip_reason == "empty_inbox"
    assert obj.extras == {"tasks_written": 0, "articles_queued": 0}
    assert obj.to_dict() == d


def test_run_log_entry_missing_required_raises_keyerror():
    d = _canonical_runlog_dict()
    del d["finished_at"]
    with pytest.raises(KeyError, match="finished_at"):
        RunLogEntry.from_dict(d)

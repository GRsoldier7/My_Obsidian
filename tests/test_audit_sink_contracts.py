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

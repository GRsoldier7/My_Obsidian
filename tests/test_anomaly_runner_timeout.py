"""
Tests for the runner_timeout anomaly rule in tools/anomaly_detector.py.

Covers:
  - single recent timeout → high severity
  - clustered timeouts across workflows within 10 min → high severity, marked clustered
  - non-runner errors do not trigger the rule
  - timeouts older than 24h → low severity FYI only
  - empty / None input → no anomaly
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from anomaly_detector import (  # noqa: E402
    detect_anomalies,
    is_runner_timeout,
    rule_runner_timeout,
)


NOW = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


def _err(workflow: str, minutes_ago: int, msg: str = "Task request timed out after 60 seconds") -> dict:
    return {
        "workflow": workflow,
        "started_at": (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z"),
        "error": msg,
    }


def test_is_runner_timeout_matches_known_strings():
    assert is_runner_timeout("Task request timed out after 60 seconds")
    assert is_runner_timeout("Task request timed out after 120 seconds")
    assert is_runner_timeout("Code node could not be matched to a runner")
    assert is_runner_timeout("LocalTaskRequester.requestExpired (...)")


def test_is_runner_timeout_ignores_other_errors():
    assert not is_runner_timeout("ECONNREFUSED")
    assert not is_runner_timeout("MinIO returned NoSuchKey")
    assert not is_runner_timeout(None)
    assert not is_runner_timeout("")


def test_no_errors_produces_no_anomaly():
    out = rule_runner_timeout([], NOW)
    assert out == []
    out = rule_runner_timeout(None, NOW)
    assert out == []


def test_non_runner_errors_do_not_trigger():
    out = rule_runner_timeout([
        {"workflow": "live-dashboard", "started_at": (NOW - timedelta(hours=1)).isoformat(),
         "error": "MinIO unreachable"},
    ], NOW)
    assert out == []


def test_single_recent_timeout_is_high_severity():
    out = rule_runner_timeout([_err("Live Dashboard Updater", 90)], NOW)
    assert len(out) == 1
    assert out[0].severity == "high"
    assert out[0].rule == "runner_timeout"
    assert "Live Dashboard Updater" in out[0].workflow


def test_clustered_timeouts_across_workflows_emit_cluster_evidence():
    errs = [
        _err("Live Dashboard Updater", 60),
        _err("Link Enricher", 58),
        _err("Article Processor", 55),
    ]
    out = rule_runner_timeout(errs, NOW)
    # Single clustered anomaly, no per-workflow duplicates.
    assert len(out) == 1
    a = out[0]
    assert a.severity == "high"
    assert "within 10 minutes" in a.evidence
    assert "Live Dashboard Updater" in a.workflow
    assert "Link Enricher" in a.workflow
    assert "Article Processor" in a.workflow


def test_old_timeouts_only_yield_low_severity_fyi():
    # Both >24h ago — should not page, but should leave a low-severity breadcrumb.
    errs = [_err("Live Dashboard Updater", 60 * 30)]  # 30h ago
    out = rule_runner_timeout(errs, NOW)
    assert len(out) == 1
    assert out[0].severity == "low"
    assert out[0].workflow == "(historical)"


def test_old_timeouts_suppressed_when_recent_present():
    errs = [
        _err("Live Dashboard Updater", 60 * 48),  # 48h ago
        _err("Link Enricher", 30),                 # 30m ago
    ]
    out = rule_runner_timeout(errs, NOW)
    # Recent one drives a high; historical is suppressed (no point double-paging).
    severities = sorted(a.severity for a in out)
    assert "high" in severities
    assert "low" not in severities


def test_detect_anomalies_passes_recent_errors_through():
    """Backward-compat: detect_anomalies still works without recent_execution_errors,
    and surfaces runner anomalies when provided."""
    out_no_errors = detect_anomalies(
        workflow_stats=[], log_index={}, mtl_last_modified=None, now=NOW,
    )
    assert isinstance(out_no_errors, list)

    out_with_errors = detect_anomalies(
        workflow_stats=[], log_index={}, mtl_last_modified=None, now=NOW,
        recent_execution_errors=[_err("Live Dashboard Updater", 30)],
    )
    rules = [a["rule"] for a in out_with_errors]
    assert "runner_timeout" in rules

"""Tests for scripts/audit_slo_conformance.py — Wave-X H3 skeleton."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_slo_conformance as asc  # noqa: E402


SAMPLE_SLO = """# SLO doc

## Workflow SLOs

### Brain dump processor

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 99% | < 95% |
| Latency p95 | ≤ 30s | > 60s |

### Morning briefing

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 99% | < 95% |
| Latency p95 (assembly + render) | ≤ 10s | > 30s |

### Telegram capture (webhook)

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 99% | < 95% |
| Latency p95 | ≤ 2s | > 5s |
"""


# ── Parser ────────────────────────────────────────────────────────────────────
def test_parse_extracts_three_workflows():
    report = asc.parse_slo_doc(SAMPLE_SLO)
    assert report.parsed_ok
    assert len(report.entries) == 3
    names = [e.workflow for e in report.entries]
    assert "Brain dump processor" in names


def test_parse_extracts_success_rate_targets():
    report = asc.parse_slo_doc(SAMPLE_SLO)
    bd = next(e for e in report.entries if e.workflow == "Brain dump processor")
    assert bd.target_success_rate == 99.0
    assert bd.page_threshold_success == 95.0


def test_parse_extracts_latency_in_seconds():
    report = asc.parse_slo_doc(SAMPLE_SLO)
    bd = next(e for e in report.entries if e.workflow == "Brain dump processor")
    assert bd.target_latency_p95_s == 30.0
    assert bd.page_threshold_latency_p95_s == 60.0


def test_parse_converts_ms_to_seconds():
    md = SAMPLE_SLO + "\n### Health\n\n| Dim | Target | Pages on |\n|---|---|---|\n| Latency p95 | ≤ 200ms | > 1s |\n"
    report = asc.parse_slo_doc(md)
    health = next(e for e in report.entries if e.workflow == "Health")
    assert health.target_latency_p95_s == 0.2
    assert health.page_threshold_latency_p95_s == 1.0


def test_parse_empty_doc_flags_error():
    report = asc.parse_slo_doc("# heading\n\nno workflows\n")
    assert not report.parsed_ok


def test_parse_real_slo_doc():
    report = asc.parse_slo_doc(asc.SLO_DOC.read_text(encoding="utf-8"))
    assert report.parsed_ok
    assert len(report.entries) >= 5, f"expected ≥5 workflow entries from real doc, got {len(report.entries)}"


# ── Conformance stub ─────────────────────────────────────────────────────────
def test_conformance_stub_returns_unknown_for_every_entry():
    entries = [asc.SLOEntry(workflow="x"), asc.SLOEntry(workflow="y")]
    out = asc.compute_conformance_stub(entries)
    assert out == {"x": "unknown", "y": "unknown"}


# ── State writer ─────────────────────────────────────────────────────────────
def test_write_state_file_emits_skeleton_marker(tmp_path):
    out = tmp_path / "slo-status.json"
    asc.write_state_file(out, {"workflow_a": "unknown"})
    doc = json.loads(out.read_text())
    assert doc["skeleton"] is True
    assert doc["conformance"] == {"workflow_a": "unknown"}


def test_write_state_file_creates_parent_dirs(tmp_path):
    out = tmp_path / "deeply" / "nested" / "slo-status.json"
    asc.write_state_file(out, {})
    assert out.exists()

"""Tests for scripts/audit_no_executecommand.py.

Born from the 2026-05-16 finding: vault-health-report.json silently failed for
~5 weeks because its receipt-audit node was an `executeCommand` not migrated
during P1.5 to the HTTP-runner pattern.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_no_executecommand as ane  # noqa: E402


# ── Detection ─────────────────────────────────────────────────────────────────
def test_finds_executecommand_node(tmp_path):
    wf = tmp_path / "evil.json"
    wf.write_text(json.dumps({
        "nodes": [
            {"id": "1", "name": "Run Script", "type": "n8n-nodes-base.executeCommand"},
            {"id": "2", "name": "OK", "type": "n8n-nodes-base.httpRequest"},
        ]
    }))
    hits = ane.find_executecommand_nodes(wf)
    assert len(hits) == 1
    assert hits[0]["name"] == "Run Script"


def test_no_findings_when_only_httprequest(tmp_path):
    wf = tmp_path / "clean.json"
    wf.write_text(json.dumps({
        "nodes": [
            {"id": "1", "name": "POST", "type": "n8n-nodes-base.httpRequest"},
        ]
    }))
    assert ane.find_executecommand_nodes(wf) == []


def test_handles_unparseable_json(tmp_path):
    wf = tmp_path / "broken.json"
    wf.write_text("{not valid")
    # Should return empty list, not raise (other audits flag parse failures)
    assert ane.find_executecommand_nodes(wf) == []


def test_handles_missing_nodes_key(tmp_path):
    wf = tmp_path / "noNodes.json"
    wf.write_text(json.dumps({"name": "x"}))
    assert ane.find_executecommand_nodes(wf) == []


# ── Scope ─────────────────────────────────────────────────────────────────────
def test_workflow_files_excludes_quarantine_and_archive():
    files = ane.workflow_files()
    for f in files:
        assert "quarantine" not in f.parts
        assert "archive" not in f.parts


# ── Real repo state ───────────────────────────────────────────────────────────
def test_real_active_workflows_post_remediation():
    """As of the 2026-05-16 commit landing this audit, vault-health-report still
    contains the executeCommand node — it's the known-broken workflow tracked
    in NEXT-STEPS.md for post-soak fix.

    This test pins the EXPECTED leaky filename so a future remediation will
    update this test by removing it from the expected set — at which point the
    audit MUST be clean.
    """
    expected_leaky = {"vault-health-report.json"}
    actual_leaky = set()
    for f in ane.workflow_files():
        if ane.find_executecommand_nodes(f):
            actual_leaky.add(f.name)
    assert actual_leaky == expected_leaky, (
        f"Expected exactly {expected_leaky} to contain executeCommand; got {actual_leaky}. "
        f"If you fixed vault-health-report.json: also update this test to assert empty."
    )

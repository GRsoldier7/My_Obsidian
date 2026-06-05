"""Tests for scripts/audit_planning_docs.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_planning_docs as apd  # noqa: E402


def test_real_repo_passes_with_orphans_allowed():
    """The real repo has historical specs from before the audit existed; allow
    orphans during the rollout window. New specs added under ADR-0007+ should
    pass even without --allow-orphans."""
    issues = apd.findings()
    # Filter to non-orphan issues — those are the hard blockers
    non_orphan = [i for i in issues if not i.startswith("orphan ")]
    assert non_orphan == [], f"Hard-blocker issues: {non_orphan}"


def test_existing_adrs_discovered():
    adrs = apd._existing_adrs()
    assert "0001" in adrs
    assert "0007" in adrs
    assert "0008" in adrs
    assert "0009" in adrs


def test_references_from_extracts_all_kinds():
    text = """
    See [ADR-0007](../adr/0007-master-plan-v2.md) and ADR-0008.
    Also docs/adr/0009-threaded-tasks.md and
    docs/superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md.
    Phase plan at docs/superpowers/phases/2026-05-13-agent-orch-lxc-recon.md.
    """
    refs = apd._references_from(text)
    assert "0007" in refs["adr_ids"]
    assert "0008" in refs["adr_ids"]
    assert "0009" in refs["adr_links"]
    assert "2026-05-13-comms-layer-lxc-desktop-vps-spec.md" in refs["spec_links"]
    assert "2026-05-13-agent-orch-lxc-recon.md" in refs["phase_links"]


def test_status_line_is_required(tmp_path, monkeypatch):
    """A synthetic ADR file with no Status line should produce a finding."""
    fake_adr_dir = tmp_path / "adr"
    fake_adr_dir.mkdir()
    (fake_adr_dir / "9999-test.md").write_text("# ADR-9999: Test\n\nNo status line.\n")
    monkeypatch.setattr(apd, "ADR_DIR", fake_adr_dir)
    monkeypatch.setattr(apd, "SPEC_DIR", tmp_path / "specs_missing")
    monkeypatch.setattr(apd, "PHASE_DIR", tmp_path / "phases_missing")
    monkeypatch.setattr(apd, "RUNBOOK_DIR", tmp_path / "runbooks_missing")
    issues = apd.findings()
    assert any("missing **Status:**" in i for i in issues)


def test_invalid_status_flagged(tmp_path, monkeypatch):
    fake_adr_dir = tmp_path / "adr"
    fake_adr_dir.mkdir()
    (fake_adr_dir / "9999-test.md").write_text("# ADR-9999\n\n**Status:** Maybe\n\nBody.\n")
    monkeypatch.setattr(apd, "ADR_DIR", fake_adr_dir)
    monkeypatch.setattr(apd, "SPEC_DIR", tmp_path / "specs_missing")
    monkeypatch.setattr(apd, "PHASE_DIR", tmp_path / "phases_missing")
    monkeypatch.setattr(apd, "RUNBOOK_DIR", tmp_path / "runbooks_missing")
    issues = apd.findings()
    assert any("status `Maybe` not in" in i for i in issues)


def test_missing_adr_reference_flagged(tmp_path, monkeypatch):
    fake_adr_dir = tmp_path / "adr"
    fake_adr_dir.mkdir()
    (fake_adr_dir / "9000-real.md").write_text(
        "# ADR-9000\n\n**Status:** Accepted\n\nSee ADR-9001 which doesn't exist.\n"
    )
    monkeypatch.setattr(apd, "ADR_DIR", fake_adr_dir)
    monkeypatch.setattr(apd, "SPEC_DIR", tmp_path / "specs_missing")
    monkeypatch.setattr(apd, "PHASE_DIR", tmp_path / "phases_missing")
    monkeypatch.setattr(apd, "RUNBOOK_DIR", tmp_path / "runbooks_missing")
    issues = apd.findings()
    assert any("references ADR-9001" in i for i in issues)

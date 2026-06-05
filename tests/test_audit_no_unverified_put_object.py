"""Tests for scripts/audit_no_unverified_put_object.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_no_unverified_put_object as anupo  # noqa: E402


# ── Detection ─────────────────────────────────────────────────────────────────
def test_finds_put_object_in_file(tmp_path, monkeypatch):
    fake = tmp_path / "tools"
    fake.mkdir()
    bad = fake / "evil.py"
    bad.write_text("import boto3\ns = boto3.client('s3')\ns.put_object(Bucket='x', Key='y', Body=b'z')\n")
    monkeypatch.setattr(anupo, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(anupo, "_KNOWN_VIOLATORS", {})
    out = anupo.find_violations()
    assert "tools/evil.py" in out
    assert any("put_object" in line for _, line in out["tools/evil.py"])


def test_helper_path_is_excluded(tmp_path, monkeypatch):
    fake = tmp_path / "tools"
    fake.mkdir()
    helper = fake / "s3_verified.py"
    helper.write_text("def put(s3, b, k, body):\n    s3.put_object(Bucket=b, Key=k, Body=body)\n")
    monkeypatch.setattr(anupo, "REPO_ROOT", tmp_path)
    out = anupo.find_violations()
    assert "tools/s3_verified.py" not in out


def test_ignores_non_py_files(tmp_path, monkeypatch):
    fake = tmp_path / "tools"
    fake.mkdir()
    (fake / "notes.md").write_text("s.put_object(Bucket='x', Key='y')")
    monkeypatch.setattr(anupo, "REPO_ROOT", tmp_path)
    out = anupo.find_violations()
    assert out == {}


def test_walks_subdirectories(tmp_path, monkeypatch):
    """services/oho_runner/app.py should be scanned, not just top-level."""
    sub = tmp_path / "services" / "oho_runner"
    sub.mkdir(parents=True)
    (sub / "app.py").write_text("s.put_object(Bucket='x', Key='y')\n")
    monkeypatch.setattr(anupo, "REPO_ROOT", tmp_path)
    out = anupo.find_violations()
    assert "services/oho_runner/app.py" in out


# ── Allowlist behavior ────────────────────────────────────────────────────────
def test_allowlisted_file_does_not_fail_audit(tmp_path, monkeypatch):
    fake = tmp_path / "tools"
    fake.mkdir()
    (fake / "legacy.py").write_text("s.put_object(Bucket='x', Key='y')\n")
    monkeypatch.setattr(anupo, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(anupo, "_KNOWN_VIOLATORS", {"tools/legacy.py": "test allowlist"})
    monkeypatch.setattr(sys, "argv", ["audit_no_unverified_put_object.py"])
    assert anupo.main() == 0


def test_non_allowlisted_file_fails_audit(tmp_path, monkeypatch):
    fake = tmp_path / "tools"
    fake.mkdir()
    (fake / "new.py").write_text("s.put_object(Bucket='x', Key='y')\n")
    monkeypatch.setattr(anupo, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(anupo, "_KNOWN_VIOLATORS", {})
    monkeypatch.setattr(sys, "argv", ["audit_no_unverified_put_object.py"])
    assert anupo.main() == 1


def test_strict_mode_fails_on_allowlisted_files_too(tmp_path, monkeypatch):
    fake = tmp_path / "tools"
    fake.mkdir()
    (fake / "legacy.py").write_text("s.put_object(Bucket='x', Key='y')\n")
    monkeypatch.setattr(anupo, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(anupo, "_KNOWN_VIOLATORS", {"tools/legacy.py": "test"})
    monkeypatch.setattr(sys, "argv", ["audit_no_unverified_put_object.py", "--strict"])
    assert anupo.main() == 1


# ── Real repo: clean pass ─────────────────────────────────────────────────────
def test_real_repo_clean_against_current_allowlist(monkeypatch):
    """The real repo MUST audit-clean against the committed allowlist. If a
    new file gets a put_object without joining the allowlist or migrating to
    s3_verified, this test catches it BEFORE the audit script does in CI."""
    monkeypatch.setattr(sys, "argv", ["audit_no_unverified_put_object.py"])
    assert anupo.main() == 0


def test_allowlist_entries_actually_have_put_object():
    """Every allowlisted file MUST actually contain a put_object call. If a
    file migrated to s3_verified but stayed allowlisted, this test forces an
    allowlist update so the audit stays honest."""
    violations = anupo.find_violations()
    stale = []
    for path in anupo._KNOWN_VIOLATORS:
        if path not in violations:
            stale.append(path)
    assert not stale, (
        f"Stale allowlist entries (file no longer contains put_object): {stale}. "
        f"Remove from _KNOWN_VIOLATORS in scripts/audit_no_unverified_put_object.py."
    )


# ── --list-allowlist mode ─────────────────────────────────────────────────────
def test_list_allowlist_mode_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["audit_no_unverified_put_object.py", "--list-allowlist"])
    assert anupo.main() == 0
    out = capsys.readouterr().out
    assert "Allowlisted files" in out

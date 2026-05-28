"""Tests for scripts/audit_egress_classifier_wired.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_egress_classifier_wired as aec  # noqa: E402


# ── Detection: guarded vs unguarded ───────────────────────────────────────────
GUARDED_SOURCE = """
import egress_guard

def extract(client, prompt):
    allowed, verdict = egress_guard.guard_for_peer(peer="to_openrouter", text=prompt)
    if not allowed:
        return None
    return client.chat.completions.create(model="x", messages=[])
"""

UNGUARDED_SOURCE = """
def extract(client, prompt):
    return client.chat.completions.create(model="x", messages=[])
"""

GUARD_AFTER_CALL_SOURCE = """
import egress_guard

def extract(client, prompt):
    resp = client.chat.completions.create(model="x", messages=[])
    allowed, _ = egress_guard.guard_for_peer(peer="to_openrouter", text=prompt)
    return resp
"""

GUARD_BARE_IMPORT_SOURCE = """
from tools.egress_guard import guard_for_peer

def extract(client, prompt):
    allowed, verdict = guard_for_peer(peer="to_openrouter", text=prompt)
    if not allowed:
        return None
    return client.chat.completions.create(model="x", messages=[])
"""

MODULE_SCOPE_CALL_SOURCE = """
import openai
client = openai.OpenAI()
resp = client.chat.completions.create(model="x", messages=[])
"""


def _write(tmp_path, subdir, name, src):
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(src)


def test_guarded_chat_call_passes(tmp_path, monkeypatch):
    _write(tmp_path, "tools", "ok.py", GUARDED_SOURCE)
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    assert aec.find_unguarded_chat_calls() == {}


def test_unguarded_chat_call_fails(tmp_path, monkeypatch):
    _write(tmp_path, "tools", "bad.py", UNGUARDED_SOURCE)
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    findings = aec.find_unguarded_chat_calls()
    assert "tools/bad.py" in findings
    assert "no guard_for_peer" in findings["tools/bad.py"][0][1]


def test_guard_after_chat_call_fails(tmp_path, monkeypatch):
    """Guard must come BEFORE the chat call — guard after = no protection."""
    _write(tmp_path, "tools", "late.py", GUARD_AFTER_CALL_SOURCE)
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    findings = aec.find_unguarded_chat_calls()
    assert "tools/late.py" in findings


def test_guard_imported_bare_name_passes(tmp_path, monkeypatch):
    """`from tools.egress_guard import guard_for_peer` then bare `guard_for_peer(...)`
    is also a valid wiring."""
    _write(tmp_path, "tools", "bare.py", GUARD_BARE_IMPORT_SOURCE)
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    assert aec.find_unguarded_chat_calls() == {}


def test_module_scope_chat_call_fails(tmp_path, monkeypatch):
    """LLM calls at module scope execute at import time — never safe.
    The audit must catch these even though there's no enclosing function."""
    _write(tmp_path, "tools", "modscope.py", MODULE_SCOPE_CALL_SOURCE)
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    findings = aec.find_unguarded_chat_calls()
    assert "tools/modscope.py" in findings
    assert "module-scope" in findings["tools/modscope.py"][0][1]


def test_guard_module_itself_is_exempt(tmp_path, monkeypatch):
    """tools/egress_guard.py is the guard implementation — exempt from scan
    so future helpers landing in it don't trip the audit."""
    src = "def foo(client):\n    return client.chat.completions.create(model='x')\n"
    _write(tmp_path, "tools", "egress_guard.py", src)
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    assert aec.find_unguarded_chat_calls() == {}


def test_ignores_non_py_files(tmp_path, monkeypatch):
    _write(tmp_path, "tools", "notes.md", "client.chat.completions.create(model='x')")
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    assert aec.find_unguarded_chat_calls() == {}


def test_walks_subdirectories(tmp_path, monkeypatch):
    _write(tmp_path, "services/oho_runner", "app.py", UNGUARDED_SOURCE)
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    findings = aec.find_unguarded_chat_calls()
    assert "services/oho_runner/app.py" in findings


# ── Allowlist behavior ────────────────────────────────────────────────────────
def test_allowlisted_file_does_not_fail_audit(tmp_path, monkeypatch):
    _write(tmp_path, "tools", "legacy.py", UNGUARDED_SOURCE)
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(aec, "_KNOWN_UNGUARDED", {"tools/legacy.py": "test allowlist"})
    monkeypatch.setattr(sys, "argv", ["audit_egress_classifier_wired.py"])
    assert aec.main() == 0


def test_strict_mode_fails_on_allowlisted_files_too(tmp_path, monkeypatch):
    _write(tmp_path, "tools", "legacy.py", UNGUARDED_SOURCE)
    monkeypatch.setattr(aec, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(aec, "_KNOWN_UNGUARDED", {"tools/legacy.py": "test"})
    monkeypatch.setattr(sys, "argv", ["audit_egress_classifier_wired.py", "--strict"])
    assert aec.main() == 1


# ── Real repo: clean pass ─────────────────────────────────────────────────────
def test_real_repo_clean(monkeypatch):
    """The real repo MUST audit-clean. ADR-0008's contract is LIVE-ENFORCED
    via tools/process_brain_dump.py:_chat_with_fallback; if a new file gets a
    chat call without a guard, this test catches it BEFORE CI."""
    monkeypatch.setattr(sys, "argv", ["audit_egress_classifier_wired.py"])
    assert aec.main() == 0


def test_real_repo_has_at_least_one_chat_call():
    """Sanity: process_brain_dump.py contains the production chat call. If
    this count drops to zero, either OpenRouter integration got ripped out
    (and this audit can also go) or the AST detection broke."""
    assert aec._count_chat_calls() >= 1


# ── --list-allowlist mode ─────────────────────────────────────────────────────
def test_list_allowlist_mode_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["audit_egress_classifier_wired.py", "--list-allowlist"])
    assert aec.main() == 0
    out = capsys.readouterr().out
    assert "Guard module" in out

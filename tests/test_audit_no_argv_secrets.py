"""Tests for scripts/audit_no_argv_secrets.py — Codex P0 #2 follow-up."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_no_argv_secrets as anas  # noqa: E402


# ── R1 shell argv detection ──────────────────────────────────────────────────
def test_r1_detects_bearer_token_in_curl_argv(tmp_path):
    sh = tmp_path / "evil.sh"
    sh.write_text(
        '#!/bin/bash\n'
        'curl -X POST http://api -H "Authorization: Bearer $OHO_RUNNER_TOKEN" -d "{}"\n'
    )
    findings = anas._scan_shell(sh, {"OHO_RUNNER_TOKEN"})
    assert len(findings) == 1
    assert findings[0].rule == "R1"


def test_r1_detects_n8n_api_key_in_curl_argv(tmp_path):
    sh = tmp_path / "evil.sh"
    sh.write_text('curl -H "X-N8N-API-KEY: $N8N_API_KEY" http://api\n')
    findings = anas._scan_shell(sh, {"N8N_API_KEY"})
    assert len(findings) == 1


def test_r1_detects_brace_form(tmp_path):
    sh = tmp_path / "evil.sh"
    sh.write_text('curl -H "Authorization: Bearer ${TOKEN}" http://api\n')
    findings = anas._scan_shell(sh, {"TOKEN"})
    assert len(findings) == 1


def test_r1_no_finding_when_secret_var_not_in_set(tmp_path):
    sh = tmp_path / "ok.sh"
    sh.write_text('curl -H "Authorization: Bearer $UNRELATED_VAR" http://api\n')
    findings = anas._scan_shell(sh, {"OHO_RUNNER_TOKEN"})  # unrelated var not in set
    assert findings == []


def test_r1_redacts_var_name_in_snippet(tmp_path):
    sh = tmp_path / "evil.sh"
    sh.write_text('curl -H "Authorization: Bearer $SECRET_KEY" http://api\n')
    findings = anas._scan_shell(sh, {"SECRET_KEY"})
    assert findings
    assert "$SECRET_KEY" not in findings[0].snippet
    assert "<REDACTED>" in findings[0].snippet


def test_r1_detects_curl_data_payload(tmp_path):
    sh = tmp_path / "evil.sh"
    # Real-world pattern: single-quoted outer + JSON inside, OR key=value.
    sh.write_text('curl -d "token=$OHO_RUNNER_TOKEN&kind=test" http://api\n')
    findings = anas._scan_shell(sh, {"OHO_RUNNER_TOKEN"})
    assert findings


def test_r1_catches_real_setup_n8n_sh_pattern():
    """Pin the audit against the real Codex P0 #2 finding: setup-n8n.sh:84
    passes N8N_API_KEY in curl -H argv. Audit must catch it; Makefile target
    allowlists this file until the post-soak refactor lands."""
    findings = anas.scan_file(REPO_ROOT / "scripts" / "setup-n8n.sh", {"N8N_API_KEY"})
    assert any(f.rule == "R1" for f in findings), (
        "audit_no_argv_secrets must catch setup-n8n.sh — otherwise it's not protecting "
        "against the regression class Codex flagged on 2026-05-16."
    )


# ── R2 Python subprocess detection ───────────────────────────────────────────
def test_r2_detects_bearer_in_subprocess_run(tmp_path):
    py = tmp_path / "evil.py"
    py.write_text(
        'import subprocess\n'
        'subprocess.run(["curl", "-H", f"Authorization: Bearer {token}", url], check=True)\n'
    )
    findings = anas._scan_python(py)
    assert len(findings) == 1
    assert findings[0].rule == "R2"


def test_r2_detects_x_n8n_api_key_in_subprocess(tmp_path):
    py = tmp_path / "evil.py"
    py.write_text(
        'import subprocess\n'
        'subprocess.run(["curl", "-H", "X-N8N-API-KEY: abc"], check=True)\n'
    )
    findings = anas._scan_python(py)
    assert len(findings) == 1


def test_r2_no_finding_when_no_argv_token(tmp_path):
    py = tmp_path / "ok.py"
    py.write_text(
        'import subprocess\n'
        'subprocess.run(["echo", "hello"], check=True)\n'
    )
    findings = anas._scan_python(py)
    assert findings == []


# ── Scope ─────────────────────────────────────────────────────────────────────
def test_target_files_includes_scripts_and_services():
    files = anas._target_files()
    suffixes = {f.suffix for f in files}
    assert ".sh" in suffixes or ".py" in suffixes


def test_target_files_excludes_self():
    self_path = (SCRIPTS_DIR / "audit_no_argv_secrets.py").resolve()
    files = anas._target_files()
    assert self_path not in (f.resolve() for f in files)


# ── Allowlist + env-var override ─────────────────────────────────────────────
def test_secret_vars_default_contains_known_secrets():
    vars = anas.secret_vars()
    assert "N8N_API_KEY" in vars
    assert "OHO_RUNNER_TOKEN" in vars
    assert "OPENROUTER_API_KEY" in vars
    assert "TELEGRAM_BOT_TOKEN" in vars


def test_secret_vars_env_extension(monkeypatch):
    monkeypatch.setenv("OHO_SECRET_VARS", "FOO_KEY,BAR_TOKEN")
    vars = anas.secret_vars()
    assert "FOO_KEY" in vars
    assert "BAR_TOKEN" in vars
    assert "N8N_API_KEY" in vars  # defaults still present

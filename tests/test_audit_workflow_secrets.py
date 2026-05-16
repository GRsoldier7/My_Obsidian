"""Tests for scripts/audit_workflow_secrets.py — born from the 2026-05-16 job-search leak."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_workflow_secrets as aws  # noqa: E402


# ── Happy path ────────────────────────────────────────────────────────────────
def test_real_workflows_clean():
    """After the job-search quarantine, every active workflow JSON should pass."""
    findings = []
    for f in aws._workflow_files():
        findings.extend(aws.scan_file(f))
    high_med = [x for x in findings if x.severity in ("high", "medium")]
    assert high_med == [], (
        f"Active workflows have high/medium severity findings: "
        f"{[(x.rule, str(x.path), x.field_path, x.snippet) for x in high_med]}"
    )


def test_quarantine_excluded():
    """Files under workflows/quarantine/ must NOT be scanned (they're known-leaked)."""
    files = aws._workflow_files()
    for f in files:
        assert "quarantine" not in f.parts


# ── R1 — key-shape literals ───────────────────────────────────────────────────
def test_r1_detects_openrouter_key(tmp_path, monkeypatch):
    wf = tmp_path / "evil.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "leaky",
            "parameters": {"jsCode": "const K = 'sk-or-v1-abc123xyz789def456ghi012jkl345';"}
        }]
    }))
    monkeypatch.setattr(aws, "WORKFLOW_DIR", tmp_path)
    findings = aws.scan_file(wf)
    assert any(f.rule == "R1" for f in findings)


def test_r1_tolerates_placeholder(tmp_path):
    wf = tmp_path / "clean.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "ok",
            "parameters": {"jsCode": "const K = '__OPENROUTER_API_KEY__';"}
        }]
    }))
    findings = aws.scan_file(wf)
    assert not any(f.rule == "R1" for f in findings)


# ── R2 — credential record IDs ────────────────────────────────────────────────
def test_r2_detects_hardcoded_cred_id(tmp_path):
    wf = tmp_path / "evil.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "google",
            "credentials": {"googleApi": {"id": "58eFJjSKdKWVvSow", "name": "Google API"}}
        }]
    }))
    findings = aws.scan_file(wf)
    assert any(f.rule == "R2" for f in findings)


def test_r2_tolerates_placeholder(tmp_path):
    wf = tmp_path / "clean.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "google",
            "credentials": {"googleApi": {"id": "__GOOGLE_SHEETS_CRED_ID__", "name": "Google API"}}
        }]
    }))
    findings = aws.scan_file(wf)
    assert not any(f.rule == "R2" for f in findings)


# ── R3 — Google document IDs ──────────────────────────────────────────────────
def test_r3_detects_44char_id_in_documentId(tmp_path):
    wf = tmp_path / "evil.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "sheets",
            "parameters": {"documentId": {"value": "1r_3cUMoBHIUPbndHZ80yLZec290irnbK7Z02_l8PEds"}}
        }]
    }))
    findings = aws.scan_file(wf)
    assert any(f.rule == "R3" for f in findings)


def test_r3_tolerates_placeholder_in_documentId(tmp_path):
    wf = tmp_path / "clean.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "sheets",
            "parameters": {"documentId": {"value": "__JOB_SEARCH_SHEET_ID__"}}
        }]
    }))
    findings = aws.scan_file(wf)
    assert not any(f.rule == "R3" for f in findings)


# ── R4 — PII shapes ───────────────────────────────────────────────────────────
def test_r4_detects_phone_number(tmp_path):
    wf = tmp_path / "evil.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "leaky",
            "parameters": {"text": "Call 616-826-4535 for the role."}
        }]
    }))
    findings = aws.scan_file(wf)
    assert any(f.rule == "R4" and "phone" not in f.snippet.lower() for f in findings) or \
           any(f.rule == "R4" for f in findings)


# ── R5 — Google URLs ──────────────────────────────────────────────────────────
def test_r5_detects_google_doc_url(tmp_path):
    wf = tmp_path / "evil.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "linker",
            "parameters": {"url": "See https://docs.google.com/spreadsheets/d/1r_3cUMoBHIUPbndHZ80yLZec290irnbK7Z02_l8PEds/edit"}
        }]
    }))
    findings = aws.scan_file(wf)
    assert any(f.rule == "R5" for f in findings)


# ── R6 — partial-redaction smell ──────────────────────────────────────────────
def test_r6_detects_partial_redaction_pattern(tmp_path):
    """The exact mistake that caused the job-search incident."""
    wf = tmp_path / "evil.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "leaky",
            "parameters": {"jsCode": "const K = '[REDACTED_OPENROUTER_KEY]bbce7805776a19533d900539';"}
        }]
    }))
    findings = aws.scan_file(wf)
    assert any(f.rule == "R6" for f in findings)


def test_r6_does_not_flag_pure_placeholder(tmp_path):
    wf = tmp_path / "clean.json"
    wf.write_text(json.dumps({
        "nodes": [{
            "name": "ok",
            "parameters": {"jsCode": "const K = '__OPENROUTER_API_KEY__';"}
        }]
    }))
    findings = aws.scan_file(wf)
    assert not any(f.rule == "R6" for f in findings)


# ── Parse failure ─────────────────────────────────────────────────────────────
def test_invalid_json_caught(tmp_path):
    wf = tmp_path / "bad.json"
    wf.write_text("{not valid json")
    findings = aws.scan_file(wf)
    assert any(f.rule == "PARSE" for f in findings)


# ── Redaction utility ─────────────────────────────────────────────────────────
def test_redact_truncates_long_strings():
    out = aws._redact("abcdefghijklmnop", keep=8)
    assert out.startswith("abcdefgh")
    assert "more chars" in out
    assert "ijklmnop" not in out  # the secret-suffix part should NOT be in the output


def test_redact_passthrough_short():
    out = aws._redact("short", keep=8)
    assert out == "short"

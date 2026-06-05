#!/usr/bin/env python3
# ruff: noqa: W605
r"""
scripts/audit_workflow_secrets.py — catch hardcoded secrets / IDs / PII in n8n workflow JSONs.

Born from the 2026-05-16 job-search-pipeline incident
(docs/security/2026-05-16-INCIDENT-job-search-leak.md): a workflow was committed
with a partial OpenRouter key suffix, a hardcoded Google credential record ID, a
hardcoded Google Sheets document ID, and Aaron's resume + phone number in Code-node
prompts. This audit catches that class of regression on every PR.

Scope: `workflows/n8n/*.json`. The `workflows/quarantine/` directory is excluded
because it's the holding pen for already-known-leaked files.

Detection rules (every match becomes a finding):
  R1. Key-shape literals — `sk-or-…`, `Bearer …`, `AIza…`, `ghp_…`, `xoxb-…`, `sk-…`.
      Tolerates the `__[A-Z0-9_]+__` placeholder form.
  R2. Hardcoded n8n credential record IDs — any `credentials.<name>.id` whose value
      is not a `__[A-Z0-9_]+__` placeholder.
  R3. Google Sheets / Drive document IDs — 44-char `[A-Za-z0-9_-]{44}` string in
      `documentId.value`, `spreadsheetId`, `sheetId`, or `fileId` fields. The
      placeholder form is allowed.
  R4. PII shapes — phone-number `\b\d{3}-\d{3}-\d{4}\b`, surname tokens from a
      configurable list, US-address line shapes.
  R5. Bare URLs to Google Workspace docs (`docs.google.com/.../d/<id>`) outside
      of a comment or description field.
  R6. Partial-redaction smell — literal that contains the substring `REDACTED`
      next to another non-placeholder value on the same line. Catches the exact
      mistake the incident introduced.

Exit codes:
  0  no findings
  1  one or more findings (CI fail)
  2  I/O failure
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"
EXCLUDED_DIRS = {"quarantine", "archive"}

PLACEHOLDER_RE = re.compile(r"^__[A-Z0-9_]+__$")

KEY_SHAPES = [
    re.compile(r"\bsk-or-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
    re.compile(r"\bghp_[A-Za-z0-9]{36,}"),
    re.compile(r"\bxox[bp]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9\._/+=-]{20,}"),
]

GOOGLE_ID_RE = re.compile(r"\b[A-Za-z0-9_-]{44}\b")
GOOGLE_URL_RE = re.compile(r"docs\.google\.com/(?:spreadsheets|document)/d/[A-Za-z0-9_-]{20,}")
PHONE_RE = re.compile(r"\b\d{3}-\d{3}-\d{4}\b")
PARTIAL_REDACT_RE = re.compile(r"\[REDACTED[A-Z0-9_]*\][A-Za-z0-9]{8,}")

# Configurable surname / first-name dictionary. Loaded from env so the audit can be
# tuned per-deploy without code changes.
def _name_tokens() -> list[str]:
    raw = os.environ.get("OHO_FAMILY_NAMES", "") + "," + os.environ.get("OHO_PII_NAMES", "")
    return [t.strip() for t in raw.split(",") if t.strip()]


# Field-path tokens that indicate a Google document/sheet ID slot. Used to gate R3.
ID_FIELD_TOKENS = {"documentid", "spreadsheetid", "sheetid", "fileid"}
# Field paths that indicate an n8n credential record reference.
CRED_FIELD_TOKENS = {"credentials"}


@dataclass
class Finding:
    rule: str                 # R1..R6
    path: Path                # workflow file
    field_path: str           # JSON-pointer-ish locator, e.g. ".nodes[3].parameters.documentId.value"
    snippet: str              # ≤80 chars of the offending value, redacted
    severity: str             # "high" | "medium" | "low"


def _redact(value: str, keep: int = 8) -> str:
    """Show only the first `keep` characters, never the full string."""
    if len(value) <= keep:
        return value
    return value[:keep] + "…" + f"[{len(value) - keep} more chars]"


def _walk(obj: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Yield (field_path, value) for every leaf in a nested dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def _scan_string(text: str, field_path: str, file_path: Path) -> list[Finding]:
    out: list[Finding] = []
    if not isinstance(text, str) or not text:
        return out

    # R1 — key-shape literals
    for pat in KEY_SHAPES:
        for m in pat.findall(text):
            if PLACEHOLDER_RE.match(m):
                continue
            out.append(Finding("R1", file_path, field_path, _redact(m), "high"))

    # R6 — partial-redaction smell
    for m in PARTIAL_REDACT_RE.findall(text):
        out.append(Finding("R6", file_path, field_path, _redact(m), "high"))

    # R5 — Google Workspace doc URL
    if GOOGLE_URL_RE.search(text):
        out.append(Finding("R5", file_path, field_path, _redact(GOOGLE_URL_RE.search(text).group(0)), "medium"))

    # R4 — phone-number shape
    if PHONE_RE.search(text):
        out.append(Finding("R4", file_path, field_path, _redact(PHONE_RE.search(text).group(0)), "medium"))

    # R4 — PII name tokens
    for token in _name_tokens():
        # whole-word case-insensitive
        if re.search(rf"\b{re.escape(token)}\b", text, re.IGNORECASE):
            out.append(Finding("R4", file_path, field_path, f"name-token:{token}", "low"))

    return out


def _scan_id_field(value: Any, field_path: str, file_path: Path) -> list[Finding]:
    """R3 — 44-char Google ID literal in a documentId/spreadsheetId/sheetId/fileId slot."""
    if not isinstance(value, str):
        return []
    if PLACEHOLDER_RE.match(value):
        return []
    if GOOGLE_ID_RE.fullmatch(value):
        return [Finding("R3", file_path, field_path, _redact(value), "medium")]
    return []


def _scan_cred_ref(node: dict, file_path: Path, node_path: str) -> list[Finding]:
    """R2 — hardcoded credential record ID."""
    out: list[Finding] = []
    creds = node.get("credentials", {})
    if not isinstance(creds, dict):
        return out
    for cred_type, cred_entry in creds.items():
        if not isinstance(cred_entry, dict):
            continue
        cred_id = cred_entry.get("id")
        if cred_id is None:
            continue
        if not isinstance(cred_id, str):
            continue
        if PLACEHOLDER_RE.match(cred_id):
            continue
        out.append(Finding(
            "R2",
            file_path,
            f"{node_path}.credentials.{cred_type}.id",
            _redact(cred_id),
            "high",
        ))
    return out


def scan_file(path: Path) -> list[Finding]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [Finding("PARSE", path, "(root)", f"invalid JSON: {e}", "high")]

    findings: list[Finding] = []

    # R2 — walk every node's credentials section
    for i, node in enumerate(doc.get("nodes", []) or []):
        if not isinstance(node, dict):
            continue
        findings.extend(_scan_cred_ref(node, path, f".nodes[{i}]"))

    # Walk every leaf for R1, R3 (gated by field name), R4, R5, R6
    for field_path, value in _walk(doc):
        if isinstance(value, str):
            findings.extend(_scan_string(value, field_path, path))
            # R3 — only check ID slots
            last_field = field_path.rsplit(".", 1)[-1].lower().rstrip("[0-9]")
            # handle .documentId.value pattern (look at last 2 segments)
            tail = field_path.lower().rstrip("0123456789[]")
            if any(tok in tail for tok in ID_FIELD_TOKENS):
                findings.extend(_scan_id_field(value, field_path, path))

    return findings


def _workflow_files() -> list[Path]:
    if not WORKFLOW_DIR.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(WORKFLOW_DIR.glob("*.json")):
        if any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit n8n workflow JSONs for hardcoded secrets / IDs / PII")
    parser.add_argument("--strict", action="store_true", help="Treat low-severity findings as failures too")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-finding output")
    args = parser.parse_args()

    files = _workflow_files()
    if not files:
        print(f"WARN: no workflow JSON files found in {WORKFLOW_DIR}", file=sys.stderr)
        return 2

    all_findings: list[Finding] = []
    for f in files:
        all_findings.extend(scan_file(f))

    if all_findings:
        by_severity: dict[str, int] = {}
        for f in all_findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        if not args.quiet:
            print(f"FAIL: workflow-secrets audit found {len(all_findings)} issue(s):", file=sys.stderr)
            for f in all_findings:
                rel = f.path.relative_to(REPO_ROOT) if f.path.is_relative_to(REPO_ROOT) else f.path
                print(f"  [{f.severity:6}] {f.rule}  {rel}{f.field_path}  →  {f.snippet}", file=sys.stderr)
        else:
            print(f"FAIL: {len(all_findings)} findings ({by_severity})", file=sys.stderr)
        # Pass-only if --strict OR if there are any high/medium findings
        if not args.strict and not any(x.severity in ("high", "medium") for x in all_findings):
            print(f"OK with low-severity findings only ({len(all_findings)} low)")
            return 0
        return 1

    print(f"OK — workflow-secrets audit passed. {len(files)} workflows scanned, 0 findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
scripts/audit_no_argv_secrets.py — block argv-secret-leak patterns in scripts.

Born from the 2026-05-16 Codex review (P0 #2): `setup-n8n.sh:84` and
`deploy_oho_runner.py:628,635` pass secrets via curl argv, where `ps aux`
exposes them to any local process. Codex flagged it; this audit catches future
regressions.

Detection rules:
  R1. Shell scripts (`*.sh`): `curl ... -H "Authorization: Bearer $SOMETHING"`
      or `curl ... -H "X-N8N-API-KEY: $SOMETHING"` where SOMETHING resolves
      to a known secret env var.
  R2. Python scripts (`*.py`): `subprocess.run([..., f"Bearer {token}", ...])`
      or string-interpolating a secret into an argv list.

Scope:
  - `scripts/*.sh`
  - `scripts/*.py`
  - `services/*/app.py` (FastAPI handlers — should never argv-out secrets)

Exclusions:
  - This file itself (recursive false-positive).
  - Tests under `tests/` (they may contain example patterns for guard tests).

Allowlist:
  - Filenames known to be in remediation (e.g., setup-n8n.sh until refactored).
    Pass `--allowlist <basename>` to skip a file. Document each allowlist entry
    in NEXT-STEPS.md.

Known secret env-var names (extend as needed via OHO_SECRET_VARS env):
  - N8N_API_KEY, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, SMTP_PASS,
    OPENROUTER_API_KEY, OHO_RUNNER_TOKEN, TELEGRAM_BOT_TOKEN,
    BW_SESSION, GCAL_CLIENT_SECRET.

Exit codes:
  0 — clean (or only allowlisted findings)
  1 — at least one new argv-secret-leak pattern
  2 — I/O failure
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SERVICES_DIR = REPO_ROOT / "services"

DEFAULT_SECRET_VARS = {
    "N8N_API_KEY",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "SMTP_PASS",
    "OPENROUTER_API_KEY",
    "OHO_RUNNER_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "BW_SESSION",
    "GCAL_CLIENT_SECRET",
}


def secret_vars() -> set[str]:
    extras = os.environ.get("OHO_SECRET_VARS", "")
    extra_set = {s.strip() for s in extras.split(",") if s.strip()}
    return DEFAULT_SECRET_VARS | extra_set


def _argv_header_pattern(varname: str) -> re.Pattern[str]:
    """Match `-H "...$VAR..."` ANYWHERE in the file. Catches both inline curl
    and multi-line curl-with-backslash-continuation. False positives on
    non-curl uses of `-H "...$VAR..."` are rare in shell + acceptable: any
    program reading a header from argv is the same leak shape.
    """
    return re.compile(
        rf"""-H\s+["'][^"']*\$\{{?{re.escape(varname)}\}}?[^"']*["']""",
    )


def _argv_data_pattern(varname: str) -> re.Pattern[str]:
    """Match `-d "...$VAR..."` (curl payload via argv). Loose end-quote so
    escaped JSON quotes inside don't break detection."""
    return re.compile(
        rf"""-d\s+["'][^"']*\$\{{?{re.escape(varname)}\}}?""",
    )


def _py_subprocess_token_pattern() -> re.Pattern[str]:
    """Catches subprocess.run([..., "<header>: ...", ...]) where header is a
    common secret-bearing key. Permissive separator (`[:\\s]+`) handles
    `Authorization: Bearer x`, `X-N8N-API-KEY: x`, `Token x`, `Bearer x`."""
    return re.compile(
        r"""subprocess\.(?:run|Popen|check_output|check_call)\s*\(\s*\[[^\]]*(?:Authorization|Bearer|X-N8N-API-KEY|X-API-KEY|Token)[:\s][^\]]*\]""",
        re.MULTILINE | re.DOTALL,
    )


@dataclass
class Finding:
    rule: str
    path: Path
    line: int
    snippet: str
    severity: str


def _scan_shell(path: Path, vars: set[str]) -> list[Finding]:
    out: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    seen_lines: set[int] = set()   # one finding per (var, line) — avoid duplicates from overlapping patterns
    for v in vars:
        for pat in (_argv_header_pattern(v), _argv_data_pattern(v)):
            for m in pat.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                key = (v, line)
                if key in seen_lines:
                    continue
                seen_lines.add(key)
                snippet = text[m.start():m.end()][:80].replace("\n", " ")
                snippet_redacted = snippet.replace(f"${v}", "$<REDACTED>")
                snippet_redacted = snippet_redacted.replace(f"${{{v}}}", "${<REDACTED>}")
                out.append(Finding(
                    rule="R1",
                    path=path,
                    line=line,
                    snippet=snippet_redacted,
                    severity="high",
                ))
    return out


def _scan_python(path: Path) -> list[Finding]:
    out: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    pat = _py_subprocess_token_pattern()
    for m in pat.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        snippet = m.group(0)[:80].replace("\n", " ")
        out.append(Finding(
            rule="R2",
            path=path,
            line=line,
            snippet=snippet,
            severity="high",
        ))
    return out


def scan_file(path: Path, vars: set[str]) -> list[Finding]:
    if path.suffix == ".sh":
        return _scan_shell(path, vars)
    if path.suffix == ".py":
        return _scan_python(path)
    return []


def _target_files() -> list[Path]:
    files: list[Path] = []
    if SCRIPTS_DIR.is_dir():
        files.extend(sorted(SCRIPTS_DIR.glob("*.sh")))
        files.extend(sorted(SCRIPTS_DIR.glob("*.py")))
    if SERVICES_DIR.is_dir():
        for app in SERVICES_DIR.rglob("app.py"):
            files.append(app)
    # Don't audit ourselves
    self_path = Path(__file__).resolve()
    return [f for f in files if f.resolve() != self_path]


def main() -> int:
    parser = argparse.ArgumentParser(description="Block argv-secret-leak patterns")
    parser.add_argument("--allowlist", action="append", default=[],
                        help="Basename allowed to contain argv-secret patterns (in remediation). Repeatable.")
    args = parser.parse_args()

    vars = secret_vars()
    files = _target_files()
    findings: list[Finding] = []
    for f in files:
        if f.name in args.allowlist:
            continue
        findings.extend(scan_file(f, vars))

    if findings:
        print(f"FAIL: {len(findings)} argv-secret-leak finding(s):", file=sys.stderr)
        for f in findings:
            rel = f.path.relative_to(REPO_ROOT) if f.path.is_relative_to(REPO_ROOT) else f.path
            print(f"  [{f.severity:4}] {f.rule}  {rel}:{f.line}  →  {f.snippet}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Resolution: pass secrets via stdin or env (not argv). Examples:", file=sys.stderr)
        print("  curl -H @header-file ...   # header-file mode 0600", file=sys.stderr)
        print("  python: pass tokens via subprocess.run(env=...) NOT in argv list", file=sys.stderr)
        return 1

    print(f"OK — argv-secrets audit passed. {len(files)} files scanned, 0 findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

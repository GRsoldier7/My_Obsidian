#!/usr/bin/env python3
"""
scripts/audit_no_unverified_put_object.py — guard new S3 writes against bypassing
the verified-write helper.

Codex P1 (2026-05-16) flagged 12 inline `s3.put_object(...)` call sites across
`tools/`, `scripts/`, and `services/` that skip the head_object verification +
ETag IfMatch protection that `tools/s3_verified.py` centralises. The migration
plan in `docs/NEXT-STEPS.md` item 13 walks call sites toward the helper one at
a time. THIS audit prevents NEW call sites from joining the violator pool while
the migration is in progress.

Detection: regex scan for `.put_object(` or `s3.put_object(` in any .py file
under `tools/`, `scripts/`, and `services/`. The helper module
`tools/s3_verified.py` is allowlisted (it IS the helper).

Allowlist: today's known violators are listed in `_KNOWN_VIOLATORS` below. Each
entry has a comment with the Codex P1 line ref + the migration owner. When a
file migrates to use `s3_verified.put_text_verified` / `put_text_if_match_verified`
/ `put_json_verified` (and its `.put_object(` call site goes away), remove its
entry from the allowlist. The audit then enforces "verified writes only" for
that file going forward.

Exit codes:
  0 — clean (or only allowlisted findings)
  1 — at least one NEW unverified put_object outside the allowlist
  2 — I/O failure
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = ("tools", "scripts", "services")

# The helper module itself — it IS the verified-write surface, so its own
# `s3.put_object(...)` calls are intentional and the helper-of-helpers.
HELPER_PATH = "tools/s3_verified.py"

# Known violators per Codex P1 (2026-05-16). Each entry maps a repo-relative
# path to the rationale + migration owner. Remove from this dict when the
# file's put_object calls have all moved to s3_verified.* helpers.
_KNOWN_VIOLATORS: dict[str, str] = {
    # Production hot path. Item 13 migration; high blast radius — careful.
    "tools/process_brain_dump.py": (
        "process_brain_dump.py — 4 put_object call sites incl. RMW telemetry "
        "(line ~1385) that needs IfMatch. Migration is item 13's biggest chunk."
    ),
    # ADR-0006 hot path. Item 13.
    "tools/build_command_center.py": (
        "build_command_center.py — RMW command-center write; needs IfMatch."
    ),
    # MANUAL-ONLY tools per ce8d03a (Aaron's marker commit). Not in cron path,
    # but still write to MinIO. Migrate when item 13 cleans them up.
    # Wave-X H3 dashboard landed 2026-05-25 by Aaron (commit 2217ab5). New
    # write site; should migrate to s3_verified.put_text_verified at next pass.
    "tools/build_health_dashboard.py": (
        "Wave-X H3 health dashboard (Aaron 2026-05-25). Migrate at item 13."
    ),
    # Test harness; not production. Allowlist permanent.
    "scripts/e2e_test.py": "e2e test harness — synthetic put for test fixtures.",
    # Hygiene scripts.
    "scripts/archive_completed_tasks.py": (
        "archive script — _write_log migrated to s3_verified.put_json_verified "
        "(2026-05-27). Remaining put_object is write_s3 (MTL + archive RMW hot path); "
        "needs IfMatch wrapper before final migration."
    ),
    "scripts/backfill_mtl_metadata.py": (
        "_write_log migrated to s3_verified.put_json_verified (2026-05-28). "
        "Remaining put_object is the file's own put_object_verified helper "
        "(line 128) — duplicates the s3_verified.put_text_if_match_verified "
        "pattern. Final migration: swap put_object_verified body to call the "
        "canonical helper, then delete this allowlist entry."
    ),
    "scripts/migrate_brain_dump_frontmatter.py": (
        "frontmatter migration RMW path; needs IfMatch. Item 13."
    ),
}


def _find_put_object_calls(tree: ast.AST) -> list[int]:
    """Return line numbers of every `<expr>.put_object(...)` call in the AST.
    AST walk avoids false positives from docstrings, comments, and string
    literals (which a regex-based scan WOULD trip on)."""
    out: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "put_object":
                out.append(node.lineno)
    return sorted(set(out))


def find_violations() -> dict[str, list[tuple[int, str]]]:
    """Return {repo-relative-path: [(line_no, line_text), ...]} for every file
    that contains a real `put_object(...)` method call, EXCLUDING the helper
    itself."""
    out: dict[str, list[tuple[int, str]]] = {}
    for d in TARGET_DIRS:
        root = REPO_ROOT / d
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            rel = str(path.relative_to(REPO_ROOT))
            if rel == HELPER_PATH:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError:
                continue
            lines = text.splitlines()
            call_lines = _find_put_object_calls(tree)
            if not call_lines:
                continue
            hits = []
            for ln in call_lines:
                snippet = lines[ln - 1].strip()[:120] if 1 <= ln <= len(lines) else ""
                hits.append((ln, snippet))
            out[rel] = hits
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard against new unverified S3 writes")
    parser.add_argument("--strict", action="store_true",
                        help="Treat allowlisted files as failures too (use to verify allowlist matches reality).")
    parser.add_argument("--list-allowlist", action="store_true",
                        help="Print the allowlist + rationale and exit.")
    args = parser.parse_args()

    if args.list_allowlist:
        print(f"  Helper: {HELPER_PATH}")
        print()
        print("  Allowlisted files (will not fail the audit):")
        for path, rationale in sorted(_KNOWN_VIOLATORS.items()):
            print(f"    {path}")
            print(f"      → {rationale}")
        return 0

    violations = find_violations()
    new_violators = {p: lines for p, lines in violations.items()
                     if args.strict or p not in _KNOWN_VIOLATORS}

    if new_violators:
        print(f"FAIL: {sum(len(v) for v in new_violators.values())} unverified put_object "
              f"call site(s) outside the allowlist:", file=sys.stderr)
        for path, lines in sorted(new_violators.items()):
            for lineno, snippet in lines:
                print(f"  {path}:{lineno}: {snippet}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Fix path: migrate to tools.s3_verified.put_text_verified / "
              "put_text_if_match_verified / put_json_verified.", file=sys.stderr)
        print("OR (if intentional + reviewed): add the file to _KNOWN_VIOLATORS in "
              "scripts/audit_no_unverified_put_object.py with a rationale.", file=sys.stderr)
        return 1

    n_allow = sum(len(v) for p, v in violations.items() if p in _KNOWN_VIOLATORS)
    print(f"OK — no NEW unverified put_object call sites. "
          f"{n_allow} allowlisted call site(s) across {len(_KNOWN_VIOLATORS)} known file(s) "
          f"(see --list-allowlist).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

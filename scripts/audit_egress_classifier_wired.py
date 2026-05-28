#!/usr/bin/env python3
"""
scripts/audit_egress_classifier_wired.py — guard every OpenRouter call site.

ADR-0008 contract: no sensitive payload reaches OpenRouter without privacy
classifier approval. Today's wiring sits inside `_chat_with_fallback`
(`tools/process_brain_dump.py`), which gates the single `chat.completions.create`
call against `egress_guard.guard_for_peer(peer="to_openrouter", ...)`.

This audit prevents regressions: any new file in `tools/`, `scripts/`, or
`services/` that calls `*.chat.completions.create(...)` MUST first invoke
`egress_guard.guard_for_peer(...)` earlier in the same function body. Catches
forgotten guards BEFORE merge.

Detection (AST):
1. Walk every .py file in TARGET_DIRS (excluding `tools/egress_guard.py` itself).
2. Find every Call node whose func resolves to `*.chat.completions.create`.
3. Locate the enclosing FunctionDef / AsyncFunctionDef.
4. Inspect that function's body for a Call to `egress_guard.guard_for_peer`
   (or imported `guard_for_peer`) appearing BEFORE the create-call's lineno.
5. Fail if missing.

Exit codes:
  0 — clean (every chat call site is guarded, or only allowlisted findings)
  1 — at least one unguarded chat call site outside the allowlist
  2 — I/O failure
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = ("tools", "scripts", "services")

# The guard module itself — its job IS to wrap classifier calls; no LLM calls
# happen inside it today, but exempt it from chat-call scanning just in case
# future helpers land here.
GUARD_MODULE_PATH = "tools/egress_guard.py"

# Files that intentionally bypass the guard. Each entry maps a repo-relative
# path to the rationale. Today none are needed — tools/process_brain_dump.py
# (the only LLM caller) is already wired. New entries require an ADR amendment.
_KNOWN_UNGUARDED: dict[str, str] = {}


def _is_chat_completions_create(node: ast.AST) -> bool:
    """True if node is a Call whose func ends in `.chat.completions.create`.

    Matches `client.chat.completions.create(...)`, `self.client.chat.completions.create(...)`,
    `openai_client.chat.completions.create(...)`, etc. AST walk over Attribute
    chains, not regex — avoids docstring / string-literal false positives.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "create":
        return False
    inner = func.value
    if not isinstance(inner, ast.Attribute) or inner.attr != "completions":
        return False
    chat = inner.value
    if not isinstance(chat, ast.Attribute) or chat.attr != "chat":
        return False
    return True


def _is_guard_call(node: ast.AST) -> bool:
    """True if node is a Call to `egress_guard.guard_for_peer` or bare
    `guard_for_peer` (after `from tools.egress_guard import guard_for_peer`)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    # `egress_guard.guard_for_peer(...)`
    if isinstance(func, ast.Attribute) and func.attr == "guard_for_peer":
        return True
    # `guard_for_peer(...)` — imported by name
    if isinstance(func, ast.Name) and func.id == "guard_for_peer":
        return True
    return False


def _enclosing_function(tree: ast.AST, target_lineno: int) -> ast.AST | None:
    """Return the smallest FunctionDef/AsyncFunctionDef whose body contains
    `target_lineno`. Returns None if the call lives at module scope (which
    itself is a violation — module-scope LLM calls execute at import time)."""
    candidate: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", None) or start
            if start <= target_lineno <= end:
                if candidate is None:
                    candidate = node
                else:
                    cand_start = candidate.lineno
                    cand_end = getattr(candidate, "end_lineno", None) or cand_start
                    if (end - start) < (cand_end - cand_start):
                        candidate = node
    return candidate


def _function_has_guard_before(func_node: ast.AST, target_lineno: int) -> bool:
    """True if the function body contains a guard_for_peer call with lineno
    strictly less than `target_lineno`."""
    for sub in ast.walk(func_node):
        if _is_guard_call(sub) and sub.lineno < target_lineno:
            return True
    return False


def find_unguarded_chat_calls() -> dict[str, list[tuple[int, str]]]:
    """Return {repo-rel-path: [(lineno, reason), ...]} for every chat call
    site missing a preceding guard. Excludes the guard module itself."""
    out: dict[str, list[tuple[int, str]]] = {}
    for d in TARGET_DIRS:
        root = REPO_ROOT / d
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            rel = str(path.relative_to(REPO_ROOT))
            if rel == GUARD_MODULE_PATH:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError:
                continue
            findings: list[tuple[int, str]] = []
            for node in ast.walk(tree):
                if not _is_chat_completions_create(node):
                    continue
                func = _enclosing_function(tree, node.lineno)
                if func is None:
                    findings.append((node.lineno, "module-scope LLM call (no enclosing function)"))
                    continue
                if not _function_has_guard_before(func, node.lineno):
                    fname = getattr(func, "name", "<lambda>")
                    findings.append((node.lineno, f"no guard_for_peer in `{fname}` before this call"))
            if findings:
                out[rel] = findings
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard against unguarded OpenRouter calls")
    parser.add_argument("--strict", action="store_true",
                        help="Treat allowlisted files as failures too.")
    parser.add_argument("--list-allowlist", action="store_true",
                        help="Print the allowlist and exit.")
    args = parser.parse_args()

    if args.list_allowlist:
        print(f"  Guard module (exempt from chat-call scan): {GUARD_MODULE_PATH}")
        print()
        if _KNOWN_UNGUARDED:
            print("  Allowlisted unguarded files (will not fail the audit):")
            for path, rationale in sorted(_KNOWN_UNGUARDED.items()):
                print(f"    {path}")
                print(f"      → {rationale}")
        else:
            print("  No allowlisted unguarded files — every chat call must have a guard.")
        return 0

    findings = find_unguarded_chat_calls()
    new = {p: lines for p, lines in findings.items()
           if args.strict or p not in _KNOWN_UNGUARDED}

    if new:
        n = sum(len(v) for v in new.values())
        print(f"FAIL: {n} unguarded chat.completions.create call site(s):", file=sys.stderr)
        for path, lines in sorted(new.items()):
            for lineno, reason in lines:
                print(f"  {path}:{lineno}: {reason}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Fix: precede the chat.completions.create call with", file=sys.stderr)
        print("  allowed, verdict = egress_guard.guard_for_peer(peer=\"to_openrouter\", text=..., fields=...)", file=sys.stderr)
        print("  if not allowed:", file=sys.stderr)
        print("      return None  # or whatever your caller treats as 'AI unavailable'", file=sys.stderr)
        print("See tools/process_brain_dump.py:_chat_with_fallback for the canonical pattern.", file=sys.stderr)
        return 1

    n_allow = sum(len(findings.get(p, [])) for p in _KNOWN_UNGUARDED)
    total_calls = _count_chat_calls()
    print(f"OK — every chat.completions.create call is guarded. "
          f"{total_calls} chat call site(s) across {len(TARGET_DIRS)} target dir(s); "
          f"{n_allow} allowlisted exception(s).")
    return 0


def _count_chat_calls() -> int:
    """Total count of chat.completions.create call sites across the repo
    (guarded or not), excluding the guard module itself. Used for the OK
    summary line so operators can see at a glance how many LLM call sites
    exist."""
    total = 0
    for d in TARGET_DIRS:
        root = REPO_ROOT / d
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            rel = str(path.relative_to(REPO_ROOT))
            if rel == GUARD_MODULE_PATH:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if _is_chat_completions_create(node):
                    total += 1
    return total


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Fail deploys if any `n8n-nodes-base.emailSend` node is misconfigured.

Background (verified live 2026-04-25 via execution probe):
    On n8n 2.13.4 the `emailSend@2` node has TWO related bugs that cause
    silent blank-email delivery:

      1. `options.emailFormat == "both"` drops the HTML body entirely.
         13.6 kB upstream HTML produced 364–678 B SMTP envelopes.
      2. `options.emailFormat` (any value) is IGNORED — the node's runtime
         schema reads `emailFormat` ONLY from the parameters root, not from
         options. When emailFormat is nested under options, the node falls
         through to its silent-default behavior (text-only, empty body).

    Verified fix: set `parameters.emailFormat = "html"` at the TOP LEVEL of
    the node's parameters (sibling of `html`, NOT under `options`). With
    this shape, the same morning-briefing produced messageSize=15493 — a
    real, deliverable HTML email.

Rules enforced (per workflows/n8n/*.json):

  1. Every emailSend node MUST set `parameters.emailFormat = "html"`
     at the top level (not under options) — UNLESS its `typeVersion >= 2.1`,
     which is a forward-compat path tracked as a followup.
  2. `emailFormat` is FORBIDDEN inside `parameters.options` (the v2 bug
     surface). If found there, the audit fails.
  3. Every emailSend node with `emailFormat == "html"` MUST have a
     non-empty `parameters.html` field.
  4. `emailFormat == "both"` is a hard fail on `typeVersion < 2.1`.
  5. `emailFormat` may be omitted entirely if the node has only a `text`
     field populated (text-only digest pattern, e.g. brain-dump-processor).

Exits non-zero on any violation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"

EMAIL_NODE_TYPE = "n8n-nodes-base.emailSend"


def _type_version_ge(node: dict, target: float) -> bool:
    raw = node.get("typeVersion")
    try:
        return float(raw) >= target
    except (TypeError, ValueError):
        return False


def audit_workflow(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        wf = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON ({exc})"]

    for node in wf.get("nodes", []) or []:
        if node.get("type") != EMAIL_NODE_TYPE:
            continue
        name = node.get("name", "<unnamed>")
        label = f"{path.name}:{name}"
        params = node.get("parameters", {}) or {}
        opts = params.get("options", {}) or {}
        html = params.get("html")
        text = params.get("text")
        is_v2_1_plus = _type_version_ge(node, 2.1)

        # Rule 2: emailFormat must NOT live under options on emailSend@2 —
        # n8n's v2 schema ignores it there. Caught the original blank-email bug.
        if "emailFormat" in opts and not is_v2_1_plus:
            issues.append(
                f"{label} emailFormat is nested under 'options' — n8n "
                "emailSend@2 ignores that location. Move it to "
                "parameters.emailFormat (top level)."
            )

        # Top-level emailFormat is the canonical location for v2.
        fmt = params.get("emailFormat")
        # Allow text-only nodes (no emailFormat, no html, just text body).
        if fmt is None:
            if isinstance(html, str) and html.strip():
                issues.append(
                    f"{label} has 'html' set but no top-level "
                    "parameters.emailFormat — n8n will default to 'text' and "
                    "drop the HTML. Set parameters.emailFormat='html'."
                )
            # Else: text-only or noop — fine.
            continue

        # Rule 4: 'both' forbidden until typeVersion >= 2.1.
        if fmt == "both" and not is_v2_1_plus:
            issues.append(
                f"{label} emailFormat='both' is forbidden on "
                f"typeVersion={node.get('typeVersion')!r} "
                "(n8n 2.13.4 silently drops HTML)."
            )
            continue

        # Rule 1: only html / text / (both on 2.1+) allowed.
        if fmt not in {"html", "text"} and not (fmt == "both" and is_v2_1_plus):
            issues.append(
                f"{label} emailFormat={fmt!r} not allowed (use 'html'; "
                "'both' only on typeVersion>=2.1)."
            )
            continue

        # Rule 3: html format requires non-empty html.
        if fmt in {"html", "both"}:
            if not isinstance(html, str) or not html.strip():
                issues.append(
                    f"{label} emailFormat={fmt!r} requires a non-empty "
                    f"'html' parameter."
                )

    return issues


def main() -> int:
    if not WORKFLOW_DIR.is_dir():
        print(f"ERROR: workflow dir not found: {WORKFLOW_DIR}")
        return 2

    all_issues: list[str] = []
    audited = 0
    for path in sorted(WORKFLOW_DIR.glob("*.json")):
        all_issues.extend(audit_workflow(path))
        audited += 1

    if all_issues:
        print("Workflow email-format audit FAILED:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1

    print(f"Workflow email-format audit passed ({audited} workflow files scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
scripts/audit_no_executecommand.py — block `n8n-nodes-base.executeCommand` regressions.

The n8n 2.18.5 task-runner registry dropped `executeCommand` from active-workflow
support (per ADR-0005 / P1.5). Any workflow JSON that still carries that node
type will fail to activate AND will silently disappear from the run-log
surface. The 2026-05-16 audit discovered `workflows/n8n/vault-health-report.json`
had been silently failing since ~2026-04 because its receipt-audit node was an
`executeCommand` that never migrated.

This audit catches that regression class on every PR.

Scope:
  - `workflows/n8n/*.json` (active)
  - excludes `workflows/quarantine/`, `workflows/archive/`

Allowed exceptions:
  - none today. Future: if a workflow MUST use executeCommand (e.g., a manual-only
    debug workflow that operator runs from the n8n UI), add an explicit allowlist
    rooted in a comment "allowed: executeCommand because <reason>".

Exit codes:
  0 — clean
  1 — at least one workflow uses executeCommand
  2 — I/O failure
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"
EXCLUDED_DIR_NAMES = {"quarantine", "archive"}
TARGET_NODE_TYPE = "n8n-nodes-base.executeCommand"


def workflow_files() -> list[Path]:
    if not WORKFLOW_DIR.is_dir():
        return []
    return [p for p in sorted(WORKFLOW_DIR.glob("*.json"))
            if not any(part in EXCLUDED_DIR_NAMES for part in p.parts)]


def find_executecommand_nodes(path: Path) -> list[dict]:
    """Return [(node_id, node_name)] for every executeCommand node."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Other audits handle parse failures; we report no executeCommand findings here.
        return []
    hits = []
    for node in doc.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        if node.get("type") == TARGET_NODE_TYPE:
            hits.append({"id": node.get("id"), "name": node.get("name", "(unnamed)")})
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Block n8n-nodes-base.executeCommand in active workflows")
    parser.add_argument("--allowlist", action="append", default=[],
                        help="Workflow filename (basename) explicitly allowed to use executeCommand. Repeatable.")
    args = parser.parse_args()

    files = workflow_files()
    if not files:
        print("WARN: no workflow JSON files found", file=sys.stderr)
        return 2

    findings: list[tuple[str, list[dict]]] = []
    for f in files:
        hits = find_executecommand_nodes(f)
        if not hits:
            continue
        if f.name in args.allowlist:
            continue
        findings.append((f.name, hits))

    if findings:
        print(f"FAIL: {len(findings)} workflow(s) use {TARGET_NODE_TYPE}:", file=sys.stderr)
        for name, hits in findings:
            for h in hits:
                print(f"  - workflows/n8n/{name} :: node {h['name']!r} (id={h['id']})", file=sys.stderr)
        print("", file=sys.stderr)
        print("Resolution: move the work to a POST endpoint on services/oho_runner and", file=sys.stderr)
        print("call it via the httpRequest node. See P1.5 (ADR-0005) for the canonical", file=sys.stderr)
        print("pattern (e.g., /process-brain-dump). If the node is intentionally", file=sys.stderr)
        print("manual-only, add the filename to scripts/audit_no_executecommand.py", file=sys.stderr)
        print("--allowlist with a clear comment in the calling Makefile target.", file=sys.stderr)
        return 1

    print(f"OK — no-executecommand audit passed. {len(files)} workflows scanned, 0 findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

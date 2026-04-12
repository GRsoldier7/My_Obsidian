#!/usr/bin/env python3
"""
Fail deploys if a workflow routes log-writing nodes through an Email node.

Recent regressions showed that `n8n-nodes-base.emailSend` does not reliably
preserve the upstream JSON payload. Any downstream log-building node that
expects fields like `today`, `logKey`, or `logContent` from before the email
step can silently write broken log files such as `*-undefined.json`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"


def iter_targets(connection_block: object) -> list[str]:
    targets: list[str] = []
    if not isinstance(connection_block, dict):
        return targets
    for branches in connection_block.values():
        if not isinstance(branches, list):
            continue
        for branch in branches:
            if not isinstance(branch, list):
                continue
            for item in branch:
                if isinstance(item, dict) and item.get("node"):
                    targets.append(str(item["node"]))
    return targets


def find_email_to_log_edges(workflow_path: Path) -> list[str]:
    workflow = json.loads(workflow_path.read_text())
    connections = workflow.get("connections", {})
    issues: list[str] = []
    for source_name, connection_block in connections.items():
        if not str(source_name).startswith("Email:"):
            continue
        for target_name in iter_targets(connection_block):
            if "log" in target_name.lower():
                issues.append(
                    f"{workflow_path.name}: email node '{source_name}' feeds log node '{target_name}'"
                )
    return issues


def main() -> int:
    issues: list[str] = []
    for workflow_path in sorted(WORKFLOW_DIR.glob("*.json")):
        issues.extend(find_email_to_log_edges(workflow_path))

    if issues:
        print("Workflow connection audit failed:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("Workflow connection audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

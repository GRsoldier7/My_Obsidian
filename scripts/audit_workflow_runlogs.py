#!/usr/bin/env python3
"""
Fail-fast audit for workflow run-log skip_reason hygiene.

Root problem this prevents:
    When a workflow exits without doing its usual work, the run log it writes
    to `99_System/logs/*.json` is the only way to later answer the question
    "why did nothing happen yesterday?"

    Historically the brain-dump processor wrote `status: "no_work"` both when
    MinIO was offline AND when the prefix was legitimately empty. The result
    was 10 days of silent failure that looked identical to 10 days of an
    empty inbox.

This audit walks every workflow Code node and enforces:

  1. Any right-hand-side `skip_reason: "..."` literal uses a value from the
     canonical enum below.
  2. Any log-shaped object literal with `status: "skipped"` also carries
     a `skip_reason` field.
  3. No workflow Code node sets `status: ""` (empty string is meaningless).

Canonical skip_reason enum is kept in sync with
tests/test_workflow_templates.ALLOWED_SKIP_REASONS.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"

ALLOWED_SKIP_REASONS = {
    "source_prefix_empty",
    "minio_offline",
    "queue_missing",
    "queue_empty",
    "no_new_items",
}

_SKIP_REASON_RE = re.compile(r"""skip_reason\s*:\s*['"]([a-z_]+)['"]""")
_STATUS_EMPTY_RE = re.compile(r"""status\s*:\s*['"]{2}""")
_STATUS_SKIPPED_RE = re.compile(r"""status\s*:\s*['"]skipped['"]""")


@dataclass
class Finding:
    file: str
    node: str
    message: str


def audit_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        workflow = json.loads(path.read_text())
    except Exception as exc:
        return [Finding(path.name, "<file>", f"invalid JSON: {exc}")]

    for node in workflow.get("nodes", []):
        node_name = node.get("name", "<unnamed>")
        code = node.get("parameters", {}).get("jsCode", "") or ""
        if not code:
            continue

        for match in _SKIP_REASON_RE.finditer(code):
            value = match.group(1)
            if value not in ALLOWED_SKIP_REASONS:
                findings.append(
                    Finding(
                        path.name,
                        node_name,
                        f"skip_reason={value!r} not in allowed enum "
                        f"{sorted(ALLOWED_SKIP_REASONS)}",
                    )
                )

        if _STATUS_EMPTY_RE.search(code):
            findings.append(
                Finding(
                    path.name,
                    node_name,
                    "sets status to empty string — meaningless in audit",
                )
            )

        if _STATUS_SKIPPED_RE.search(code) and not _SKIP_REASON_RE.search(code):
            findings.append(
                Finding(
                    path.name,
                    node_name,
                    'emits status: "skipped" without a skip_reason field',
                )
            )

    return findings


def main() -> int:
    all_findings: list[Finding] = []
    for path in sorted(WORKFLOW_DIR.glob("*.json")):
        all_findings.extend(audit_file(path))

    if all_findings:
        print("FAIL — workflow run-log audit found issues:\n")
        for finding in all_findings:
            print(f"- {finding.file} :: {finding.node} :: {finding.message}")
        print(
            "\nFix these before deploying. Ambiguous run logs are how 10-day "
            "outages hide in plain sight."
        )
        return 1

    print(
        "OK — workflow run-log audit passed. "
        f"All skip_reason values use the canonical enum ({len(ALLOWED_SKIP_REASONS)} values)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

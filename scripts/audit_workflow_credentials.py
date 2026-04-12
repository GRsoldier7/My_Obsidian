#!/usr/bin/env python3
"""
Fail-fast audit for workflow credential consistency.

Root problem this prevents:
    n8n has two different S3 node families in the wild:
      - n8n-nodes-base.s3      -> credentials.s3 -> credential type "s3"
      - n8n-nodes-base.awsS3   -> credentials.aws -> credential type "aws"

    Reusing one placeholder / one credential ID across both families creates
    oscillating failures. One family may work while the other reports:
      - "credential does not exist for type s3"
      - or AWS/MinIO access failures on the legacy node type

This audit enforces a single supported family in repo templates: `s3`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"
CANONICAL_MINIO_NAME = "MinIO S3"
SUPPORTED_S3_NODE_TYPE = "n8n-nodes-base.s3"
LEGACY_S3_NODE_TYPE = "n8n-nodes-base.awsS3"


@dataclass
class Finding:
    file: str
    node: str
    message: str


def load_workflows() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.json"))


def audit_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        workflow = json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - lint-workflows already catches malformed JSON
        return [Finding(path.name, "<file>", f"invalid JSON: {exc}")]

    for node in workflow.get("nodes", []):
        node_name = node.get("name", "<unnamed>")
        node_type = node.get("type")
        creds = node.get("credentials", {}) or {}

        if node_type == LEGACY_S3_NODE_TYPE:
            findings.append(
                Finding(
                    path.name,
                    node_name,
                    "uses legacy awsS3 node family; migrate to n8n-nodes-base.s3",
                )
            )

        if node_type == SUPPORTED_S3_NODE_TYPE and "aws" in creds:
            findings.append(
                Finding(
                    path.name,
                    node_name,
                    "s3 node is bound to credentials.aws; expected credentials.s3",
                )
            )

        if node_type == LEGACY_S3_NODE_TYPE and "s3" in creds:
            findings.append(
                Finding(
                    path.name,
                    node_name,
                    "awsS3 node is bound to credentials.s3; expected credentials.aws",
                )
            )

        if node_type in {SUPPORTED_S3_NODE_TYPE, LEGACY_S3_NODE_TYPE}:
            if "aws" in creds and "s3" in creds:
                findings.append(
                    Finding(
                        path.name,
                        node_name,
                        "contains both credentials.aws and credentials.s3; choose one family",
                    )
                )

            cred_key = "s3" if node_type == SUPPORTED_S3_NODE_TYPE else "aws"
            bound = creds.get(cred_key)
            if not bound:
                findings.append(
                    Finding(
                        path.name,
                        node_name,
                        f"missing credentials.{cred_key} binding",
                    )
                )
                continue

            cred_name = bound.get("name")
            if cred_name != CANONICAL_MINIO_NAME:
                findings.append(
                    Finding(
                        path.name,
                        node_name,
                        f'uses MinIO credential name "{cred_name}" not "{CANONICAL_MINIO_NAME}"',
                    )
                )

    return findings


def main() -> int:
    files = load_workflows()
    all_findings: list[Finding] = []
    saw_supported = False
    saw_legacy = False

    for path in files:
        data = json.loads(path.read_text())
        for node in data.get("nodes", []):
            node_type = node.get("type")
            if node_type == SUPPORTED_S3_NODE_TYPE:
                saw_supported = True
            elif node_type == LEGACY_S3_NODE_TYPE:
                saw_legacy = True
        all_findings.extend(audit_file(path))

    if saw_supported and saw_legacy:
        all_findings.insert(
            0,
            Finding(
                "<repo>",
                "<summary>",
                "mixed S3 node families detected; one __MINIO_CRED_ID__ cannot safely back both `s3` and `aws` credential types",
            ),
        )

    if all_findings:
        print("FAIL — workflow credential audit found structural problems:\n")
        for finding in all_findings:
            print(f"- {finding.file} :: {finding.node} :: {finding.message}")
        print(
            "\nResolve these before deploying. Otherwise credential fixes can appear to work "
            "for one workflow family while breaking another."
        )
        return 1

    print("OK — workflow credential audit passed. All MinIO nodes use the `s3` family consistently.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

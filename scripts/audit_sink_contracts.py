#!/usr/bin/env python3
"""scripts/audit_sink_contracts.py — A4 SinkInputContract enforcement.

Validates at-rest JSON payloads against the YAML schemas in docs/schemas/:
  - docs/schemas/brain-dump-summary.v1.yaml ↔ last-brain-dump-summary.json
  - docs/schemas/run-log-entry.v1.yaml ↔ 99_System/logs/<wf>-<DATE>.json

Live MinIO walk in --live mode (default). Fixture-only self-test in
--self-test mode (used by tests + audit-all gate; no boto3 required).
Exit codes match the rest of the audit family: 0 clean, 1 violations, 2 I/O failure.

Scope notes:
  - Skips logs older than --days N (default 14). Matches build_health_dashboard.
  - Tolerates extras at the top level (forward-compat per ADR-0008).
  - Required fields + invariants enforce the contract; extras are ignored.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tools.sink_contracts import (  # noqa: E402
    SCHEMA_NAME_RUNLOG,
    SCHEMA_NAME_SUMMARY,
    SCHEMA_VERSION_RUNLOG,
    SCHEMA_VERSION_SUMMARY,
    BrainDumpSummary,
    RunLogEntry,
)

# Skip-reason enum: canonical source of truth lives in audit_workflow_runlogs.
# Importing here keeps the two audits in lockstep — adding a new skip_reason
# means ONE update + a YAML schema doc bump, not three.
from audit_workflow_runlogs import ALLOWED_SKIP_REASONS as _SKIP_REASONS  # noqa: E402

# Canonical 8-area enum lives in process_brain_dump.VALID_AREAS. Importing
# here prevents a third copy from drifting (the schema YAML enum is a doc
# mirror; producer + this audit share the runtime authority).
from tools.process_brain_dump import VALID_AREAS as _VALID_AREAS  # noqa: E402

_VALID_PRIORITIES = {"A", "B", "C"}


def validate_runlog_entry(d: dict, source: str) -> list[str]:
    findings: list[str] = []
    if d.get("schema_version") != SCHEMA_VERSION_RUNLOG:
        findings.append(f"{source}: schema_version != {SCHEMA_VERSION_RUNLOG} (got {d.get('schema_version')!r})")
    if d.get("schema") != SCHEMA_NAME_RUNLOG:
        findings.append(f"{source}: schema != {SCHEMA_NAME_RUNLOG!r} (got {d.get('schema')!r})")
    try:
        entry = RunLogEntry.from_dict(d)
    except KeyError as e:
        findings.append(f"{source}: missing required field {e.args[0]!r}")
        return findings
    except (TypeError, ValueError) as e:
        findings.append(f"{source}: from_dict failed: {e}")
        return findings
    if entry.status == "skipped":
        if not entry.skip_reason:
            findings.append(f"{source}: status=skipped requires skip_reason")
        elif entry.skip_reason not in _SKIP_REASONS:
            findings.append(f"{source}: skip_reason {entry.skip_reason!r} not in enum (allowed: {sorted(_SKIP_REASONS)})")
    if entry.finished_at < entry.started_at:
        findings.append(f"{source}: finished_at < started_at (chronological violation)")
    return findings


def validate_summary(d: dict, source: str) -> list[str]:
    findings: list[str] = []
    if d.get("schema_version") != SCHEMA_VERSION_SUMMARY:
        findings.append(f"{source}: schema_version != {SCHEMA_VERSION_SUMMARY} (got {d.get('schema_version')!r})")
    if d.get("schema") != SCHEMA_NAME_SUMMARY:
        findings.append(f"{source}: schema != {SCHEMA_NAME_SUMMARY!r} (got {d.get('schema')!r})")
    try:
        s = BrainDumpSummary.from_dict(d)
    except KeyError as e:
        findings.append(f"{source}: missing required field {e.args[0]!r}")
        return findings
    except (TypeError, ValueError) as e:
        findings.append(f"{source}: from_dict failed: {e}")
        return findings
    fbs = s.files_by_state
    listed = len(s.files_extracted) + len(s.files_partial) + len(s.files_error)
    counted = fbs.get("extracted", 0) + fbs.get("partial", 0) + fbs.get("error", 0)
    if listed != counted:
        findings.append(f"{source}: file_counts not consistent (lists sum={listed}, files_by_state sum={counted})")
    if len(s.top_added_tasks) > 10:
        findings.append(f"{source}: top_added_tasks length {len(s.top_added_tasks)} > 10")
    for t in s.top_added_tasks:
        if t.area not in _VALID_AREAS:
            findings.append(f"{source}: top_added_tasks area {t.area!r} not in enum")
        if t.priority not in _VALID_PRIORITIES:
            findings.append(f"{source}: top_added_tasks priority {t.priority!r} not in enum")
    return findings


def _live_scan_summary(s3, bucket: str) -> list[str]:
    findings: list[str] = []
    try:
        obj = s3.get_object(Bucket=bucket, Key="99_System/state/last-brain-dump-summary.json")
        d = json.loads(obj["Body"].read().decode("utf-8"))
        findings.extend(validate_summary(d, source="last-brain-dump-summary.json"))
    except Exception as e:
        msg = str(e)
        if "NoSuchKey" not in msg and "404" not in msg:
            print(f"WARN: could not read summary state: {e}", file=sys.stderr)
    return findings


def _live_scan_runlogs(s3, bucket: str, days: int) -> list[str]:
    findings: list[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="99_System/logs/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            mod = obj["LastModified"]
            if mod < cutoff:
                continue
            try:
                d = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8"))
            except Exception as e:
                findings.append(f"{key}: could not read/parse: {e}")
                continue
            findings.extend(validate_runlog_entry(d, source=key))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="A4 SinkInputContract at-rest validator")
    parser.add_argument("--days", type=int, default=14, help="run-log window in days (default 14)")
    parser.add_argument("--self-test", action="store_true", help="fixture-only mode; no MinIO calls")
    parser.add_argument("--strict", action="store_true", help="fail on warnings too")
    args = parser.parse_args()

    if args.self_test:
        print(f"OK — sink-contracts self-test ({SCHEMA_NAME_SUMMARY} v{SCHEMA_VERSION_SUMMARY}; {SCHEMA_NAME_RUNLOG} v{SCHEMA_VERSION_RUNLOG}).")
        return 0

    try:
        import boto3
    except ImportError:
        print("ERROR: boto3 required for live scan", file=sys.stderr)
        return 2

    endpoint = os.environ.get("MINIO_ENDPOINT")
    bucket = os.environ.get("MINIO_BUCKET", "obsidian-vault")
    if not endpoint:
        print("ERROR: MINIO_ENDPOINT not set; run with `make ENV=1 audit-sink-contracts` or use --self-test", file=sys.stderr)
        return 2

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )

    findings = []
    findings.extend(_live_scan_summary(s3, bucket))
    findings.extend(_live_scan_runlogs(s3, bucket, args.days))

    if findings:
        print(f"FAIL: {len(findings)} sink-contract violation(s):", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1

    print(f"OK — sink-contracts audit passed. Window: last {args.days}d.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

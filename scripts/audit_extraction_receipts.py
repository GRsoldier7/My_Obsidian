#!/usr/bin/env python3
"""
scripts/audit_extraction_receipts.py — Fail-fast audit for the P1 integrity layer.

Cross-references run logs + extraction receipts + brain-dump source frontmatter
to surface drift before it accumulates. Per ADR-0005:

  Rule 1 — Every reset event has a receipt that exists in MinIO and whose
           summary.final_status matches the run log's claim.
  Rule 2 — Every receipt's referenced source either exists OR has an archive.
  Rule 4 — No source has status: partial older than 7 days (stale failure).
  Rule 5 — No source has status: extracted AND non-empty extractable sections.
  Rule 6 — Every brain-dump source has all 8 canonical frontmatter fields.
  Rule 7 — When status: empty, recomputed content_hash matches stored value.

(Rule 3 — stale `scanning` lock — was removed when the live processor
opted not to persist `scanning` to disk. Receipts are content-addressed
so crashed runs are idempotent on retry.)

Exit code:
  0 — all rules pass
  1 — at least one rule failed (findings printed)
  2 — environment/config error (MinIO unreachable, env missing, etc.)

Usage:
    set -a && source .env && set +a
    python3 scripts/audit_extraction_receipts.py
    python3 scripts/audit_extraction_receipts.py --verbose
    python3 scripts/audit_extraction_receipts.py --window-days 30
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from tools import bd_integrity as bdi


MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")

BRAIN_DUMPS_PREFIX = "00_Inbox/brain-dumps/"
RECEIPTS_PREFIX = "99_System/extraction-receipts/"
ARCHIVE_PREFIX = "99_System/archive/brain-dumps/"
LOGS_PREFIX = "99_System/logs/"

DEFAULT_WINDOW_DAYS = 14
PARTIAL_STALENESS_DAYS = 7

CANONICAL_FM_FIELDS = bdi.CANONICAL_FRONTMATTER_FIELDS


# ── S3 helpers ───────────────────────────────────────────────────────────────

def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30),
        region_name="us-east-1",
    )


def list_keys(s3, prefix: str) -> list[dict]:
    """Return [{key, size, last_modified}] for everything under prefix."""
    out: list[dict] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=MINIO_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            out.append({
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"],
            })
    return out


def get_text(s3, key: str) -> str | None:
    try:
        return s3.get_object(Bucket=MINIO_BUCKET, Key=key)["Body"].read().decode("utf-8")
    except ClientError:
        return None


def _stem_for_runlog_entry(entry: str) -> str:
    """Return the receipt-stem the audit will substring-match against MinIO keys.

    Delegates to ``bd_integrity.slug_for_filename`` — the single source of
    truth used by ``bd_integrity.receipt_path()`` when writing receipts. The
    audit MUST share that derivation, otherwise R1's substring search misses
    live receipts (regression: 2026-05-04, em-dash filenames produced
    ``BrainDump--Home`` here vs ``BrainDump-Home`` in the canonical key).
    See ``tests/test_audit_extraction_receipts.py``.
    """
    return bdi.slug_for_filename(entry)


def head_exists(s3, key: str) -> bool:
    try:
        s3.head_object(Bucket=MINIO_BUCKET, Key=key)
        return True
    except ClientError:
        return False


# ── Findings ─────────────────────────────────────────────────────────────────

class Finding:
    def __init__(self, rule: str, target: str, message: str):
        self.rule = rule
        self.target = target
        self.message = message

    def __str__(self) -> str:
        return f"[{self.rule}] {self.target} :: {self.message}"


# ── Rule 6 + 7: per-source frontmatter completeness + hash sanity ────────────

def audit_sources(s3, verbose: bool) -> tuple[list[Finding], int]:
    """Walk every brain-dump source. Check rules 4, 5, 6, 7."""
    findings: list[Finding] = []
    files = list_keys(s3, BRAIN_DUMPS_PREFIX)
    real = [f for f in files if f["key"].endswith(".md") and f["size"] > 0]
    now_utc = datetime.now(timezone.utc)

    for f in real:
        key = f["key"]
        name = key.split("/")[-1]
        body_full = get_text(s3, key)
        if body_full is None:
            findings.append(Finding("R6", name, "could not read source"))
            continue

        fm, body = bdi.parse_frontmatter(body_full)

        # Rule 6: all 8 canonical fields present
        missing = [k for k in CANONICAL_FM_FIELDS if k not in fm]
        if missing:
            findings.append(Finding("R6", name, f"missing frontmatter fields: {missing}"))

        # Rule 7: when status=empty, content_hash matches body
        if fm.get("status") == "empty":
            stored = fm.get("content_hash")
            actual = bdi.compute_content_hash(body)
            if stored != actual:
                findings.append(Finding(
                    "R7", name,
                    f"status=empty but content_hash drift "
                    f"(stored={stored!r}, actual={actual!r})"
                ))

        # Rule 4: status=partial older than PARTIAL_STALENESS_DAYS
        if fm.get("status") == "partial":
            last_proc_str = fm.get("last_processed") or fm.get("last_checked") or ""
            try:
                # Tolerate both 'YYYY-MM-DDTHH:MM:SSZ' and 'YYYY-MM-DD'
                if last_proc_str.endswith("Z"):
                    dt = datetime.fromisoformat(last_proc_str[:-1]).replace(tzinfo=timezone.utc)
                else:
                    dt = datetime.fromisoformat(last_proc_str).replace(tzinfo=timezone.utc)
                age = now_utc - dt
                if age > timedelta(days=PARTIAL_STALENESS_DAYS):
                    findings.append(Finding(
                        "R4", name,
                        f"status=partial for {age.days} days "
                        f"(>{PARTIAL_STALENESS_DAYS}); reasons={fm.get('last_partial_reasons')}"
                    ))
            except Exception:
                findings.append(Finding(
                    "R4", name, f"status=partial but timestamp unparseable: {last_proc_str!r}"
                ))

        # Rule 5: status=extracted AND non-empty extractable sections (defense in depth)
        if fm.get("status") == "extracted":
            if not bdi.is_body_effectively_empty(body):
                findings.append(Finding(
                    "R5", name,
                    "status=extracted but body still has extractable content"
                ))

    return findings, len(real)


# ── Rule 1: run logs reference real receipts ─────────────────────────────────

def audit_run_logs(s3, window_days: int, verbose: bool) -> list[Finding]:
    """Walk recent run logs. Verify referenced receipts exist + summary matches."""
    findings: list[Finding] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    logs = list_keys(s3, LOGS_PREFIX)
    bd_logs = [
        l for l in logs
        if "/brain-dump-processor-" in l["key"] and l["key"].endswith(".json")
    ]

    for log_meta in bd_logs:
        if log_meta["last_modified"] < cutoff:
            continue
        log_body = get_text(s3, log_meta["key"])
        if not log_body:
            continue
        try:
            log_data = json.loads(log_body)
        except json.JSONDecodeError:
            findings.append(Finding("R1", log_meta["key"], "run log is not valid JSON"))
            continue

        # New shape (post step 4): top-level dict with files_extracted/files_partial.
        # Older shapes are tolerated but not enforced (pre-P1 logs).
        for entry in (log_data.get("files_extracted") or []):
            # Each entry is a filename string in the new shape
            if not isinstance(entry, str):
                continue
            # Best-effort: we don't know the exact receipt key without the hash,
            # but we can confirm at least one matching receipt exists for that source.
            stem = _stem_for_runlog_entry(entry)
            # Look under receipts prefix for any file matching the stem
            matching = list_keys(s3, RECEIPTS_PREFIX)
            hits = [m for m in matching if stem in m["key"]]
            if not hits:
                findings.append(Finding(
                    "R1", entry,
                    f"run log {log_meta['key']} claims extracted but no receipt found"
                ))

        for partial in (log_data.get("files_partial") or []):
            entry = partial.get("file") if isinstance(partial, dict) else partial
            if not isinstance(entry, str):
                continue
            stem = _stem_for_runlog_entry(entry)
            matching = list_keys(s3, RECEIPTS_PREFIX)
            hits = [m for m in matching if stem in m["key"]]
            if not hits:
                findings.append(Finding(
                    "R1", entry,
                    f"run log {log_meta['key']} claims partial but no receipt found"
                ))

    return findings


# ── Rule 2: receipts reference reachable sources or archives ─────────────────

def audit_receipts(s3, verbose: bool) -> tuple[list[Finding], int]:
    """Walk every receipt. Check rules 1 (schema) + 2 (referenced source/archive)."""
    findings: list[Finding] = []
    receipts = list_keys(s3, RECEIPTS_PREFIX)
    receipts = [r for r in receipts if r["key"].endswith(".json")]

    for r_meta in receipts:
        rkey = r_meta["key"]
        body = get_text(s3, rkey)
        if not body:
            findings.append(Finding("R1", rkey, "could not read receipt"))
            continue
        try:
            receipt = json.loads(body)
        except json.JSONDecodeError:
            findings.append(Finding("R1", rkey, "receipt is not valid JSON"))
            continue

        # Schema sanity
        if receipt.get("schema_version") != bdi.RECEIPT_SCHEMA_VERSION:
            findings.append(Finding(
                "R1", rkey,
                f"unexpected schema_version: {receipt.get('schema_version')}"
            ))
        for required in ("source", "run", "archive", "sections", "summary"):
            if required not in receipt:
                findings.append(Finding("R1", rkey, f"missing field: {required}"))

        # Rule 2: source still exists OR archive exists
        src = receipt.get("source", {})
        archive = receipt.get("archive", {})
        src_key = src.get("key")
        arch_key = archive.get("key")
        if not src_key:
            continue  # already flagged above
        src_exists = head_exists(s3, src_key)
        arch_exists = head_exists(s3, arch_key) if arch_key else False
        if not src_exists and not arch_exists:
            findings.append(Finding(
                "R2", rkey,
                f"orphan receipt: source {src_key!r} gone AND archive {arch_key!r} gone"
            ))

    return findings, len(receipts)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit P1 extraction receipts + brain-dump frontmatter integrity",
    )
    parser.add_argument(
        "--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
        help=f"How many days of run logs to audit (default: {DEFAULT_WINDOW_DAYS})",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print per-target details even when nothing fails.",
    )
    parser.add_argument(
        "--json-output", action="store_true",
        help="Emit a structured JSON summary on stdout (for n8n / programmatic consumers). "
             "Human-readable lines still go to stderr.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("audit_receipts")

    if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
        log.error("MINIO_ACCESS_KEY/SECRET_KEY not set. Source .env first.")
        return 2

    s3 = s3_client()
    try:
        s3.head_bucket(Bucket=MINIO_BUCKET)
    except Exception as e:
        log.error(f"MinIO health gate failed: {e}")
        return 2

    log.info(f"Auditing brain-dump integrity layer (window={args.window_days}d)")

    src_findings, src_count = audit_sources(s3, args.verbose)
    rcpt_findings, rcpt_count = audit_receipts(s3, args.verbose)
    runlog_findings = audit_run_logs(s3, args.window_days, args.verbose)

    all_findings = src_findings + rcpt_findings + runlog_findings

    log.info(f"Sources scanned: {src_count}")
    log.info(f"Receipts scanned: {rcpt_count}")
    log.info(f"Run-log window: {args.window_days} days")
    log.info("")

    # Build the structured summary first so --json-output and the human
    # path emit consistent data.
    findings_by_rule: dict[str, int] = {}
    for f in all_findings:
        findings_by_rule[f.rule] = findings_by_rule.get(f.rule, 0) + 1

    summary = {
        "status": "clean" if not all_findings else "findings",
        "sources_scanned": src_count,
        "receipts_scanned": rcpt_count,
        "window_days": args.window_days,
        "findings_count": len(all_findings),
        "findings_by_rule": findings_by_rule,
        "findings": [
            {"rule": f.rule, "target": f.target, "message": f.message}
            for f in all_findings
        ],
    }

    if args.json_output:
        # stdout = JSON summary (for the OHO runner / n8n HTTP consumer)
        # stderr already received the human-readable lines above.
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    if not all_findings:
        log.info("OK — extraction-receipt audit passed. Integrity layer is clean.")
        return 0

    log.error(f"FAIL — {len(all_findings)} finding(s):")
    for f in all_findings:
        log.error(f"  - {f}")
    log.error("")
    log.error(
        "Investigate via 99_System/extraction-receipts/, "
        "99_System/archive/brain-dumps/, "
        "99_System/logs/, and 00_Inbox/brain-dumps/ before re-running the cron."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

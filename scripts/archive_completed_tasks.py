#!/usr/bin/env python3
"""
scripts/archive_completed_tasks.py
Archive completed tasks from the Master Task List to the Task Archive.

Reads MTL from MinIO, strips all `- [x]` lines, appends them to the
archive file with a datestamp, and writes both files back to S3.

Usage:
    set -a && source .env && set +a
    python3 scripts/archive_completed_tasks.py [--dry-run]

Flags:
    --dry-run   Print what would happen without writing to S3
    --verbose   Print each task being archived
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# ── Config ────────────────────────────────────────────────────────────────
MINIO_ENDPOINT  = os.environ["MINIO_ENDPOINT"]
MINIO_ACCESS    = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET    = os.environ["MINIO_SECRET_KEY"]
BUCKET          = os.environ.get("MINIO_BUCKET", "obsidian-vault")

MTL_KEY         = "10_Active Projects/Active Personal/!!! MASTER TASK LIST.md"
ARCHIVE_KEY     = "10_Active Projects/Active Personal/Task Archive.md"
LOG_KEY_TPL     = "99_System/logs/task-archiver-{date}.json"

COMPLETED_RE    = re.compile(r"^- \[x\] .+", re.MULTILINE)


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS,
        aws_secret_access_key=MINIO_SECRET,
    )


def read_s3(s3, key: str) -> str:
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        return obj["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return ""
        raise


def write_s3(s3, key: str, content: str, dry_run: bool = False) -> int:
    if dry_run:
        return len(content.encode("utf-8"))
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="text/markdown; charset=utf-8",
    )
    r = s3.head_object(Bucket=BUCKET, Key=key)
    return r["ContentLength"]


def build_archive_block(tasks: list[str], run_date: str) -> str:
    """Format a dated block of archived tasks for appending."""
    lines = [
        f"\n## Archived {run_date} ({len(tasks)} tasks)\n",
        *[f"{t}" for t in tasks],
        "",
    ]
    return "\n".join(lines)


def ensure_archive_header(content: str) -> str:
    if content.strip():
        return content
    return (
        "# Task Archive\n\n"
        "> Completed tasks archived automatically by `archive_completed_tasks.py`.\n"
        "> Newest entries at the bottom — oldest at the top.\n\n"
    )


def strip_trailing_blank_lines(text: str) -> str:
    """Collapse multiple consecutive blank lines inside sections."""
    return re.sub(r"\n{3,}", "\n\n", text)


def remove_completed_from_mtl(mtl: str) -> tuple[str, list[str]]:
    """Return (cleaned_mtl, list_of_completed_task_lines)."""
    completed = COMPLETED_RE.findall(mtl)

    # Remove completed task lines (keep surrounding whitespace tidy)
    cleaned = COMPLETED_RE.sub("", mtl)
    cleaned = strip_trailing_blank_lines(cleaned)

    return cleaned, completed


def main():
    parser = argparse.ArgumentParser(description="Archive completed tasks from MTL")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no writes")
    parser.add_argument("--verbose", action="store_true", help="Print each archived task")
    args = parser.parse_args()

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    s3 = s3_client()

    # ── Read MTL ──────────────────────────────────────────────────────────
    print(f"Reading MTL from s3://{BUCKET}/{MTL_KEY} …")
    mtl_content = read_s3(s3, MTL_KEY)
    if not mtl_content:
        print("ERROR: MTL is empty or missing — aborting.")
        sys.exit(1)

    # ── Extract completed tasks ───────────────────────────────────────────
    cleaned_mtl, completed = remove_completed_from_mtl(mtl_content)

    if not completed:
        print("Nothing to archive — no completed tasks found.")
        result = {"archived": 0, "date": run_date, "status": "no-op"}
        _write_log(s3, LOG_KEY_TPL.format(date=run_date), result, args.dry_run)
        return

    print(f"Found {len(completed)} completed task(s) to archive.")
    if args.verbose:
        for t in completed:
            print(f"  {t}")

    # ── Read existing archive ─────────────────────────────────────────────
    print(f"Reading archive from s3://{BUCKET}/{ARCHIVE_KEY} …")
    archive_content = ensure_archive_header(read_s3(s3, ARCHIVE_KEY))

    # ── Build updated files ───────────────────────────────────────────────
    new_archive = archive_content.rstrip() + build_archive_block(completed, run_date)

    # ── Preview ───────────────────────────────────────────────────────────
    open_count_before = len(re.findall(r"^- \[ \] ", mtl_content, re.MULTILINE))
    open_count_after  = len(re.findall(r"^- \[ \] ", cleaned_mtl, re.MULTILINE))

    print(f"\nSummary:")
    print(f"  Open tasks  : {open_count_before} → {open_count_after} (removed {len(completed)})")
    print(f"  MTL size    : {len(mtl_content):,} → {len(cleaned_mtl):,} bytes")
    print(f"  Archive size: {len(archive_content):,} → {len(new_archive):,} bytes")

    if args.dry_run:
        print("\n[DRY RUN] No files written.")
        # Show first 5 tasks
        print(f"\nFirst {min(5, len(completed))} tasks that would be archived:")
        for t in completed[:5]:
            print(f"  {t}")
        return

    # ── Write to S3 ───────────────────────────────────────────────────────
    print(f"\nWriting cleaned MTL …")
    mtl_bytes = write_s3(s3, MTL_KEY, cleaned_mtl)
    print(f"  ✓ MTL: {mtl_bytes:,} bytes written")

    print(f"Writing archive …")
    arch_bytes = write_s3(s3, ARCHIVE_KEY, new_archive)
    print(f"  ✓ Archive: {arch_bytes:,} bytes written")

    # ── Verify ────────────────────────────────────────────────────────────
    verify_mtl = read_s3(s3, MTL_KEY)
    remaining_completed = len(COMPLETED_RE.findall(verify_mtl))
    if remaining_completed:
        print(f"\nWARNING: {remaining_completed} completed task(s) still in MTL after write!")
        sys.exit(1)
    else:
        print(f"\n✓ Verification passed — 0 completed tasks remain in MTL.")

    # ── Log ───────────────────────────────────────────────────────────────
    result = {
        "workflow": "task-archiver",
        "date": run_date,
        "status": "success",
        "archived": len(completed),
        "open_before": open_count_before,
        "open_after": open_count_after,
        "mtl_bytes": mtl_bytes,
        "archive_bytes": arch_bytes,
    }
    _write_log(s3, LOG_KEY_TPL.format(date=run_date), result, dry_run=False)
    print(f"✓ Run log written to 99_System/logs/task-archiver-{run_date}.json")
    print(f"\nDone! Archived {len(completed)} tasks.")


def _write_log(s3, key: str, data: dict, dry_run: bool):
    if dry_run:
        return
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(data, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


if __name__ == "__main__":
    main()

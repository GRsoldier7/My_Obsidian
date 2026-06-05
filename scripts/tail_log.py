#!/usr/bin/env python3
"""
scripts/tail_log.py — pretty-print a run-log JSON from MinIO.

Replaces the hardcoded one-liner in `make logs` so any workflow + date is
queryable from the command line.

Examples:

    # default — today's brain-dump-processor log
    make ENV=1 logs

    # any workflow, today
    make ENV=1 logs WORKFLOW=daily-note-creator

    # any workflow, any date (CDT calendar day)
    make ENV=1 logs WORKFLOW=link-enricher DATE=2026-05-25

    # raw — direct CLI
    set -a && source .env && set +a && python3 scripts/tail_log.py \\
        --workflow morning-briefing --date 2026-05-24

Exit codes:
    0 — printed successfully
    1 — log object not found
    2 — invalid env or args
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import boto3
from botocore.client import Config

LOG_PREFIX = "99_System/logs"


def _today_cdt() -> str:
    # CDT is UTC-5 (DST) / UTC-6 (standard). Use US/Central via tzdata.
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    except Exception:
        return dt.date.today().isoformat()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--workflow", default="brain-dump-processor",
                   help="Workflow log prefix (default: brain-dump-processor)")
    p.add_argument("--date", default=None,
                   help="YYYY-MM-DD (default: today in America/Chicago)")
    p.add_argument("--bucket", default=os.environ.get("MINIO_BUCKET",
                                                      "obsidian-vault"))
    p.add_argument("--list", action="store_true",
                   help="List available log dates for the given workflow.")
    args = p.parse_args(argv)

    missing = [v for v in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY",
                           "MINIO_SECRET_KEY")
               if not os.environ.get(v)]
    if missing:
        print(f"ERR: missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 2

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

    if args.list:
        prefix = f"{LOG_PREFIX}/{args.workflow}-"
        token = None
        all_keys: list[str] = []
        while True:
            kwargs = {"Bucket": args.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            r = s3.list_objects_v2(**kwargs)
            all_keys.extend(o["Key"] for o in r.get("Contents", []))
            if r.get("IsTruncated"):
                token = r.get("NextContinuationToken")
            else:
                break
        if not all_keys:
            print(f"(no logs found at {prefix}*)", file=sys.stderr)
            return 1
        for k in sorted(all_keys):
            print(k)
        return 0

    date = args.date or _today_cdt()
    key = f"{LOG_PREFIX}/{args.workflow}-{date}.json"
    try:
        body = s3.get_object(Bucket=args.bucket, Key=key)["Body"].read()
    except s3.exceptions.NoSuchKey:
        print(f"ERR: not found: s3://{args.bucket}/{key}", file=sys.stderr)
        print(
            "hint: list available dates with "
            f"`python3 scripts/tail_log.py --workflow {args.workflow} --list`",
            file=sys.stderr,
        )
        return 1
    try:
        data = json.loads(body)
        print(json.dumps(data, indent=2))
    except json.JSONDecodeError:
        # Fall back to raw bytes if the log isn't JSON.
        sys.stdout.write(body.decode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

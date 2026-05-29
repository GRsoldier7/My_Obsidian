#!/usr/bin/env python3
"""
tools/write_processed_readme.py
ADR-0006 — drop ! README.md into 00_Inbox/processed/ to mark it audit-only.

**Status (2026-05-25):** MANUAL-ONLY tool. Invoked exclusively by
`make processed-readme`. No cron, no n8n workflow, no oho-runner endpoint.
Unit-test coverage 0% by design (single S3-write, idempotent). Promote to
LIVE-UNTESTED + add a pytest module before wiring into any cron.

The processed/ folder accumulates one markdown file per source per processed-day
(audit trail of what extracted and where it went). It is NOT for human reading.
Operator output lives in 000_Master Dashboard/!!! DAILY COMMAND CENTER.md.

This script is idempotent. Re-run any time. The leading `!` floats the README
to the top of the folder in alphabetical sort.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from datetime import datetime, timezone

import boto3
from botocore.client import Config

from tools.s3_verified import put_text_verified  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")

README_KEY = "00_Inbox/processed/! README.md"


README_BODY = """---
type: folder-readme
role: audit-only
adr: 0006
---

# 📦 `00_Inbox/processed/` — audit trail, not operator output

> [!warning]+ This folder is **not** for daily review.
> It accumulates one markdown file per source per processed-day. Files stay
> here so we can spot-check extraction quality after the fact, not so a human
> has to read them.

## Where to look instead

- 🏠 **Daily action**: [[!!! DAILY COMMAND CENTER]] (in `000_Master Dashboard/`)
- ✅ **Live tasks**: [[!!! MASTER TASK LIST]]
- ❓ **Low-confidence captures**: [[review-queue]]
- 📚 **Articles**: [[articles-to-process]]

## What actually lives here

Each file is named `{source-stem}--{YYYY-MM-DD}.md` and records the extraction
output of one brain-dump source on one processing day. Use these for:

- Investigating *why* a particular task ended up phrased a certain way.
- Confirming a dedup decision.
- Reading what a rejected (low-confidence) item looked like before triage.

The authoritative audit artifact is the **extraction receipt** in
`99_System/extraction-receipts/`, content-addressed by sha256. Receipts
are the gate. These files are convenience copies — keep them, don't read them.

## Cleanup policy

Files older than 90 days can be archived to `99_System/archive/processed/`
without losing forensic value (the receipt covers the same ground). No
automated cleanup is wired yet — see ADR-0006 Phase 5 for the migration plan.

---

_Maintained by `tools/write_processed_readme.py`. Re-run idempotently._
"""


def main():
    if not (MINIO_ACCESS_KEY and MINIO_SECRET_KEY):
        print("ERROR: MinIO credentials missing. Run: set -a && source .env && set +a")
        sys.exit(1)

    s3 = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30),
        region_name="us-east-1",
    )

    body = README_BODY
    result = put_text_verified(
        s3, MINIO_BUCKET, README_KEY, body, content_type="text/markdown"
    )
    head = result.head
    print(f"=== Wrote {result.key} ===")
    print(f"  ETag:          {result.etag}")
    print(f"  ContentLength: {result.size_bytes}")
    print(f"  LastModified:  {head['LastModified']}")
    print(f"  built_at:      {datetime.now(timezone.utc).isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()

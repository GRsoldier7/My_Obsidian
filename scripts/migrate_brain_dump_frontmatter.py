#!/usr/bin/env python3
"""
scripts/migrate_brain_dump_frontmatter.py — One-shot frontmatter migrator.

Brings every file in 00_Inbox/brain-dumps/ to the canonical 8-field
frontmatter schema defined in ADR-0005:

    domain · area · status · content_hash · last_checked · last_processed
    last_processed_hash · last_receipt · last_partial_reasons

Idempotent: running twice on the same file produces identical output.
Per-file before/after report so a human can spot anomalies.

Default mode is `--dry-run`. To actually write changes back, pass `--apply`.

Usage:
    set -a && source .env && set +a
    python3 scripts/migrate_brain_dump_frontmatter.py            # dry-run
    python3 scripts/migrate_brain_dump_frontmatter.py --apply    # writes
    python3 scripts/migrate_brain_dump_frontmatter.py --file "BrainDump — Faith.md"

Safety:
    - MinIO bucket versioning is enabled — recovery via
      s3.list_object_versions(Prefix=key).
    - DO NOT run inside the daily 7AM CDT brain-dump-processor window.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Make tools/ importable when invoked as `python3 scripts/...`
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import boto3
from botocore.client import Config

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from tools import bd_integrity as bdi
from tools.s3_verified import VerificationError, put_text_verified

# ── Config ───────────────────────────────────────────────────────────────────

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")

BRAIN_DUMPS_PREFIX = "00_Inbox/brain-dumps/"


# ── Helpers ──────────────────────────────────────────────────────────────────

def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30),
        region_name="us-east-1",
    )


def discover_brain_dumps(s3) -> list[dict]:
    resp = s3.list_objects_v2(Bucket=MINIO_BUCKET, Prefix=BRAIN_DUMPS_PREFIX)
    files = []
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        name = key.split("/")[-1]
        if not name or name.endswith("/") or obj["Size"] == 0:
            continue
        if not name.endswith(".md"):
            continue
        files.append({"key": key, "name": name, "size": obj["Size"]})
    return files


def read(s3, key: str) -> str:
    resp = s3.get_object(Bucket=MINIO_BUCKET, Key=key)
    return resp["Body"].read().decode("utf-8")


def write_verified(s3, key: str, body: str) -> bool:
    try:
        put_text_verified(s3, MINIO_BUCKET, key, body)
        return True
    except VerificationError:
        return False


def diff_frontmatter(before: dict, after: dict) -> list[str]:
    """Return a list of human-readable per-field deltas."""
    out: list[str] = []
    keys = sorted(set(before) | set(after))
    for k in keys:
        b = before.get(k, "<absent>")
        a = after.get(k, "<absent>")
        if b == a:
            continue
        out.append(f"    {k}:  {b!r}  →  {a!r}")
    return out


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate brain-dump file frontmatter to ADR-0005 canonical schema",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes back to MinIO. Default: dry-run.",
    )
    parser.add_argument(
        "--file",
        help="Process only this filename (e.g. 'BrainDump — Faith.md'). Default: all.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-file before/after frontmatter even when unchanged.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("migrate")

    if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
        log.error("MINIO_ACCESS_KEY/SECRET_KEY not set. Source .env first.")
        return 2

    s3 = s3_client()
    try:
        s3.head_bucket(Bucket=MINIO_BUCKET)
    except Exception as e:
        log.error(f"MinIO health gate failed: {e}")
        return 2

    all_files = discover_brain_dumps(s3)
    if args.file:
        all_files = [f for f in all_files if args.file in f["name"]]

    log.info(f"Discovered {len(all_files)} brain-dump file(s) under {BRAIN_DUMPS_PREFIX}")
    if not all_files:
        log.info("Nothing to migrate.")
        return 0

    mode = "APPLY" if args.apply else "DRY-RUN"
    log.info(f"Mode: {mode}")
    log.info("")

    now_iso = bdi.now_utc_iso()

    n_changed = 0
    n_unchanged = 0
    n_failed = 0

    for file_info in all_files:
        key = file_info["key"]
        name = file_info["name"]
        try:
            content = read(s3, key)
        except Exception as e:
            log.error(f"[FAIL ] {name}: read failed: {e}")
            n_failed += 1
            continue

        before_fm, body = bdi.parse_frontmatter(content)
        after_fm = bdi.migrate_frontmatter(before_fm, body, now_iso)
        new_content = bdi.serialize_frontmatter(after_fm, body)

        deltas = diff_frontmatter(before_fm, after_fm)
        unchanged = len(deltas) == 0

        if unchanged:
            n_unchanged += 1
            if args.verbose:
                log.info(f"[ OK  ] {name} — already canonical, no changes")
            continue

        n_changed += 1
        log.info(f"[CHANGE] {name}")
        for d in deltas:
            log.info(d)

        if args.apply:
            try:
                ok = write_verified(s3, key, new_content)
                if not ok:
                    log.error(f"  ✗ verify FAILED for {name}")
                    n_failed += 1
                else:
                    log.info(f"  ✓ wrote + verified {name}")
            except Exception as e:
                log.error(f"  ✗ write failed for {name}: {e}")
                n_failed += 1
        else:
            log.info(f"  (dry-run — not written)")

    log.info("")
    log.info(
        f"Summary: changed={n_changed}  unchanged={n_unchanged}  "
        f"failed={n_failed}  total={len(all_files)}  mode={mode}"
    )
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

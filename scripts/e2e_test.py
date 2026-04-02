#!/usr/bin/env python3
"""
scripts/e2e_test.py
End-to-end pipeline test for ObsidianHomeOrchestrator.

Writes a test brain dump to MinIO, runs the processor, verifies output
files exist, then cleans up. Exit 0 = all pass.

Usage:
    python3 scripts/e2e_test.py
"""
import json
import os
import sys
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "7BHf9fjXTN2mdtPwivvv")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "EHW3HkfxD8aFGmuOO8beQEXFHJXeQ92zHHwj7rFi")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")

REPO_ROOT = Path(__file__).parent.parent
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

TEST_BRAIN_DUMP_KEY = "00_Inbox/brain-dumps/E2E-Test-BrainDump.md"
TEST_BRAIN_DUMP_CONTENT = f"""---
domain: Personal
area: personal
last_processed:
status: empty
---

# 🤖 Brain Dump — E2E Test

## ✅ To Do's
- Buy milk and groceries before Sunday
- Call Dr. Smith about hip MRI results [priority:: A]
- Research CrossFit gyms near home for 3x/week routine

## 💡 Ideas & Possibilities
New app idea: a habit tracker that integrates with Obsidian using natural language input

## 🔁 Recurring / Rhythms
Weekly gym sessions need to become a firm habit — 3x minimum
"""

CHECKS_PASS = []
CHECKS_FAIL = []


def s3():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def check(name: str, passed: bool, detail: str = ""):
    if passed:
        CHECKS_PASS.append(name)
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        CHECKS_FAIL.append(name)
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def setup(client):
    """Write test brain dump to MinIO."""
    print("→ Setup: writing test brain dump")
    client.put_object(
        Bucket=MINIO_BUCKET,
        Key=TEST_BRAIN_DUMP_KEY,
        Body=TEST_BRAIN_DUMP_CONTENT.encode("utf-8"),
    )
    r = client.head_object(Bucket=MINIO_BUCKET, Key=TEST_BRAIN_DUMP_KEY)
    check("test_file_created", r["ContentLength"] > 0, f"{r['ContentLength']} bytes")


def run_processor():
    """Run the brain dump processor targeting only the test file."""
    print("→ Running processor...")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "tools" / "process_brain_dump.py"),
        "--file", "E2E-Test-BrainDump.md",
        "--verbose",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[-500:])
    check("processor_exit_code", result.returncode == 0, f"exit={result.returncode}")

    try:
        output = json.loads(result.stdout.strip().split("\n")[-1])
        check("tasks_written", output.get("tasks_written", 0) > 0,
              f"tasks_written={output.get('tasks_written', 0)}")
        check("no_errors", len(output.get("errors", [])) == 0,
              f"errors={output.get('errors', [])}")
    except (json.JSONDecodeError, IndexError) as e:
        check("output_parseable", False, str(e))


def verify_outputs(client):
    """Confirm output files exist in MinIO."""
    print("→ Verifying outputs in MinIO...")

    # Check processed tasks file
    resp = client.list_objects_v2(
        Bucket=MINIO_BUCKET,
        Prefix=f"00_Inbox/processed/{TODAY}-E2E-Test",
    )
    files = [o["Key"] for o in resp.get("Contents", [])]
    check("task_file_created", len(files) > 0, f"found={files}")

    if files:
        content = client.get_object(Bucket=MINIO_BUCKET, Key=files[0])["Body"].read().decode()
        check("task_file_has_content", len(content) > 100, f"bytes={len(content)}")
        check("task_format_valid", "- [ ]" in content and "[area::" in content)

    # Check run log written
    log_resp = client.list_objects_v2(
        Bucket=MINIO_BUCKET,
        Prefix=f"99_System/logs/brain-dump-processor-{TODAY}",
    )
    log_files = [o["Key"] for o in log_resp.get("Contents", [])]
    check("run_log_written", len(log_files) > 0, f"found={log_files}")

    if log_files:
        log_content = client.get_object(Bucket=MINIO_BUCKET, Key=log_files[0])["Body"].read().decode()
        try:
            log_data = json.loads(log_content)
            check("run_log_valid_json", True)
            check("run_log_status_success", log_data.get("status") in ("success", "partial"),
                  f"status={log_data.get('status')}")
        except json.JSONDecodeError:
            check("run_log_valid_json", False)


def cleanup(client):
    """Delete test artifacts from MinIO."""
    print("→ Cleanup...")
    try:
        client.delete_object(Bucket=MINIO_BUCKET, Key=TEST_BRAIN_DUMP_KEY)
    except ClientError:
        pass

    # Delete task output files
    resp = client.list_objects_v2(
        Bucket=MINIO_BUCKET,
        Prefix=f"00_Inbox/processed/{TODAY}-E2E-Test",
    )
    for obj in resp.get("Contents", []):
        client.delete_object(Bucket=MINIO_BUCKET, Key=obj["Key"])

    print("  Cleaned up test artifacts")


def main():
    print("=" * 50)
    print("E2E Test — ObsidianHomeOrchestrator v2")
    print(f"Date: {TODAY}")
    print("=" * 50)

    client = s3()

    try:
        setup(client)
        run_processor()
        verify_outputs(client)
    finally:
        cleanup(client)

    print()
    print(f"Results: {len(CHECKS_PASS)} passed, {len(CHECKS_FAIL)} failed")
    if CHECKS_FAIL:
        print(f"FAILED: {', '.join(CHECKS_FAIL)}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED ✅")
        sys.exit(0)


if __name__ == "__main__":
    main()

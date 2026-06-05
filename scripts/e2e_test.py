#!/usr/bin/env python3
"""
scripts/e2e_test.py
End-to-end pipeline test for ObsidianHomeOrchestrator.

Writes a test brain dump to MinIO, runs the processor, verifies output
files exist, then cleans up. Exit 0 = all pass.

Usage:
    python3 scripts/e2e_test.py
"""
import io
import json
import os
import sys
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")  # Required: set in .env
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")  # Required: set in .env
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")

N8N_HOST = os.environ.get("N8N_HOST", "http://192.168.1.121:5678")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")
# Floor required by Track A (2026-04-25). The blank-email regression on
# emailSend@2 + emailFormat:"both" produced 364–678 B SMTP envelopes for
# 13.6 kB upstream HTML. Anything below 1 kB means HTML is being dropped.
SMTP_MESSAGE_SIZE_FLOOR = 1024

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
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, capture_output=True, cwd=str(REPO_ROOT), env=env)
    stdout = result.stdout.decode("utf-8", errors="replace")
    print(stdout[-2000:] if len(stdout) > 2000 else stdout)
    check("processor_exit_code", result.returncode == 0, f"exit={result.returncode}")

    # Extract JSON — find last top-level {...} block in stdout
    output = {}
    try:
        start = stdout.rfind("{")
        end = stdout.rfind("}")
        if start >= 0 and end > start:
            output = json.loads(stdout[start:end + 1])
            check("output_parseable", True, f"parsed {len(output)} keys")
        else:
            check("output_parseable", False, "no JSON block found in stdout")
    except json.JSONDecodeError as e:
        check("output_parseable", False, str(e))

    check("tasks_written", output.get("tasks_written", 0) > 0,
          f"tasks_written={output.get('tasks_written', 0)}")
    check("no_errors", len(output.get("errors", [])) == 0,
          f"errors={output.get('errors', [])}")


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


def _n8n_request(method: str, path: str, payload: dict | None = None, timeout: int = 30):
    url = f"{N8N_HOST.rstrip('/')}/api/v1{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-N8N-API-KEY", N8N_API_KEY)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        if not body:
            return {}
        return json.loads(body)


def _find_smtp_message_size(execution_payload: dict) -> tuple[int | None, str | None]:
    """
    Walk an n8n execution result and return (messageSize, nodeName) for the
    first emailSend node output found. Returns (None, None) if no email
    node fired.
    """
    run_data = (
        execution_payload.get("data", {})
        .get("resultData", {})
        .get("runData", {})
    )
    if not isinstance(run_data, dict):
        return None, None
    for node_name, runs in run_data.items():
        if not isinstance(runs, list) or not runs:
            continue
        for run in runs:
            outputs = (run or {}).get("data", {}).get("main", [])
            if not isinstance(outputs, list):
                continue
            for branch in outputs:
                if not isinstance(branch, list):
                    continue
                for item in branch:
                    if not isinstance(item, dict):
                        continue
                    json_blob = item.get("json", {}) or {}
                    if "messageSize" in json_blob:
                        try:
                            return int(json_blob["messageSize"]), node_name
                        except (TypeError, ValueError):
                            pass
    return None, None


def verify_email_message_size():
    """
    Track A regression guard: trigger morning-briefing via n8n REST,
    pull the execution data, and assert SMTP messageSize > floor (1024).

    Why: emailSend@2 + emailFormat:"both" silently drops the HTML body
    on n8n 2.13.4, producing 364–678 B SMTP envelopes for 13 kB+ HTML.
    A test that doesn't probe SMTP envelope size cannot detect the bug.
    """
    print("→ Verifying SMTP message size on a real email send...")

    if not N8N_API_KEY:
        check("smtp_message_size_floor", False,
              "N8N_API_KEY not set — cannot trigger workflow")
        return

    target_name_substr = "Morning Briefing"
    try:
        wf_list = _n8n_request("GET", "/workflows")
    except Exception as exc:
        check("smtp_message_size_floor", False,
              f"n8n API unreachable: {exc}")
        return

    workflow_id = None
    workflow_name = None
    for wf in wf_list.get("data", []):
        if target_name_substr in wf.get("name", ""):
            workflow_id = wf.get("id")
            workflow_name = wf.get("name")
            break
    if not workflow_id:
        check("smtp_message_size_floor", False,
              f"workflow matching {target_name_substr!r} not found")
        return

    print(f"  Triggering workflow: {workflow_name} ({workflow_id})")
    try:
        run = _n8n_request("POST", f"/workflows/{workflow_id}/execute", payload={})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        check("smtp_message_size_floor", False,
              f"trigger HTTP {exc.code}: {body}")
        return
    except Exception as exc:
        check("smtp_message_size_floor", False, f"trigger failed: {exc}")
        return

    execution_id = (run.get("data") or run).get("executionId") or run.get("id")
    if not execution_id:
        # Some n8n builds return the new execution wrapped in {"data": {...}}
        execution_id = run.get("data", {}).get("id")
    if not execution_id:
        check("smtp_message_size_floor", False,
              f"trigger returned no executionId: {json.dumps(run)[:200]}")
        return

    # Poll for completion (most workflows under 10s; allow up to 60s).
    deadline = time.time() + 60
    exec_payload = None
    while time.time() < deadline:
        try:
            exec_payload = _n8n_request(
                "GET", f"/executions/{execution_id}?includeData=true"
            )
        except Exception as exc:
            check("smtp_message_size_floor", False,
                  f"execution fetch failed: {exc}")
            return
        if exec_payload.get("finished"):
            break
        time.sleep(1)

    if not exec_payload or not exec_payload.get("finished"):
        check("smtp_message_size_floor", False,
              f"execution {execution_id} did not finish in 60s")
        return

    if exec_payload.get("status") not in (None, "success"):
        check("smtp_message_size_floor", False,
              f"execution {execution_id} status={exec_payload.get('status')}")
        return

    msg_size, node_name = _find_smtp_message_size(exec_payload)
    if msg_size is None:
        check("smtp_message_size_floor", False,
              f"no emailSend output found in execution {execution_id}")
        return

    detail = f"node={node_name!r} messageSize={msg_size} (floor={SMTP_MESSAGE_SIZE_FLOOR})"
    check("smtp_message_size_floor", msg_size > SMTP_MESSAGE_SIZE_FLOOR, detail)


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
        verify_email_message_size()
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

#!/usr/bin/env python3
"""
scripts/health_check.py
Health check for ObsidianHomeOrchestrator: verifies MinIO, n8n, and key vault files.

Returns JSON to stdout. Exit code 0 = all pass, 1 = any failure.

Usage:
    python3 scripts/health_check.py
    python3 scripts/health_check.py --json   # machine-readable output
"""
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

import boto3
import requests
from botocore.client import Config
from botocore.exceptions import ClientError


MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")  # Set in .env
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")  # Set in .env
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")
N8N_HOST = os.environ.get("N8N_HOST", "http://192.168.1.121:5678")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

_RUNNER_TIMEOUT_RE = re.compile(
    r"task request timed out after \d+ seconds?"
    r"|matched to a runner"
    r"|requestExpired",
    re.IGNORECASE,
)

_DISK_FULL_RE = re.compile(
    r"ENOSPC"
    r"|no space left on device"
    r"|disk (?:is )?full",
    re.IGNORECASE,
)

REQUIRED_VAULT_FILES = [
    "000_Master Dashboard/North Star.md",
    "10_Active Projects/Active Personal/!!! MASTER TASK LIST.md",
    "40_Timeline_Weekly/Daily/.gitkeep",
    "99_System/logs/.gitkeep",
]

REQUIRED_BRAIN_DUMP_PREFIX = "00_Inbox/brain-dumps/"


@dataclass
class HealthResult:
    component: str
    status: str   # "pass" | "fail" | "warn"
    message: str
    details: dict


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def check_minio() -> HealthResult:
    """Verify MinIO is reachable and bucket exists."""
    try:
        s3 = _s3_client()
        s3.head_bucket(Bucket=MINIO_BUCKET)
        return HealthResult(
            component="minio",
            status="pass",
            message=f"Bucket '{MINIO_BUCKET}' accessible at {MINIO_ENDPOINT}",
            details={"endpoint": MINIO_ENDPOINT, "bucket": MINIO_BUCKET},
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        return HealthResult(
            component="minio",
            status="fail",
            message=f"MinIO error: {code}",
            details={"error": str(e)},
        )
    except Exception as e:
        return HealthResult(
            component="minio",
            status="fail",
            message=f"MinIO unreachable: {e}",
            details={"error": str(e)},
        )


def check_n8n() -> HealthResult:
    """Verify n8n is reachable."""
    try:
        r = requests.get(f"{N8N_HOST}/healthz", timeout=5)
        if r.status_code == 200:
            return HealthResult(
                component="n8n",
                status="pass",
                message=f"n8n healthy at {N8N_HOST}",
                details={"status_code": r.status_code},
            )
        return HealthResult(
            component="n8n",
            status="fail",
            message=f"n8n returned HTTP {r.status_code}",
            details={"status_code": r.status_code},
        )
    except Exception as e:
        return HealthResult(
            component="n8n",
            status="fail",
            message=f"n8n unreachable: {e}",
            details={"error": str(e)},
        )


def check_vault_files() -> HealthResult:
    """Verify required vault files exist in MinIO."""
    try:
        s3 = _s3_client()
        missing = []
        found = []
        for key in REQUIRED_VAULT_FILES:
            try:
                s3.head_object(Bucket=MINIO_BUCKET, Key=key)
                found.append(key)
            except ClientError:
                missing.append(key)

        if missing:
            return HealthResult(
                component="vault_files",
                status="fail",
                message=f"{len(missing)} required file(s) missing",
                details={"missing": missing, "found": found},
            )
        return HealthResult(
            component="vault_files",
            status="pass",
            message=f"All {len(REQUIRED_VAULT_FILES)} required files present",
            details={"found": found},
        )
    except Exception as e:
        return HealthResult(
            component="vault_files",
            status="fail",
            message=f"Vault file check failed: {e}",
            details={"error": str(e)},
        )


def check_brain_dumps() -> HealthResult:
    """Verify brain dump files exist and count them."""
    try:
        s3 = _s3_client()
        resp = s3.list_objects_v2(Bucket=MINIO_BUCKET, Prefix=REQUIRED_BRAIN_DUMP_PREFIX)
        files = [
            obj["Key"].split("/")[-1]
            for obj in resp.get("Contents", [])
            if not obj["Key"].endswith("/") and obj["Size"] > 0
        ]
        if not files:
            return HealthResult(
                component="brain_dumps",
                status="warn",
                message="No brain dump files found",
                details={"prefix": REQUIRED_BRAIN_DUMP_PREFIX},
            )
        return HealthResult(
            component="brain_dumps",
            status="pass",
            message=f"{len(files)} brain dump file(s) found",
            details={"files": files, "count": len(files)},
        )
    except Exception as e:
        return HealthResult(
            component="brain_dumps",
            status="fail",
            message=f"Brain dump check failed: {e}",
            details={"error": str(e)},
        )


def check_n8n_task_runner_recent_errors() -> HealthResult:
    """
    Inspect recent failed executions for n8n task-runner stalls.

    Behavior:
      - PASS  → no runner-timeout errors at all (or N8N_API_KEY not set: skipped-PASS)
      - WARN  → runner timeout(s) found older than 24h (system has self-recovered)
      - FAIL  → runner timeout(s) found within last 24h (capacity issue or
                schedule collision is currently degrading the pipeline)
    """
    if not N8N_API_KEY:
        return HealthResult(
            component="n8n_task_runner_recent_errors",
            status="pass",
            message="Skipped (N8N_API_KEY not set)",
            details={"reason": "no_api_key"},
        )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    timeouts: list[dict] = []
    older_count = 0

    try:
        # Fetch last ~50 errored executions across the whole instance.
        r = requests.get(
            f"{N8N_HOST}/api/v1/executions",
            params={"status": "error", "limit": 50},
            headers={"X-N8N-API-KEY": N8N_API_KEY},
            timeout=10,
        )
        r.raise_for_status()
        execs = r.json().get("data", [])
    except Exception as e:
        return HealthResult(
            component="n8n_task_runner_recent_errors",
            status="warn",
            message=f"Could not query n8n executions API: {e}",
            details={"error": str(e)},
        )

    for ex in execs:
        ex_id = ex.get("id")
        if not ex_id:
            continue
        try:
            d = requests.get(
                f"{N8N_HOST}/api/v1/executions/{ex_id}",
                params={"includeData": "true"},
                headers={"X-N8N-API-KEY": N8N_API_KEY},
                timeout=10,
            ).json()
        except Exception:
            continue
        err = d.get("data", {}).get("resultData", {}).get("error", {}) or {}
        msg = err.get("message", "") or ""
        if not _RUNNER_TIMEOUT_RE.search(msg):
            continue
        started = ex.get("startedAt") or d.get("startedAt") or ""
        try:
            dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            dt = None
        record = {
            "execution_id": ex_id,
            "started_at": started,
            "workflow_id": ex.get("workflowId"),
            "error": msg[:200],
        }
        if dt and dt >= cutoff:
            timeouts.append(record)
        else:
            older_count += 1

    if timeouts:
        return HealthResult(
            component="n8n_task_runner_recent_errors",
            status="fail",
            message=(f"{len(timeouts)} task-runner timeout(s) in last 24h "
                     f"({older_count} older, ignored)"),
            details={"recent": timeouts, "older_count": older_count,
                     "fix": "RUNBOOK § Task-runner recovery"},
        )
    if older_count:
        return HealthResult(
            component="n8n_task_runner_recent_errors",
            status="warn",
            message=f"{older_count} historical runner timeout(s) — none in last 24h",
            details={"older_count": older_count},
        )
    return HealthResult(
        component="n8n_task_runner_recent_errors",
        status="pass",
        message="No task-runner timeouts in recent executions",
        details={"checked": len(execs)},
    )


# Execution-backlog canary. binaryData accrues on the n8n LXC disk per
# execution (filesystem mode), so retained-execution count is a shell-free
# proxy for disk pressure. With EXECUTIONS_DATA_PRUNE on (cap 500) the steady
# state is a few hundred. Crossing these means pruning is off / disk is at
# risk — the 2026-05-31 ENOSPC incident hit ~860 with no pruning.
EXEC_BACKLOG_WARN = 1200
EXEC_BACKLOG_FAIL = 2500
_EXEC_BACKLOG_MAX_PAGES = 40   # 250/page → caps the scan at 10k


def check_n8n_execution_backlog() -> HealthResult:
    """
    Count retained n8n executions as a disk-pressure early-warning.

    Behavior:
      - PASS → backlog under EXEC_BACKLOG_WARN (or N8N_API_KEY not set: skipped-PASS)
      - WARN → backlog >= EXEC_BACKLOG_WARN — pruning likely off; set
               EXECUTIONS_DATA_PRUNE (RUNBOOK § Disk-Full / Execution Pruning)
      - FAIL → backlog >= EXEC_BACKLOG_FAIL — disk fill imminent; prune now
    """
    if not N8N_API_KEY:
        return HealthResult(
            component="n8n_execution_backlog",
            status="pass",
            message="Skipped (N8N_API_KEY not set)",
            details={"reason": "no_api_key"},
        )

    total = 0
    cursor = None
    try:
        for _ in range(_EXEC_BACKLOG_MAX_PAGES):
            params = {"limit": 250}
            if cursor:
                params["cursor"] = cursor
            r = requests.get(
                f"{N8N_HOST}/api/v1/executions",
                params=params,
                headers={"X-N8N-API-KEY": N8N_API_KEY},
                timeout=15,
            )
            r.raise_for_status()
            body = r.json()
            total += len(body.get("data", []))
            cursor = body.get("nextCursor")
            if not cursor:
                break
    except Exception as e:
        return HealthResult(
            component="n8n_execution_backlog",
            status="warn",
            message=f"Could not count n8n executions: {e}",
            details={"error": str(e)},
        )

    capped = bool(cursor)  # still more pages than we scanned
    if total >= EXEC_BACKLOG_FAIL:
        status, msg = "fail", f"{total}{'+' if capped else ''} executions retained — disk fill imminent, prune now"
    elif total >= EXEC_BACKLOG_WARN:
        status, msg = "warn", f"{total} executions retained — enable EXECUTIONS_DATA_PRUNE"
    else:
        status, msg = "pass", f"{total} executions retained (under {EXEC_BACKLOG_WARN})"
    return HealthResult(
        component="n8n_execution_backlog",
        status=status,
        message=msg,
        details={"retained": total, "scan_capped": capped,
                 "warn_at": EXEC_BACKLOG_WARN, "fail_at": EXEC_BACKLOG_FAIL,
                 "fix": "RUNBOOK § Disk-Full / Execution Pruning"},
    )


def check_n8n_disk_errors() -> HealthResult:
    """
    Scan recent failed executions for disk-full (ENOSPC) errors.

    This watches the *actual* failure mode directly, unlike
    check_n8n_execution_backlog which only counts retained executions as a
    proxy for disk pressure. In the 2026-06-05 incident the Proxmox HOST root
    LV filled (a stale 48G photo-sync copy + unrotated backups) — NOT the n8n
    binaryData itself — so the backlog count stayed green (~220) while every
    binary-writing workflow failed ENOSPC for days. A symptom-level canary
    catches that regardless of which filesystem fills.

    Behavior:
      - PASS → no ENOSPC errors (or N8N_API_KEY not set: skipped-PASS)
      - WARN → ENOSPC error(s) older than 24h (a disk has since recovered)
      - FAIL → ENOSPC error(s) within last 24h (a disk is full NOW)
    """
    if not N8N_API_KEY:
        return HealthResult(
            component="n8n_disk_errors",
            status="pass",
            message="Skipped (N8N_API_KEY not set)",
            details={"reason": "no_api_key"},
        )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent: list[dict] = []
    older_count = 0

    try:
        r = requests.get(
            f"{N8N_HOST}/api/v1/executions",
            params={"status": "error", "limit": 50},
            headers={"X-N8N-API-KEY": N8N_API_KEY},
            timeout=10,
        )
        r.raise_for_status()
        execs = r.json().get("data", [])
    except Exception as e:
        return HealthResult(
            component="n8n_disk_errors",
            status="warn",
            message=f"Could not query n8n executions API: {e}",
            details={"error": str(e)},
        )

    for ex in execs:
        ex_id = ex.get("id")
        if not ex_id:
            continue
        try:
            d = requests.get(
                f"{N8N_HOST}/api/v1/executions/{ex_id}",
                params={"includeData": "true"},
                headers={"X-N8N-API-KEY": N8N_API_KEY},
                timeout=10,
            ).json()
        except Exception:
            continue
        err = d.get("data", {}).get("resultData", {}).get("error", {}) or {}
        msg = err.get("message", "") or ""
        if not _DISK_FULL_RE.search(msg):
            continue
        started = ex.get("startedAt") or d.get("startedAt") or ""
        try:
            dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            dt = None
        record = {
            "execution_id": ex_id,
            "started_at": started,
            "workflow_id": ex.get("workflowId"),
            "error": msg[:200],
        }
        if dt and dt >= cutoff:
            recent.append(record)
        else:
            older_count += 1

    if recent:
        return HealthResult(
            component="n8n_disk_errors",
            status="fail",
            message=(f"{len(recent)} disk-full (ENOSPC) error(s) in last 24h "
                     "— verify `df -h` (a disk filled recently)"),
            details={"recent": recent, "older_count": older_count,
                     "fix": "RUNBOOK § Disk-Full — check `df -h /` on the "
                            "Proxmox host (pve-root), not just n8n binaryData"},
        )
    if older_count:
        return HealthResult(
            component="n8n_disk_errors",
            status="warn",
            message=f"{older_count} historical ENOSPC error(s) — none in last 24h",
            details={"older_count": older_count},
        )
    return HealthResult(
        component="n8n_disk_errors",
        status="pass",
        message="No disk-full (ENOSPC) errors in recent executions",
        details={"checked": len(execs)},
    )


def run_all_checks() -> list[HealthResult]:
    return [
        check_minio(),
        check_n8n(),
        check_vault_files(),
        check_brain_dumps(),
        check_n8n_task_runner_recent_errors(),
        check_n8n_execution_backlog(),
        check_n8n_disk_errors(),
    ]


def main():
    results = run_all_checks()
    # Treat WARN as non-failing for overall status — only FAIL flips the exit code.
    has_fail = any(r.status == "fail" for r in results)

    output = {
        "status": "fail" if has_fail else "pass",
        "checks": [asdict(r) for r in results],
    }

    if "--json" in sys.argv:
        print(json.dumps(output, indent=2))
    else:
        for r in results:
            icon = "[PASS]" if r.status == "pass" else ("[WARN]" if r.status == "warn" else "[FAIL]")
            print(f"{icon} {r.component}: {r.message}")
        print()
        print(f"Overall: {'PASS' if not has_fail else 'FAIL'}")

    sys.exit(0 if not has_fail else 1)


if __name__ == "__main__":
    main()

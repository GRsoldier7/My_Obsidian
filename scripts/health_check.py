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
import sys
from dataclasses import dataclass, asdict

import boto3
import requests
from botocore.client import Config
from botocore.exceptions import ClientError


MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")  # Set in .env
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")  # Set in .env
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")
N8N_HOST = os.environ.get("N8N_HOST", "http://192.168.1.121:5678")

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


def run_all_checks() -> list[HealthResult]:
    return [
        check_minio(),
        check_n8n(),
        check_vault_files(),
        check_brain_dumps(),
    ]


def main():
    results = run_all_checks()
    all_pass = all(r.status == "pass" for r in results)

    output = {
        "status": "pass" if all_pass else "fail",
        "checks": [asdict(r) for r in results],
    }

    if "--json" in sys.argv:
        print(json.dumps(output, indent=2))
    else:
        for r in results:
            icon = "[PASS]" if r.status == "pass" else ("[WARN]" if r.status == "warn" else "[FAIL]")
            print(f"{icon} {r.component}: {r.message}")
        print()
        print(f"Overall: {'PASS' if all_pass else 'FAIL'}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()

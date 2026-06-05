#!/usr/bin/env python3
"""
tools/build_health_dashboard.py — Wave-X H3 skeleton.

Reads recent run-log objects from MinIO `99_System/logs/`, rolls them up by
workflow, and writes a single human-readable pane to
`99_System/health.md`. Goal: Aaron answers "is the system healthy?" in <30s
from one vault note instead of reading JSON.

Outputs (idempotent, verified-write):

    99_System/health.md   — Markdown table rendered for Obsidian

Exit codes:
    0 — wrote (or noop) successfully
    1 — could not reach MinIO or write failed
    2 — invalid env

Usage:

    set -a && source .env && set +a && python3 tools/build_health_dashboard.py
    # or:
    make ENV=1 health-dashboard

Run-log JSON shapes vary by workflow; this script reads what it can and
falls back to "unknown" rather than crashing on schema drift. New workflows
land here automatically — every key under `99_System/logs/<workflow>-YYYY-
MM-DD.json` is grouped by the prefix before the date.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any

import boto3
from botocore.client import Config

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.s3_verified import put_text_verified  # noqa: E402

LOG_PREFIX = "99_System/logs/"
DASH_KEY = "99_System/health.md"
DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})(?:-\d{2})?\.json$")


def _required_env() -> dict[str, str]:
    missing = [v for v in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY",
                           "MINIO_SECRET_KEY", "MINIO_BUCKET")
               if not os.environ.get(v)]
    if missing:
        print(f"ERR: missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)
    return {v: os.environ[v] for v in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY",
                                       "MINIO_SECRET_KEY", "MINIO_BUCKET")}


def _s3_client(env: dict[str, str]):
    return boto3.client(
        "s3",
        endpoint_url=env["MINIO_ENDPOINT"],
        aws_access_key_id=env["MINIO_ACCESS_KEY"],
        aws_secret_access_key=env["MINIO_SECRET_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _parse_log_key(key: str) -> tuple[str, str] | None:
    """Return (workflow_name, date) or None if the key isn't a log object."""
    leaf = key[len(LOG_PREFIX):]
    m = DATE_RE.search(leaf)
    if not m:
        return None
    date = m.group(1)
    # workflow prefix is everything before the `-YYYY-MM-DD…` tail
    name = leaf[:m.start()]
    return name, date


def collect_recent(s3, bucket: str, days: int = 14) -> dict[str, list[dict]]:
    """Group log objects by workflow name, sorted ascending by date."""
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    by_wf: dict[str, list[dict]] = defaultdict(list)
    token = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": LOG_PREFIX}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            parsed = _parse_log_key(obj["Key"])
            if not parsed:
                continue
            wf, date = parsed
            if date < cutoff:
                continue
            by_wf[wf].append({
                "key": obj["Key"],
                "date": date,
                "size": obj["Size"],
                "lm": obj["LastModified"].isoformat(),
            })
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    for wf in by_wf:
        by_wf[wf].sort(key=lambda x: x["date"])
    return by_wf


def fetch_status(s3, bucket: str, key: str) -> dict[str, Any]:
    """Best-effort read of a run-log JSON. Returns {} on any parse error so a
    single corrupt log doesn't break the whole dashboard."""
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        return json.loads(body)
    except Exception:
        return {}


def _status_glyph(s: str) -> str:
    return {
        "success": "✅",
        "pass":    "✅",
        "ok":      "✅",
        "skipped": "⏭️",
        "noop":    "⏭️",
        "fail":    "❌",
        "error":   "❌",
        "partial": "⚠️",
    }.get(str(s).lower(), "❓")


def _render(by_wf: dict[str, list[dict]], statuses: dict[str, dict]) -> str:
    today = dt.date.today().isoformat()
    lines = [
        "---",
        "tag: oho/health",
        f"generated: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        "---",
        "",
        f"# 📡 OHO Health — {today}",
        "",
        "Wave-X H3 dashboard. Rolled up from `99_System/logs/` (last 14 days).",
        "Regenerate: `make ENV=1 health-dashboard`.",
        "",
        "## Per-workflow last-run signal",
        "",
        "| Workflow | Last run | Status | Runs (14d) | Last log key |",
        "|---|---|---|---:|---|",
    ]
    for wf in sorted(by_wf):
        runs = by_wf[wf]
        last = runs[-1]
        st = statuses.get(last["key"], {})
        status = st.get("status") or "unknown"
        skip = st.get("skip_reason") or ""
        status_cell = f"{_status_glyph(status)} `{status}`"
        if skip:
            status_cell += f" · _{skip}_"
        lines.append(
            f"| `{wf}` | {last['date']} | {status_cell} | {len(runs)} | "
            f"`{last['key']}` |"
        )
    lines += [
        "",
        "## Recent skip reasons (last 14d)",
        "",
    ]
    skip_counts: dict[str, int] = defaultdict(int)
    for runs in by_wf.values():
        for r in runs:
            st = statuses.get(r["key"], {})
            reason = st.get("skip_reason")
            if reason:
                skip_counts[reason] += 1
    if not skip_counts:
        lines.append("_No `skip_reason` values in the window._")
    else:
        lines.append("| Reason | Count |")
        lines.append("|---|---:|")
        for reason, n in sorted(skip_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| `{reason}` | {n} |")
    lines += [
        "",
        "## Coverage gaps",
        "",
        "Workflows with **zero log objects** in the last 14d (potential silent failures):",
        "",
    ]
    expected = {
        "brain-dump-processor", "daily-note-creator", "morning-briefing",
        "weekly-digest", "link-enricher", "live-dashboard-updater",
        "article-processor", "system-health-monitor", "vault-health-report",
    }
    silent = sorted(expected - set(by_wf.keys()))
    if not silent:
        lines.append("_None — every expected workflow has logged in the window._")
    else:
        for wf in silent:
            lines.append(f"- ⚠️  `{wf}` — no logs in 14d")
    lines.append("")
    return "\n".join(lines)


def write_dashboard(s3, bucket: str, content: str) -> None:
    put_text_verified(
        s3, bucket, DASH_KEY, content,
        content_type="text/markdown; charset=utf-8",
    )


def main() -> int:
    env = _required_env()
    s3 = _s3_client(env)
    by_wf = collect_recent(s3, env["MINIO_BUCKET"])
    # Only fetch the LATEST log per workflow to keep the dashboard cheap.
    latest_keys = [runs[-1]["key"] for runs in by_wf.values()]
    statuses = {k: fetch_status(s3, env["MINIO_BUCKET"], k) for k in latest_keys}
    content = _render(by_wf, statuses)
    write_dashboard(s3, env["MINIO_BUCKET"], content)
    print(f"OK wrote {DASH_KEY} ({len(content)} chars, {len(by_wf)} workflows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

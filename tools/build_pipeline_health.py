#!/usr/bin/env python3
"""
tools/build_pipeline_health.py
Layer 1 of the observability stack — surfaces n8n workflow truth into the vault.

Outputs:
    99_System/Pipeline Health.md   (always)
    00_Inbox/daily-summary.md      (when --daily-summary flag is set)

Modes:
    default  — fetch live n8n state, render Pipeline Health.md
    --daily-summary  — also write daily-summary.md (overwritten daily)
    --print-anomalies-json  — print high-severity anomalies as JSON to stdout
                              (used by the audit script in CI)
    --offline  — skip n8n calls; still render run-log-derived view

The script is safe to run from any host that can reach MinIO. n8n is optional —
if unreachable, the report degrades gracefully instead of failing the whole job.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3
import requests
from botocore.client import Config
from botocore.exceptions import ClientError

# Make sibling import work whether invoked as module or script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_detector import detect_anomalies, has_high_severity  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")
N8N_HOST = os.environ.get("N8N_HOST", "http://192.168.1.121:5678")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

PIPELINE_HEALTH_KEY = "99_System/Pipeline Health.md"
DAILY_SUMMARY_KEY = "00_Inbox/daily-summary.md"
LOG_PREFIX = "99_System/logs/"
MTL_KEY = "10_Active Projects/Active Personal/!!! MASTER TASK LIST.md"

# Map n8n display name → short workflow id used in run-log filenames.
# Order matters for substring matching — most specific first.
NAME_TO_SHORT = [
    ("Brain Dump Processor", "brain-dump-processor"),
    ("Daily Note Creator", "daily-note-creator"),
    ("Morning Briefing", "morning-briefing"),
    ("Overdue Task Alert", "overdue-task-alert"),
    ("Article Processor", "article-processor"),
    ("Weekly Needle Mover", "weekly-digest"),
    ("Weekly Digest", "weekly-digest"),
    ("Vault Health Report", "vault-health"),
    ("Live Dashboard Updater", "live-dashboard"),
    ("Link Enricher", "link-enricher"),
    ("Telegram Capture", "telegram-capture"),
    ("System Health Monitor", "system-health-monitor"),
    ("Error Handler", "error-handler"),
    ("Weekend Planner", "weekend-planner"),
    ("Pipeline Health Monitor", "pipeline-health-monitor"),
    ("AI Brain", "ai-brain"),
]

DAILY_CADENCE = {
    "brain-dump-processor",
    "daily-note-creator",
    "morning-briefing",
    "overdue-task-alert",
    "article-processor",
}


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30),
        region_name="us-east-1",
    )


def short_name_for(display: str) -> str:
    for needle, short in NAME_TO_SHORT:
        if needle.lower() in display.lower():
            return short
    # fallback — slugify the display name
    return re.sub(r"[^a-z0-9]+", "-", display.lower()).strip("-")[:40]


# ── n8n REST API ─────────────────────────────────────────────────────────────

def n8n_list_active_workflows() -> list[dict]:
    if not N8N_API_KEY:
        return []
    try:
        r = requests.get(
            f"{N8N_HOST}/api/v1/workflows",
            headers={"X-N8N-API-KEY": N8N_API_KEY},
            timeout=10,
        )
        r.raise_for_status()
        return [w for w in r.json().get("data", []) if w.get("active")]
    except Exception as exc:
        print(f"[warn] n8n list workflows failed: {exc}", file=sys.stderr)
        return []


def n8n_recent_executions(workflow_id: str, limit: int = 30) -> list[dict]:
    if not N8N_API_KEY:
        return []
    try:
        r = requests.get(
            f"{N8N_HOST}/api/v1/executions",
            params={"workflowId": workflow_id, "limit": limit},
            headers={"X-N8N-API-KEY": N8N_API_KEY},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as exc:
        print(f"[warn] n8n executions for {workflow_id} failed: {exc}", file=sys.stderr)
        return []


def n8n_execution_error(execution_id: str) -> str:
    """Pull the error message for a failed execution. Best-effort."""
    if not N8N_API_KEY:
        return ""
    try:
        r = requests.get(
            f"{N8N_HOST}/api/v1/executions/{execution_id}",
            params={"includeData": "true"},
            headers={"X-N8N-API-KEY": N8N_API_KEY},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        err = data.get("data", {}).get("resultData", {}).get("error", {})
        msg = err.get("message", "")
        node = data.get("data", {}).get("resultData", {}).get("lastNodeExecuted", "")
        if msg and node:
            return f"{node}: {msg}"
        return msg or ""
    except Exception:
        return ""


def collect_workflow_stats(workflows: list[dict]) -> list[dict]:
    """For each workflow: build a stats dict the renderer + anomaly detector consume."""
    stats = []
    for wf in workflows:
        wf_id = wf["id"]
        name = wf["name"]
        execs = n8n_recent_executions(wf_id, limit=30)
        total = len(execs)
        successes = sum(1 for e in execs if e.get("status") == "success")
        errors = sum(1 for e in execs if e.get("status") == "error")
        # Avg duration in seconds
        durations = []
        for e in execs:
            started = e.get("startedAt")
            stopped = e.get("stoppedAt")
            if started and stopped:
                try:
                    s = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    t = datetime.fromisoformat(stopped.replace("Z", "+00:00"))
                    durations.append((t - s).total_seconds())
                except ValueError:
                    pass
        avg_dur = sum(durations) / len(durations) if durations else 0.0
        last = execs[0] if execs else {}
        last_error_msg = ""
        if last.get("status") == "error":
            last_error_msg = n8n_execution_error(last["id"])
        success_rate = (successes / total * 100) if total else 0.0
        stats.append({
            "id": wf_id,
            "name": name,
            "short_name": short_name_for(name),
            "active": wf.get("active", False),
            "total_runs": total,
            "successes": successes,
            "errors": errors,
            "success_rate": success_rate,
            "avg_duration_s": avg_dur,
            "last_started_at": last.get("startedAt"),
            "last_stopped_at": last.get("stoppedAt"),
            "last_status": last.get("status"),
            "last_error": last_error_msg,
        })
    return stats


# ── Run-log index from MinIO ─────────────────────────────────────────────────

LOG_FILENAME_RE = re.compile(r"^(?P<wf>[a-z0-9-]+?)-(?P<date>\d{4}-\d{2}-\d{2})(?:-\d+)?\.json$")


def fetch_run_log_index(s3) -> dict[str, list[dict]]:
    """Return {short_name: [most-recent-first run-log dicts]}."""
    index: dict[str, list[dict]] = defaultdict(list)
    try:
        paginator = s3.get_paginator("list_objects_v2")
        objects = []
        for page in paginator.paginate(Bucket=MINIO_BUCKET, Prefix=LOG_PREFIX):
            for o in page.get("Contents", []):
                objects.append(o)
        # Sort by LastModified desc — newest first
        objects.sort(key=lambda o: o["LastModified"], reverse=True)
        for o in objects[:200]:  # cap to keep this fast
            key = o["Key"]
            fname = key.rsplit("/", 1)[-1]
            m = LOG_FILENAME_RE.match(fname)
            if not m:
                continue
            wf_short = m.group("wf")
            try:
                body = s3.get_object(Bucket=MINIO_BUCKET, Key=key)["Body"].read().decode("utf-8")
                doc = json.loads(body)
            except Exception:
                continue
            doc["_key"] = key
            doc["_last_modified"] = o["LastModified"].isoformat()
            index[wf_short].append(doc)
    except Exception as exc:
        print(f"[warn] failed to load run-log index: {exc}", file=sys.stderr)
    return dict(index)


def fetch_mtl_last_modified(s3) -> datetime | None:
    try:
        head = s3.head_object(Bucket=MINIO_BUCKET, Key=MTL_KEY)
        lm = head["LastModified"]
        if lm.tzinfo is None:
            lm = lm.replace(tzinfo=timezone.utc)
        return lm
    except ClientError:
        return None


def fetch_summary_counters(s3, log_index: dict, now: datetime) -> dict:
    """Aggregate metrics for the daily summary callout."""
    cutoff = now - timedelta(hours=24)
    tasks = 0
    brain_dumps = 0
    articles_enriched = 0
    emails_sent = 0
    runs_24h = 0
    runs_24h_success = 0

    for wf_short, logs in log_index.items():
        for log in logs:
            ts = log.get("finished_at") or log.get("_last_modified")
            try:
                dt = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt < cutoff:
                continue
            runs_24h += 1
            if log.get("status") == "success":
                runs_24h_success += 1
            if wf_short == "brain-dump-processor":
                tasks += int(log.get("tasks_extracted") or 0)
                brain_dumps += int(log.get("files_with_content") or 0)
            if wf_short == "link-enricher":
                articles_enriched += int(log.get("enriched") or log.get("items_processed") or 0)
            if log.get("body_length"):
                emails_sent += 1

    success_pct = (runs_24h_success / runs_24h * 100) if runs_24h else 0.0
    silent_zeros = sum(
        1 for wf in ("brain-dump-processor", "article-processor")
        for log in log_index.get(wf, [])[:1]
        if log.get("status") in ("skipped", "success")
        and not any([log.get("tasks_extracted"), log.get("articles_queued"),
                    log.get("articles_processed")])
    )

    return {
        "tasks": tasks,
        "brain_dumps": brain_dumps,
        "articles_enriched": articles_enriched,
        "emails_sent": emails_sent,
        "runs_24h": runs_24h,
        "success_pct": success_pct,
        "silent_zeros": silent_zeros,
    }


# ── Rendering ────────────────────────────────────────────────────────────────

def humanize_ago(ts: str | None, now: datetime) -> str:
    if not ts:
        return "never"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ts
    delta = now - dt
    if delta < timedelta(minutes=2):
        return "just now"
    if delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() // 60)}m ago"
    if delta < timedelta(days=2):
        return f"{int(delta.total_seconds() // 3600)}h ago"
    return f"{delta.days}d ago"


def is_red(stat: dict, now: datetime) -> bool:
    """Red = needs attention."""
    if stat.get("last_status") == "error":
        return True
    if stat["short_name"] in DAILY_CADENCE:
        last = stat.get("last_started_at")
        if not last:
            return True
        try:
            dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if (now - dt) > timedelta(hours=24):
                return True
        except ValueError:
            return True
    if stat["total_runs"] >= 5 and stat["success_rate"] < 80:
        return True
    return False


def render_workflow_row(stat: dict, now: datetime) -> str:
    ago = humanize_ago(stat.get("last_started_at"), now)
    sr = stat["success_rate"]
    avg = stat["avg_duration_s"]
    line = (f"- **{stat['name']}** — last run: {ago}, "
            f"success: {sr:.0f}% ({stat['successes']}/{stat['total_runs']}), "
            f"avg: {avg:.1f}s, errors: {stat['errors']}")
    if stat.get("last_error"):
        excerpt = stat["last_error"][:140].replace("\n", " ")
        line += f"\n  - last error: `{excerpt}`"
    return line


def render_anomaly_row(a: dict) -> str:
    icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(a["severity"], "⚪")
    return (f"- {icon} **{a['rule']}** [{a['severity']}] — `{a['workflow']}`: "
            f"{a['evidence']}\n  - *Fix:* {a['suggested_fix']}")


def render_pipeline_health(stats: list[dict], anomalies: list[dict],
                           summary: dict, now: datetime) -> str:
    red = [s for s in stats if is_red(s, now)]
    green = [s for s in stats if not is_red(s, now)]
    green.sort(key=lambda s: s.get("last_started_at") or "", reverse=True)

    lines = [
        "---",
        "type: ops",
        f"updated: {now.isoformat()}",
        "---",
        "",
        "# 🩺 Pipeline Health",
        "",
        "> Auto-updated. If a row is red, the workflow needs attention.",
        "",
        "## 🔴 Needs attention",
        "",
    ]
    if red:
        for s in red:
            lines.append(render_workflow_row(s, now))
    else:
        lines.append("_None — all monitored workflows are healthy._")

    lines += ["", "## 🟢 Healthy", ""]
    if green:
        for s in green:
            lines.append(render_workflow_row(s, now))
    else:
        lines.append("_No healthy workflows reported._")

    lines += ["", "## ⚠️ Anomaly alerts", ""]
    if anomalies:
        # high first
        for sev in ("high", "medium", "low"):
            for a in anomalies:
                if a["severity"] == sev:
                    lines.append(render_anomaly_row(a))
    else:
        lines.append("_No anomalies detected._")

    lines += [
        "",
        "## 📊 Summary",
        "",
        f"- Workflows monitored: {len(stats)}",
        f"- Last 24h: {summary['runs_24h']} runs, {summary['success_pct']:.0f}% success",
        f"- Silent zeros (n8n success but empty work): {summary['silent_zeros']}",
        f"- Tasks added in 24h: {summary['tasks']}",
        f"- Brain dumps processed in 24h: {summary['brain_dumps']}",
        f"- Articles enriched in 24h: {summary['articles_enriched']}",
        "",
        "---",
        "",
        "_Source: n8n REST API + 99_System/logs/. Refreshed by `tools/build_pipeline_health.py`._",
        "",
    ]
    return "\n".join(lines)


def render_daily_summary(summary: dict, now: datetime) -> str:
    return (
        "---\n"
        "type: ops\n"
        f"updated: {now.isoformat()}\n"
        "---\n\n"
        f"> **Last 24h:** {summary['tasks']} tasks added · "
        f"{summary['brain_dumps']} brain dumps processed · "
        f"{summary['articles_enriched']} articles enriched · "
        f"{summary['emails_sent']} emails sent · "
        f"{summary['success_pct']:.0f}% pipeline success "
        f"({summary['runs_24h']} runs).\n\n"
        "_Auto-generated by `tools/build_pipeline_health.py --daily-summary`. "
        "Overwritten daily. Track A morning-briefing references this as a callout._\n"
    )


# ── S3 verified write ────────────────────────────────────────────────────────

def s3_put_verified(s3, key: str, body: str) -> dict:
    s3.put_object(Bucket=MINIO_BUCKET, Key=key,
                  Body=body.encode("utf-8"), ContentType="text/markdown")
    head = s3.head_object(Bucket=MINIO_BUCKET, Key=key)
    return {
        "ETag": head["ETag"],
        "ContentLength": head["ContentLength"],
        "LastModified": str(head["LastModified"]),
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-summary", action="store_true",
                        help="Also write 00_Inbox/daily-summary.md")
    parser.add_argument("--print-anomalies-json", action="store_true",
                        help="Print anomalies JSON to stdout (for CI gating)")
    parser.add_argument("--offline", action="store_true",
                        help="Skip n8n calls; use only run-log derived data")
    parser.add_argument("--dry-run", action="store_true",
                        help="Render to stdout, do not write to MinIO")
    args = parser.parse_args()

    if not (MINIO_ACCESS_KEY and MINIO_SECRET_KEY):
        print("ERROR: MinIO credentials missing. Run: set -a && source .env && set +a",
              file=sys.stderr)
        return 1

    s3 = s3_client()
    now = datetime.now(timezone.utc)

    workflows = [] if args.offline else n8n_list_active_workflows()
    stats = collect_workflow_stats(workflows) if workflows else []

    log_index = fetch_run_log_index(s3)

    # If n8n is offline, synthesize stats from run-log filenames so the report
    # still shows something useful.
    if not stats:
        for wf_short, logs in log_index.items():
            if not logs:
                continue
            last = logs[0]
            stats.append({
                "id": "",
                "name": wf_short,
                "short_name": wf_short,
                "active": True,
                "total_runs": len(logs),
                "successes": sum(1 for l in logs if l.get("status") == "success"),
                "errors": sum(1 for l in logs if l.get("status") == "error"),
                "success_rate": (sum(1 for l in logs if l.get("status") == "success")
                                 / len(logs) * 100),
                "avg_duration_s": 0.0,
                "last_started_at": last.get("finished_at") or last.get("_last_modified"),
                "last_status": last.get("status"),
                "last_error": last.get("error", ""),
            })

    mtl_lm = fetch_mtl_last_modified(s3)
    anomalies = detect_anomalies(stats, log_index, mtl_lm, now=now)
    summary = fetch_summary_counters(s3, log_index, now)

    if args.print_anomalies_json:
        print(json.dumps(anomalies, indent=2))

    health_md = render_pipeline_health(stats, anomalies, summary, now)
    summary_md = render_daily_summary(summary, now)

    if args.dry_run:
        print(health_md)
        if args.daily_summary:
            print("\n--- daily-summary.md ---\n")
            print(summary_md)
        return 1 if has_high_severity(anomalies) else 0

    head = s3_put_verified(s3, PIPELINE_HEALTH_KEY, health_md)
    print(f"[ok] wrote {PIPELINE_HEALTH_KEY}: ETag={head['ETag']} "
          f"size={head['ContentLength']}")

    if args.daily_summary:
        head2 = s3_put_verified(s3, DAILY_SUMMARY_KEY, summary_md)
        print(f"[ok] wrote {DAILY_SUMMARY_KEY}: ETag={head2['ETag']} "
              f"size={head2['ContentLength']}")

    print(f"[info] workflows={len(stats)} anomalies={len(anomalies)} "
          f"high={sum(1 for a in anomalies if a['severity']=='high')} "
          f"runs_24h={summary['runs_24h']}")

    return 1 if has_high_severity(anomalies) else 0


if __name__ == "__main__":
    sys.exit(main())

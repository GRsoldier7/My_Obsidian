#!/usr/bin/env python3
"""
tools/anomaly_detector.py
Programmatic anomaly detection for the Life OS automation pipeline.

Each rule produces a dict:
    {rule, severity, workflow, evidence, suggested_fix}

Severities: high (operator action required), medium (investigate), low (FYI).

Public API:
    detect_anomalies(workflow_stats, log_index, mtl_last_modified,
                     recent_execution_errors=None) -> list[dict]
        workflow_stats:           list of dicts from build_pipeline_health.collect_workflow_stats
        log_index:                dict[str, list[dict]] mapping workflow name -> recent run logs
        mtl_last_modified:        datetime of MTL file (or None)
        recent_execution_errors:  optional list of {workflow, started_at, error} dicts;
                                  used by the runner_timeout rule. Default None for
                                  backward compatibility.

The rules are intentionally simple regex/threshold checks — anything more
sophisticated belongs in a dedicated workflow. The point of this module is
to surface drift the operator cannot see by skimming n8n's UI.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

# Substrings that identify an n8n task-runner stall in an execution error message.
# Both the original "Task request timed out after 60 seconds" and the
# alternative "could not be matched to a runner" variants are caught.
RUNNER_TIMEOUT_PATTERNS = (
    re.compile(r"task request timed out after \d+ seconds?", re.IGNORECASE),
    re.compile(r"matched to a runner", re.IGNORECASE),
    re.compile(r"requestExpired", re.IGNORECASE),
    re.compile(r"task[-_ ]?runner.*?(timeout|timed out|unavailable)", re.IGNORECASE),
)


def is_runner_timeout(message: str | None) -> bool:
    if not message:
        return False
    return any(p.search(message) for p in RUNNER_TIMEOUT_PATTERNS)


# Workflows we expect to fire daily — used by stale_pipeline + silent_zero.
DAILY_CADENCE_WORKFLOWS = {
    "brain-dump-processor",
    "daily-note-creator",
    "morning-briefing",
    "overdue-task-alert",
    "article-processor",
}

# Workflows where 0 work units processed for 3+ days running is suspicious.
ZERO_WORK_SUSPECTS = {
    "brain-dump-processor",
    "article-processor",
}

EMAIL_BODY_FLOOR = 1024  # bytes; below this an email is almost certainly broken.

# Workflows we expect to write run-logs. Others (live-dashboard, link-enricher,
# error-handler) intentionally don't, so excluding them prevents noise.
EXPECT_RUNLOG = {
    "brain-dump-processor",
    "daily-note-creator",
    "morning-briefing",
    "overdue-task-alert",
    "article-processor",
    "weekly-digest",
    "vault-health",
    "system-health-monitor",
    "weekend-planner",
    "pipeline-health-monitor",
}


@dataclass
class Anomaly:
    rule: str
    severity: str  # high | medium | low
    workflow: str
    evidence: str
    suggested_fix: str
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # n8n returns ...Z; python wants +00:00
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── Rule 1: Silent zero ──────────────────────────────────────────────────────
def rule_silent_zero(log_index: dict[str, list[dict]]) -> list[Anomaly]:
    out: list[Anomaly] = []
    for wf in ZERO_WORK_SUSPECTS:
        logs = log_index.get(wf, [])
        # Expect chronologically descending; keep first 3
        recent = logs[:3]
        if len(recent) < 3:
            continue
        all_zero = True
        for log in recent:
            # different workflows use different counter keys
            counters = [
                log.get("tasks_extracted"),
                log.get("articles_queued"),
                log.get("files_with_content"),
                log.get("articles_processed"),
                log.get("items_processed"),
            ]
            if any(isinstance(c, int) and c > 0 for c in counters):
                all_zero = False
                break
        if all_zero:
            out.append(Anomaly(
                rule="silent_zero",
                severity="medium",
                workflow=wf,
                evidence=f"Last 3 run logs all show 0 items processed (dates: "
                         f"{', '.join(l.get('run_date','?') for l in recent)})",
                suggested_fix=f"Check the upstream input source for {wf}. "
                              "Brain dumps land in 00_Inbox/brain-dumps/; "
                              "articles in 00_Inbox/articles-to-process.md.",
            ))
    return out


# ── Rule 2: Stale pipeline ───────────────────────────────────────────────────
def rule_stale_pipeline(workflow_stats: list[dict], now: datetime) -> list[Anomaly]:
    out: list[Anomaly] = []
    threshold = timedelta(hours=36)
    for stat in workflow_stats:
        wf_short = stat.get("short_name", "")
        if wf_short not in DAILY_CADENCE_WORKFLOWS:
            continue
        last_run = _parse_iso(stat.get("last_started_at"))
        if last_run is None:
            out.append(Anomaly(
                rule="stale_pipeline",
                severity="high",
                workflow=wf_short,
                evidence="No executions found in n8n history",
                suggested_fix=f"Workflow {wf_short!r} has never run. "
                              "Verify it is active in n8n UI and the cron expression is valid.",
            ))
            continue
        gap = now - last_run
        if gap > threshold:
            out.append(Anomaly(
                rule="stale_pipeline",
                severity="high",
                workflow=wf_short,
                evidence=f"Last execution was {gap.total_seconds()/3600:.1f}h ago "
                         f"({last_run.isoformat()}); threshold is 36h",
                suggested_fix=f"Open n8n at http://192.168.1.121:5678, find {wf_short!r}, "
                              "and check schedule trigger + recent execution errors.",
            ))
    return out


# ── Rule 3: Quiet error (email payload too small) ────────────────────────────
def rule_quiet_error(log_index: dict[str, list[dict]]) -> list[Anomaly]:
    out: list[Anomaly] = []
    for wf, logs in log_index.items():
        for log in logs[:3]:
            body_len = log.get("body_length")
            status = log.get("status")
            # only inspect 'success' email-producing workflows
            if status == "success" and isinstance(body_len, int) and 0 < body_len < EMAIL_BODY_FLOOR:
                out.append(Anomaly(
                    rule="quiet_error",
                    severity="high",
                    workflow=wf,
                    evidence=f"{log.get('run_date','?')}: status=success but "
                             f"body_length={body_len} bytes (floor={EMAIL_BODY_FLOOR})",
                    suggested_fix=f"Open {wf} run log and inspect HTML/text generation. "
                                  "Empty-body emails are the symptom of upstream node "
                                  "returning [] but the email node continuing anyway.",
                ))
                break  # one anomaly per workflow is enough
    return out


# ── Rule 4: Run-log gap (n8n executed but no run-log on disk) ────────────────
def rule_runlog_gap(workflow_stats: list[dict], log_index: dict[str, list[dict]],
                    now: datetime) -> list[Anomaly]:
    out: list[Anomaly] = []
    window = timedelta(hours=48)
    for stat in workflow_stats:
        wf_short = stat.get("short_name", "")
        if not wf_short or wf_short not in EXPECT_RUNLOG:
            continue
        last_started = _parse_iso(stat.get("last_started_at"))
        last_status = stat.get("last_status")
        if last_started is None or (now - last_started) > window:
            continue
        # Did we get a run-log within 48h?
        recent_logs = log_index.get(wf_short, [])
        has_recent_log = False
        for log in recent_logs[:5]:
            log_dt = _parse_iso(log.get("finished_at") or log.get("run_date"))
            if log_dt and (now - log_dt) <= window:
                has_recent_log = True
                break
        if not has_recent_log and last_status == "success":
            out.append(Anomaly(
                rule="runlog_gap",
                severity="high",
                workflow=wf_short,
                evidence=f"n8n shows {last_status} execution at "
                         f"{last_started.isoformat()} but no run-log written "
                         f"to 99_System/logs/{wf_short}-*.json in last 48h",
                suggested_fix=f"Verify the 'S3: Write Log' node in {wf_short} workflow. "
                              "Silent log-write failures masquerade as healthy runs — "
                              "this is the bug class CLAUDE.md calls out.",
            ))
    return out


# ── Rule 5: MTL stagnation ───────────────────────────────────────────────────
def rule_mtl_stagnation(mtl_last_modified: datetime | None, now: datetime) -> list[Anomaly]:
    if mtl_last_modified is None:
        return [Anomaly(
            rule="mtl_stagnation",
            severity="high",
            workflow="(system)",
            evidence="MTL file not found at 10_Active Projects/Active Personal/!!! MASTER TASK LIST.md",
            suggested_fix="Run scripts/health_check.py — MTL is a required file. "
                          "If missing, restore from a daily-note backup.",
        )]
    gap = now - mtl_last_modified
    if gap > timedelta(days=5):
        return [Anomaly(
            rule="mtl_stagnation",
            severity="medium",
            workflow="(system)",
            evidence=f"MTL last modified {gap.days}d ago "
                     f"({mtl_last_modified.isoformat()}); threshold is 5d",
            suggested_fix="The pipeline isn't producing tasks. Check brain-dump-processor "
                          "and the 00_Inbox/brain-dumps/ prefix. Even one weekly captures should "
                          "have moved this file by now.",
        )]
    return []


# ── Rule 6: Runner timeout cluster ───────────────────────────────────────────
def rule_runner_timeout(recent_execution_errors: Iterable[dict] | None,
                        now: datetime) -> list[Anomaly]:
    """
    Surface n8n task-runner stalls. A single timeout in 24h is high severity;
    two or more timeouts within a 10-minute window across different workflows
    upgrades the evidence to "clustered" (a strong signal of capacity contention,
    not a one-off Code-node bug).

    Old timeouts (>24h) are intentionally NOT high severity — the runner has
    typically self-recovered by then and we don't want to page on stale state.
    """
    if not recent_execution_errors:
        return []

    window_24h = now - timedelta(hours=24)
    cluster_window = timedelta(minutes=10)

    timeouts: list[dict] = []
    for entry in recent_execution_errors:
        msg = entry.get("error") or ""
        if not is_runner_timeout(msg):
            continue
        ts = _parse_iso(entry.get("started_at") or entry.get("finished_at"))
        timeouts.append({
            "workflow": entry.get("workflow") or "(unknown)",
            "started_at": ts,
            "raw": ts.isoformat() if ts else (entry.get("started_at") or "(no timestamp)"),
            "error": msg.strip()[:160],
        })

    if not timeouts:
        return []

    recent = [t for t in timeouts if t["started_at"] and t["started_at"] >= window_24h]
    older = [t for t in timeouts if not (t["started_at"] and t["started_at"] >= window_24h)]

    out: list[Anomaly] = []

    # Cluster detection — 2+ timeouts within 10 min across different workflows.
    clusters: list[list[dict]] = []
    sorted_recent = sorted(recent, key=lambda t: t["started_at"])
    for t in sorted_recent:
        if clusters and (t["started_at"] - clusters[-1][0]["started_at"]) <= cluster_window:
            clusters[-1].append(t)
        else:
            clusters.append([t])

    for cluster in clusters:
        if len(cluster) >= 2 and len({t["workflow"] for t in cluster}) >= 2:
            wfs = ", ".join(sorted({t["workflow"] for t in cluster}))
            first = cluster[0]["raw"]
            out.append(Anomaly(
                rule="runner_timeout",
                severity="high",
                workflow=wfs,
                evidence=(f"{len(cluster)} task-runner timeouts within 10 minutes "
                          f"starting {first} across workflows: {wfs}. "
                          f"This is a runner-pool capacity stall, not a Code-node bug."),
                suggested_fix=(
                    "1) Verify schedules are staggered (no two Code-heavy workflows "
                    "share a cron minute — see RUNBOOK 'Task-runner scheduling slots'). "
                    "2) On the n8n host, restart the runner: "
                    "`docker restart n8n` (or LXC equivalent). "
                    "3) If it recurs, raise N8N_RUNNERS_TASK_TIMEOUT (default 60s) "
                    "and N8N_RUNNERS_MAX_CONCURRENCY on the n8n container, then restart."
                ),
            ))

    # Per-workflow individual timeouts in 24h (skip ones already in a cluster).
    clustered_ids = {id(t) for c in clusters if len(c) >= 2 for t in c}
    for t in recent:
        if id(t) in clustered_ids:
            continue
        out.append(Anomaly(
            rule="runner_timeout",
            severity="high",
            workflow=t["workflow"],
            evidence=(f"n8n task-runner timeout at {t['raw']}: "
                      f"{t['error'] or 'task request timed out'}"),
            suggested_fix=(
                "Code node could not reach a task runner within the timeout. "
                "Check the n8n container is healthy (`/healthz`), confirm the "
                "workflow's cron does not collide with another Code-heavy workflow, "
                "and re-run the failing execution. Persistent timeouts mean the "
                "runner pool needs more capacity (RUNBOOK has the env-var tuning)."
            ),
        ))

    # Older timeouts → low severity FYI, only one rolled-up anomaly.
    if older and not out:
        out.append(Anomaly(
            rule="runner_timeout",
            severity="low",
            workflow="(historical)",
            evidence=(f"{len(older)} runner timeout(s) >24h ago — system has "
                      f"since recovered. Most recent: "
                      f"{max(t['raw'] for t in older)}"),
            suggested_fix=(
                "No action required. Ensure schedule staggering is still in place "
                "(RUNBOOK 'Task-runner scheduling slots') so this stays historical."
            ),
        ))

    return out


# ── Public entrypoint ────────────────────────────────────────────────────────
def detect_anomalies(workflow_stats: list[dict],
                     log_index: dict[str, list[dict]],
                     mtl_last_modified: datetime | None,
                     now: datetime | None = None,
                     recent_execution_errors: Iterable[dict] | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    anomalies: list[Anomaly] = []
    anomalies.extend(rule_silent_zero(log_index))
    anomalies.extend(rule_stale_pipeline(workflow_stats, now))
    anomalies.extend(rule_quiet_error(log_index))
    anomalies.extend(rule_runlog_gap(workflow_stats, log_index, now))
    anomalies.extend(rule_mtl_stagnation(mtl_last_modified, now))
    anomalies.extend(rule_runner_timeout(recent_execution_errors, now))
    return [a.to_dict() for a in anomalies]


def has_high_severity(anomalies: list[dict]) -> bool:
    return any(a.get("severity") == "high" for a in anomalies)


if __name__ == "__main__":
    # Smoke test
    import json
    stub_stats = [{"short_name": "brain-dump-processor", "last_started_at": None,
                   "last_status": None}]
    stub_logs = {"brain-dump-processor": [
        {"run_date": "2026-04-25", "tasks_extracted": 0, "articles_queued": 0,
         "files_with_content": 0, "status": "skipped"},
        {"run_date": "2026-04-24", "tasks_extracted": 0, "articles_queued": 0,
         "files_with_content": 0, "status": "skipped"},
        {"run_date": "2026-04-23", "tasks_extracted": 0, "articles_queued": 0,
         "files_with_content": 0, "status": "skipped"},
    ]}
    out = detect_anomalies(stub_stats, stub_logs, None)
    print(json.dumps(out, indent=2))

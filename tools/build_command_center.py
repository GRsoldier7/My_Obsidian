#!/usr/bin/env python3
"""
tools/build_command_center.py
ADR-0006 — the single auto-rebuilt landing page for the Life OS.

Output: 000_Master Dashboard/!!! DAILY COMMAND CENTER.md

Section structure (locked by user 2026-05-06):
  # !!! DAILY COMMAND CENTER
  ## 🔥 Do This First
  ## 🧠 New From Brain Dumps
  ## ✅ Ready-To-Act Tasks
  ## ❓ Needs Review
  ## 📚 Articles / References
  ## 🗂 By Life Area
  ## 🧾 System/Audit Links

Visual hierarchy via Obsidian callouts (`> [!type]+/-`). Mobile-first.
Tasks render via Dataview TASK queries so checking off the rendered task
also checks the original line in MTL.

Idempotent. Re-run any time. Verified writes (head_object after PUT).

Read sources (all from MinIO):
  - 10_Active Projects/Active Personal/!!! MASTER TASK LIST.md
  - 00_Inbox/articles-to-process.md
  - 00_Inbox/review-queue.md
  - 99_System/state/last-brain-dump-summary.json     (ADR-0006 contract)
  - 99_System/extraction-receipts/                    (count + last-modified)
  - 99_System/logs/brain-dump-processor-*.json        (latest)

Write target:
  - 000_Master Dashboard/!!! DAILY COMMAND CENTER.md  (verified)
  - 000_Master Dashboard/Home.md                      (one-line redirect stub)
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")

MTL_KEY = "10_Active Projects/Active Personal/!!! MASTER TASK LIST.md"
ARTICLES_KEY = "00_Inbox/articles-to-process.md"
REVIEW_QUEUE_KEY = "00_Inbox/review-queue.md"
COMMAND_CENTER_KEY = "000_Master Dashboard/!!! DAILY COMMAND CENTER.md"
HOME_KEY = "000_Master Dashboard/Home.md"
OPERATOR_SUMMARY_KEY = "99_System/state/last-brain-dump-summary.json"
BD_LOG_PREFIX = "99_System/logs/brain-dump-processor-"
RECEIPTS_PREFIX = "99_System/extraction-receipts/"

VALID_AREAS = ["faith", "family", "business", "consulting", "work", "health", "home", "personal"]
AREA_EMOJI = {
    "faith": "🙏", "family": "👨‍👩‍👧", "business": "🚀",
    "consulting": "💼", "work": "🏢", "health": "💪",
    "home": "🏠", "personal": "🛠️",
}

# Threshold: if no brain-dump summary newer than this, render a warning.
SUMMARY_STALE_HOURS = 36

# Overdue criticality buckets (days past due).
OVERDUE_CRITICAL_DAYS = 8
OVERDUE_HIGH_DAYS = 4


# ── S3 helpers ────────────────────────────────────────────────────────────────

def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30),
        region_name="us-east-1",
    )


def s3_get(s3, key: str) -> str:
    return s3.get_object(Bucket=MINIO_BUCKET, Key=key)["Body"].read().decode("utf-8")


def s3_get_safe(s3, key: str) -> str | None:
    try:
        return s3_get(s3, key)
    except ClientError:
        return None


def s3_put_verified(s3, key: str, body: str) -> dict:
    s3.put_object(Bucket=MINIO_BUCKET, Key=key, Body=body.encode("utf-8"), ContentType="text/markdown")
    head = s3.head_object(Bucket=MINIO_BUCKET, Key=key)
    return {"ETag": head["ETag"], "ContentLength": head["ContentLength"], "LastModified": str(head["LastModified"])}


# ── Pure parsers (testable, no I/O) ──────────────────────────────────────────

OPEN_TASK_RE = re.compile(r"^- \[ \] (.+?)$")
DONE_TASK_RE = re.compile(r"^- \[x\] (.+?)$", re.IGNORECASE)
AREA_RE = re.compile(r"\[area::\s*([a-z]+)\]")
PRIORITY_RE = re.compile(r"\[priority::\s*([ABC])\]")
DUE_RE = re.compile(r"\[due::\s*(\d{4}-\d{2}-\d{2})\]")
EXPLORE_RE = re.compile(r"\[explore::\s*true\]")


def parse_mtl_open(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        m = OPEN_TASK_RE.match(line.rstrip())
        if not m:
            continue
        body = m.group(1)
        area = AREA_RE.search(body)
        prio = PRIORITY_RE.search(body)
        due = DUE_RE.search(body)
        explore = bool(EXPLORE_RE.search(body))
        # [source:: [[wikilink]]] has a triple-close `]]]` that the generic
        # [^\]]* strip can't span; strip wikilink-shaped sources first.
        cleaned = re.sub(r"\s*\[source::\s*\[\[[^\]]+\]\]\]", "", body)
        desc = re.sub(r"\s*\[(?:area|priority|due|explore|completion|source)::[^\]]*\]", "", cleaned).strip()
        out.append({
            "raw": line.rstrip(),
            "desc": desc,
            "area": area.group(1) if area else None,
            "priority": prio.group(1) if prio else None,
            "due": due.group(1) if due else None,
            "explore": explore,
        })
    return out


def pick_top_priority(open_tasks: list[dict], today: date) -> dict | None:
    """Compute the single #1 task to do right now.

    Ordering:
      1. Priority A AND most overdue
      2. Priority A with earliest due date
      3. Priority A with no due date
      4. Most overdue regardless of priority
      5. Earliest due regardless of priority
    Returns None if there are no open tasks.
    """
    if not open_tasks:
        return None

    today_ord = today.toordinal()

    def days_overdue(t: dict) -> int | None:
        if not t["due"]:
            return None
        try:
            return today_ord - date.fromisoformat(t["due"]).toordinal()
        except ValueError:
            return None

    a_overdue = []
    a_due = []
    a_no_due = []
    for t in open_tasks:
        if t["priority"] != "A":
            continue
        d = days_overdue(t)
        if d is not None and d > 0:
            a_overdue.append((d, t))
        elif t["due"]:
            a_due.append(t)
        else:
            a_no_due.append(t)

    if a_overdue:
        a_overdue.sort(key=lambda pair: -pair[0])
        return a_overdue[0][1]
    if a_due:
        a_due.sort(key=lambda t: t["due"])
        return a_due[0]
    if a_no_due:
        return a_no_due[0]

    # Fall back to priority B/C: most overdue, else earliest due.
    overdue_any = [(days_overdue(t), t) for t in open_tasks if days_overdue(t) and days_overdue(t) > 0]
    if overdue_any:
        overdue_any.sort(key=lambda pair: -pair[0])
        return overdue_any[0][1]

    with_due = [t for t in open_tasks if t["due"]]
    if with_due:
        with_due.sort(key=lambda t: t["due"])
        return with_due[0]

    return open_tasks[0]


def bucket_overdue(open_tasks: list[dict], today: date) -> dict:
    """Return {critical: [...], high: [...], recent: [...]} buckets by days-overdue."""
    today_ord = today.toordinal()
    crit, high, recent = [], [], []
    for t in open_tasks:
        if not t["due"]:
            continue
        try:
            d = today_ord - date.fromisoformat(t["due"]).toordinal()
        except ValueError:
            continue
        if d < 1:
            continue
        if d >= OVERDUE_CRITICAL_DAYS:
            crit.append((d, t))
        elif d >= OVERDUE_HIGH_DAYS:
            high.append((d, t))
        else:
            recent.append((d, t))
    return {
        "critical": [t for _, t in sorted(crit, key=lambda x: -x[0])],
        "high": [t for _, t in sorted(high, key=lambda x: -x[0])],
        "recent": [t for _, t in sorted(recent, key=lambda x: -x[0])],
    }


def parse_review_queue(text: str | None, limit: int = 8) -> list[str]:
    """Return up to `limit` `- [ ]` lines from the review queue."""
    if not text:
        return []
    items = []
    for line in text.splitlines():
        if OPEN_TASK_RE.match(line.rstrip()):
            items.append(line.rstrip())
    return items[:limit]


def summary_age_hours(summary: dict | None, *, now: datetime) -> float | None:
    if not summary or not summary.get("run_finished_at"):
        return None
    try:
        ts = datetime.fromisoformat(summary["run_finished_at"].replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() / 3600.0


# ── Section renderers (pure — string in, string out) ─────────────────────────

def render_do_this_first(top: dict | None, overdue: dict, today: date) -> str:
    lines: list[str] = ["## 🔥 Do This First", ""]

    if top is None:
        lines += [
            "> [!success]+ Nothing on fire",
            "> Open MTL is empty. Capture something or take a breath.",
            "",
        ]
    else:
        area = top["area"] or "?"
        prio = top["priority"] or "?"
        due = top["due"] or "—"
        emoji = AREA_EMOJI.get(top["area"] or "", "•")
        lines += [
            "> [!important]+ #1 PRIORITY RIGHT NOW",
            f"> **{emoji} {top['desc']}**",
            f"> ",
            f"> Area: `{area}` · Priority: `{prio}` · Due: `{due}`",
            "",
        ]

    n_crit = len(overdue["critical"])
    n_high = len(overdue["high"])
    n_recent = len(overdue["recent"])
    n_total = n_crit + n_high + n_recent

    if n_total == 0:
        lines += [
            "> [!success] Nothing overdue",
            "",
        ]
    else:
        lines.append(f"> [!warning]+ {n_total} overdue · 🔴 {n_crit} critical (8d+) · 🟠 {n_high} high (4-7d) · 🟡 {n_recent} recent (1-3d)")
        if overdue["critical"]:
            lines.append("> ")
            lines.append("> **🔴 Critical (8+ days late)**")
            for t in overdue["critical"][:5]:
                lines.append(f"> - `{t['area'] or '?'}` `{t['priority'] or '?'}` {t['desc']} (due {t['due']})")
        if overdue["high"]:
            lines.append("> ")
            lines.append("> **🟠 High (4-7 days late)**")
            for t in overdue["high"][:5]:
                lines.append(f"> - `{t['area'] or '?'}` `{t['priority'] or '?'}` {t['desc']} (due {t['due']})")
        if overdue["recent"]:
            lines.append("> ")
            lines.append("> **🟡 Recent (1-3 days late)**")
            for t in overdue["recent"][:5]:
                lines.append(f"> - `{t['area'] or '?'}` `{t['priority'] or '?'}` {t['desc']} (due {t['due']})")
        lines.append("")

    lines += [
        "> [!quote]- Q2 Rocks alignment",
        "> The five rocks today's #1 should advance:",
        "> - **Faith** — Launch social media Bible study (4 sessions)",
        "> - **Family** — Marriage Alignment Questionnaire + bi-weekly check-in",
        "> - **Business** — Echelon Seven MVP: site live, offer defined, 3 outreach convos",
        "> - **Work** — Deliver Union project + position for Parallon exit",
        "> - **Health** — Make hip decision + 3x/week gym for 8 weeks",
        "",
    ]
    return "\n".join(lines)


def render_brain_dumps(summary: dict | None, summary_age_h: float | None) -> str:
    lines: list[str] = ["## 🧠 New From Brain Dumps", ""]

    if summary is None:
        lines += [
            "> [!warning]+ No brain-dump summary on disk yet",
            "> The processor hasn't written `99_System/state/last-brain-dump-summary.json`.",
            "> Run `make run` (or wait for the next 7AM cron) to populate this.",
            "",
        ]
        return "\n".join(lines)

    if summary_age_h is not None and summary_age_h > SUMMARY_STALE_HOURS:
        lines += [
            f"> [!warning]+ Last brain-dump run is **{summary_age_h:.1f}h old** (threshold: {SUMMARY_STALE_HOURS}h)",
            "> Pipeline may be stuck. Check `99_System/logs/brain-dump-processor-*.json`.",
            "",
        ]

    finished = summary.get("run_finished_at", "—")
    status = summary.get("status", "?")
    n_added = summary.get("tasks_written", 0)
    n_review = summary.get("review_added", 0)
    n_articles = summary.get("articles_queued", 0)
    files_extracted = summary.get("files_extracted", []) or []
    files_partial = summary.get("files_partial", []) or []
    files_error = summary.get("files_error", []) or []

    # Callout kind picks green when the run is clean. Empty-but-healthy
    # (status=success, no errors, n_added=0) is GREEN not grey — Aaron asked
    # for "pipeline healthy" visibility so an empty inbox reads as "system
    # is fine, capture more" not "is something broken?" (UI audit
    # 2026-05-27 §4 win #2).
    if status == "success" and not files_error:
        callout_kind = "success"
    else:
        callout_kind = "warning"

    lines += [
        f"> [!{callout_kind}]+ Last run · `{finished}` · status: `{status}`",
        f"> ",
        f"> ✅ **{n_added} tasks added to MTL** · ❓ {n_review} routed to review · 📚 {n_articles} articles queued",
        f"> ",
        f"> 📄 Sources: extracted={len(files_extracted)} · partial={len(files_partial)} · error={len(files_error)}",
    ]
    if files_partial:
        lines.append(f"> - 🟠 Partial: {', '.join(files_partial[:5])}")
    if files_error:
        lines.append(f"> - 🔴 Error: {', '.join(str(e)[:60] for e in files_error[:5])}")
    lines.append("")

    top_added = summary.get("top_added_tasks", []) or []
    if top_added:
        lines.append("**Top added (newest run, sorted by priority):**")
        lines.append("")
        by_area = defaultdict(list)
        for t in top_added:
            by_area[t.get("area") or "_unset"].append(t)
        for area in sorted(by_area):
            emoji = AREA_EMOJI.get(area, "•")
            lines.append(f"- {emoji} **{area}**")
            for t in by_area[area]:
                prio = t.get("priority") or "?"
                lines.append(f"  - `{prio}` {t.get('desc', '').strip()}")
        lines.append("")
    else:
        # Empty-inbox or fully-dedup'd run: this is the HEALTHY steady state,
        # not a failure. Aaron specifically called out the prior italic
        # disclaimer as ambiguous ("ran but did nothing" vs "broken silently").
        # A green callout removes that ambiguity (UI audit 2026-05-27 §4 win #2).
        lines += [
            "> [!success]+ Pipeline healthy — no new tasks this run",
            "> Either the inbox was empty or every captured item dedup'd against MTL.",
            "> Capture something new in `00_Inbox/brain-dumps/` and the next cron tick will pick it up.",
            "",
        ]

    return "\n".join(lines)


def render_ready_to_act() -> str:
    return """## ✅ Ready-To-Act Tasks

> [!todo]+ Due today + Priority A

```dataview
TASK
FROM "10_Active Projects/Active Personal/!!! MASTER TASK LIST"
WHERE !completed AND ((due = date(today)) OR priority = "A")
SORT priority ASC, due ASC
GROUP BY area
```

> [!success]- Quick wins (low-friction, no due date)

```dataview
TASK
FROM "10_Active Projects/Active Personal/!!! MASTER TASK LIST"
WHERE !completed AND priority = "C" AND !due
LIMIT 10
```
"""


def render_needs_review(review_items: list[str]) -> str:
    lines: list[str] = ["## ❓ Needs Review", ""]
    if not review_items:
        lines += [
            "> [!success] Review queue clear",
            "> No low-confidence captures waiting on you.",
            "",
        ]
        return "\n".join(lines)

    lines += [
        f"> [!question]+ {len(review_items)} item(s) need a human call",
        "> Each was extracted with low confidence. Approve, edit, or delete.",
        "",
        "_(Top of the queue — full list in [review-queue.md](00_Inbox/review-queue.md))_",
        "",
    ]
    for item in review_items:
        lines.append(item)
    lines.append("")
    return "\n".join(lines)


def render_articles() -> str:
    return """## 📚 Articles / References

```dataviewjs
const path = "00_Inbox/articles-to-process.md";
try {
  const lines = (await dv.io.load(path)).split("\\n");
  const rows = [];
  let added = null;
  for (const line of lines) {
    const h = line.match(/^## Added (\\d{4}-\\d{2}-\\d{2})/);
    if (h) { added = h[1]; continue; }
    const m = line.match(/^- \\[([^\\]]+)\\]\\(([^\\)]+)\\)(.*)$/);
    if (!m) continue;
    const rest = m[3] || "";
    const title = (rest.match(/\\[title::\\s*([^\\]]+)\\]/) || [])[1] || m[1];
    const desc  = (rest.match(/\\[description::\\s*([^\\]]+)\\]/) || [])[1] || "_(no blurb yet)_";
    rows.push([added || "—", `[${title}](${m[2]})`, desc]);
  }
  rows.sort((a, b) => (b[0] || "").localeCompare(a[0] || ""));
  if (rows.length === 0) {
    dv.paragraph("_Reading queue empty._");
  } else {
    dv.table(["Added", "Article", "Blurb"], rows.slice(0, 25));
  }
} catch (e) {
  dv.paragraph("_articles-to-process.md not found._");
}
```

> [!example]- Curiosity items (`[explore:: true]`)

```dataview
TASK
FROM "10_Active Projects" OR "00_Inbox"
WHERE explore = true AND !completed
SORT area ASC, priority ASC
GROUP BY area
```
"""


def render_by_area() -> str:
    return """## 🗂 By Life Area

> [!abstract]+ All open tasks, grouped by domain — sorted priority/due

```dataview
TASK
FROM "10_Active Projects/Active Personal/!!! MASTER TASK LIST"
WHERE !completed
SORT priority ASC, due ASC
GROUP BY area
LIMIT 60
```
"""


def render_system_audit(stats: dict) -> str:
    lines: list[str] = [
        "## 🧾 System/Audit Links",
        "",
        "> [!example]+ Drill-down navigation",
        "> - 📊 [Live Dashboard](Live%20Dashboard.md) — hourly metrics",
        "> - 🎯 [Needle Movers](Needle%20Movers.md) — Q2 rocks tracker",
        "> - 🩺 [Pipeline Health](../99_System/Pipeline%20Health.md)",
        "> - 📋 [Master Task List](../10_Active%20Projects/Active%20Personal/!!!%20MASTER%20TASK%20LIST.md)",
        "> - 📥 [Brain dumps inbox](../00_Inbox/brain-dumps/) — drop captures here",
        "> - 📦 [Processed (audit-only)](../00_Inbox/processed/) — see `! README.md`",
        "> - 🧾 [Extraction receipts](../99_System/extraction-receipts/) — content-addressed audit trail",
        "> - 📝 [Run logs](../99_System/logs/) — JSON per workflow per day",
        "",
        "> [!abstract]- System health snapshot",
        f"> - Receipts on disk (last 14d): **{stats['receipts_count']}**",
        f"> - Latest brain-dump log: `{stats['bd_latest_log']}` — status `{stats['bd_latest_status']}`",
        f"> - Open tasks: {stats['open_count']} · with `[priority::]`: {stats['has_priority']} · with `[due::]`: {stats['has_due']}",
        f"> - Built: `{stats['built_at']}`",
        "",
    ]
    return "\n".join(lines)


# ── Page assembler ───────────────────────────────────────────────────────────

PAGE_HEADER = """---
type: dashboard
role: command-center
updated: {built_at}
source: tools/build_command_center.py
adr: 0006
---

# !!! DAILY COMMAND CENTER

> The single daily action surface. `Live Dashboard.md` is metrics-only;
> this page is for deciding and acting. Auto-rebuilt — do not hand-edit.

"""

PAGE_FOOTER = """---

_Built by `tools/build_command_center.py` — see [ADR-0006](../docs/adr/0006-life-os-home-consolidation.md). Last build: {built_at}_
"""


def assemble_page(
    *,
    open_tasks: list[dict],
    review_items: list[str],
    summary: dict | None,
    summary_age_h: float | None,
    stats: dict,
    today: date,
    built_at: str,
) -> str:
    top = pick_top_priority(open_tasks, today)
    overdue = bucket_overdue(open_tasks, today)
    parts = [
        PAGE_HEADER.format(built_at=built_at),
        render_do_this_first(top, overdue, today),
        render_brain_dumps(summary, summary_age_h),
        render_ready_to_act(),
        render_needs_review(review_items),
        render_articles(),
        render_by_area(),
        render_system_audit(stats),
        PAGE_FOOTER.format(built_at=built_at),
    ]
    return "\n".join(parts)


HOME_REDIRECT_STUB = """---
type: redirect
moved_to: "[[!!! DAILY COMMAND CENTER]]"
updated: {built_at}
---

# 🏠 Home (moved)

The daily action surface has moved to **[[!!! DAILY COMMAND CENTER]]**. This file is
no longer auto-rebuilt — see [ADR-0006](../docs/adr/0006-life-os-home-consolidation.md).
"""


# ── Live build (S3) ──────────────────────────────────────────────────────────

def gather_stats(s3, open_tasks: list[dict], built_at: str) -> dict:
    """Compute the System Health snapshot fields."""
    receipts_count = 0
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=MINIO_BUCKET, Prefix=RECEIPTS_PREFIX):
            for obj in page.get("Contents") or []:
                if str(obj["LastModified"]) >= cutoff:
                    receipts_count += 1
    except ClientError:
        pass

    bd_latest_log = "(none)"
    bd_latest_status = "unknown"
    try:
        r = s3.list_objects_v2(Bucket=MINIO_BUCKET, Prefix=BD_LOG_PREFIX)
        candidates = [o for o in (r.get("Contents") or []) if o["Key"].endswith(".json")]
        if candidates:
            latest = max(candidates, key=lambda o: o["LastModified"])
            bd_latest_log = latest["Key"].rsplit("/", 1)[-1]
            try:
                data = json.loads(s3_get(s3, latest["Key"]))
                bd_latest_status = str(data.get("status", "unknown"))
            except Exception:
                pass
    except ClientError:
        pass

    return {
        "receipts_count": receipts_count,
        "bd_latest_log": bd_latest_log,
        "bd_latest_status": bd_latest_status,
        "open_count": len(open_tasks),
        "has_priority": sum(1 for t in open_tasks if t["priority"]),
        "has_due": sum(1 for t in open_tasks if t["due"]),
        "built_at": built_at,
    }


def main():
    if not (MINIO_ACCESS_KEY and MINIO_SECRET_KEY):
        print("ERROR: MinIO credentials missing. Run: set -a && source .env && set +a")
        sys.exit(1)

    s3 = s3_client()
    now = datetime.now(timezone.utc)
    built_at = now.isoformat(timespec="seconds")
    today = now.date()

    # Read sources
    mtl_text = s3_get(s3, MTL_KEY)
    review_text = s3_get_safe(s3, REVIEW_QUEUE_KEY)
    summary_text = s3_get_safe(s3, OPERATOR_SUMMARY_KEY)

    open_tasks = parse_mtl_open(mtl_text)
    review_items = parse_review_queue(review_text)
    summary = json.loads(summary_text) if summary_text else None
    age_h = summary_age_hours(summary, now=now)
    stats = gather_stats(s3, open_tasks, built_at)

    # Assemble
    body = assemble_page(
        open_tasks=open_tasks,
        review_items=review_items,
        summary=summary,
        summary_age_h=age_h,
        stats=stats,
        today=today,
        built_at=built_at,
    )

    # Write command center (verified)
    print(f"\n=== Writing {COMMAND_CENTER_KEY} ({len(body)}B) ===")
    head = s3_put_verified(s3, COMMAND_CENTER_KEY, body)
    print(f"  ETag:          {head['ETag']}")
    print(f"  ContentLength: {head['ContentLength']}")
    print(f"  LastModified:  {head['LastModified']}")
    readback = s3_get(s3, COMMAND_CENTER_KEY)
    assert readback == body, "READBACK MISMATCH on command center"
    print("  readback:      OK (byte-exact)")

    # Replace Home.md with redirect stub (idempotent)
    stub = HOME_REDIRECT_STUB.format(built_at=built_at)
    print(f"\n=== Writing redirect stub to {HOME_KEY} ===")
    s3_put_verified(s3, HOME_KEY, stub)
    print("  redirect:      OK")

    # Brief summary
    print("\n=== Summary ===")
    print(f"  open tasks:        {len(open_tasks)}")
    print(f"  review items:      {len(review_items)}")
    print(f"  summary present:   {summary is not None} (age: {age_h}h)" if summary else "  summary present:   False")
    print(f"  receipts (14d):    {stats['receipts_count']}")
    print(f"  latest bd log:     {stats['bd_latest_log']} ({stats['bd_latest_status']})")
    print("\n=== DONE ===")


if __name__ == "__main__":
    main()

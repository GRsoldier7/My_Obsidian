#!/usr/bin/env python3
"""
tools/build_home_view.py
Track C — Build 000_Master Dashboard/Home.md as the operator's daily entry point.

v2 structure (2026-04-25):
  - Morning Setup (hand-fillable)
  - Today (Overdue / Due+PriorityA / Quick Wins) — Dataview
  - Active Projects — Dataview grouped by area
  - This Week (Completed last 7d / Next 7d) — Dataview
  - Reading Queue — dataviewjs
  - To Look Into — Dataview (explore = true)
  - Inbox Health — STATIC values populated at build time from MinIO
  - Quick Actions — markdown links into vault paths

Idempotent. Re-run at any time to refresh Inbox Health stats and timestamp.
PUTs Home.md with head_object verification (verified-write rule).
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone

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
LIVE_DASH_KEY = "000_Master Dashboard/Live Dashboard.md"
HOME_KEY = "000_Master Dashboard/Home.md"
REVIEW_QUEUE_KEY = "00_Inbox/review-queue.md"

BRAINDUMPS_PREFIX = "00_Inbox/brain-dumps/"
LOGS_PREFIX = "99_System/logs/"
BD_LOG_PREFIX = "99_System/logs/brain-dump-processor-"

VALID_AREAS = {"faith", "family", "business", "consulting", "work", "health", "home", "personal"}


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


def s3_head_safe(s3, key: str) -> dict | None:
    try:
        return s3.head_object(Bucket=MINIO_BUCKET, Key=key)
    except ClientError:
        return None


def s3_put_verified(s3, key: str, body: str) -> dict:
    s3.put_object(Bucket=MINIO_BUCKET, Key=key, Body=body.encode("utf-8"), ContentType="text/markdown")
    head = s3.head_object(Bucket=MINIO_BUCKET, Key=key)
    return {"ETag": head["ETag"], "ContentLength": head["ContentLength"], "LastModified": str(head["LastModified"])}


# ── MTL parsing ───────────────────────────────────────────────────────────────

OPEN_TASK_RE = re.compile(r"^- \[ \] (.+?)$")
DONE_TASK_RE = re.compile(r"^- \[x\] (.+?)$", re.IGNORECASE)
AREA_RE = re.compile(r"\[area::\s*([a-z]+)\]")
PRIORITY_RE = re.compile(r"\[priority::\s*([ABC])\]")
DUE_RE = re.compile(r"\[due::\s*(\d{4}-\d{2}-\d{2})\]")
COMPLETION_RE = re.compile(r"\[completion::\s*(\d{4}-\d{2}-\d{2})\]")
EXPLORE_RE = re.compile(r"\[explore::\s*true\]")


def parse_mtl(text: str) -> dict:
    open_tasks: list[dict] = []
    done_tasks: list[dict] = []
    for line in text.splitlines():
        raw = line.rstrip()
        m_open = OPEN_TASK_RE.match(raw)
        m_done = DONE_TASK_RE.match(raw)
        if m_open:
            body = m_open.group(1)
            t = _build_task(body, raw, completed=False)
            open_tasks.append(t)
        elif m_done:
            body = m_done.group(1)
            t = _build_task(body, raw, completed=True)
            done_tasks.append(t)
    return {"open": open_tasks, "done": done_tasks}


def _build_task(body: str, raw: str, *, completed: bool) -> dict:
    area = AREA_RE.search(body)
    prio = PRIORITY_RE.search(body)
    due = DUE_RE.search(body)
    comp = COMPLETION_RE.search(body)
    explore = bool(EXPLORE_RE.search(body))
    desc = re.sub(r"\s*\[(?:area|priority|due|explore|completion)::[^\]]*\]", "", body).strip()
    return {
        "raw": raw,
        "desc": desc,
        "area": area.group(1) if area else None,
        "priority": prio.group(1) if prio else None,
        "due": due.group(1) if due else None,
        "completion": comp.group(1) if comp else None,
        "explore": explore,
        "completed": completed,
    }


# ── Articles parsing ──────────────────────────────────────────────────────────

ARTICLE_RE = re.compile(r"^- \[(?P<linktext>[^\]]+)\]\((?P<url>[^\)]+)\)(?P<rest>.*)$")
TITLE_FIELD_RE = re.compile(r"\[title::\s*([^\]]+)\]")
DESC_FIELD_RE = re.compile(r"\[description::\s*([^\]]+)\]")


def parse_articles(text: str) -> list[dict]:
    articles: list[dict] = []
    current_date = None
    for line in text.splitlines():
        h2 = re.match(r"^## Added (\d{4}-\d{2}-\d{2})", line.strip())
        if h2:
            current_date = h2.group(1)
            continue
        m = ARTICLE_RE.match(line.strip())
        if not m:
            continue
        rest = m.group("rest")
        title_m = TITLE_FIELD_RE.search(rest)
        desc_m = DESC_FIELD_RE.search(rest)
        articles.append({
            "linktext": m.group("linktext"),
            "url": m.group("url"),
            "title": title_m.group(1).strip() if title_m else None,
            "description": desc_m.group(1).strip() if desc_m else None,
            "added": current_date,
        })
    return articles


# ── Inbox Health computation (data-driven from MinIO) ────────────────────────

def count_brain_dumps(s3) -> int:
    """Count non-zero brain dump files (exclude folder marker)."""
    r = s3.list_objects_v2(Bucket=MINIO_BUCKET, Prefix=BRAINDUMPS_PREFIX)
    n = 0
    for o in r.get("Contents") or []:
        if o["Key"].endswith("/"):
            continue
        if o["Size"] == 0:
            continue
        n += 1
    return n


def count_articles_unread(articles: list[dict]) -> int:
    """Articles in queue (presence in articles-to-process.md)."""
    return len(articles)


def review_queue_count(s3) -> tuple[int, bool]:
    """If review-queue.md exists, count `- [ ]` lines. Returns (count, exists)."""
    head = s3_head_safe(s3, REVIEW_QUEUE_KEY)
    if not head:
        return (0, False)
    try:
        text = s3_get(s3, REVIEW_QUEUE_KEY)
    except ClientError:
        return (0, True)
    n = sum(1 for line in text.splitlines() if OPEN_TASK_RE.match(line.rstrip()))
    return (n, True)


def stale_tasks_priority_a(open_tasks: list[dict]) -> int:
    """Open priority-A tasks with no [due::]."""
    return sum(1 for t in open_tasks if t["priority"] == "A" and not t["due"])


def last_brain_dump_run(s3) -> tuple[str, str]:
    """Return (timestamp_iso, status) for the most recent brain-dump-processor log."""
    r = s3.list_objects_v2(Bucket=MINIO_BUCKET, Prefix=BD_LOG_PREFIX)
    contents = [o for o in (r.get("Contents") or []) if o["Key"].endswith(".json")]
    if not contents:
        return ("(no log found)", "unknown")
    latest = max(contents, key=lambda o: o["LastModified"])
    try:
        text = s3_get(s3, latest["Key"])
        data = json.loads(text)
        ts = data.get("finished_at") or data.get("started_at") or str(latest["LastModified"])
        status = data.get("status", "unknown")
        if data.get("skip_reason"):
            status = f"{status} ({data['skip_reason']})"
        return (ts, status)
    except Exception:
        return (str(latest["LastModified"]), "unknown")


# ── Render simulation helpers ─────────────────────────────────────────────────

def simulate_today(open_tasks: list[dict], today: date) -> dict:
    overdue, due_or_A, quick = [], [], []
    for t in open_tasks:
        if t["due"]:
            try:
                d = date.fromisoformat(t["due"])
                if d < today:
                    overdue.append(t)
            except ValueError:
                pass
        is_due_today = t["due"] == today.isoformat()
        if is_due_today or t["priority"] == "A":
            due_or_A.append(t)
        if t["priority"] == "C" and not t["due"]:
            quick.append(t)
    return {"overdue": overdue, "due_or_A": due_or_A, "quick": quick}


def simulate_active_projects(open_tasks: list[dict]) -> dict:
    """Group by area, top priority-A task per area."""
    by_area = defaultdict(list)
    for t in open_tasks:
        key = t["area"] or "_unset"
        by_area[key].append(t)
    # Top one (priority A first; else priority B; else C; else nothing)
    rank = {"A": 0, "B": 1, "C": 2, None: 3}
    top_per_area = {}
    for area, tasks in by_area.items():
        ranked = sorted(tasks, key=lambda t: (rank.get(t["priority"], 3), t["due"] or "9999"))
        top_per_area[area] = ranked[0]
    return top_per_area


def simulate_this_week(open_tasks: list[dict], done_tasks: list[dict], today: date) -> dict:
    """Completed last 7d (need [completion::] field) + Next 7d (priority A or due-soon)."""
    seven_ago = today.toordinal() - 7
    seven_ahead = today.toordinal() + 7
    completed_7d: list[dict] = []
    for t in done_tasks:
        if t["completion"]:
            try:
                d = date.fromisoformat(t["completion"]).toordinal()
                if seven_ago <= d <= today.toordinal():
                    completed_7d.append(t)
            except ValueError:
                pass

    next_7d: list[dict] = []
    for t in open_tasks:
        is_A = t["priority"] == "A"
        in_window = False
        if t["due"]:
            try:
                d = date.fromisoformat(t["due"]).toordinal()
                in_window = today.toordinal() <= d <= seven_ahead
            except ValueError:
                pass
        if is_A or in_window:
            next_7d.append(t)
    return {"completed_7d": completed_7d, "next_7d": next_7d}


def simulate_explore(open_tasks: list[dict]) -> list[dict]:
    return [t for t in open_tasks if t["explore"]]


# ── Home.md template ──────────────────────────────────────────────────────────

HOME_TEMPLATE = """---
type: dashboard
updated: {updated_iso}
---

# 🏠 Home

> Daily entry point. Hand-curated. `Live Dashboard.md` is for at-a-glance metrics; this file is for action.

## 🌅 Morning Setup

> Fill this when you sit down. The system reads it for the rest of the day.

- **🎯 ONE Thing** — _(write today's needle-mover)_
- **⚡ Energy** — _high / medium / low_
- **🚧 Constraint** — _(biggest blocker today, if any)_

## 🔥 Today

> What needs attention right now. Auto-updated from MTL.

### Overdue

```dataview
TASK
FROM "10_Active Projects/Active Personal/!!! MASTER TASK LIST"
WHERE !completed AND due AND due < date(today)
SORT due ASC
GROUP BY area
```

### Due Today + Priority A

```dataview
TASK
FROM "10_Active Projects/Active Personal/!!! MASTER TASK LIST"
WHERE !completed AND ((due = date(today)) OR priority = "A")
SORT priority ASC, due ASC
GROUP BY area
```

### Quick Wins

```dataview
TASK
FROM "10_Active Projects/Active Personal/!!! MASTER TASK LIST"
WHERE !completed AND priority = "C" AND !due
LIMIT 10
```

## 🎯 Active Projects

> Top open task per active area, sorted by priority. (Group-by-project will activate once tasks carry a `[project::]` inline field; today we group by area.)

```dataview
TASK
FROM "10_Active Projects/Active Personal/!!! MASTER TASK LIST"
WHERE !completed
SORT priority ASC, due ASC
GROUP BY area
LIMIT 24
```

## 📈 This Week

> Momentum. What you finished, what's next.

### ✅ Completed (last 7d)

```dataview
TASK
FROM "10_Active Projects/Active Personal/!!! MASTER TASK LIST"
WHERE completed AND completion AND completion >= date(today) - dur(7 days)
SORT completion DESC
LIMIT 10
```

### 🎯 Next 7d (Priority A or due-soon)

```dataview
TASK
FROM "10_Active Projects/Active Personal/!!! MASTER TASK LIST"
WHERE !completed AND ((priority = "A") OR (due >= date(today) AND due <= date(today) + dur(7 days)))
SORT due ASC, priority ASC
LIMIT 10
```

## 📚 Reading Queue

> Articles with blurbs from link-enricher. Newest first. If a row shows only a URL, link-enricher hasn't run yet — wait an hour or kick the workflow.

```dataviewjs
const file = dv.page('"00_Inbox/articles-to-process"');
if (!file) {{
  dv.paragraph("_No articles file found._");
}} else {{
  const lines = (await dv.io.load('00_Inbox/articles-to-process.md')).split("\\n");
  const rows = [];
  let added = null;
  for (const line of lines) {{
    const h = line.match(/^## Added (\\d{{4}}-\\d{{2}}-\\d{{2}})/);
    if (h) {{ added = h[1]; continue; }}
    const m = line.match(/^- \\[([^\\]]+)\\]\\(([^\\)]+)\\)(.*)$/);
    if (!m) continue;
    const rest = m[3] || "";
    const title = (rest.match(/\\[title::\\s*([^\\]]+)\\]/) || [])[1] || m[1];
    const desc  = (rest.match(/\\[description::\\s*([^\\]]+)\\]/) || [])[1] || "_(no blurb yet)_";
    rows.push([added || "—", `[${{title}}](${{m[2]}})`, desc]);
  }}
  rows.sort((a, b) => (b[0] || "").localeCompare(a[0] || ""));
  if (rows.length === 0) {{
    dv.paragraph("_Reading queue empty. Drop URLs into `00_Inbox/articles-to-process.md` or via Telegram._");
  }} else {{
    dv.table(["Added", "Article", "Blurb"], rows.slice(0, 25));
  }}
}}
```

## 🤔 To Look Into

> Curiosity items. Add `[explore:: true]` to any task you want to revisit but isn't urgent. Brain-dump processor will auto-tag research-intent items here.

```dataview
TASK
FROM "10_Active Projects" OR "00_Inbox"
WHERE explore = true AND !completed
SORT area ASC, priority ASC
GROUP BY area
```

## 📥 Inbox Health

> Click anything that's not zero.

- **Unprocessed brain dumps**: {bd_count} — [open folder](00_Inbox/brain-dumps/)
- **Articles unread**: {articles_count} — [articles-to-process.md](00_Inbox/articles-to-process.md)
- **Review queue**: {review_count}{review_link}
- **Stale tasks** (priority A, no `[due::]`): {stale_a}
- **Last brain-dump run**: `{bd_last_ts}` — _{bd_last_status}_

## ⚡ Quick Actions

- 📝 [New brain dump folder](00_Inbox/brain-dumps/)
- 📋 [Open MTL](10_Active%20Projects/Active%20Personal/!!!%20MASTER%20TASK%20LIST.md)
- 📅 [Today's daily note folder](40_Timeline_Weekly/Daily/)
- 🩺 [Pipeline Health](99_System/Pipeline%20Health.md)

---

_Built by `tools/build_home_view.py`. Re-run any time to refresh stats. Last build: {updated_iso}_
"""


# ── Build ────────────────────────────────────────────────────────────────────

def render_home(stats: dict, updated_iso: str) -> str:
    if stats["review_exists"]:
        review_link = " — [review-queue.md](00_Inbox/review-queue.md)"
    else:
        review_link = " _(file not present)_"
    return HOME_TEMPLATE.format(
        updated_iso=updated_iso,
        bd_count=stats["bd_count"],
        articles_count=stats["articles_count"],
        review_count=stats["review_count"],
        review_link=review_link,
        stale_a=stats["stale_a"],
        bd_last_ts=stats["bd_last_ts"],
        bd_last_status=stats["bd_last_status"],
    )


def main():
    if not (MINIO_ACCESS_KEY and MINIO_SECRET_KEY):
        print("ERROR: MinIO credentials missing. Run: set -a && source .env && set +a")
        sys.exit(1)

    s3 = s3_client()

    # 1. Fetch live state
    mtl_text = s3_get(s3, MTL_KEY)
    articles_text = s3_get(s3, ARTICLES_KEY)
    live_dash_present = s3_head_safe(s3, LIVE_DASH_KEY) is not None

    parsed = parse_mtl(mtl_text)
    open_tasks = parsed["open"]
    done_tasks = parsed["done"]
    articles = parse_articles(articles_text)

    # 2. Compute Inbox Health (data-driven)
    bd_count = count_brain_dumps(s3)
    review_count, review_exists = review_queue_count(s3)
    stale_a = stale_tasks_priority_a(open_tasks)
    bd_last_ts, bd_last_status = last_brain_dump_run(s3)

    stats = {
        "bd_count": bd_count,
        "articles_count": count_articles_unread(articles),
        "review_count": review_count,
        "review_exists": review_exists,
        "stale_a": stale_a,
        "bd_last_ts": bd_last_ts,
        "bd_last_status": bd_last_status,
    }

    # Coverage stats (informational)
    total = len(open_tasks)
    has_area = sum(1 for t in open_tasks if t["area"])
    has_prio = sum(1 for t in open_tasks if t["priority"])
    has_due = sum(1 for t in open_tasks if t["due"])
    has_explore = sum(1 for t in open_tasks if t["explore"])

    print("\n=== MTL stats ===")
    print(f"  open tasks:   {total}")
    print(f"  [area::]:     {has_area} ({(has_area/total*100 if total else 0):.0f}%)")
    print(f"  [priority::]: {has_prio} ({(has_prio/total*100 if total else 0):.0f}%)")
    print(f"  [due::]:      {has_due} ({(has_due/total*100 if total else 0):.0f}%)")
    print(f"  [explore::]:  {has_explore}")
    print(f"  done tasks:   {len(done_tasks)} (with completion: {sum(1 for t in done_tasks if t['completion'])})")

    print("\n=== Articles stats ===")
    print(f"  total entries:        {len(articles)}")
    print(f"  with [title::]:       {sum(1 for a in articles if a['title'])}")
    print(f"  with [description::]: {sum(1 for a in articles if a['description'])}")

    print(f"\n=== Live Dashboard.md present (read-only): {live_dash_present} ===")

    print("\n=== Inbox Health (data-driven) ===")
    print(f"  brain dumps:   {bd_count}")
    print(f"  articles:      {stats['articles_count']}")
    print(f"  review queue:  {review_count} (file exists: {review_exists})")
    print(f"  stale prio A:  {stale_a}")
    print(f"  last bd run:   {bd_last_ts}  [{bd_last_status}]")

    # 3. Render + PUT + verify
    updated_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    body = render_home(stats, updated_iso)

    print(f"\n=== Writing {HOME_KEY} ({len(body)}B) ===")
    head = s3_put_verified(s3, HOME_KEY, body)
    print(f"  ETag:          {head['ETag']}")
    print(f"  ContentLength: {head['ContentLength']}")
    print(f"  LastModified:  {head['LastModified']}")

    # Read back, byte-exact verify
    readback = s3_get(s3, HOME_KEY)
    assert readback == body, "READBACK MISMATCH"
    print("  readback:      OK (byte-exact)")

    # 4. Render simulation
    today = date(2026, 4, 25)
    sim = simulate_today(open_tasks, today)

    print("\n=== Render simulation: TODAY ===")
    print(f"\n[Overdue] would render {len(sim['overdue'])} task(s). Top 5:")
    for t in sorted(sim["overdue"], key=lambda x: x["due"])[:5]:
        print(f"  - [{t['area'] or '?'}] {t['desc'][:80]} (due {t['due']}, prio {t['priority'] or '?'})")

    print(f"\n[Due Today + Priority A] would render {len(sim['due_or_A'])} task(s). Top 5:")
    grouped = defaultdict(list)
    for t in sim["due_or_A"]:
        grouped[t["area"] or "_unset"].append(t)
    shown = 0
    for area in sorted(grouped):
        for t in grouped[area]:
            if shown >= 5:
                break
            print(f"  - [{area}] {t['desc'][:80]} (prio {t['priority'] or '?'}, due {t['due'] or '—'})")
            shown += 1
        if shown >= 5:
            break

    print(f"\n[Quick Wins] would render {len(sim['quick'])} task(s). Top 5:")
    for t in sim["quick"][:5]:
        print(f"  - [{t['area'] or '?'}] {t['desc'][:80]}")

    # Active Projects
    proj = simulate_active_projects(open_tasks)
    print(f"\n=== Render simulation: ACTIVE PROJECTS ({len(proj)} area buckets) ===")
    for area, t in sorted(proj.items()):
        print(f"  - [{area}] {t['desc'][:80]} (prio {t['priority'] or '?'}, due {t['due'] or '—'})")

    # This Week
    week = simulate_this_week(open_tasks, done_tasks, today)
    print(f"\n=== Render simulation: THIS WEEK ===")
    print(f"\n[Completed last 7d] would render {len(week['completed_7d'])}. Top 5:")
    for t in week["completed_7d"][:5]:
        print(f"  - [{t['area'] or '?'}] {t['desc'][:80]} (done {t['completion']})")
    print(f"\n[Next 7d] would render {len(week['next_7d'])}. Top 5:")
    for t in week["next_7d"][:5]:
        print(f"  - [{t['area'] or '?'}] {t['desc'][:80]} (prio {t['priority'] or '?'}, due {t['due'] or '—'})")

    # Explore
    explore_tasks = simulate_explore(open_tasks)
    print(f"\n=== Render simulation: TO LOOK INTO ===")
    print(f"  would render {len(explore_tasks)} task(s)")
    for t in explore_tasks[:5]:
        print(f"  - [{t['area'] or '?'}] {t['desc'][:80]}")

    # Reading Queue
    sorted_articles = sorted(
        [a for a in articles if a["url"]],
        key=lambda a: (a["added"] or ""),
        reverse=True,
    )
    print(f"\n=== Render simulation: READING QUEUE ===")
    print(f"  would render {len(sorted_articles)} article(s). Top 5:")
    for a in sorted_articles[:5]:
        title = a["title"] or a["linktext"]
        blurb = a["description"] or "(no blurb yet)"
        print(f"  - [{a['added'] or '—'}] {title[:60]} — {blurb[:80]}")

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()

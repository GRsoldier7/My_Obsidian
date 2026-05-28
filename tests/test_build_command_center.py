"""
Pure-renderer tests for tools/build_command_center.py (ADR-0006).

These exercise the section renderers and pickers without any S3/network I/O.
Live MinIO behavior is covered by the e2e harness; here we lock the user's
pinned 7-section structure and the callout/empty-state contracts.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from tools import build_command_center as bcc


# ── parse_mtl_open ───────────────────────────────────────────────────────────

def test_parse_mtl_open_extracts_canonical_fields():
    text = (
        "## Notes\n"
        "Some prose that should be ignored.\n"
        "\n"
        "- [ ] Ship the website [area:: business] [priority:: A] [due:: 2026-05-01]\n"
        "- [ ] Read that thing [area:: personal] [explore:: true]\n"
        "- [x] Already done [area:: faith] [priority:: B] [completion:: 2026-05-04]\n"
    )
    out = bcc.parse_mtl_open(text)
    assert len(out) == 2
    assert out[0]["desc"] == "Ship the website"
    assert out[0]["area"] == "business"
    assert out[0]["priority"] == "A"
    assert out[0]["due"] == "2026-05-01"
    assert out[0]["explore"] is False
    assert out[1]["explore"] is True
    assert out[1]["priority"] is None


def test_parse_mtl_open_strips_source_field_from_desc():
    text = "- [ ] Call mom [area:: family] [priority:: A] [source:: [[BrainDump — Personal]]]\n"
    out = bcc.parse_mtl_open(text)
    assert out[0]["desc"] == "Call mom"


# ── pick_top_priority ────────────────────────────────────────────────────────

def _t(desc, *, area="personal", priority=None, due=None):
    return {"raw": "", "desc": desc, "area": area, "priority": priority, "due": due, "explore": False}


def test_pick_top_priority_prefers_overdue_priority_a():
    today = date(2026, 5, 6)
    tasks = [
        _t("nothing-overdue-A", priority="A"),
        _t("recent-overdue-A", priority="A", due="2026-05-04"),
        _t("ancient-overdue-A", priority="A", due="2026-04-15"),
    ]
    top = bcc.pick_top_priority(tasks, today)
    assert top["desc"] == "ancient-overdue-A"


def test_pick_top_priority_falls_back_to_earliest_due_when_no_overdue_a():
    today = date(2026, 5, 6)
    tasks = [
        _t("future-A-far", priority="A", due="2026-06-01"),
        _t("future-A-near", priority="A", due="2026-05-08"),
    ]
    top = bcc.pick_top_priority(tasks, today)
    assert top["desc"] == "future-A-near"


def test_pick_top_priority_returns_none_for_empty_list():
    assert bcc.pick_top_priority([], date(2026, 5, 6)) is None


def test_pick_top_priority_falls_through_to_overdue_b_when_no_a():
    today = date(2026, 5, 6)
    tasks = [
        _t("future-B", priority="B", due="2026-06-01"),
        _t("overdue-B", priority="B", due="2026-04-30"),
    ]
    top = bcc.pick_top_priority(tasks, today)
    assert top["desc"] == "overdue-B"


# ── bucket_overdue ───────────────────────────────────────────────────────────

def test_bucket_overdue_classifies_by_days():
    today = date(2026, 5, 6)
    tasks = [
        _t("ancient", priority="A", due="2026-04-25"),    # 11 days → critical
        _t("medium", priority="B", due="2026-05-01"),     # 5 days → high
        _t("yesterday", priority="A", due="2026-05-05"),  # 1 day → recent
        _t("today", priority="A", due="2026-05-06"),      # 0 → not overdue
        _t("future", priority="A", due="2026-05-10"),     # not overdue
        _t("no_due", priority="A"),
    ]
    buckets = bcc.bucket_overdue(tasks, today)
    assert [t["desc"] for t in buckets["critical"]] == ["ancient"]
    assert [t["desc"] for t in buckets["high"]] == ["medium"]
    assert [t["desc"] for t in buckets["recent"]] == ["yesterday"]


def test_bucket_overdue_sorts_within_bucket_by_days_desc():
    today = date(2026, 5, 6)
    tasks = [
        _t("a", priority="A", due="2026-04-20"),  # 16d
        _t("b", priority="A", due="2026-04-15"),  # 21d
    ]
    buckets = bcc.bucket_overdue(tasks, today)
    assert [t["desc"] for t in buckets["critical"]] == ["b", "a"]


# ── parse_review_queue ───────────────────────────────────────────────────────

def test_parse_review_queue_returns_open_items_only():
    text = (
        "# Review Queue\n"
        "\n"
        "- [ ] First item [area:: business]\n"
        "- [x] Already triaged [area:: business]\n"
        "- [ ] Second item [area:: personal]\n"
    )
    out = bcc.parse_review_queue(text)
    assert len(out) == 2
    assert out[0].startswith("- [ ] First")


def test_parse_review_queue_handles_none_or_empty():
    assert bcc.parse_review_queue(None) == []
    assert bcc.parse_review_queue("") == []


def test_parse_review_queue_respects_limit():
    text = "\n".join(f"- [ ] item{i} [area:: personal]" for i in range(20))
    out = bcc.parse_review_queue(text, limit=5)
    assert len(out) == 5


# ── summary_age_hours ────────────────────────────────────────────────────────

def test_summary_age_hours_returns_none_for_missing_or_malformed():
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    assert bcc.summary_age_hours(None, now=now) is None
    assert bcc.summary_age_hours({}, now=now) is None
    assert bcc.summary_age_hours({"run_finished_at": "not-a-date"}, now=now) is None


def test_summary_age_hours_computes_delta():
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    summary = {"run_finished_at": "2026-05-06T06:00:00+00:00"}
    age = bcc.summary_age_hours(summary, now=now)
    assert age == 6.0


# ── render_do_this_first ─────────────────────────────────────────────────────

def test_render_do_this_first_includes_section_header():
    out = bcc.render_do_this_first(None, {"critical": [], "high": [], "recent": []}, date(2026, 5, 6))
    assert out.startswith("## 🔥 Do This First")


def test_render_do_this_first_handles_empty_state():
    out = bcc.render_do_this_first(None, {"critical": [], "high": [], "recent": []}, date(2026, 5, 6))
    assert "Nothing on fire" in out
    assert "Nothing overdue" in out
    # Q2 Rocks callout always present.
    assert "Q2 Rocks alignment" in out


def test_render_do_this_first_renders_top_task_callout():
    top = _t("Ship MVP", area="business", priority="A", due="2026-05-01")
    overdue = {
        "critical": [_t("ancient", area="business", priority="A", due="2026-04-25")],
        "high": [],
        "recent": [],
    }
    out = bcc.render_do_this_first(top, overdue, date(2026, 5, 6))
    assert "[!important]+" in out
    assert "Ship MVP" in out
    assert "[!warning]+" in out
    assert "1 critical" in out


# ── render_brain_dumps ──────────────────────────────────────────────────────

def test_render_brain_dumps_warns_when_summary_missing():
    out = bcc.render_brain_dumps(None, None)
    assert out.startswith("## 🧠 New From Brain Dumps")
    assert "[!warning]+" in out
    assert "make run" in out


def test_render_brain_dumps_warns_when_summary_stale():
    summary = {
        "run_finished_at": "2026-05-04T06:00:00+00:00",
        "status": "success",
        "tasks_written": 0,
        "files_extracted": [],
    }
    out = bcc.render_brain_dumps(summary, summary_age_h=72.0)
    assert "Last brain-dump run is **72.0h old**" in out


def test_render_brain_dumps_lists_top_added_grouped_by_area():
    summary = {
        "run_finished_at": "2026-05-06T07:00:00+00:00",
        "status": "success",
        "tasks_written": 3,
        "review_added": 1,
        "articles_queued": 2,
        "files_extracted": ["BrainDump — Personal.md"],
        "files_partial": [],
        "files_error": [],
        "top_added_tasks": [
            {"area": "business", "priority": "A", "desc": "Ship landing page"},
            {"area": "business", "priority": "B", "desc": "Draft pitch deck"},
            {"area": "faith", "priority": "A", "desc": "Outline next sermon"},
        ],
    }
    out = bcc.render_brain_dumps(summary, summary_age_h=2.0)
    assert "3 tasks added to MTL" in out
    assert "1 routed to review" in out
    assert "2 articles queued" in out
    assert "**business**" in out
    assert "**faith**" in out
    assert "Ship landing page" in out


def test_render_brain_dumps_no_added_tasks_states_so():
    """Empty-but-healthy run renders the positive "Pipeline healthy" banner
    (UI audit 2026-05-27 §4 win #2) and is presented as a success callout —
    not an ambiguous italic disclaimer. The banner must explicitly tell
    Aaron the system is fine + capture hint."""
    summary = {
        "run_finished_at": "2026-05-06T07:00:00+00:00",
        "status": "success",
        "tasks_written": 0,
        "files_extracted": [],
        "files_partial": [],
        "files_error": [],
        "top_added_tasks": [],
    }
    out = bcc.render_brain_dumps(summary, summary_age_h=1.0)
    assert "Pipeline healthy" in out, (
        "Empty-run banner must use the positive 'Pipeline healthy' phrasing "
        "(UI audit 2026-05-27 §4 win #2)"
    )
    assert "[!success]+ Pipeline healthy" in out, "Must render as a success callout"
    assert "00_Inbox/brain-dumps/" in out, "Must include the capture hint"
    # Healthy-run summary callout is success, not info.
    assert "[!success]+ Last run" in out


def test_render_brain_dumps_flags_partial_and_error_files():
    summary = {
        "run_finished_at": "2026-05-06T07:00:00+00:00",
        "status": "partial",
        "tasks_written": 1,
        "files_extracted": [],
        "files_partial": ["BrainDump — Work.md"],
        "files_error": [{"file": "BrainDump — Faith.md", "error": "openrouter timeout"}],
        "top_added_tasks": [],
    }
    out = bcc.render_brain_dumps(summary, summary_age_h=1.0)
    assert "[!warning]+" in out
    assert "🟠 Partial" in out
    assert "🔴 Error" in out
    assert "BrainDump — Work.md" in out


# ── render_needs_review ──────────────────────────────────────────────────────

def test_render_needs_review_empty_state():
    out = bcc.render_needs_review([])
    assert "Review queue clear" in out


def test_render_needs_review_lists_items():
    items = [
        "- [ ] Maybe cancel that subscription [area:: personal]",
        "- [ ] Talk to John about handoff [area:: work]",
    ]
    out = bcc.render_needs_review(items)
    assert "2 item(s) need a human call" in out
    assert "Maybe cancel" in out
    assert "Talk to John" in out


# ── render_system_audit ──────────────────────────────────────────────────────

def test_render_system_audit_includes_drill_down_links_and_health():
    stats = {
        "receipts_count": 12,
        "bd_latest_log": "brain-dump-processor-2026-05-06.json",
        "bd_latest_status": "success",
        "open_count": 47,
        "has_priority": 30,
        "has_due": 5,
        "built_at": "2026-05-06T11:18:42+00:00",
    }
    out = bcc.render_system_audit(stats)
    assert "Live Dashboard" in out
    assert "Pipeline Health" in out
    assert "Receipts on disk (last 14d): **12**" in out
    assert "brain-dump-processor-2026-05-06.json" in out


# ── assemble_page (top-level structural lock) ────────────────────────────────

def test_assemble_page_includes_all_seven_pinned_sections_in_order():
    """
    User pinned the H2 structure on 2026-05-06. This is the structural lock —
    if any of these renames the test must be deliberately updated alongside
    the user-facing rename.
    """
    page = bcc.assemble_page(
        open_tasks=[],
        review_items=[],
        summary=None,
        summary_age_h=None,
        stats={
            "receipts_count": 0, "bd_latest_log": "(none)",
            "bd_latest_status": "unknown", "open_count": 0,
            "has_priority": 0, "has_due": 0,
            "built_at": "2026-05-06T00:00:00+00:00",
        },
        today=date(2026, 5, 6),
        built_at="2026-05-06T00:00:00+00:00",
    )

    expected_order = [
        "# !!! DAILY COMMAND CENTER",
        "## 🔥 Do This First",
        "## 🧠 New From Brain Dumps",
        "## ✅ Ready-To-Act Tasks",
        "## ❓ Needs Review",
        "## 📚 Articles / References",
        "## 🗂 By Life Area",
        "## 🧾 System/Audit Links",
    ]
    indices = [page.find(h) for h in expected_order]
    assert all(i >= 0 for i in indices), f"missing section: {dict(zip(expected_order, indices))}"
    assert indices == sorted(indices), f"sections out of order: {dict(zip(expected_order, indices))}"


def test_assemble_page_renders_yaml_frontmatter_with_adr_pointer():
    page = bcc.assemble_page(
        open_tasks=[],
        review_items=[],
        summary=None,
        summary_age_h=None,
        stats={
            "receipts_count": 0, "bd_latest_log": "(none)",
            "bd_latest_status": "unknown", "open_count": 0,
            "has_priority": 0, "has_due": 0,
            "built_at": "2026-05-06T00:00:00+00:00",
        },
        today=date(2026, 5, 6),
        built_at="2026-05-06T00:00:00+00:00",
    )
    # Frontmatter sanity
    assert page.startswith("---\n")
    assert "type: dashboard" in page.split("---", 2)[1]
    assert "role: command-center" in page.split("---", 2)[1]
    assert "adr: 0006" in page.split("---", 2)[1]

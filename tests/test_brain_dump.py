"""Tests for tools/process_brain_dump.py — section parsing and content detection."""
import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from process_brain_dump import (
    parse_sections,
    is_section_empty,
    extract_real_sections,
    _strip_yaml_frontmatter,
    infer_area_from_filename,
    validate_task_line,
    quality_gate_tasks,
    section_type,
    reset_to_template,
    regex_extract_tasks,
    normalize_shorthand_dates,
    extract_tasks_with_ai_fallback,
)


# ── parse_sections ────────────────────────────────────────────────────────────

def test_parse_sections_basic():
    content = """---
frontmatter: true
---

## ⚡ Quick Notes
Some content here

## ✅ To Do's
- buy milk
"""
    sections = parse_sections(content)
    assert "⚡ Quick Notes" in sections
    assert "✅ To Do's" in sections
    assert "buy milk" in sections["✅ To Do's"]


def test_parse_sections_empty_file():
    sections = parse_sections("")
    assert "_frontmatter" in sections


def test_parse_sections_multiple_sections():
    content = "## Section A\nline1\n## Section B\nline2\n## Section C\nline3"
    sections = parse_sections(content)
    assert "Section A" in sections
    assert "Section B" in sections
    assert "Section C" in sections


# ── is_section_empty ──────────────────────────────────────────────────────────

def test_is_section_empty_html_comment_only():
    assert is_section_empty("<!-- Add items here -->") is True


def test_is_section_empty_whitespace_only():
    assert is_section_empty("   \n\n   \t  ") is True


def test_is_section_empty_obsidian_placeholder():
    assert is_section_empty("=this.field\n=this.other") is True


def test_is_section_empty_horizontal_rule():
    assert is_section_empty("---\n\n---") is True


def test_is_section_empty_italic_template():
    assert is_section_empty("*Raw thoughts, observations*") is True


def test_is_section_empty_blockquote():
    assert is_section_empty("> **How to use:** Drop anything here") is True


def test_is_section_empty_format_hint():
    assert is_section_empty("<!-- Format: - [ ] <task> [priority:: A/B/C] -->") is True


def test_is_section_empty_real_content():
    assert is_section_empty("- Buy milk before Sunday") is False


def test_is_section_empty_task_line():
    assert is_section_empty("- [ ] Call Dr. Smith about hip MRI") is False


def test_is_section_empty_url():
    assert is_section_empty("https://example.com/article") is False


def test_is_section_empty_mixed_with_real():
    content = """<!-- Add items here -->

- This is real content
"""
    assert is_section_empty(content) is False


def test_is_section_empty_multiline_comment():
    content = """<!--
This is a multiline
comment
-->
"""
    assert is_section_empty(content) is True


# ── extract_real_sections ─────────────────────────────────────────────────────

def test_extract_real_sections_skips_empty():
    sections = {
        "⚡ Quick Notes": "<!-- Add notes here -->",
        "✅ To Do's": "- Buy milk\n- Call dentist",
    }
    real = extract_real_sections(sections)
    assert "✅ To Do's" in real
    assert "⚡ Quick Notes" not in real


def test_extract_real_sections_skips_frontmatter():
    sections = {
        "_frontmatter": "domain: personal",
        "✅ To Do's": "- do something real",
    }
    real = extract_real_sections(sections)
    assert "_frontmatter" not in real
    assert "✅ To Do's" in real


def test_extract_real_sections_all_empty():
    sections = {
        "⚡ Quick Notes": "<!-- Add notes here -->",
        "✅ To Do's": "<!-- Format: - [ ] task -->",
    }
    real = extract_real_sections(sections)
    assert len(real) == 0


# ── extract_real_sections — header-less file fallback ────────────────────────

def test_extract_real_sections_headerless_plain_text():
    """Files with no ## headers (e.g. Coding.md) fall back to _frontmatter body."""
    sections = {
        "_frontmatter": "- Do this thing\n- And this other thing\n",
    }
    real = extract_real_sections(sections)
    assert "✅ To Do's" in real
    assert "Do this thing" in real["✅ To Do's"]


def test_extract_real_sections_headerless_template_file_stays_empty():
    """A structured brain dump template with all-empty named sections should return {} even
    though _frontmatter has a H1 title and blockquote instructions."""
    content = """---
domain: Consulting
area: consulting
status: empty
---

# 💼 Brain Dump — Consulting

> How to use: drop anything here.

---

## ✅ To Do's
<!-- Format: - [ ] <task> -->
"""
    sections = parse_sections(content)
    real = extract_real_sections(sections)
    assert len(real) == 0, f"Template file should be empty, got: {real}"


def test_extract_real_sections_headerless_with_yaml():
    """Header-less file with YAML front matter — YAML stripped, real body detected."""
    sections = {
        "_frontmatter": "---\nstatus: empty\n---\nJohn 6:44 - God pulls us into his presence.",
    }
    real = extract_real_sections(sections)
    assert "✅ To Do's" in real
    assert "John 6:44" in real["✅ To Do's"]


# ── _strip_yaml_frontmatter ───────────────────────────────────────────────────

def test_strip_yaml_frontmatter_removes_yaml():
    text = "---\ndomain: faith\n---\n\nSome real content"
    result = _strip_yaml_frontmatter(text)
    assert "domain" not in result
    assert "Some real content" in result


def test_strip_yaml_frontmatter_removes_h1():
    text = "---\nstatus: empty\n---\n\n# Brain Dump Title\n\nReal content here"
    result = _strip_yaml_frontmatter(text)
    assert "Brain Dump Title" not in result
    assert "Real content here" in result


def test_strip_yaml_frontmatter_removes_blockquotes():
    text = "---\nstatus: empty\n---\n\n> How to use this template\n\nReal content"
    result = _strip_yaml_frontmatter(text)
    assert "How to use" not in result
    assert "Real content" in result


def test_strip_yaml_frontmatter_no_yaml():
    text = "Plain text with no frontmatter\n- item one"
    result = _strip_yaml_frontmatter(text)
    assert "Plain text" in result
    assert "item one" in result


# ── regex_extract_tasks — plain-text priority suffix ─────────────────────────

def test_regex_extract_tasks_priority_suffix():
    """Lines ending in ' - A/B/C' should be captured with the explicit priority."""
    body = "Apply to Reggie program ASAP - A\nScraping websites for Biohacking - A"
    tasks = regex_extract_tasks(body, "business")
    assert len(tasks) == 2
    assert "[priority:: A]" in tasks[0]
    assert "Apply to Reggie program ASAP" in tasks[0]


def test_regex_extract_tasks_priority_suffix_b():
    body = "Review the quarterly report - B"
    tasks = regex_extract_tasks(body, "work")
    assert len(tasks) == 1
    assert "[priority:: B]" in tasks[0]


def test_regex_extract_tasks_no_false_positive_short():
    """Short lines like 'A - B' should not match the priority suffix pattern."""
    body = "A - B"
    tasks = regex_extract_tasks(body, "personal")
    assert len(tasks) == 0


# ── infer_area_from_filename ──────────────────────────────────────────────────

def test_infer_area_faith():
    assert infer_area_from_filename("BrainDump — Faith.md") == "faith"


def test_infer_area_business():
    assert infer_area_from_filename("BrainDump — Business (Echelon Seven).md") == "business"


def test_infer_area_work():
    assert infer_area_from_filename("BrainDump — Work (Parallon).md") == "work"


def test_infer_area_consulting():
    assert infer_area_from_filename("BrainDump — Consulting.md") == "consulting"


def test_infer_area_coding_defaults_to_personal():
    assert infer_area_from_filename("Coding.md") == "personal"


def test_infer_area_unknown_defaults_to_personal():
    assert infer_area_from_filename("random-file.md") == "personal"


# ── validate_task_line ────────────────────────────────────────────────────────

def test_validate_task_line_minimal_valid():
    assert validate_task_line("- [ ] Buy groceries [area:: personal]") is True


def test_validate_task_line_full_valid():
    assert validate_task_line(
        "- [ ] Launch Bible study [area:: faith] [priority:: A] [due:: 2026-06-01]"
    ) is True


def test_validate_task_line_priority_only():
    assert validate_task_line("- [ ] Work on offer [area:: business] [priority:: B]") is True


def test_validate_task_line_invalid_area():
    assert validate_task_line("- [ ] Do thing [area:: invalid_area]") is False


def test_validate_task_line_missing_area():
    assert validate_task_line("- [ ] Do thing [priority:: A]") is False


def test_validate_task_line_not_a_task():
    assert validate_task_line("This is just text") is False


def test_validate_task_line_checked_task():
    # Completed tasks (- [x]) should not match
    assert validate_task_line("- [x] Done thing [area:: personal]") is False


def test_validate_task_line_with_explore_tag():
    # Auto-explore tag must validate (regression: silently rejected on 2026-04-25)
    assert validate_task_line(
        "- [ ] Dig into vagal tone [area:: health] [priority:: B] [explore:: true]"
    ) is True


def test_validate_task_line_with_source_wikilink():
    # Source-link wikilink contains nested brackets — must validate (regression: 2026-04-25)
    assert validate_task_line(
        "- [ ] Email TMC [area:: personal] [priority:: B] [due:: 2026-04-20] "
        "[source:: [[braindump-2026-04-26-BrainDump--Personal]]]"
    ) is True


def test_validate_task_line_with_explore_and_source():
    # Both extensions together (the failure mode that wiped the operator's brain dump)
    assert validate_task_line(
        "- [ ] Research vagal tone [area:: health] [priority:: A] "
        "[explore:: true] [source:: [[braindump-2026-04-26-X]]]"
    ) is True


# ── quality_gate_tasks ────────────────────────────────────────────────────────

def test_quality_gate_filters_invalid():
    tasks = [
        "- [ ] Valid task [area:: health] [priority:: A]",
        "This is not a task",
        "- [ ] Another valid [area:: faith]",
    ]
    valid, rejections = quality_gate_tasks(tasks)
    assert len(valid) == 2
    assert len(rejections) == 1
    assert "invalid canonical format" in rejections[0]["reason"]


def test_quality_gate_all_valid():
    tasks = [
        "- [ ] Task one [area:: work] [priority:: B]",
        "- [ ] Task two [area:: family]",
    ]
    valid, rejections = quality_gate_tasks(tasks)
    assert len(valid) == 2
    assert len(rejections) == 0


def test_quality_gate_all_invalid():
    tasks = ["random text", "also random", "not a task either"]
    valid, rejections = quality_gate_tasks(tasks)
    assert len(valid) == 0
    assert len(rejections) == 3


# ── section_type ──────────────────────────────────────────────────────────────

def test_section_type_todos():
    assert section_type("✅ To Do's") == "tasks"


def test_section_type_needle_movers():
    assert section_type("🎯 Needle Movers") == "tasks"


def test_section_type_articles():
    assert section_type("📰 Articles & Resources to Follow Up On") == "articles"


def test_section_type_quick_notes():
    assert section_type("⚡ Quick Notes") == "notes"


def test_section_type_ideas():
    assert section_type("💡 Ideas & Possibilities") == "notes"


# ── reset_to_template ────────────────────────────────────────────────────────

def test_reset_to_template_clears_content():
    content = """---
domain: Personal
area: personal
last_processed:
status: empty
---

# Brain Dump — Personal

## ✅ To Do's
- Buy groceries
- Call dentist
- Fix the car

## 💡 Ideas & Possibilities
App idea: habit tracker for Obsidian

---

*Tags: #brain-dump #personal*
"""
    result = reset_to_template(content, ["✅ To Do's", "💡 Ideas & Possibilities"], "2026-04-02")
    assert "Buy groceries" not in result
    assert "App idea" not in result
    assert "last_processed: 2026-04-02" in result
    assert "status: empty" in result
    # Template placeholders should be restored
    assert "<!-- Format:" in result or "<!-- Add" in result


# ── Track B: prose-shaped input with non-whitelist verbs ─────────────────────

def test_regex_extract_prose_nonwhitelist_verbs():
    """The operator's actual writing patterns: 'Flush out', 'Fine Tune', 'Re-apply', 'Dig into'."""
    body = """Email to TMC Personnel to wrap up New Hire - 20260420
Flush out ICP for Leads & Cold Email Solution - 20260421
Fine Tune E7 & start Temple Protocol Website - 20260422
Re-apply to Google Scholarship - 20260425
Dig into ICP for E7 & Legal - 20260425
"""
    tasks = regex_extract_tasks(body, "personal")
    assert len(tasks) >= 5, f"Expected ≥5 tasks, got {len(tasks)}: {tasks}"
    joined = "\n".join(tasks)
    assert "Flush out" in joined
    assert "Fine Tune" in joined
    assert "Re-apply" in joined
    assert "Dig into" in joined


def test_regex_extract_canonical_tags_present():
    """Every extracted task must have [area::] and [priority::]."""
    body = "Flush out ICP for Leads"
    tasks = regex_extract_tasks(body, "business")
    assert len(tasks) >= 1
    for t in tasks:
        assert "[area::" in t
        assert "[priority::" in t


# ── Track B: shorthand dates ─────────────────────────────────────────────────

def test_normalize_shorthand_dates_basic():
    """`- YYYYMMDD` shorthand at end of line → `[due:: YYYY-MM-DD]`."""
    assert normalize_shorthand_dates("Email TMC - 20260420") == "Email TMC [due:: 2026-04-20]"


def test_normalize_shorthand_dates_in_extracted_task():
    body = "Re-apply to Google Scholarship - 20260425"
    tasks = regex_extract_tasks(body, "personal")
    assert len(tasks) == 1
    assert "[due:: 2026-04-25]" in tasks[0]
    # Shorthand must NOT remain literally in the task description
    assert "20260425" not in tasks[0]


def test_normalize_shorthand_dates_invalid_passthrough():
    """Random 8-digit numbers should NOT be parsed as dates."""
    assert normalize_shorthand_dates("Buy 12345678 widgets") == "Buy 12345678 widgets"


# ── Track B: AI fallback fires when regex returns nothing ────────────────────

def test_ai_fallback_fires_on_empty_regex_match():
    """Pure prose with no actionable verbs → regex empty → AI fallback fires."""
    body = "Some musing about a thing without any verb signals at all just nouns nouns nouns blue sky"

    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=
        "- [ ] Investigate the blue-sky idea [area:: personal] [priority:: C]"
    ))]
    fake_client.chat.completions.create.return_value = fake_resp

    tasks = extract_tasks_with_ai_fallback(fake_client, body, "personal", "2026-04-25")
    assert len(tasks) >= 1
    # The fallback may auto-append [explore:: true] when intent words are present;
    # validate the canonical core, not the optional extension.
    import re as _re
    canonical = _re.sub(r"\s*\[explore::[^\]]+\]\s*$", "", tasks[0]).strip()
    assert validate_task_line(canonical), f"Not canonical: {canonical}"
    assert fake_client.chat.completions.create.called


def test_ai_fallback_explore_autotag():
    """AI flagging research/investigate intent → [explore:: true] auto-applied."""
    body = "Look into the new vector DB landscape"

    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=
        "- [ ] Research vector DB landscape [area:: personal] [priority:: C] [explore:: true]"
    ))]
    fake_client.chat.completions.create.return_value = fake_resp

    tasks = extract_tasks_with_ai_fallback(fake_client, body, "personal", "2026-04-25")
    assert len(tasks) >= 1
    assert "[explore:: true]" in tasks[0]


def test_ai_fallback_auto_adds_explore_when_intent_research():
    """Even if AI omits the [explore:: true] tag, if the description mentions
    research/investigate/explore the post-processor auto-adds it."""
    body = "Anything"

    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=
        "- [ ] Investigate hip surgery alternatives [area:: health] [priority:: B]"
    ))]
    fake_client.chat.completions.create.return_value = fake_resp

    tasks = extract_tasks_with_ai_fallback(fake_client, body, "health", "2026-04-25")
    assert len(tasks) >= 1
    assert "[explore:: true]" in tasks[0]


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 — Intelligent extractor: intent classification + routing,
# source-linking, confidence-gated review queue, fuzzy dedup, telemetry.
# These tests are RED until the new pipeline is built.
# ─────────────────────────────────────────────────────────────────────────────

from process_brain_dump import (
    classify_intent,
    fuzzy_dedup_filter,
    build_source_link,
    route_by_intent,
    write_telemetry_entry,
    confidence_gate,
)


# ── Intent classification ────────────────────────────────────────────────────

def test_classify_intent_action_imperative():
    """Imperative-shaped lines classify as 'action'."""
    item = classify_intent("Email TMC to wrap up new hire")
    assert item["intent"] == "action"


def test_classify_intent_research_explore():
    """Research/explore verbs classify as 'research'."""
    item = classify_intent("Investigate vagal tone monitoring tools")
    assert item["intent"] in ("research", "explore")


def test_classify_intent_question():
    """Lines ending in '?' classify as 'question'."""
    item = classify_intent("Should I quit Parallon?")
    assert item["intent"] == "question"


def test_classify_intent_event():
    """Calendar-shaped lines (Lunch/Meeting/Dinner with X) classify as 'event'."""
    item = classify_intent("Lunch with Reggie tomorrow at noon")
    assert item["intent"] == "event"


def test_classify_intent_reference_url():
    """Bare URLs / 'check out X' classify as 'reference'."""
    item = classify_intent("https://example.com/cool-post")
    assert item["intent"] == "reference"


def test_classify_intent_returns_confidence():
    """Every classification includes a confidence in [0.0, 1.0]."""
    item = classify_intent("Email TMC to wrap up new hire")
    assert "confidence" in item
    assert 0.0 <= item["confidence"] <= 1.0


def test_classify_intent_low_confidence_for_ambiguous():
    """Ambiguous one-word input → low confidence (< 0.6)."""
    item = classify_intent("blue")
    assert item["confidence"] < 0.6


# ── Area auto-detection via keyword dictionary ───────────────────────────────

def test_classify_intent_area_christy_family():
    item = classify_intent("Talk to Christy about weekend plans")
    assert item["area"] == "family"


def test_classify_intent_area_echelon_business():
    item = classify_intent("Refine Echelon Seven ICP for cold outreach")
    assert item["area"] == "business"


def test_classify_intent_area_hip_health():
    item = classify_intent("Decide on hip surgery this month")
    assert item["area"] == "health"


def test_classify_intent_area_parallon_work():
    item = classify_intent("Wrap up Parallon BAM Q2 report")
    assert item["area"] == "work"


def test_classify_intent_area_unknown_defaults_personal():
    """No keyword match + AI-uncertain → personal."""
    item = classify_intent("Random thing with no domain markers", file_area_hint=None)
    assert item["area"] == "personal"


# ── Priority inference ───────────────────────────────────────────────────────

def test_classify_intent_priority_urgent_to_a():
    item = classify_intent("Reply to client ASAP — urgent")
    assert item["priority"] == "A"


def test_classify_intent_priority_should_to_b():
    item = classify_intent("Should review the Q2 metrics")
    assert item["priority"] == "B"


def test_classify_intent_priority_someday_to_c():
    item = classify_intent("Maybe someday try woodworking")
    assert item["priority"] == "C"


# ── Source-linking ───────────────────────────────────────────────────────────

def test_build_source_link_basic():
    """Source link references the brain dump filename without extension."""
    link = build_source_link("BrainDump — Personal.md", "2026-04-25")
    assert link.startswith("[source::")
    assert "[[" in link
    assert "BrainDump" in link or "braindump" in link.lower()


def test_build_source_link_synthetic_test():
    link = build_source_link("test-synthetic-1234.md", "2026-04-25")
    assert "[source::" in link
    assert "test-synthetic" in link


# ── Routing by intent ────────────────────────────────────────────────────────

def test_route_by_intent_action_to_mtl():
    item = {"intent": "action", "task": "Email TMC", "area": "work",
            "priority": "B", "due": None, "confidence": 0.9}
    result = route_by_intent(item, source_file="BrainDump — Personal.md", today="2026-04-25")
    assert result["destination"] == "mtl"
    assert result["task_line"].startswith("- [ ]")
    assert "[area:: work]" in result["task_line"]
    assert "[source::" in result["task_line"]


def test_route_by_intent_research_to_mtl_with_explore():
    item = {"intent": "research", "task": "Investigate vagal tone tools",
            "area": "health", "priority": "C", "due": None, "confidence": 0.9}
    result = route_by_intent(item, source_file="BrainDump — Personal.md", today="2026-04-25")
    assert result["destination"] == "mtl"
    assert "[explore:: true]" in result["task_line"]


def test_route_by_intent_question_to_daily_note():
    item = {"intent": "question", "task": "Should I quit Parallon?",
            "area": "work", "priority": "B", "due": None, "confidence": 0.9}
    result = route_by_intent(item, source_file="BrainDump — Personal.md", today="2026-04-25")
    assert result["destination"] == "daily_note"
    assert result["section"] in ("Open Questions", "❓ Open Questions")


def test_route_by_intent_event_to_daily_note_events():
    item = {"intent": "event", "task": "Lunch with Reggie tomorrow",
            "area": "personal", "priority": "B", "due": None, "confidence": 0.9}
    result = route_by_intent(item, source_file="BrainDump — Personal.md", today="2026-04-25")
    assert result["destination"] == "daily_note"
    assert result["section"] in ("Events", "📅 Events")


def test_route_by_intent_reference_to_captured_refs():
    item = {"intent": "reference", "task": "https://example.com/cool",
            "area": "personal", "priority": "C", "due": None, "confidence": 0.9}
    result = route_by_intent(item, source_file="BrainDump — Personal.md", today="2026-04-25")
    assert result["destination"] == "captured_references"
    assert "2026-04" in result["target_key"]


# ── Confidence gating ────────────────────────────────────────────────────────

def test_confidence_gate_high_confidence_passes():
    """Items with confidence >= 0.6 pass through unchanged."""
    item = {"intent": "action", "confidence": 0.85}
    assert confidence_gate(item) == "promote"


def test_confidence_gate_low_confidence_to_review():
    """Items with confidence < 0.6 route to review-queue."""
    item = {"intent": "action", "confidence": 0.4}
    assert confidence_gate(item) == "review_queue"


def test_confidence_gate_threshold_boundary():
    """Boundary: exactly 0.6 promotes."""
    assert confidence_gate({"confidence": 0.6}) == "promote"
    assert confidence_gate({"confidence": 0.59}) == "review_queue"


# ── Fuzzy dedup ──────────────────────────────────────────────────────────────

def test_fuzzy_dedup_exact_match_dropped():
    existing = {"email tmc to wrap up new hire"}
    candidates = ["- [ ] Email TMC to wrap up new hire [area:: work] [priority:: B]"]
    kept = fuzzy_dedup_filter(candidates, existing, threshold=0.85)
    assert len(kept) == 0


def test_fuzzy_dedup_near_match_dropped():
    """≥85% similarity → drop as duplicate."""
    existing = {"email tmc personnel to wrap up new hire"}
    # near-identical phrasing should match at ≥85%
    candidates = ["- [ ] Email TMC Personnel to wrap up the new hire [area:: work] [priority:: B]"]
    kept = fuzzy_dedup_filter(candidates, existing, threshold=0.85)
    assert len(kept) == 0


def test_fuzzy_dedup_distinct_kept():
    existing = {"email tmc personnel to wrap up new hire"}
    candidates = ["- [ ] Re-apply to Google Scholarship [area:: personal] [priority:: B]"]
    kept = fuzzy_dedup_filter(candidates, existing, threshold=0.85)
    assert len(kept) == 1


# ── Telemetry sidecar ────────────────────────────────────────────────────────

def test_write_telemetry_entry_appends_jsonl(tmp_path, monkeypatch):
    """Telemetry writes one JSON object per line to brain-dump-extraction.jsonl."""
    from unittest.mock import MagicMock
    fake_s3 = MagicMock()
    fake_s3.get_object.side_effect = Exception("NoSuchKey")
    fake_s3.head_object.return_value = {"ContentLength": 200}

    entry = {
        "timestamp": "2026-04-25T12:00:00Z",
        "file_count": 1,
        "candidates": 7,
        "extracted": 5,
        "ai_calls": 5,
        "dedup_skips": 1,
        "low_confidence": 1,
    }
    write_telemetry_entry(fake_s3, entry, dry_run=False)

    # head_object should have been called for verification
    assert fake_s3.put_object.called
    args, kwargs = fake_s3.put_object.call_args
    body = kwargs.get("Body") or args[2]
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    # Body must be a single JSON object on one line + newline
    assert body.endswith("\n")
    assert '"timestamp"' in body
    assert '"file_count": 1' in body


def test_write_telemetry_entry_appends_to_existing(tmp_path):
    """When file already exists, the new entry is appended (not overwritten)."""
    from unittest.mock import MagicMock
    fake_s3 = MagicMock()
    existing_body = b'{"timestamp": "2026-04-24T12:00:00Z", "file_count": 0}\n'
    fake_s3.get_object.return_value = {"Body": MagicMock(read=lambda: existing_body)}
    fake_s3.head_object.return_value = {"ContentLength": 500}

    entry = {"timestamp": "2026-04-25T12:00:00Z", "file_count": 1}
    write_telemetry_entry(fake_s3, entry, dry_run=False)

    args, kwargs = fake_s3.put_object.call_args
    body = kwargs.get("Body") or args[2]
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    # Both lines must be present
    assert "2026-04-24" in body
    assert "2026-04-25" in body
    assert body.count("\n") == 2


def test_reset_to_template_preserves_other_sections():
    content = """---
status: empty
last_processed:
---

## ⚡ Quick Notes
<!-- Add notes here -->

## ✅ To Do's
Real task here

## 📰 Articles & Resources to Follow Up On
<!-- Add links here -->
"""
    result = reset_to_template(content, ["✅ To Do's"], "2026-04-02")
    assert "Real task here" not in result
    # Quick Notes was NOT extracted, should stay unchanged
    assert "<!-- Add notes here -->" in result

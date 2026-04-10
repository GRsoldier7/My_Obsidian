"""Tests for tools/process_brain_dump.py — section parsing and content detection."""
import pytest
import sys
import os

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

"""
tests/test_process_brain_dump_e2e.py
Full pipeline integration tests for the brain dump processor.

These tests run the complete extraction pipeline end-to-end using:
- Mock S3 (no real MinIO)
- Mock OpenRouter (no real AI calls)
- Fixture brain dump files

Tests marked @pytest.mark.integration require:
  RUN_INTEGRATION_TESTS=1 pytest -m integration
"""
import json
import runpy
import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from process_brain_dump import (
    parse_sections,
    extract_real_sections,
    regex_extract_tasks,
    quality_gate_tasks,
    validate_task_line,
    write_task_file,
    infer_area_from_filename,
    section_type,
    reset_to_template,
    s3_put_verified,
    PROCESSED_PREFIX,
    VALID_AREAS,
    VALID_PRIORITIES,
)
from conftest import SAMPLE_BRAIN_DUMP, SAMPLE_BRAIN_DUMP_EMPTY, SAMPLE_BRAIN_DUMP_TASKS_ONLY


TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Full pipeline: regex-only path ────────────────────────────────────────────

def test_full_pipeline_structured_dump_regex_only():
    """Structured brain dump (checkboxes) → tasks extracted without AI."""
    content = SAMPLE_BRAIN_DUMP_TASKS_ONLY
    sections = parse_sections(content)
    real_sections = extract_real_sections(sections)

    assert "✅ To Do's" in real_sections

    tasks = []
    for header, body in real_sections.items():
        if section_type(header) == "tasks":
            extracted = regex_extract_tasks(body, "work")
            tasks.extend(extracted)

    assert len(tasks) >= 2
    valid_tasks, rejections = quality_gate_tasks(tasks)
    assert len(valid_tasks) >= 2
    assert len(rejections) == 0


def test_full_pipeline_empty_dump_produces_nothing():
    """Template-only brain dump → no sections, no AI calls, no output files."""
    content = SAMPLE_BRAIN_DUMP_EMPTY
    sections = parse_sections(content)
    real_sections = extract_real_sections(sections)

    assert len(real_sections) == 0, "Empty template should produce 0 real sections"


def test_full_pipeline_quality_gate_rejects_malformed():
    """Tasks that don't match canonical format are rejected by quality gate.

    Note: priority is OPTIONAL in the regex — [area:: X] alone is valid.
    """
    tasks = [
        "- [ ] Valid with priority [area:: health] [priority:: A]",  # valid
        "- [ ] Valid without priority [area:: work]",                 # also valid — priority is optional
        "- [ ] Missing area tag [priority:: B]",                      # invalid: no area
        "- [ ] Wrong area [area:: invalid] [priority:: A]",           # invalid: bad area
        "Some prose, not a task",                                      # invalid: not a task
    ]

    valid, rejections = quality_gate_tasks(tasks)

    assert len(valid) == 2
    assert len(rejections) == 3


def test_full_pipeline_write_task_file_called_with_tasks():
    """write_task_file creates a MinIO file when tasks are provided."""
    s3 = MagicMock()
    s3.head_object.return_value = {"ContentLength": 500}

    tasks = [
        "- [ ] Deliver Union project report [area:: work] [priority:: A]",
        "- [ ] Schedule exit conversation [area:: work] [priority:: B]",
    ]

    written = write_task_file(s3, tasks, "BrainDump-Work.md", "work", TODAY, dry_run=False)

    assert written == 2
    s3.put_object.assert_called_once()
    put_call = s3.put_object.call_args
    key = put_call.kwargs.get("Key") or put_call[1].get("Key")
    assert key.startswith(PROCESSED_PREFIX)
    assert TODAY in key


def test_full_pipeline_write_task_file_empty_tasks_no_write():
    """write_task_file does NOT create a file when task list is empty."""
    s3 = MagicMock()

    written = write_task_file(s3, [], "BrainDump-Work.md", "work", TODAY, dry_run=False)

    assert written == 0
    s3.put_object.assert_not_called()


def test_full_pipeline_write_task_file_dry_run():
    """dry_run=True skips all S3 writes."""
    s3 = MagicMock()
    tasks = ["- [ ] Task [area:: work] [priority:: A]"]

    written = write_task_file(s3, tasks, "BrainDump-Work.md", "work", TODAY, dry_run=True)

    assert written == 1  # dry run still reports "would write" count
    s3.put_object.assert_not_called()


# ── Task format validation ────────────────────────────────────────────────────

@pytest.mark.parametrize("task,expected_valid", [
    ("- [ ] Buy milk [area:: personal] [priority:: B]", True),
    ("- [ ] Call Dr Smith [area:: health] [priority:: A]", True),
    ("- [ ] Task with due date [area:: work] [priority:: A] [due:: 2026-04-15]", True),
    ("- [ ] All 8 areas valid [area:: faith] [priority:: C]", True),
    ("- [ ] All 8 areas valid [area:: family] [priority:: C]", True),
    ("- [ ] All 8 areas valid [area:: business] [priority:: C]", True),
    ("- [ ] All 8 areas valid [area:: consulting] [priority:: C]", True),
    ("- [ ] All 8 areas valid [area:: home] [priority:: C]", True),
    # Invalid cases
    ("- [x] Completed task [area:: work] [priority:: A]", False),      # completed not unchecked
    ("- [ ] No area tag [priority:: A]", False),                        # missing area
    ("- [ ] No priority [area:: work]", True),                          # valid: priority is optional in regex
    ("- [ ] Bad priority [area:: work] [priority:: D]", False),         # D is not valid
    ("- [ ] Bad area [area:: invalid] [priority:: A]", False),          # invalid area
    ("Just a sentence without checkbox", False),                         # no checkbox
    ("", False),                                                          # empty
])
def test_validate_task_line(task, expected_valid):
    assert validate_task_line(task) == expected_valid


# ── Section routing ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("header,expected_type", [
    ("✅ To Do's", "tasks"),
    ("🎯 Needle Movers", "tasks"),
    ("🔁 Recurring / Rhythms", "tasks"),
    ("🗂️ Things to Organize & Follow Up On", "tasks"),
    ("💡 Ideas & Possibilities", "notes"),
    ("⚡ Quick Notes", "notes"),
    ("📰 Articles & Resources to Follow Up On", "articles"),
])
def test_section_type_routing(header, expected_type):
    assert section_type(header) == expected_type


# ── Area inference ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename,expected_area", [
    ("BrainDump — Work.md", "work"),
    ("BrainDump — Faith.md", "faith"),
    ("BrainDump — Health.md", "health"),
    ("BrainDump — Business.md", "business"),
    ("BrainDump — Consulting.md", "consulting"),
    ("BrainDump — Home.md", "home"),
    ("BrainDump — Family.md", "family"),
    ("BrainDump — Parallon.md", "work"),
    ("BrainDump — Echelon.md", "business"),
    ("Random filename.md", "personal"),  # default fallback
])
def test_infer_area_from_filename(filename, expected_area):
    assert infer_area_from_filename(filename) == expected_area


# ── Task output file format ───────────────────────────────────────────────────

def test_task_file_content_has_frontmatter():
    """Written task file must have YAML frontmatter."""
    s3 = MagicMock()
    s3.head_object.return_value = {"ContentLength": 200}

    tasks = ["- [ ] Test task [area:: work] [priority:: A]"]
    write_task_file(s3, tasks, "BrainDump-Work.md", "work", TODAY, dry_run=False)

    put_call = s3.put_object.call_args
    body_bytes = put_call.kwargs.get("Body") or put_call[1].get("Body")
    body = body_bytes.decode("utf-8") if isinstance(body_bytes, bytes) else body_bytes

    assert body.startswith("---"), "Task file must start with YAML frontmatter"
    assert "source: BrainDump-Work.md" in body
    assert "area: work" in body
    assert "type: extracted-tasks" in body


def test_task_file_contains_all_tasks():
    """All passed tasks appear in the output file body."""
    s3 = MagicMock()
    s3.head_object.return_value = {"ContentLength": 300}

    tasks = [
        "- [ ] Task one [area:: work] [priority:: A]",
        "- [ ] Task two [area:: work] [priority:: B]",
        "- [ ] Task three [area:: work] [priority:: C]",
    ]
    write_task_file(s3, tasks, "BrainDump-Work.md", "work", TODAY, dry_run=False)

    put_call = s3.put_object.call_args
    body_bytes = put_call.kwargs.get("Body") or put_call[1].get("Body")
    body = body_bytes.decode("utf-8") if isinstance(body_bytes, bytes) else body_bytes

    for task in tasks:
        assert task in body, f"Task missing from output: {task}"


# ── reset_to_template ─────────────────────────────────────────────────────────

def test_reset_to_template_returns_string():
    """reset_to_template returns a non-empty string."""
    content = SAMPLE_BRAIN_DUMP
    extracted_headers = ["✅ To Do's"]
    result = reset_to_template(content, extracted_headers, TODAY)
    assert isinstance(result, str)
    assert len(result) > 0


def test_reset_to_template_has_section_headers():
    """Reset template still contains section headers after reset."""
    content = SAMPLE_BRAIN_DUMP
    extracted_headers = ["✅ To Do's"]
    result = reset_to_template(content, extracted_headers, TODAY)
    assert "## " in result


# ── Integration tests (require live MinIO + OpenRouter) ──────────────────────

@pytest.mark.integration
def test_integration_full_run_against_live_minio():
    """
    Full pipeline test against the real MinIO and OpenRouter.
    Run with: RUN_INTEGRATION_TESTS=1 pytest tests/ -m integration
    """
    if not os.environ.get("RUN_INTEGRATION_TESTS"):
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")

    repo_root = os.path.join(os.path.dirname(__file__), "..")
    script_path = os.path.join(repo_root, "scripts", "e2e_test.py")

    with patch.object(sys, "argv", [script_path]):
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(script_path, run_name="__main__")

    assert exc.value.code == 0

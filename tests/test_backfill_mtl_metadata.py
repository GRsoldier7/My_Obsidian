"""Tests for scripts/backfill_mtl_metadata.py — HYG-B4.

Discipline guarantees verified here:
  1. Parser correctly classifies every task into one of 5 buckets.
  2. Idempotency: running --apply twice on the same MTL produces zero changes
     on the second pass (the TODO marker is never duplicated).
  3. Dry-run safety: --dry-run never calls put_object on the MTL key (mock S3).
  4. Hallucination guard: closed tasks with no recoverable date get the
     ``<!-- needs-completion-date -->`` marker, NEVER a fabricated date.
  5. Format preservation: lines not classified as closed_no_completion pass
     through byte-identical (whitespace, inline-field ordering, etc.).
  6. Concurrency guard: aborts when MTL was modified within 60s.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Provide MinIO env vars so module import works (the s3_client() factory reads them
# lazily, but we patch boto3.client in each test).
os.environ.setdefault("MINIO_ENDPOINT", "http://test.invalid:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "test")

import backfill_mtl_metadata as bf  # noqa: E402


# ── Fixture MTL ───────────────────────────────────────────────────────────────
SAMPLE_MTL = """# Master Task List

## Section header — not a task

- [ ] Open task with everything [area:: business] [priority:: A] [due:: 2026-05-20]
- [ ] Open task missing due [area:: home] [priority:: B]
- [ ] Open task with no fields at all
- [x] Closed task with completion [area:: faith] [priority:: A] [completion:: 2026-05-10]
- [x] Closed task no completion [area:: health] [priority:: B]
- [x] Another closed no completion [area:: business] [priority:: C]
- [x] Already marked closed [area:: home] <!-- needs-completion-date -->

Some prose line that is not a task.
- not a task at all
"""

MALFORMED_MTL = "- [ ]   \n"  # well-formed checkbox + only whitespace afterwards


# ── Parser ────────────────────────────────────────────────────────────────────
def test_parse_tasks_finds_every_task_line():
    tasks = bf.parse_tasks(SAMPLE_MTL)
    # 7 well-formed task lines; non-task prose lines ignored
    assert len(tasks) == 7


def test_parse_tasks_extracts_inline_fields():
    tasks = bf.parse_tasks(SAMPLE_MTL)
    t = next(t for t in tasks if t.description.startswith("Open task with everything"))
    assert t.fields["area"] == "business"
    assert t.fields["priority"] == "A"
    assert t.fields["due"] == "2026-05-20"
    assert t.has_due is True


def test_parse_tasks_detects_todo_marker():
    tasks = bf.parse_tasks(SAMPLE_MTL)
    t = next(t for t in tasks if "Already marked closed" in t.description)
    assert t.has_todo_marker is True


# ── Classification ────────────────────────────────────────────────────────────
def test_classify_buckets_correctly():
    tasks = bf.parse_tasks(SAMPLE_MTL)
    c = bf.classify(tasks)
    # Open with due (1), open missing due (1 + 1 fieldless), closed with completion (1),
    # closed missing completion (2 plain + 1 already-marked).
    assert len(c.open_has_due) == 1
    assert len(c.open_no_due) == 2
    assert len(c.closed_has_completion) == 1
    assert len(c.closed_no_completion) == 3
    assert len(c.malformed) == 0


def test_classify_isolates_malformed():
    tasks = bf.parse_tasks(MALFORMED_MTL)
    c = bf.classify(tasks)
    assert len(c.malformed) == 1
    assert c.total == 1


# ── Apply (TODO markers only) ─────────────────────────────────────────────────
def test_apply_only_marks_closed_no_completion():
    tasks = bf.parse_tasks(SAMPLE_MTL)
    c = bf.classify(tasks)
    new_mtl, modified = bf.apply_todo_markers(SAMPLE_MTL, c)
    # The already-marked line is skipped; only 2 new markers added
    assert modified == 2
    assert new_mtl.count(bf.TODO_MARKER) == 3  # 1 pre-existing + 2 new


def test_apply_idempotency():
    tasks = bf.parse_tasks(SAMPLE_MTL)
    c1 = bf.classify(tasks)
    after_first, modified_first = bf.apply_todo_markers(SAMPLE_MTL, c1)
    # Re-parse + re-classify the already-modified MTL
    tasks2 = bf.parse_tasks(after_first)
    c2 = bf.classify(tasks2)
    after_second, modified_second = bf.apply_todo_markers(after_first, c2)
    assert modified_first == 2
    assert modified_second == 0
    assert after_first == after_second


def test_apply_preserves_open_tasks_byte_identical():
    """Open-task lines must pass through untouched — including the one missing due."""
    tasks = bf.parse_tasks(SAMPLE_MTL)
    c = bf.classify(tasks)
    new_mtl, _ = bf.apply_todo_markers(SAMPLE_MTL, c)
    original_lines = SAMPLE_MTL.splitlines()
    new_lines = new_mtl.splitlines()
    for orig, new in zip(original_lines, new_lines):
        if orig.startswith("- [ ]"):
            assert orig == new, f"Open task line modified: {orig!r} → {new!r}"


def test_apply_preserves_trailing_newline():
    assert SAMPLE_MTL.endswith("\n")
    tasks = bf.parse_tasks(SAMPLE_MTL)
    c = bf.classify(tasks)
    new_mtl, _ = bf.apply_todo_markers(SAMPLE_MTL, c)
    assert new_mtl.endswith("\n")


# ── Hallucination guard ──────────────────────────────────────────────────────
def test_hallucination_guard_no_fabricated_dates():
    """Closed tasks missing completion get the marker, never a date."""
    tasks = bf.parse_tasks(SAMPLE_MTL)
    c = bf.classify(tasks)
    new_mtl, _ = bf.apply_todo_markers(SAMPLE_MTL, c)
    # No newly inserted [completion::] field
    original_completions = SAMPLE_MTL.count("[completion::")
    new_completions = new_mtl.count("[completion::")
    assert new_completions == original_completions
    # Every closed-no-completion target now carries the marker
    for t in c.closed_no_completion:
        target_line = new_mtl.splitlines()[t.line_no - 1]
        assert bf.TODO_MARKER in target_line


# ── Dry-run safety (mocked S3) ───────────────────────────────────────────────
def _mock_s3_with_mtl(mtl: str, *, last_modified: datetime | None = None):
    """Build a mock S3 that tracks per-key body sizes so head_object responses
    line up with whatever put_object last wrote. Required because
    tools.s3_verified.put_text_verified compares head_object ContentLength
    against body length; a single-static head_object mock would explode every
    non-MTL-sized write (backup, report, etc.)."""
    last_modified = last_modified or (datetime.now(timezone.utc) - timedelta(minutes=10))
    body = MagicMock()
    body.read.return_value = mtl.encode("utf-8")
    s3 = MagicMock()
    s3.get_object.return_value = {
        "Body": body,
        "ETag": '"abc123"',
        "LastModified": last_modified,
    }
    # Pre-seed the MTL key size so fetch_mtl_last_modified + the read path
    # see consistent ContentLength even before any writes.
    sizes_by_key: dict[str, int] = {bf.MTL_KEY: len(mtl.encode("utf-8"))}

    def _put_object_side_effect(**kwargs):
        sizes_by_key[kwargs["Key"]] = len(kwargs["Body"])
        return {"ETag": '"new-etag"'}

    def _head_object_side_effect(**kwargs):
        return {
            "ContentLength": sizes_by_key.get(kwargs["Key"], 0),
            "ETag": '"abc123"',
            "LastModified": last_modified,
        }

    s3.put_object.side_effect = _put_object_side_effect
    s3.head_object.side_effect = _head_object_side_effect
    s3.get_paginator.return_value.paginate.return_value = iter([])  # no versions
    return s3


def test_dry_run_never_writes_mtl():
    s3 = _mock_s3_with_mtl(SAMPLE_MTL)
    with patch.object(bf, "s3_client", return_value=s3):
        args = bf.build_parser().parse_args(["--dry-run", "--skip-report"])
        rc = bf.run(args)
    assert rc == 0
    # put_object may be called for the run log (separate key); verify the MTL key was never written.
    put_calls = [c for c in s3.put_object.call_args_list if c.kwargs.get("Key") == bf.MTL_KEY]
    assert put_calls == [], f"Dry run wrote to MTL: {put_calls}"


def test_review_only_never_writes_mtl():
    s3 = _mock_s3_with_mtl(SAMPLE_MTL)
    with patch.object(bf, "s3_client", return_value=s3):
        args = bf.build_parser().parse_args(["--review-only", "--skip-report"])
        rc = bf.run(args)
    assert rc == 0
    put_calls = [c for c in s3.put_object.call_args_list if c.kwargs.get("Key") == bf.MTL_KEY]
    assert put_calls == []


def test_apply_writes_mtl_and_backup_with_if_match():
    s3 = _mock_s3_with_mtl(SAMPLE_MTL)
    with patch.object(bf, "s3_client", return_value=s3):
        args = bf.build_parser().parse_args(["--apply", "--skip-report"])
        rc = bf.run(args)
    assert rc == 0
    keys_written = [c.kwargs["Key"] for c in s3.put_object.call_args_list]
    # Backup written before MTL
    assert any(k.startswith("99_System/backup/MTL-pre-backfill-") for k in keys_written)
    assert bf.MTL_KEY in keys_written
    # MTL write carried If-Match guard
    mtl_calls = [c for c in s3.put_object.call_args_list if c.kwargs["Key"] == bf.MTL_KEY]
    assert mtl_calls and mtl_calls[0].kwargs.get("IfMatch") == '"abc123"'


# ── Concurrency guard ────────────────────────────────────────────────────────
def test_concurrency_guard_aborts_on_recent_write():
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    s3 = _mock_s3_with_mtl(SAMPLE_MTL, last_modified=recent)
    with patch.object(bf, "s3_client", return_value=s3):
        args = bf.build_parser().parse_args(["--dry-run", "--skip-report"])
        rc = bf.run(args)
    assert rc == 3  # concurrency abort code
    assert not s3.put_object.called


def test_force_overrides_concurrency_guard():
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    s3 = _mock_s3_with_mtl(SAMPLE_MTL, last_modified=recent)
    with patch.object(bf, "s3_client", return_value=s3):
        args = bf.build_parser().parse_args(["--dry-run", "--skip-report", "--force"])
        rc = bf.run(args)
    assert rc == 0


# ── Argparse contract ────────────────────────────────────────────────────────
def test_default_is_dry_run():
    args = bf.build_parser().parse_args([])
    assert args.dry_run is True
    assert args.apply is False


def test_apply_and_review_are_mutually_exclusive():
    parser = bf.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--apply", "--review-only"])

"""Tests for tools/task_id.py — Phase C skeleton (ADR-0009)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import task_id as tid  # noqa: E402


# ── Format ────────────────────────────────────────────────────────────────────
def test_generated_id_matches_canonical_regex():
    now = datetime(2026, 5, 20, 7, 0, 0, tzinfo=timezone.utc)
    out = tid.generate_task_id("business", "Ship the SOW draft", now)
    assert tid.is_valid_task_id(out)
    parsed = tid.parse_task_id(out)
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.week == 21  # 2026-05-20 is in ISO week 21


def test_parse_rejects_garbage():
    assert tid.parse_task_id("not-a-task-id") is None
    assert tid.parse_task_id("t-2026w99-abcd") is not None  # 99 is technically allowed by regex
    assert tid.parse_task_id("t-2026w21-XYZ") is None       # uppercase rejected
    assert tid.parse_task_id("t-2026w21-ab") is None        # too short (<4)
    assert tid.parse_task_id("t-2026w21-zzzz") is None      # z not in hex alphabet


def test_is_valid_task_id_basic():
    assert tid.is_valid_task_id("t-2026w21-a7f1")
    assert not tid.is_valid_task_id("t-2026w21-A7F1")
    assert not tid.is_valid_task_id("t-2026w21-a7f")  # 3 chars
    assert tid.is_valid_task_id("t-2026w21-abcdef0")  # 7 hex chars OK


# ── Determinism + uniqueness ─────────────────────────────────────────────────
def test_same_inputs_same_id():
    ts = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    a = tid.generate_task_id("home", "Mow the lawn", ts)
    b = tid.generate_task_id("home", "Mow the lawn", ts)
    assert a == b


def test_different_areas_different_id():
    ts = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    a = tid.generate_task_id("home", "Same description", ts)
    b = tid.generate_task_id("business", "Same description", ts)
    assert a != b


def test_different_descriptions_different_id():
    ts = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    a = tid.generate_task_id("home", "Task A", ts)
    b = tid.generate_task_id("home", "Task B", ts)
    assert a != b


def test_whitespace_normalized_in_description():
    ts = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    a = tid.generate_task_id("home", "Mow  the   lawn", ts)
    b = tid.generate_task_id("home", " Mow the lawn ", ts)
    assert a == b


# ── Tz + validation ──────────────────────────────────────────────────────────
def test_naive_datetime_rejected():
    naive = datetime(2026, 5, 19, 12, 0, 0)  # no tzinfo
    with pytest.raises(ValueError):
        tid.generate_task_id("home", "x", naive)


def test_hash_len_clamped():
    ts = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        tid.generate_task_id("home", "x", ts, hash_len=3)
    with pytest.raises(ValueError):
        tid.generate_task_id("home", "x", ts, hash_len=9)


def test_hash_len_escalation_produces_longer_id():
    ts = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    short = tid.generate_task_id("home", "x", ts, hash_len=4)
    long = tid.generate_task_id("home", "x", ts, hash_len=6)
    parsed_short = tid.parse_task_id(short)
    parsed_long = tid.parse_task_id(long)
    assert len(parsed_short.hash_part) == 4
    assert len(parsed_long.hash_part) == 6
    # The first 4 chars are NOT guaranteed to overlap — hash bytes consumed differently.


# ── Collision check ──────────────────────────────────────────────────────────
def test_collides_detects_existing():
    existing = {"t-2026w21-a7f1", "t-2026w21-b9e2"}
    assert tid.collides("t-2026w21-a7f1", existing)
    assert not tid.collides("t-2026w21-c0c0", existing)


def test_hex_alphabet_only_in_real_output():
    ts = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    out = tid.generate_task_id("home", "test", ts)
    parsed = tid.parse_task_id(out)
    assert parsed is not None
    assert all(c in "0123456789abcdef" for c in parsed.hash_part)


def test_collides_returns_false_for_invalid_input():
    assert not tid.collides("garbage", set())


# ── Backing file path ────────────────────────────────────────────────────────
def test_derive_backing_file_path_happy():
    out = tid.derive_backing_file_path("t-2026w21-a7f1", "business")
    assert out == "30_Tasks/business/t-2026w21-a7f1.md"


def test_derive_backing_file_path_rejects_bad_area():
    with pytest.raises(ValueError):
        tid.derive_backing_file_path("t-2026w21-a7f1", "")
    with pytest.raises(ValueError):
        tid.derive_backing_file_path("t-2026w21-a7f1", "../escape")
    with pytest.raises(ValueError):
        tid.derive_backing_file_path("t-2026w21-a7f1", ".hidden")


def test_derive_backing_file_path_rejects_bad_id():
    with pytest.raises(ValueError):
        tid.derive_backing_file_path("not-an-id", "home")


# ── Week anchor accessor ─────────────────────────────────────────────────────
def test_week_anchor_property():
    parsed = tid.parse_task_id("t-2026w21-a7f1")
    assert parsed.week_anchor == "2026w21"

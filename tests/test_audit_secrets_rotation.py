"""Tests for scripts/audit_secrets_rotation.py."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_secrets_rotation as asr  # noqa: E402


# ── Fixture markdown ──────────────────────────────────────────────────────────
SAMPLE_MD = """# Heading prose ignored by parser.

Some unrelated content.

## Rotation cadence table

| Edge / secret    | Type   | Where it lives | Rotation cadence | Last rotated | Next due   | Runbook |
|------------------|--------|----------------|------------------|--------------|------------|---------|
| Token A          | bearer | .env A         | 90d              | 2026-01-01   | 2026-04-01 | runbook |
| Token B          | bearer | .env B         | 90d              | 2026-05-01   | 2026-08-01 | runbook |
| Token C          | bearer | .env C         | 90d              | 2026-04-15   | 2026-07-15 | runbook |
| Token D (TBD)    | bearer | .env D         | 90d              | TBD          | TBD        | runbook |
| MinIO            | a+s    | .env M         | 180d             | 2026-04-08*  | 2026-10-05 | runbook |

End of table.

More prose.
"""


def test_parse_table_returns_all_rows():
    rows = asr.parse_table(SAMPLE_MD)
    assert len(rows) == 5
    assert rows[0].name == "Token A"


def test_parse_table_picks_correct_columns():
    rows = asr.parse_table(SAMPLE_MD)
    a = rows[0]
    assert a.last_rotated == "2026-01-01"
    assert a.next_due == "2026-04-01"
    assert a.next_due_date == date(2026, 4, 1)


def test_parse_table_handles_unparseable_date():
    rows = asr.parse_table(SAMPLE_MD)
    d = next(r for r in rows if r.name.startswith("Token D"))
    assert d.next_due_date is None


def test_parse_table_handles_asterisk_suffix():
    """`2026-04-08*` (approx-date marker) still parses."""
    rows = asr.parse_table(SAMPLE_MD)
    minio = next(r for r in rows if r.name == "MinIO")
    # last_rotated has the asterisk but the ISO_DATE_RE only matches leading 10 chars
    assert minio.next_due_date == date(2026, 10, 5)


# ── Classification ────────────────────────────────────────────────────────────
def test_classify_at_2026_05_16_with_14d_window():
    rows = asr.parse_table(SAMPLE_MD)
    buckets = asr.classify(rows, today=date(2026, 5, 16), warn_days=14)
    overdue_names = [r.name for r in buckets["overdue"]]
    warn_names = [r.name for r in buckets["warn"]]
    ok_names = [r.name for r in buckets["ok"]]
    assert "Token A" in overdue_names              # 2026-04-01 < 2026-05-16
    assert "Token B" in ok_names                   # 2026-08-01 well future
    assert "Token C" in ok_names                   # 2026-07-15 > 2026-05-30
    assert "Token D (TBD)" in [r.name for r in buckets["unparseable"]]
    assert "MinIO" in ok_names


def test_classify_warn_window_30_days_pulls_C_into_warn():
    rows = asr.parse_table(SAMPLE_MD)
    # Push today close to Token C's next_due (2026-07-15)
    buckets = asr.classify(rows, today=date(2026, 7, 1), warn_days=30)
    assert any(r.name == "Token C" for r in buckets["warn"])  # 14 days out


def test_classify_overdue_only_when_strictly_past():
    rows = asr.parse_table(SAMPLE_MD)
    # On exact next_due date, NOT overdue (today == next_due → still due TODAY)
    buckets = asr.classify(rows, today=date(2026, 4, 1), warn_days=0)
    assert any(r.name == "Token A" for r in buckets["warn"]) or any(r.name == "Token A" for r in buckets["ok"])
    assert all(r.name != "Token A" for r in buckets["overdue"])


# ── Render + exit codes ───────────────────────────────────────────────────────
def test_render_lists_overdue_and_warn():
    rows = asr.parse_table(SAMPLE_MD)
    buckets = asr.classify(rows, today=date(2026, 5, 16), warn_days=14)
    out = asr.render(buckets, today=date(2026, 5, 16), warn_days=14, verbose=False)
    assert "OVERDUE" in out
    assert "Token A" in out


def test_render_verbose_includes_ok_and_unparseable():
    rows = asr.parse_table(SAMPLE_MD)
    buckets = asr.classify(rows, today=date(2026, 5, 16), warn_days=14)
    out = asr.render(buckets, today=date(2026, 5, 16), warn_days=14, verbose=True)
    assert "Token B" in out
    assert "Token D (TBD)" in out


# ── Real repo doc parses ──────────────────────────────────────────────────────
def test_real_rotation_doc_has_rows():
    md = asr.ROTATION_DOC.read_text(encoding="utf-8")
    rows = asr.parse_table(md)
    assert len(rows) >= 10, f"Expected ≥10 rows in real doc, found {len(rows)}"

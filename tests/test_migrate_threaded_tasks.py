"""Tests for scripts/migrate_threaded_tasks.py — Phase C skeleton."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import migrate_threaded_tasks as mtt  # noqa: E402


SAMPLE_MTL = """# Master Task List

## Active

- [ ] Ship the SOW draft [area:: business] [priority:: A] [due:: 2026-05-23]
- [ ] Mow the lawn [area:: home] [priority:: C]
- [ ] Untagged task that needs an area
- [x] Old completed work [area:: personal] [priority:: B] [completion:: 2026-05-10]
- [ ] Already threaded [area:: faith] [priority:: A] [id:: t-2026w20-deadbeef]

Some prose.
"""


# ── Parser ────────────────────────────────────────────────────────────────────
def test_parse_extracts_all_task_lines():
    tasks = mtt.parse_tasks(SAMPLE_MTL)
    assert len(tasks) == 5


def test_parse_picks_up_inline_fields():
    tasks = mtt.parse_tasks(SAMPLE_MTL)
    sow = next(t for t in tasks if t.description.startswith("Ship the SOW"))
    assert sow.area == "business"
    assert sow.fields["priority"] == "A"


def test_parse_recognizes_existing_id():
    tasks = mtt.parse_tasks(SAMPLE_MTL)
    threaded = next(t for t in tasks if t.existing_id)
    assert threaded.existing_id == "t-2026w20-deadbeef"


# ── Plan classifier ──────────────────────────────────────────────────────────
def test_plan_classifies_correctly():
    plan = mtt.plan_migration(SAMPLE_MTL, now=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc))
    assert len(plan.to_assign) == 3            # SOW + mow + old completed (have area + description, no id)
    assert len(plan.already_threaded) == 1     # the threaded faith line
    assert len(plan.skipped_no_area) == 1      # "Untagged task that needs an area"
    assert len(plan.skipped_malformed) == 0


def test_plan_assigns_valid_task_ids():
    plan = mtt.plan_migration(SAMPLE_MTL, now=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc))
    for entry in plan.to_assign:
        import tools.task_id as tid
        assert tid.is_valid_task_id(entry.proposed_id)
        # Backing file path uses the entry's area
        assert entry.backing_file_path.startswith(f"30_Tasks/{entry.area}/")
        assert entry.backing_file_path.endswith(f"{entry.proposed_id}.md")


def test_plan_idempotent_with_fixed_now():
    """Re-run with same `now` → same IDs."""
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    plan_a = mtt.plan_migration(SAMPLE_MTL, now=now)
    plan_b = mtt.plan_migration(SAMPLE_MTL, now=now)
    ids_a = [e.proposed_id for e in plan_a.to_assign]
    ids_b = [e.proposed_id for e in plan_b.to_assign]
    assert ids_a == ids_b


# ── Report rendering ─────────────────────────────────────────────────────────
def test_render_plan_contains_summary_counts():
    plan = mtt.plan_migration(SAMPLE_MTL, now=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc))
    out = mtt.render_plan_report(plan, run_ts="2026-05-20T12:00:00Z")
    assert "Will assign new `[id::]`" in out
    assert "Already threaded" in out
    assert "missing `[area::]`" in out


def test_render_plan_lists_skipped_no_area():
    plan = mtt.plan_migration(SAMPLE_MTL, now=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc))
    out = mtt.render_plan_report(plan, run_ts="2026-05-20T12:00:00Z")
    assert "Untagged task that needs an area" in out


# ── Apply + Verify are stubbed ───────────────────────────────────────────────
def test_apply_is_stubbed():
    plan = mtt.MigrationPlan()
    with pytest.raises(NotImplementedError):
        mtt.apply_migration(plan)


def test_verify_is_stubbed():
    plan = mtt.MigrationPlan()
    with pytest.raises(NotImplementedError):
        mtt.verify_migration(plan)


# ── Edge cases ───────────────────────────────────────────────────────────────
def test_empty_mtl_produces_empty_plan():
    plan = mtt.plan_migration("")
    assert plan.parsed_tasks == 0
    assert plan.entries == []


def test_mtl_without_tasks_produces_no_entries():
    plan = mtt.plan_migration("# heading\n\nprose only\n")
    assert plan.parsed_tasks == 0
    assert plan.entries == []

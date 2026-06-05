"""
Tests for the operator-summary state file emission added in ADR-0006.

Covers `build_operator_summary` (pure function over RunLog) — the I/O wrapper
`write_operator_summary` is not unit-tested here; live MinIO behavior is
covered by the e2e suite.

A4 SinkInputContract (2026-05-29): `build_operator_summary` now returns a
`BrainDumpSummary` dataclass instead of a plain dict. Tests assert on the
serialised `.to_dict()` payload so they exercise the exact JSON shape that
lands at rest in 99_System/state/last-brain-dump-summary.json.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from process_brain_dump import RunLog, build_operator_summary  # noqa: E402
from tools.sink_contracts import (  # noqa: E402
    SCHEMA_NAME_SUMMARY,
    SCHEMA_VERSION_SUMMARY,
    BrainDumpSummary,
)


def test_build_operator_summary_empty_run():
    log = RunLog(
        run_date="2026-05-06",
        started_at="2026-05-06T07:00:00+00:00",
        finished_at="2026-05-06T07:00:01+00:00",
        status="success",
    )
    summary = build_operator_summary(log)
    assert isinstance(summary, BrainDumpSummary)
    out = summary.to_dict()
    assert out["schema_version"] == SCHEMA_VERSION_SUMMARY
    assert out["schema"] == SCHEMA_NAME_SUMMARY
    assert out["status"] == "success"
    assert out["tasks_written"] == 0
    assert out["top_added_tasks"] == []
    assert out["total_added_tasks"] == 0
    assert out["files_extracted"] == []
    assert out["run_finished_at"] == "2026-05-06T07:00:01+00:00"


def test_build_operator_summary_parses_added_task_lines():
    log = RunLog(
        run_date="2026-05-06",
        started_at="2026-05-06T07:00:00+00:00",
        finished_at="2026-05-06T07:00:05+00:00",
        status="success",
        tasks_written=3,
        articles_queued=1,
    )
    log.new_tasks_added = [
        "- [ ] Ship landing page [area:: business] [priority:: A] [due:: 2026-05-10]",
        "- [ ] Draft pitch deck [area:: business] [priority:: B]",
        "- [ ] Outline next sermon [area:: faith] [priority:: A]",
    ]
    out = build_operator_summary(log).to_dict()
    assert out["total_added_tasks"] == 3
    assert len(out["top_added_tasks"]) == 3

    # Priority A first, then B
    priorities = [t["priority"] for t in out["top_added_tasks"]]
    assert priorities[0] == "A"
    assert priorities[-1] == "B"

    descs = [t["desc"] for t in out["top_added_tasks"]]
    assert "Ship landing page" in descs
    assert "Outline next sermon" in descs

    # Inline metadata fields are stripped from desc.
    for t in out["top_added_tasks"]:
        assert "[area::" not in t["desc"]
        assert "[priority::" not in t["desc"]


def test_build_operator_summary_tolerates_unparseable_lines():
    log = RunLog(run_date="2026-05-06", status="success")
    log.new_tasks_added = [
        "garbage line that doesn't start with checkbox",
        "- [ ] Real task [area:: personal] [priority:: C]",
    ]
    out = build_operator_summary(log).to_dict()
    assert out["total_added_tasks"] == 1
    assert out["top_added_tasks"][0]["desc"] == "Real task"


def test_build_operator_summary_respects_top_n():
    log = RunLog(run_date="2026-05-06", status="success")
    log.new_tasks_added = [
        f"- [ ] Task {i} [area:: personal] [priority:: B]" for i in range(20)
    ]
    out = build_operator_summary(log, top_n=5).to_dict()
    assert len(out["top_added_tasks"]) == 5
    assert out["total_added_tasks"] == 20


def test_build_operator_summary_carries_files_lists_and_state_counts():
    log = RunLog(run_date="2026-05-06", status="partial")
    log.files_extracted = ["BrainDump — Personal.md"]
    log.files_partial = [{"file": "BrainDump — Work.md", "reasons": ["mtl_put_or_head_failed"]}]
    log.files_error = [{"file": "BrainDump — Faith.md", "error": "openrouter timeout"}]
    log.files_by_state["extracted"] = 1
    log.files_by_state["partial"] = 1
    log.items_routed["review_queue"] = 2

    out = build_operator_summary(log).to_dict()
    assert out["files_extracted"] == ["BrainDump — Personal.md"]
    assert out["files_partial"][0]["file"] == "BrainDump — Work.md"
    assert out["files_error"][0]["error"] == "openrouter timeout"
    assert out["files_by_state"]["extracted"] == 1
    assert out["review_added"] == 2

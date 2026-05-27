#!/usr/bin/env python3
"""
scripts/migrate_threaded_tasks.py — Phase C migration tool (ADR-0009 step 2).

Three phases per ADR-0009:
  1. PLAN  — Read MTL from MinIO. Parse every task line. Assign a stable
             [id::] via tools.task_id.generate_task_id. Emit a report to
             99_System/reports/threaded-tasks-migration-plan-<date>.md.
             Idempotent: re-runs against the same MTL produce identical IDs
             (deterministic generator).
  2. APPLY — Write the modified MTL back via verified S3 put (If-Match ETag
             guard). Create the per-task backing file at
             30_Tasks/<area>/<id>.md with the YAML front-matter from
             docs/schemas/task-backing-file.v1.yaml. NOT YET IMPLEMENTED
             (Phase C day-2).
  3. VERIFY — Round-trip every backing file. Read each, derive the MTL line,
              and assert byte-identical match against the MTL we wrote.
              NOT YET IMPLEMENTED (Phase C day-3).

PHASE STATUS: SKELETON. Phase C kickoff is post-soak.
This file is on the `feature/phase-c-f-skeletons` branch until merge.

The PLAN phase is implemented in skeleton form: it works against an in-memory
MTL string. The MinIO read + write paths are stubbed so the audit + the test
suite can exercise the classification logic without live S3.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import task_id as tid  # noqa: E402

# Match canonical task line: `- [ ]` or `- [x]` + description + inline fields.
TASK_LINE_RE = re.compile(r"^- \[([ x])\] (.+?)\s*$", re.MULTILINE)
INLINE_FIELD_RE = re.compile(r"\[(\w+)::\s*([^\]]*?)\]")
EXISTING_ID_RE = re.compile(r"\[id::\s*(t-\d{4}w\d{2}-[a-f0-9]{4,8})\]")


@dataclass
class TaskLine:
    line_no: int
    raw: str
    checked: bool
    description: str
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def existing_id(self) -> str | None:
        return self.fields.get("id")

    @property
    def area(self) -> str | None:
        return self.fields.get("area")


@dataclass
class PlanEntry:
    line_no: int
    raw: str
    description: str
    area: str | None
    existing_id: str | None
    proposed_id: str | None
    backing_file_path: str | None
    action: str            # 'skip-has-id' | 'assign' | 'skip-no-area' | 'skip-malformed'


@dataclass
class MigrationPlan:
    total_lines: int = 0
    parsed_tasks: int = 0
    entries: list[PlanEntry] = field(default_factory=list)

    @property
    def to_assign(self) -> list[PlanEntry]:
        return [e for e in self.entries if e.action == "assign"]

    @property
    def already_threaded(self) -> list[PlanEntry]:
        return [e for e in self.entries if e.action == "skip-has-id"]

    @property
    def skipped_no_area(self) -> list[PlanEntry]:
        return [e for e in self.entries if e.action == "skip-no-area"]

    @property
    def skipped_malformed(self) -> list[PlanEntry]:
        return [e for e in self.entries if e.action == "skip-malformed"]


# ── Parsing ──────────────────────────────────────────────────────────────────
def parse_tasks(mtl: str) -> list[TaskLine]:
    """Walk every line; return TaskLine for those matching the canonical regex."""
    out: list[TaskLine] = []
    for idx, line in enumerate(mtl.splitlines(), start=1):
        m = TASK_LINE_RE.match(line)
        if not m:
            continue
        checked = m.group(1) == "x"
        rest = m.group(2)
        # Description = text up to first [
        cut = rest.find("[")
        desc = rest[:cut].strip() if cut >= 0 else rest.strip()
        fields = {k: v.strip() for k, v in INLINE_FIELD_RE.findall(rest)}
        out.append(TaskLine(
            line_no=idx, raw=line, checked=checked, description=desc, fields=fields,
        ))
    return out


# ── Plan phase ───────────────────────────────────────────────────────────────
def plan_migration(mtl: str, *, now: datetime | None = None) -> MigrationPlan:
    """Pure function: take an MTL string, return a MigrationPlan with proposed IDs.

    Idempotent: re-run on the same MTL yields the same IDs (task_id.generate_task_id
    is deterministic given (area, description, timestamp)). The timestamp anchors
    on `now` (default: utcnow) — for reproducible runs, pass a fixed `now`.
    """
    now = now or datetime.now(timezone.utc)
    plan = MigrationPlan()
    plan.total_lines = len(mtl.splitlines())
    tasks = parse_tasks(mtl)
    plan.parsed_tasks = len(tasks)

    for t in tasks:
        if t.existing_id:
            plan.entries.append(PlanEntry(
                line_no=t.line_no, raw=t.raw, description=t.description,
                area=t.area, existing_id=t.existing_id, proposed_id=None,
                backing_file_path=None, action="skip-has-id",
            ))
            continue
        if not t.area:
            plan.entries.append(PlanEntry(
                line_no=t.line_no, raw=t.raw, description=t.description,
                area=None, existing_id=None, proposed_id=None,
                backing_file_path=None, action="skip-no-area",
            ))
            continue
        if not t.description:
            plan.entries.append(PlanEntry(
                line_no=t.line_no, raw=t.raw, description="", area=t.area,
                existing_id=None, proposed_id=None,
                backing_file_path=None, action="skip-malformed",
            ))
            continue
        proposed = tid.generate_task_id(t.area, t.description, now)
        backing = tid.derive_backing_file_path(proposed, t.area)
        plan.entries.append(PlanEntry(
            line_no=t.line_no, raw=t.raw, description=t.description,
            area=t.area, existing_id=None, proposed_id=proposed,
            backing_file_path=backing, action="assign",
        ))
    return plan


def render_plan_report(plan: MigrationPlan, *, run_ts: str) -> str:
    """Markdown report for 99_System/reports/threaded-tasks-migration-plan-<date>.md."""
    lines = [
        "# Threaded-Tasks Migration Plan (ADR-0009)",
        "",
        f"**Run timestamp (UTC):** {run_ts}",
        f"**MTL lines scanned:** {plan.total_lines}",
        f"**Tasks parsed:** {plan.parsed_tasks}",
        "",
        "## Summary",
        "",
        f"- Will assign new `[id::]`: **{len(plan.to_assign)}**",
        f"- Already threaded (skip): {len(plan.already_threaded)}",
        f"- Skipped — missing `[area::]`: {len(plan.skipped_no_area)}",
        f"- Skipped — malformed (no description): {len(plan.skipped_malformed)}",
        "",
        "## Will assign",
        "",
        "| Line | Area | Description (preview) | Proposed ID | Backing file |",
        "|------|------|-----------------------|-------------|--------------|",
    ]
    for e in plan.to_assign[:200]:  # cap report rendering
        desc = e.description.replace("|", "\\|")[:60]
        lines.append(f"| {e.line_no} | {e.area} | {desc} | `{e.proposed_id}` | `{e.backing_file_path}` |")
    if len(plan.to_assign) > 200:
        lines.append(f"| … | … | (truncated; {len(plan.to_assign) - 200} more) | … | … |")
    lines += [
        "",
        "## Skipped — missing `[area::]`",
        "",
    ]
    for e in plan.skipped_no_area:
        lines.append(f"- L{e.line_no}: \"{e.description[:80]}\"")
    return "\n".join(lines) + "\n"


# ── Apply / Verify (STUBBED for Phase C day-2/3) ─────────────────────────────
def apply_migration(plan: MigrationPlan, *, dry_run: bool = True) -> None:
    """Phase C day-2: write updated MTL + create backing files. NOT YET IMPLEMENTED."""
    raise NotImplementedError(
        "apply_migration() is Phase C day-2 work. Skeleton on "
        "feature/phase-c-f-skeletons branch — wire after merge."
    )


def verify_migration(plan: MigrationPlan) -> bool:
    """Phase C day-3: round-trip each backing file vs MTL. NOT YET IMPLEMENTED."""
    raise NotImplementedError(
        "verify_migration() is Phase C day-3 work."
    )


# ── CLI ──────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C threaded-tasks migration (skeleton)")
    parser.add_argument("--input", type=Path, required=True,
                        help="Path to a local MTL copy (skeleton: file input only; "
                             "post-soak --from-minio reads canonical key)")
    parser.add_argument("--out-report", type=Path, default=None,
                        help="Local path to write the plan report (default: print to stdout)")
    args = parser.parse_args()

    mtl = args.input.read_text(encoding="utf-8")
    plan = plan_migration(mtl)
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = render_plan_report(plan, run_ts=run_ts)
    if args.out_report:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(report, encoding="utf-8")
        print(f"Plan written to {args.out_report}")
    else:
        print(report)
    print(
        f"\nSummary: {len(plan.to_assign)} assign / "
        f"{len(plan.already_threaded)} skip-has-id / "
        f"{len(plan.skipped_no_area)} skip-no-area / "
        f"{len(plan.skipped_malformed)} skip-malformed",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

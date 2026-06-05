#!/usr/bin/env python3
"""
scripts/audit_secrets_rotation.py — surface overdue + upcoming secret rotations.

Parses the markdown table in docs/security/secrets-rotation.md and reports:
  - OVERDUE   rotations whose `next_due` is in the past
  - WARN      rotations whose `next_due` is within --days (default 14)
  - ok        everything else (silenced unless --verbose)

Run:
    python3 scripts/audit_secrets_rotation.py
    python3 scripts/audit_secrets_rotation.py --days 30 --strict

Exit codes:
    0   no overdue rotations (warnings allowed)
    1   one or more overdue rotations (or --strict + any warning)
    2   could not parse / IO error
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROTATION_DOC = REPO_ROOT / "docs" / "security" / "secrets-rotation.md"

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass
class Row:
    name: str
    secret_type: str
    last_rotated: str
    next_due: str

    @property
    def next_due_date(self) -> date | None:
        m = ISO_DATE_RE.match(self.next_due.strip())
        if not m:
            return None
        try:
            return datetime.strptime(m.group(0), "%Y-%m-%d").date()
        except ValueError:
            return None


def _split_row(line: str) -> list[str]:
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    return parts


def parse_table(md_text: str) -> list[Row]:
    """Find the rotation cadence table and return one Row per data line."""
    rows: list[Row] = []
    in_table = False
    header_cells: list[str] | None = None
    for raw_line in md_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("| Edge / secret"):
            in_table = True
            header_cells = _split_row(line)
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            in_table = False
            break
        if set(line.replace("|", "").replace(":", "").replace("-", "").strip()) == set():
            # The separator row underneath the header
            continue
        cells = _split_row(line)
        if not header_cells or len(cells) < 5:
            continue
        # Expected columns: Edge / secret | Type | Where it lives | Cadence | Last rotated | Next due | Runbook
        rows.append(Row(
            name=cells[0],
            secret_type=cells[1],
            last_rotated=cells[4] if len(cells) > 4 else "",
            next_due=cells[5] if len(cells) > 5 else "",
        ))
    return rows


def classify(rows: list[Row], today: date, warn_days: int) -> dict[str, list[Row]]:
    overdue: list[Row] = []
    warn: list[Row] = []
    ok: list[Row] = []
    unparseable: list[Row] = []
    cutoff = today + timedelta(days=warn_days)
    for r in rows:
        d = r.next_due_date
        if d is None:
            unparseable.append(r)
            continue
        if d < today:
            overdue.append(r)
        elif d <= cutoff:
            warn.append(r)
        else:
            ok.append(r)
    return {"overdue": overdue, "warn": warn, "ok": ok, "unparseable": unparseable}


def render(buckets: dict[str, list[Row]], today: date, warn_days: int, *, verbose: bool) -> str:
    lines = [
        f"Secrets-rotation audit — today {today.isoformat()}, warn-window {warn_days}d",
        f"  rows total:       {sum(len(v) for v in buckets.values())}",
        f"  overdue:          {len(buckets['overdue'])}",
        f"  due-within-{warn_days}d:    {len(buckets['warn'])}",
        f"  ok / future:      {len(buckets['ok'])}",
        f"  unparseable / TBD: {len(buckets['unparseable'])}",
        "",
    ]
    if buckets["overdue"]:
        lines.append("OVERDUE:")
        for r in buckets["overdue"]:
            days = (today - r.next_due_date).days  # type: ignore[operator]
            lines.append(f"  [{days:+4d}d] {r.name} — next_due {r.next_due}")
    if buckets["warn"]:
        lines.append("DUE SOON:")
        for r in buckets["warn"]:
            days = (r.next_due_date - today).days  # type: ignore[operator]
            lines.append(f"  [{days:+4d}d] {r.name} — next_due {r.next_due}")
    if verbose:
        if buckets["ok"]:
            lines.append("OK:")
            for r in buckets["ok"]:
                lines.append(f"        {r.name} — next_due {r.next_due}")
        if buckets["unparseable"]:
            lines.append("UNPARSEABLE / TBD:")
            for r in buckets["unparseable"]:
                lines.append(f"        {r.name} — next_due {r.next_due!r}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit secret rotation cadence")
    parser.add_argument("--days", type=int, default=14, help="Warn threshold in days")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if any warning OR overdue (default: only overdue)")
    parser.add_argument("--verbose", action="store_true", help="List ok + unparseable rows too")
    parser.add_argument("--today", type=str, default=None,
                        help="Override today's date (YYYY-MM-DD) — for tests")
    args = parser.parse_args()

    if args.today:
        today = datetime.strptime(args.today, "%Y-%m-%d").date()
    else:
        today = date.today()

    try:
        md = ROTATION_DOC.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"FAIL: {ROTATION_DOC} not found", file=sys.stderr)
        return 2

    rows = parse_table(md)
    if not rows:
        print(f"FAIL: no rotation rows parsed from {ROTATION_DOC}", file=sys.stderr)
        return 2

    buckets = classify(rows, today, args.days)
    print(render(buckets, today, args.days, verbose=args.verbose))

    if buckets["overdue"]:
        return 1
    if args.strict and buckets["warn"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

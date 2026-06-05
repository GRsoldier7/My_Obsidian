#!/usr/bin/env python3
"""
scripts/audit_slo_conformance.py — Wave-X H3 skeleton.

Parses ``docs/SLO-life-os.md`` workflow tables and (when run with MinIO creds
in env) reads ``99_System/logs/<workflow>-<date>.json`` files from MinIO to
compute per-workflow 7-day-rolling conformance. Writes the verdict map to
``99_System/state/slo-status.json`` so the Daily Command Center can render a
"🩺 SLO health" panel.

PHASE STATUS: SKELETON.
  - The SLO doc parser is implemented + tested.
  - The conformance computation against MinIO is stubbed (only schema +
    dispatch; the actual log-reading lands Wave-X H3 day-2).
  - The state-file writer is implemented (writes a stub map today).

Soak-safe: this skeleton does NOT read MinIO at runtime; no live signal is
touched. ``make audit-slo`` runs the parser only; ``--apply`` is the post-soak
flag that turns on the MinIO reads.

Exit codes:
  0 — parse + compute clean
  1 — SLO doc malformed OR conformance breaches detected
  2 — I/O failure
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SLO_DOC = REPO_ROOT / "docs" / "SLO-life-os.md"


@dataclass
class SLOEntry:
    workflow: str
    target_success_rate: float | None = None      # e.g. 99.0
    page_threshold_success: float | None = None   # e.g. 95.0
    target_latency_p95_s: float | None = None
    page_threshold_latency_p95_s: float | None = None
    notes: str = ""


@dataclass
class SLOReport:
    entries: list[SLOEntry] = field(default_factory=list)
    parsed_ok: bool = True
    parse_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": [asdict(e) for e in self.entries],
            "parsed_ok": self.parsed_ok,
            "parse_errors": self.parse_errors,
        }


# ── Parser ────────────────────────────────────────────────────────────────────
_HEADING_WORKFLOW_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_LATENCY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|s)")


def parse_slo_doc(text: str) -> SLOReport:
    """Walk the SLO markdown and extract workflow target tuples.

    Format expectation (per docs/SLO-life-os.md): each workflow lives under a
    `### Workflow Name` heading and has a `| Dimension | Target | Pages on |`
    table beneath. We scrape the success-rate row + the latency-p95 row.
    """
    report = SLOReport()
    # Split by H3 headings
    sections = re.split(r"(?m)^###\s+", text)
    if len(sections) <= 1:
        report.parsed_ok = False
        report.parse_errors.append("no ### workflow headings found")
        return report

    for section in sections[1:]:  # skip the pre-first-H3 preamble
        # First line is the heading content
        lines = section.split("\n", 1)
        name = lines[0].strip()
        body = lines[1] if len(lines) > 1 else ""
        if not name or name.startswith("Workflow SLOs"):
            continue
        # Find the table row containing "success rate" (case-insensitive)
        entry = SLOEntry(workflow=name)
        for row in body.split("\n"):
            row_lc = row.lower()
            if "success rate" in row_lc and "|" in row:
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                if len(cells) >= 3:
                    target_pct = _first_pct(cells[1])
                    page_pct = _first_pct(cells[2])
                    if target_pct is not None:
                        entry.target_success_rate = target_pct
                    if page_pct is not None:
                        entry.page_threshold_success = page_pct
            elif ("latency p95" in row_lc or "latency_p95" in row_lc) and "|" in row:
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                if len(cells) >= 3:
                    target_lat = _first_latency_s(cells[1])
                    page_lat = _first_latency_s(cells[2])
                    if target_lat is not None:
                        entry.target_latency_p95_s = target_lat
                    if page_lat is not None:
                        entry.page_threshold_latency_p95_s = page_lat
        # Only keep entries that actually parsed a target
        if entry.target_success_rate is not None or entry.target_latency_p95_s is not None:
            report.entries.append(entry)
    return report


def _first_pct(text: str) -> float | None:
    m = _PCT_RE.search(text)
    return float(m.group(1)) if m else None


def _first_latency_s(text: str) -> float | None:
    m = _LATENCY_RE.search(text)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).lower()
    return val / 1000.0 if unit == "ms" else val


# ── Conformance (STUB) ───────────────────────────────────────────────────────
def compute_conformance_stub(entries: list[SLOEntry]) -> dict[str, str]:
    """SKELETON: returns 'unknown' for every entry. Wave-X H3 day-2 implements
    the MinIO-log walk + per-workflow 7-day conformance calculation."""
    return {e.workflow: "unknown" for e in entries}


def write_state_file(state_path: Path, conformance: dict[str, str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"conformance": conformance, "skeleton": True}, indent=2),
        encoding="utf-8",
    )


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Wave-X H3 SLO conformance skeleton")
    parser.add_argument("--apply", action="store_true",
                        help="(post-soak) read MinIO logs + compute live conformance. SKELETON: today this flag is a NO-OP that prints a notice.")
    parser.add_argument("--state-out", type=Path, default=None,
                        help="Optional local path to write the state JSON (default: stdout only)")
    args = parser.parse_args()

    if not SLO_DOC.is_file():
        print(f"FAIL: {SLO_DOC} not found", file=sys.stderr)
        return 2

    report = parse_slo_doc(SLO_DOC.read_text(encoding="utf-8"))
    if not report.parsed_ok:
        print("FAIL: SLO doc parse errors:", file=sys.stderr)
        for err in report.parse_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    if args.apply:
        print("NOTE: --apply is a SKELETON no-op until Wave-X H3 day-2 ships the MinIO log walker.", file=sys.stderr)

    conformance = compute_conformance_stub(report.entries)
    print(f"OK — SLO doc parsed. {len(report.entries)} workflow targets extracted.")
    for e in report.entries:
        verdict = conformance.get(e.workflow, "unknown")
        print(f"  - {e.workflow}: success≥{e.target_success_rate}% latency≤{e.target_latency_p95_s}s  →  {verdict}")

    if args.state_out:
        write_state_file(args.state_out, conformance)
        print(f"  wrote state to {args.state_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

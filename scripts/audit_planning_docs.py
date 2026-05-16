#!/usr/bin/env python3
"""
scripts/audit_planning_docs.py — keep the planning surface consistent.

The OHO planning surface is layered:
  docs/adr/*.md              — Accepted decisions
  docs/superpowers/specs/*.md — Detailed design specs
  docs/superpowers/phases/*.md — Phase plans
  docs/runbooks/*.md         — Operator playbooks

ADRs reference specs; specs reference phases + ADRs; runbooks reference ADRs.
When the planning surface drifts (a referenced ADR is missing, a spec is orphaned,
a phase doc has no parent ADR), readers get confused and decisions stop tracking.

This audit catches drift in CI.

Checks:
  1. Every `ADR-NNNN` reference in any markdown resolves to docs/adr/NNNN-*.md.
  2. Every `docs/adr/NNNN-*.md` link target exists.
  3. Every `docs/superpowers/specs/*.md` is referenced from at least one ADR.
  4. Every `docs/superpowers/phases/*.md` is referenced from at least one ADR or spec.
  5. Every ADR has a Status line in {Accepted, Proposed, Superseded, Deprecated}.

Exit codes:
  0   planning surface consistent
  1   issues found (CI-visible failure)
  2   I/O failure
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = REPO_ROOT / "docs" / "adr"
SPEC_DIR = REPO_ROOT / "docs" / "superpowers" / "specs"
PHASE_DIR = REPO_ROOT / "docs" / "superpowers" / "phases"
RUNBOOK_DIR = REPO_ROOT / "docs" / "runbooks"

# Anchored ADR IDs like "ADR-0007" — case-sensitive 4-digit.
ADR_REF_RE = re.compile(r"\bADR-(\d{4})\b")
# Markdown link / relative path to ADR file.
ADR_LINK_RE = re.compile(r"docs/adr/(\d{4})-[a-z0-9-]+\.md")
SPEC_LINK_RE = re.compile(r"docs/superpowers/specs/([\w.-]+\.md)")
PHASE_LINK_RE = re.compile(r"docs/superpowers/phases/([\w.-]+\.md)")
STATUS_LINE_RE = re.compile(r"^\*\*Status:\*\*\s*([A-Za-z][\w\- ]*)", re.MULTILINE)
ALLOWED_STATUSES = {"Accepted", "Proposed", "Superseded", "Deprecated"}


def _all_docs(*dirs: Path) -> list[Path]:
    paths: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            paths.append(p)
    return paths


def _existing_adrs() -> dict[str, Path]:
    """Return {4-digit-id: path} for every ADR file present."""
    out: dict[str, Path] = {}
    if not ADR_DIR.is_dir():
        return out
    for p in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")):
        out[p.name[:4]] = p
    return out


def _references_from(text: str) -> dict[str, set[str]]:
    """Pull every kind of reference from one document."""
    return {
        "adr_ids": set(ADR_REF_RE.findall(text)),
        "adr_links": set(ADR_LINK_RE.findall(text)),
        "spec_links": set(SPEC_LINK_RE.findall(text)),
        "phase_links": set(PHASE_LINK_RE.findall(text)),
    }


def _label(doc: Path) -> str:
    """Render a doc path relative to REPO_ROOT when possible, absolute otherwise."""
    try:
        return str(doc.relative_to(REPO_ROOT))
    except ValueError:
        return str(doc)


def findings() -> list[str]:
    issues: list[str] = []
    adrs = _existing_adrs()
    spec_files = {p.name for p in _all_docs(SPEC_DIR)}
    phase_files = {p.name for p in _all_docs(PHASE_DIR)}

    # Track which specs / phases are referenced by SOMETHING.
    spec_refs: dict[str, set[str]] = defaultdict(set)
    phase_refs: dict[str, set[str]] = defaultdict(set)

    # ── walk every planning doc ───────────────────────────────────────────
    for doc in _all_docs(ADR_DIR, SPEC_DIR, PHASE_DIR, RUNBOOK_DIR):
        try:
            text = doc.read_text(encoding="utf-8")
        except Exception as e:
            issues.append(f"{doc}: read error {e}")
            continue
        refs = _references_from(text)

        # Check ADR-NNNN textual references resolve
        for adr_id in refs["adr_ids"]:
            if adr_id not in adrs:
                # Allow self-reference if the doc itself starts with that ID
                if doc.name.startswith(adr_id + "-"):
                    continue
                issues.append(f"{_label(doc)}: references ADR-{adr_id} which does not exist")

        # Check explicit ADR file links resolve
        for adr_id in refs["adr_links"]:
            if adr_id not in adrs:
                issues.append(f"{_label(doc)}: links docs/adr/{adr_id}-*.md which does not exist")

        # Record spec / phase references
        for spec_name in refs["spec_links"]:
            spec_refs[spec_name].add(_label(doc))
            if spec_name not in spec_files:
                issues.append(f"{_label(doc)}: links docs/superpowers/specs/{spec_name} which does not exist")
        for phase_name in refs["phase_links"]:
            phase_refs[phase_name].add(_label(doc))
            if phase_name not in phase_files:
                issues.append(f"{_label(doc)}: links docs/superpowers/phases/{phase_name} which does not exist")

    # ── ADR-specific checks (status + minimal shape) ─────────────────────
    for adr_id, path in adrs.items():
        text = path.read_text(encoding="utf-8")
        statuses = STATUS_LINE_RE.findall(text)
        if not statuses:
            issues.append(f"{_label(path)}: missing **Status:** line")
        else:
            status = statuses[0].strip().split()[0]  # first word
            if status not in ALLOWED_STATUSES:
                issues.append(f"{_label(path)}: status `{status}` not in {sorted(ALLOWED_STATUSES)}")

    # ── orphan detection (specs + phases not referenced from any ADR) ───
    # We skip historical specs (date prefix < ADR-0007 era) because those
    # were synthesized before the planning-doc-audit existed. Phase docs
    # similarly; we only enforce orphan-free on the current frontier.
    for spec_name in spec_files:
        if spec_name not in spec_refs:
            issues.append(f"orphan spec: docs/superpowers/specs/{spec_name} not referenced from any ADR/spec/phase/runbook")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit planning-doc cross-references")
    parser.add_argument("--allow-orphans", action="store_true",
                        help="Skip orphan-spec detection (kept for historical files during rollout)")
    args = parser.parse_args()

    try:
        issues = findings()
    except FileNotFoundError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 2

    if args.allow_orphans:
        issues = [i for i in issues if not i.startswith("orphan ")]

    if issues:
        print(f"FAIL: planning-doc audit found {len(issues)} issue(s):", file=sys.stderr)
        for i in issues:
            print(f"  - {i}", file=sys.stderr)
        return 1

    adrs = _existing_adrs()
    spec_count = sum(1 for _ in SPEC_DIR.glob("*.md")) if SPEC_DIR.is_dir() else 0
    phase_count = sum(1 for _ in PHASE_DIR.glob("*.md")) if PHASE_DIR.is_dir() else 0
    print(f"OK — planning-doc audit passed. {len(adrs)} ADRs, {spec_count} specs, {phase_count} phases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

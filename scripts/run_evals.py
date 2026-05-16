#!/usr/bin/env python3
"""
scripts/run_evals.py — eval harness for the privacy classifier (ADR-0008 §15).

In schema-only mode (the current default — the classifier is not yet
implemented), this script:
  - enumerates every fixture under evals/<suite>/F-*.json
  - parses + schema-validates each (same checks as tests/test_eval_fixtures_schema.py)
  - reports coverage stats per class
  - flags fixtures that fail the schema

Once tools/privacy_classifier.py exists, --run-classifier swaps in the
real-classification pass: every fixture is run through classify(); precision /
recall is computed per class; failures land in evals/<suite>/.last-run-failures.json.

This harness is intentionally framework-free (no pytest dependency at runtime)
so it can be invoked from a future cron job or n8n Code node without test infra.

Run:
    python3 scripts/run_evals.py
    python3 scripts/run_evals.py --suite comms_privacy
    python3 scripts/run_evals.py --suite comms_privacy --json
    python3 scripts/run_evals.py --suite comms_privacy --run-classifier  # NOT YET
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_ROOT = REPO_ROOT / "evals"

REQUIRED_KEYS = {"id", "class", "category", "payload", "hints", "expected_reasons", "expected_egress"}
ALLOWED_CLASSES = {"public", "private", "sensitive"}
REQUIRED_PEERS = {"to_lxc", "to_desktop", "to_vps", "to_broker", "to_openrouter"}


@dataclass
class FixtureFailure:
    path: str
    issues: list[str] = field(default_factory=list)


@dataclass
class SuiteReport:
    suite: str
    total: int = 0
    by_class: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)
    failures: list[FixtureFailure] = field(default_factory=list)

    def add_class(self, c: str) -> None:
        self.by_class[c] = self.by_class.get(c, 0) + 1

    def add_category(self, c: str) -> None:
        self.by_category[c] = self.by_category.get(c, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "total": self.total,
            "by_class": self.by_class,
            "by_category": self.by_category,
            "failures": [{"path": f.path, "issues": f.issues} for f in self.failures],
            "ok": not self.failures,
        }


def validate_fixture(doc: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    missing = REQUIRED_KEYS - set(doc.keys())
    if missing:
        issues.append(f"missing keys: {sorted(missing)}")
        return issues
    if doc["class"] not in ALLOWED_CLASSES:
        issues.append(f"class={doc['class']!r} not in {sorted(ALLOWED_CLASSES)}")
    eg = doc.get("expected_egress", {})
    missing_peers = REQUIRED_PEERS - set(eg.keys())
    if missing_peers:
        issues.append(f"expected_egress missing peers: {sorted(missing_peers)}")
    if not isinstance(doc.get("payload"), dict):
        issues.append("`payload` must be a mapping")
    if not isinstance(doc.get("expected_reasons"), list):
        issues.append("`expected_reasons` must be a list")
    return issues


def run_suite(suite: str) -> SuiteReport:
    report = SuiteReport(suite=suite)
    suite_dir = EVALS_ROOT / suite
    if not suite_dir.is_dir():
        report.failures.append(FixtureFailure(path=str(suite_dir), issues=["suite directory missing"]))
        return report

    for path in sorted(suite_dir.glob("F-*.json")):
        if not path.is_file():
            continue
        report.total += 1
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            report.failures.append(FixtureFailure(path=str(path), issues=[f"invalid JSON: {e}"]))
            continue
        issues = validate_fixture(doc)
        if issues:
            report.failures.append(FixtureFailure(path=str(path), issues=issues))
            continue
        report.add_class(doc["class"])
        report.add_category(str(doc.get("category", "unknown")))

    return report


def render_human(report: SuiteReport, *, target_count: int) -> str:
    lines = [
        f"Eval suite: {report.suite}",
        f"  fixtures parsed: {report.total} / target {target_count}",
        f"  by class:        " + ", ".join(f"{k}={v}" for k, v in sorted(report.by_class.items())),
        f"  by category:     " + ", ".join(f"{k}={v}" for k, v in sorted(report.by_category.items())),
        f"  failures:        {len(report.failures)}",
    ]
    if report.failures:
        lines.append("")
        lines.append("FAILURES:")
        for f in report.failures:
            lines.append(f"  {f.path}")
            for issue in f.issues:
                lines.append(f"    - {issue}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Privacy-classifier eval harness")
    parser.add_argument("--suite", default="comms_privacy", help="Which evals/<suite>/ directory to run")
    parser.add_argument("--target-count", type=int, default=200, help="Expected total fixtures (ADR-0008 §15)")
    parser.add_argument("--json", action="store_true", help="Emit JSON report instead of human-readable")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if fixture count below target (default: only on schema failure)")
    parser.add_argument("--run-classifier", action="store_true",
                        help="(Phase F) run each fixture through tools.privacy_classifier — NOT YET IMPLEMENTED")
    args = parser.parse_args()

    if args.run_classifier:
        print("ERROR: --run-classifier requires tools/privacy_classifier.py which has not shipped yet "
              "(Phase F, post-soak). See ADR-0008.", file=sys.stderr)
        return 2

    report = run_suite(args.suite)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(render_human(report, target_count=args.target_count))

    if report.failures:
        return 1
    if args.strict and report.total < args.target_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
scripts/backfill_mtl_metadata.py — HYG-B4 from ADR-0007 master plan v2.

Reads MTL from MinIO, classifies every task line, and produces a structured
review report for Aaron to triage. NEVER hallucinates dates: `[due::]` is
flagged in the report only; `[completion::]` gets a `<!-- needs-completion-date -->`
TODO marker on `--apply`. Version-history candidate dates are surfaced in the
report as SUGGESTIONS only, never written back as authoritative.

Spec: docs/superpowers/phases/2026-05-12-hygiene-carry-forwards.md §Item 3.

Usage:
    set -a && source .env && set +a
    python3 scripts/backfill_mtl_metadata.py                  # dry-run (default)
    python3 scripts/backfill_mtl_metadata.py --review-only    # report only
    python3 scripts/backfill_mtl_metadata.py --apply          # write TODO markers
    python3 scripts/backfill_mtl_metadata.py --verbose

Hallucination guard:
    The script will NEVER invent a date. `--apply` only writes structural
    markers (`<!-- needs-completion-date -->`). Auto-fill from S3 version
    history is recorded as a SUGGESTION in the review report; Aaron decides.

Concurrency guard:
    Aborts if the canonical MTL was modified within 60 seconds (an active
    brain-dump-processor run may be writing). Override with --force.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools.s3_verified import (  # noqa: E402
    PreconditionFailedError,
    VerificationError,
    put_json_verified,
    put_text_if_match_verified,
    put_text_verified,
)

# ── Config ────────────────────────────────────────────────────────────────────
MTL_KEY = "10_Active Projects/Active Personal/!!! MASTER TASK LIST.md"
REPORT_KEY_TPL = "99_System/reports/mtl-backfill-review-{date}.md"
LOG_KEY_TPL = "99_System/logs/mtl-backfill-{date}.json"
BACKUP_KEY_TPL = "99_System/backup/MTL-pre-backfill-{date}.md"

TODO_MARKER = "<!-- needs-completion-date -->"
CONCURRENCY_WINDOW_SECONDS = 60

# Canonical task line — `- [ ]` or `- [x]` followed by description + inline fields.
TASK_LINE_RE = re.compile(r"^- \[([ x])\] (.*?)(?:\s*$)", re.MULTILINE)
INLINE_FIELD_RE = re.compile(r"\[(\w+)::\s*([^\]]*?)\]")
DUE_FIELD_RE = re.compile(r"\[due::\s*[^\]]+\]")
COMPLETION_FIELD_RE = re.compile(r"\[completion::\s*[^\]]+\]")


# ── Models ────────────────────────────────────────────────────────────────────
@dataclass
class Task:
    line_no: int            # 1-indexed line number in the MTL
    raw: str                # the raw line, no trailing newline
    checked: bool           # True if `- [x]`
    description: str        # text up to the first `[`, stripped
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def has_due(self) -> bool:
        return "due" in self.fields and bool(self.fields["due"].strip())

    @property
    def has_completion(self) -> bool:
        return "completion" in self.fields and bool(self.fields["completion"].strip())

    @property
    def has_todo_marker(self) -> bool:
        return TODO_MARKER in self.raw


@dataclass
class Classification:
    open_no_due: list[Task] = field(default_factory=list)
    open_has_due: list[Task] = field(default_factory=list)
    closed_no_completion: list[Task] = field(default_factory=list)
    closed_has_completion: list[Task] = field(default_factory=list)
    malformed: list[Task] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(len(getattr(self, k)) for k in (
            "open_no_due", "open_has_due",
            "closed_no_completion", "closed_has_completion", "malformed",
        ))


# ── S3 helpers (mirrored from archive_completed_tasks.py) ────────────────────
def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    )


def bucket() -> str:
    return os.environ.get("MINIO_BUCKET", "obsidian-vault")


def get_object(s3, key: str) -> tuple[str, dict]:
    """Return (body_text, metadata) where metadata includes ETag + LastModified."""
    obj = s3.get_object(Bucket=bucket(), Key=key)
    body = obj["Body"].read().decode("utf-8")
    meta = {"ETag": obj["ETag"], "LastModified": obj["LastModified"]}
    return body, meta


def put_object_verified(s3, key: str, body: str, if_match: Optional[str] = None) -> int:
    if if_match:
        result = put_text_if_match_verified(
            s3, bucket(), key, body, if_match,
            content_type="text/markdown; charset=utf-8",
        )
    else:
        result = put_text_verified(
            s3, bucket(), key, body,
            content_type="text/markdown; charset=utf-8",
        )
    return result.size_bytes


# ── Parsing ──────────────────────────────────────────────────────────────────
def parse_tasks(mtl: str) -> list[Task]:
    """Parse every task line. Lines that match TASK_LINE_RE but fail field parsing
    end up as `malformed`."""
    tasks: list[Task] = []
    for line_idx, line in enumerate(mtl.splitlines(), start=1):
        match = TASK_LINE_RE.match(line)
        if not match:
            continue
        checked = match.group(1) == "x"
        rest = match.group(2)

        # Description = text up to the first `[`, trimmed
        first_field = rest.find("[")
        description = rest[:first_field].strip() if first_field >= 0 else rest.strip()
        fields = {k: v.strip() for k, v in INLINE_FIELD_RE.findall(rest)}

        tasks.append(Task(
            line_no=line_idx,
            raw=line,
            checked=checked,
            description=description,
            fields=fields,
        ))
    return tasks


def classify(tasks: list[Task]) -> Classification:
    out = Classification()
    for t in tasks:
        # Malformed = no `area` AND no `priority` AND no description — pathological.
        if not t.description and not t.fields:
            out.malformed.append(t)
            continue
        if t.checked:
            if t.has_completion:
                out.closed_has_completion.append(t)
            else:
                out.closed_no_completion.append(t)
        else:
            if t.has_due:
                out.open_has_due.append(t)
            else:
                out.open_no_due.append(t)
    return out


# ── Apply (TODO markers only — never invents dates) ──────────────────────────
def apply_todo_markers(mtl: str, classification: Classification) -> tuple[str, int]:
    """Append the TODO marker to every `closed_no_completion` line that doesn't
    already carry one. Returns (new_mtl, lines_modified)."""
    if not classification.closed_no_completion:
        return mtl, 0

    targets = {t.line_no: t for t in classification.closed_no_completion if not t.has_todo_marker}
    if not targets:
        return mtl, 0

    out_lines: list[str] = []
    for idx, line in enumerate(mtl.splitlines(keepends=False), start=1):
        if idx in targets:
            out_lines.append(f"{line.rstrip()} {TODO_MARKER}")
        else:
            out_lines.append(line)
    # Preserve trailing newline behavior of the original
    new_mtl = "\n".join(out_lines)
    if mtl.endswith("\n"):
        new_mtl += "\n"
    return new_mtl, len(targets)


# ── Version-history candidate (SUGGESTION ONLY — never auto-applied) ─────────
def suggest_completion_dates(s3, classification: Classification) -> dict[int, str]:
    """For each closed_no_completion task, find the earliest version where the
    line was `- [x]`. The LastModified of that version is the SUGGESTED
    completion date. Returns {line_no: ISO-date-or-empty}.

    Returns empty dict if S3 versioning is OFF for the bucket — no PaginatorError,
    no false positives, just silence.
    """
    suggestions: dict[int, str] = {}
    if not classification.closed_no_completion:
        return suggestions

    try:
        paginator = s3.get_paginator("list_object_versions")
        versions: list[dict] = []
        for page in paginator.paginate(Bucket=bucket(), Prefix=MTL_KEY):
            versions.extend(page.get("Versions", []))
    except ClientError:
        return suggestions

    # Filter to the exact MTL key, sort oldest→newest
    versions = [v for v in versions if v.get("Key") == MTL_KEY]
    if not versions:
        return suggestions
    versions.sort(key=lambda v: v["LastModified"])

    targets = {t.line_no: t.description for t in classification.closed_no_completion}

    # For each historical version, see when each target description first appears as `- [x]`
    for v in versions:
        version_id = v.get("VersionId")
        if not version_id or v.get("IsLatest"):
            continue
        try:
            obj = s3.get_object(Bucket=bucket(), Key=MTL_KEY, VersionId=version_id)
            body = obj["Body"].read().decode("utf-8", errors="replace")
        except ClientError:
            continue
        for line_no, desc in list(targets.items()):
            if line_no in suggestions or not desc:
                continue
            # Match by description (line numbers shift between versions)
            for raw_line in body.splitlines():
                if raw_line.startswith("- [x] ") and desc in raw_line:
                    suggestions[line_no] = v["LastModified"].strftime("%Y-%m-%d")
                    break
    return suggestions


# ── Report rendering ─────────────────────────────────────────────────────────
def render_report(
    classification: Classification,
    suggestions: dict[int, str],
    mtl_etag: str,
    run_ts: str,
) -> str:
    c = classification
    lines = [
        "# MTL Backfill Review Report",
        "",
        f"**Run timestamp (UTC):** {run_ts}",
        f"**MTL ETag at read time:** `{mtl_etag}`",
        f"**Source key:** `{MTL_KEY}`",
        "",
        "## Summary",
        "",
        f"- Total tasks parsed: **{c.total}**",
        f"- Open + has `[due::]`: {len(c.open_has_due)}",
        f"- Open + missing `[due::]`: **{len(c.open_no_due)}** (Aaron triage required — script will NOT auto-fill)",
        f"- Closed + has `[completion::]`: {len(c.closed_has_completion)}",
        f"- Closed + missing `[completion::]`: **{len(c.closed_no_completion)}**",
        f"- Malformed (parsed but no description or fields): {len(c.malformed)}",
        "",
        "## Hallucination guard",
        "",
        "This script will **never invent a date.** `--apply` only writes the structural",
        f"marker `{TODO_MARKER}` on closed tasks missing `[completion::]`. Any candidate",
        "completion dates below are SUGGESTIONS from MinIO object-version history — review",
        "before manually editing the MTL.",
        "",
    ]

    if c.closed_no_completion:
        lines += [
            "## Closed tasks missing `[completion::]`",
            "",
            "| Line | Area | Priority | Description | Version-history suggestion |",
            "|------|------|----------|-------------|-----------------------------|",
        ]
        for t in c.closed_no_completion:
            suggestion = suggestions.get(t.line_no, "(none — versioning off or no transition found)")
            area = t.fields.get("area", "—")
            prio = t.fields.get("priority", "—")
            desc = t.description.replace("|", "\\|")[:80]
            lines.append(f"| {t.line_no} | {area} | {prio} | {desc} | {suggestion} |")
        lines.append("")

    if c.open_no_due:
        lines += [
            "## Open tasks missing `[due::]` (manual triage)",
            "",
        ]
        for t in c.open_no_due:
            area = t.fields.get("area", "—")
            prio = t.fields.get("priority", "—")
            desc = t.description[:120]
            lines.append(f"- L{t.line_no} `[area: {area}, priority: {prio}]` — \"{desc}\"")
        lines.append("")

    if c.malformed:
        lines += [
            "## Malformed lines (parsed but ambiguous)",
            "",
        ]
        for t in c.malformed:
            lines.append(f"- L{t.line_no}: `{t.raw[:120]}`")
        lines.append("")

    lines += [
        "---",
        "",
        "## How to act on this report",
        "",
        "1. **For closed tasks**: run `python3 scripts/backfill_mtl_metadata.py --apply`",
        f"   to add `{TODO_MARKER}` to every `closed_no_completion` line. Then edit the",
        "   MTL by hand (or via Obsidian) to replace each marker with the correct",
        "   `[completion:: YYYY-MM-DD]` field, using the version-history suggestion",
        "   above as a starting point when present.",
        "2. **For open tasks**: there is no automation. Aaron should review the list",
        "   above and either set a `[due::]` field or accept that the task is",
        "   intentionally undated.",
        "3. **Re-run** the script any time to refresh the report. It is idempotent.",
        "",
    ]
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────
def run(args: argparse.Namespace) -> int:
    s3 = s3_client()
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Read MTL ───────────────────────────────────────────────────────────
    print(f"Reading MTL from s3://{bucket()}/{MTL_KEY} …")
    try:
        mtl, meta = get_object(s3, MTL_KEY)
    except ClientError as e:
        print(f"ERROR reading MTL: {e}", file=sys.stderr)
        return 2
    print(f"  read {len(mtl):,} bytes, ETag={meta['ETag']}, LastModified={meta['LastModified']}")

    # ── Concurrency guard ──────────────────────────────────────────────────
    last_modified = meta["LastModified"]
    if last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - last_modified
    if age < timedelta(seconds=CONCURRENCY_WINDOW_SECONDS) and not args.force:
        print(
            f"ABORT: MTL was modified {age.total_seconds():.0f}s ago "
            f"(< {CONCURRENCY_WINDOW_SECONDS}s). An active write may be in progress. "
            "Re-run later or pass --force.",
            file=sys.stderr,
        )
        return 3

    # ── Parse + classify ───────────────────────────────────────────────────
    tasks = parse_tasks(mtl)
    classification = classify(tasks)
    if args.verbose:
        print(
            f"Parsed {classification.total} tasks: "
            f"{len(classification.open_no_due)} open_no_due / "
            f"{len(classification.open_has_due)} open_has_due / "
            f"{len(classification.closed_no_completion)} closed_no_completion / "
            f"{len(classification.closed_has_completion)} closed_has_completion / "
            f"{len(classification.malformed)} malformed"
        )

    # ── Strategy (b): S3 version-history suggestions (read-only) ──────────
    suggestions = suggest_completion_dates(s3, classification)
    if args.verbose:
        print(f"Version-history suggestions: {len(suggestions)} candidates")

    # ── Render + write review report (always, every mode) ──────────────────
    report = render_report(classification, suggestions, meta["ETag"], run_ts)
    report_key = REPORT_KEY_TPL.format(date=run_date)
    if args.dry_run or args.review_only or args.apply:
        # The review report is informational and always written, even on dry-run,
        # because Aaron needs it to make the apply decision.
        if not args.skip_report:
            put_object_verified(s3, report_key, report)
            print(f"  ✓ review report → s3://{bucket()}/{report_key} ({len(report):,} bytes)")
        else:
            print(f"  [--skip-report] review report NOT written (preview {len(report):,} bytes)")

    # ── Apply path: TODO markers + verified put + backup ───────────────────
    if not args.apply:
        if args.dry_run or args.review_only:
            print("[DRY RUN / REVIEW ONLY] MTL not modified.")
            _write_log(s3, run_date, classification, suggestions, applied=False)
            return 0
        return 0

    if args.review_only:
        print("ERROR: --apply and --review-only are mutually exclusive.", file=sys.stderr)
        return 1

    new_mtl, modified = apply_todo_markers(mtl, classification)
    if modified == 0:
        print("Apply: nothing to change (all closed tasks already have completion or a marker).")
        _write_log(s3, run_date, classification, suggestions, applied=False)
        return 0

    # Backup canonical first (always for --apply)
    backup_key = BACKUP_KEY_TPL.format(date=run_date)
    print(f"Backing up MTL → s3://{bucket()}/{backup_key}")
    put_object_verified(s3, backup_key, mtl)

    # Conditional put: abort if someone else wrote MTL between our GET and PUT
    print(f"Writing MTL ({modified} TODO marker(s) added) with If-Match guard …")
    try:
        put_object_verified(s3, MTL_KEY, new_mtl, if_match=meta["ETag"])
    except PreconditionFailedError:
        print("ABORT: MTL ETag changed between read and write. Concurrent edit detected.", file=sys.stderr)
        return 4

    print(f"  ✓ MTL updated. Backup preserved at {backup_key}.")
    _write_log(s3, run_date, classification, suggestions, applied=True, modified_lines=modified)
    return 0


def _write_log(s3, run_date: str, c: Classification, suggestions: dict, applied: bool, modified_lines: int = 0) -> None:
    payload = {
        "workflow": "mtl-backfill",
        "date": run_date,
        "status": "applied" if applied else "dry-run",
        "totals": {
            "parsed": c.total,
            "open_no_due": len(c.open_no_due),
            "open_has_due": len(c.open_has_due),
            "closed_no_completion": len(c.closed_no_completion),
            "closed_has_completion": len(c.closed_has_completion),
            "malformed": len(c.malformed),
        },
        "version_history_suggestions": len(suggestions),
        "modified_lines": modified_lines,
    }
    log_key = LOG_KEY_TPL.format(date=run_date)
    try:
        put_json_verified(s3, bucket(), log_key, payload)
    except (ClientError, VerificationError) as e:
        print(f"WARN: could not write run log: {e}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Backfill MTL metadata — review-only by default, never invents dates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Write review report; do not modify MTL (DEFAULT).")
    mode.add_argument("--review-only", action="store_true",
                      help="Same as --dry-run but explicit; alias for cron use.")
    mode.add_argument("--apply", action="store_true",
                      help=f"Write {TODO_MARKER} on closed tasks missing [completion::]. "
                           "Always backs up the MTL first. Never invents dates.")
    p.add_argument("--force", action="store_true",
                   help=f"Override the {CONCURRENCY_WINDOW_SECONDS}s last-modified safety window.")
    p.add_argument("--skip-report", action="store_true",
                   help="Skip writing the review report to S3 (useful for test runs).")
    p.add_argument("--verbose", action="store_true", help="Verbose per-classification output.")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.apply:
        args.dry_run = False
    if args.review_only:
        args.dry_run = True
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

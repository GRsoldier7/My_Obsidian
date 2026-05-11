# Agent Quick Add Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe Claude Code/Codex quick-add command that appends one item to an exact Obsidian brain-dump section through MinIO and optionally promotes it with the existing brain-dump processor.

**Architecture:** A small Python CLI owns agent-facing validation, section/file mapping, markdown insertion, and frontmatter refresh. It uses the existing MinIO helpers and `tools.bd_integrity` primitives, then delegates promotion to `tools/process_brain_dump.py` instead of writing directly to MTL, notes, or articles.

**Tech Stack:** Python 3.12+, boto3, existing `.env` loading through `tools/process_brain_dump.py`, pytest, MinIO S3 bucket `obsidian-vault`.

**Spec:** `docs/superpowers/specs/2026-05-10-agent-quick-add-design.md`

**Commit Policy:** This repo requires explicit approval before git commit, push, merge, PR creation, deployment, or infrastructure changes. Treat commit steps as approval-gated checkpoints.

---

## File Structure

- Create `tools/agent_quick_add.py`
  - CLI entry point and pure helpers for area/section mapping, validation, markdown insertion, frontmatter refresh, verified write, and optional processor handoff.
- Create `tests/test_agent_quick_add.py`
  - Unit coverage using a mock S3 client; no network.
- Modify `docs/RUNBOOK.md`
  - Add operator command examples for coding-session quick-adds.
- Modify `AGENTS.md`
  - Add a short Codex-facing Agent Quick Add protocol.
- Modify `CLAUDE.md`
  - Add the same Claude Code-facing protocol without changing unrelated project state.

## Task 1: Pure Mapping And Formatting Helpers

**Files:**
- Create: `tools/agent_quick_add.py`
- Test: `tests/test_agent_quick_add.py`

- [ ] **Step 1: Write failing tests for mappings and formatting**

Create `tests/test_agent_quick_add.py` with this initial coverage:

```python
from tools import agent_quick_add as q


def test_area_maps_to_brain_dump_key():
    assert q.target_key("business") == "00_Inbox/brain-dumps/BrainDump — Business.md"
    assert q.target_key("health") == "00_Inbox/brain-dumps/BrainDump — Health.md"


def test_file_override_must_be_basename_md():
    assert q.target_key("business", "BrainDump — Echelon.md") == (
        "00_Inbox/brain-dumps/BrainDump — Echelon.md"
    )


def test_file_override_rejects_paths():
    for bad in ["../x.md", "foo/bar.md", "foo\\bar.md", "Homelab/Bad.md"]:
        try:
            q.target_key("business", bad)
        except q.QuickAddError:
            pass
        else:
            raise AssertionError(f"accepted unsafe override: {bad}")


def test_section_aliases_resolve_to_canonical_h2():
    assert q.resolve_section("todos") == "## ✅ To Do's"
    assert q.resolve_section("articles") == "## 📰 Articles & Resources to Follow Up On"


def test_task_entry_formatting_with_priority_and_due():
    entry = q.format_entry("todos", "Follow up with Acme", priority="A", due="2026-05-15")
    assert entry == "- [ ] Follow up with Acme [priority:: A] [due:: 2026-05-15]"


def test_note_entry_formatting_is_plain_bullet():
    assert q.format_entry("ideas", "Agent quick-add command") == "- Agent quick-add command"


def test_article_entry_formatting_keeps_url():
    assert q.format_entry("articles", "https://example.com") == "- https://example.com"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -m pytest tests/test_agent_quick_add.py -q
```

Expected: import failure because `tools/agent_quick_add.py` does not exist.

- [ ] **Step 3: Implement the pure helper skeleton**

Create `tools/agent_quick_add.py`:

```python
#!/usr/bin/env python3
"""Agent quick-add CLI for ObsidianHomeOrchestrator.

Writes only to MinIO-backed brain-dump sources. Promotion into MTL, notes,
articles, review queue, receipts, archive, and source reset remains owned by
tools/process_brain_dump.py.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from tools import bd_integrity as bdi
from tools.process_brain_dump import (
    BRAIN_DUMPS_PREFIX,
    MINIO_BUCKET,
    s3_client,
    s3_get,
    s3_put_verified,
)


VALID_AREAS = {"faith", "family", "business", "consulting", "work", "health", "home", "personal"}
VALID_PRIORITIES = {"A", "B", "C"}

AREA_FILE_MAP = {
    "faith": "BrainDump — Faith.md",
    "family": "BrainDump — Family.md",
    "business": "BrainDump — Business.md",
    "consulting": "BrainDump — Consulting.md",
    "work": "BrainDump — Work.md",
    "health": "BrainDump — Health.md",
    "home": "BrainDump — Home.md",
    "personal": "BrainDump — Personal.md",
}

SECTION_ALIASES = {
    "quick": "## ⚡ Quick Notes",
    "needle": "## 🎯 Needle Movers",
    "todos": "## ✅ To Do's",
    "articles": "## 📰 Articles & Resources to Follow Up On",
    "followup": "## 🗂️ Things to Organize & Follow Up On",
    "ideas": "## 💡 Ideas & Possibilities",
    "recurring": "## 🔁 Recurring / Rhythms",
}

TASK_SECTIONS = {"needle", "todos", "followup", "recurring"}
BLOCKED_SOURCE_STATES = {"partial", "error"}


class QuickAddError(Exception):
    """Raised for user-fixable quick-add validation or write failures."""


def target_key(area: str, file_override: str | None = None) -> str:
    area = area.strip().lower()
    if area not in VALID_AREAS:
        raise QuickAddError(f"invalid area: {area}")
    filename = file_override.strip() if file_override else AREA_FILE_MAP[area]
    if not filename.endswith(".md"):
        raise QuickAddError("--file override must end in .md")
    if "/" in filename or "\\" in filename or ".." in filename or "Homelab/" in filename:
        raise QuickAddError("--file override must be a safe basename under 00_Inbox/brain-dumps/")
    key = f"{BRAIN_DUMPS_PREFIX}{filename}"
    if key.startswith("Homelab/") or "Homelab/" in key:
        raise QuickAddError("refusing Homelab/ prefix")
    return key


def resolve_section(section: str) -> str:
    alias = section.strip().lower()
    try:
        return SECTION_ALIASES[alias]
    except KeyError as exc:
        raise QuickAddError(f"invalid section: {section}") from exc


def _validate_due(due: str | None) -> None:
    if due and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
        raise QuickAddError("--due must use YYYY-MM-DD")


def format_entry(section: str, text: str, *, priority: str | None = None, due: str | None = None) -> str:
    alias = section.strip().lower()
    if alias not in SECTION_ALIASES:
        raise QuickAddError(f"invalid section: {section}")
    text = text.strip()
    if not text:
        raise QuickAddError("--text cannot be empty")
    if "\x00" in text:
        raise QuickAddError("--text cannot contain null bytes")
    if priority:
        priority = priority.strip().upper()
        if priority not in VALID_PRIORITIES:
            raise QuickAddError("--priority must be A, B, or C")
    _validate_due(due)

    if alias in TASK_SECTIONS:
        desc = re.sub(r"^- \[[ xX]\]\s*", "", text).strip()
        fields = []
        if priority:
            fields.append(f"[priority:: {priority}]")
        if due:
            fields.append(f"[due:: {due}]")
        suffix = f" {' '.join(fields)}" if fields else ""
        return f"- [ ] {desc}{suffix}"
    return f"- {text.lstrip('- ').strip()}"
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -m pytest tests/test_agent_quick_add.py -q
```

Expected: mapping and formatting tests pass.

## Task 2: Markdown Insertion And Frontmatter Refresh

**Files:**
- Modify: `tools/agent_quick_add.py`
- Modify: `tests/test_agent_quick_add.py`

- [ ] **Step 1: Add failing tests for section insertion and frontmatter**

Append these tests:

```python
SOURCE = """---
domain: business
area: business
status: empty
content_hash: sha256:old
last_checked: 2026-05-01T00:00:00Z
last_processed: 2026-05-01T00:00:00Z
last_processed_hash: sha256:old
last_receipt: null
last_partial_reasons: []
---

# Brain Dump — Business

## ✅ To Do's

<!-- Format: - [ ] <task> -->

## 💡 Ideas & Possibilities

<!-- Add ideas here -->
"""


def test_append_entry_to_existing_section_preserves_other_sections():
    out = q.append_entry_to_section(SOURCE, "## ✅ To Do's", "- [ ] Follow up [priority:: A]")
    assert "- [ ] Follow up [priority:: A]" in out
    assert "## 💡 Ideas & Possibilities" in out
    assert "<!-- Add ideas here -->" in out


def test_refresh_frontmatter_marks_source_has_content():
    body = q.append_entry_to_section(SOURCE, "## ✅ To Do's", "- [ ] Follow up")
    out = q.refresh_frontmatter_for_quick_add(body)
    fm, parsed_body = q.bdi.parse_frontmatter(out)
    assert fm["status"] == "has_content"
    assert fm["last_processed"] is None
    assert fm["last_processed_hash"] is None
    assert fm["content_hash"].startswith("sha256:")
    assert "- [ ] Follow up" in parsed_body


def test_partial_or_error_source_is_blocked():
    partial = SOURCE.replace("status: empty", "status: partial")
    try:
        q.ensure_source_is_writable(partial)
    except q.QuickAddError as exc:
        assert "status=partial" in str(exc)
    else:
        raise AssertionError("partial source was accepted")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -m pytest tests/test_agent_quick_add.py -q
```

Expected: helper functions are missing.

- [ ] **Step 3: Implement insertion and frontmatter helpers**

Add this code below the formatting helpers:

```python
def ensure_source_is_writable(content: str) -> None:
    fm, _body = bdi.parse_frontmatter(content)
    status = str(fm.get("status") or "").strip().lower()
    if status in BLOCKED_SOURCE_STATES:
        raise QuickAddError(
            f"target brain dump has status={status}; run the processor/audit first before adding new content"
        )


def append_entry_to_section(content: str, canonical_heading: str, entry: str) -> str:
    lines = content.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == canonical_heading)
    except StopIteration as exc:
        raise QuickAddError(f"section not found: {canonical_heading}") from exc

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    before = lines[:end]
    after = lines[end:]
    while before and before[-1].strip() == "":
        before.pop()
    before.extend(["", entry, ""])
    return "\n".join(before + after).rstrip() + "\n"


def refresh_frontmatter_for_quick_add(content: str) -> str:
    fm, body = bdi.parse_frontmatter(content)
    now = bdi.now_utc_iso()
    area = fm.get("area") or "personal"
    domain = fm.get("domain") or area
    fm["domain"] = domain
    fm["area"] = area
    fm["status"] = "has_content"
    fm["content_hash"] = bdi.compute_content_hash(body)
    fm["last_checked"] = now
    fm["last_processed"] = None
    fm["last_processed_hash"] = None
    fm.setdefault("last_receipt", None)
    fm["last_partial_reasons"] = []
    return bdi.serialize_frontmatter(fm, body)
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -m pytest tests/test_agent_quick_add.py -q
```

Expected: all tests pass.

## Task 3: Verified MinIO Write And CLI

**Files:**
- Modify: `tools/agent_quick_add.py`
- Modify: `tests/test_agent_quick_add.py`

- [ ] **Step 1: Add failing tests for mock S3 write and dry-run**

Append:

```python
class _Body:
    def __init__(self, data: bytes):
        self.data = data

    def read(self):
        return self.data


class MockS3:
    def __init__(self):
        self.objects = {}
        self.head_calls = []

    def get_object(self, Bucket, Key):
        return {"Body": _Body(self.objects[Key])}

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body.encode("utf-8") if isinstance(Body, str) else Body
        return {"ETag": '"abc"'}

    def head_object(self, Bucket, Key):
        self.head_calls.append(Key)
        return {"ContentLength": len(self.objects[Key]), "ETag": '"abc"'}


def test_quick_add_writes_and_verifies_source(monkeypatch):
    s3 = MockS3()
    key = q.target_key("business")
    s3.objects[key] = SOURCE.encode("utf-8")

    result = q.quick_add(
        s3,
        area="business",
        section="todos",
        text="Follow up with Acme",
        priority="A",
        due=None,
        file_override=None,
        dry_run=False,
    )

    assert result["status"] == "ok"
    assert result["verified"] is True
    assert key in s3.head_calls
    assert b"Follow up with Acme" in s3.objects[key]


def test_quick_add_dry_run_does_not_write():
    s3 = MockS3()
    key = q.target_key("business")
    s3.objects[key] = SOURCE.encode("utf-8")
    before = s3.objects[key]

    result = q.quick_add(
        s3,
        area="business",
        section="ideas",
        text="Do not write this",
        priority=None,
        due=None,
        file_override=None,
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert s3.objects[key] == before
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -m pytest tests/test_agent_quick_add.py -q
```

Expected: `quick_add` is missing.

- [ ] **Step 3: Implement `quick_add`, CLI parsing, optional processor handoff**

Add:

```python
def quick_add(
    s3,
    *,
    area: str,
    section: str,
    text: str,
    priority: str | None,
    due: str | None,
    file_override: str | None,
    dry_run: bool,
) -> dict:
    key = target_key(area, file_override)
    canonical_heading = resolve_section(section)
    entry = format_entry(section, text, priority=priority, due=due)
    original = s3_get(s3, key)
    ensure_source_is_writable(original)
    updated = append_entry_to_section(original, canonical_heading, entry)
    updated = refresh_frontmatter_for_quick_add(updated)

    if dry_run:
        return {
            "status": "dry_run",
            "bucket": MINIO_BUCKET,
            "key": key,
            "section": canonical_heading,
            "entry": entry,
            "verified": False,
        }

    verified = s3_put_verified(s3, key, updated, dry_run=False)
    if not verified:
        raise QuickAddError(f"write verification failed for {key}")

    return {
        "status": "ok",
        "bucket": MINIO_BUCKET,
        "key": key,
        "file": key.rsplit("/", 1)[-1],
        "section": canonical_heading,
        "entry": entry,
        "verified": True,
    }


def run_processor_for_file(filename: str) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        str(repo_root / "tools" / "process_brain_dump.py"),
        "--file",
        filename,
        "--verbose",
    ]
    return subprocess.run(cmd, cwd=repo_root, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Append one agent quick-add item to an OHO brain-dump section")
    p.add_argument("--area", required=True, choices=sorted(VALID_AREAS))
    p.add_argument("--section", required=True, choices=sorted(SECTION_ALIASES))
    p.add_argument("--text", required=True)
    p.add_argument("--priority", choices=sorted(VALID_PRIORITIES))
    p.add_argument("--due")
    p.add_argument("--file", dest="file_override")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--process", action="store_true", help="Run process_brain_dump.py for the target file after verified write")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = quick_add(
            s3_client(),
            area=args.area,
            section=args.section,
            text=args.text,
            priority=args.priority,
            due=args.due,
            file_override=args.file_override,
            dry_run=args.dry_run,
        )
        if args.process and result["status"] == "ok":
            result["processor_exit_code"] = run_processor_for_file(result["file"])
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("processor_exit_code", 0) == 0 else int(result["processor_exit_code"])
    except QuickAddError as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_agent_quick_add.py -q
```

Expected: all quick-add tests pass.

## Task 4: Documentation And Agent Instructions

**Files:**
- Modify: `docs/RUNBOOK.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add RUNBOOK section**

Add a section near "Manual Trigger Commands":

````markdown
### Agent Quick Add During Coding Sessions

Append one item into a canonical brain-dump section through MinIO:

```bash
python3 tools/agent_quick_add.py --area business --section todos \
  --text "Follow up with Acme about proposal" --priority A --due 2026-05-15
```

Append and immediately promote through the safe processor:

```bash
python3 tools/agent_quick_add.py --area business --section todos \
  --text "Follow up with Acme about proposal" --priority A --process
```

Valid sections: `quick`, `needle`, `todos`, `articles`, `followup`, `ideas`,
`recurring`.

The quick-add tool writes only to `00_Inbox/brain-dumps/*`, verifies the S3
write, and lets `tools/process_brain_dump.py` handle MTL append, notes/articles
routing, receipts, archives, deduplication, and source reset.
````

- [ ] **Step 2: Add AGENTS.md protocol**

Add a concise section:

````markdown
## Agent Quick Add Protocol

When Aaron asks Codex to add a task, note, idea, article, follow-up, or rhythm
to Obsidian during a coding session, use:

```bash
python3 tools/agent_quick_add.py --area <area> --section <section> --text "<item>"
```

Use `--process` only when Aaron wants it promoted immediately. Never append
directly to MTL or the vault filesystem. Valid sections are `quick`, `needle`,
`todos`, `articles`, `followup`, `ideas`, and `recurring`.
````

- [ ] **Step 3: Add CLAUDE.md protocol**

Mirror the same protocol for Claude Code so both agents behave consistently.

- [ ] **Step 4: Run AI tooling checks**

Run:

```bash
python3 scripts/audit_ai_tooling.py
python -m pytest tests/test_ai_tooling.py -q
```

Expected: both pass. If the audit expects specific sections, adjust only the
new quick-add text, not unrelated tooling rules.

## Task 5: Regression And Optional Live Smoke Test

**Files:**
- No new files unless a test failure requires a scoped fix.

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
python -m pytest tests/test_agent_quick_add.py tests/test_brain_dump.py tests/test_brain_dump_integrity.py tests/test_brain_dump_orchestrator.py -q
```

Expected: all pass.

- [ ] **Step 2: Run non-integration project slice**

Run:

```bash
python -m pytest tests/ -v --ignore=tests/test_process_brain_dump_e2e.py -k "not integration" --tb=short
```

Expected: pass. If runtime is too high for the session, record the exact subset
that passed and the unrun risk.

- [ ] **Step 3: Optional dry-run CLI smoke test**

Run:

```bash
python3 tools/agent_quick_add.py --area personal --section ideas \
  --text "Dry-run smoke test for agent quick add" --dry-run
```

Expected JSON includes:

```json
{
  "status": "dry_run",
  "key": "00_Inbox/brain-dumps/BrainDump — Personal.md",
  "section": "## 💡 Ideas & Possibilities",
  "verified": false
}
```

- [ ] **Step 4: Optional live MinIO smoke test**

Only run this with Aaron's approval because it writes to live Obsidian intake:

```bash
python3 tools/agent_quick_add.py --area personal --section quick \
  --text "Agent quick-add live smoke test" --process
```

Expected:

- quick-add JSON returns `status: ok` and `verified: true`
- processor exits `0`
- `tools/process_brain_dump.py` writes normal logs/receipts
- Obsidian receives the promoted output after Remotely Save sync

## Self-Review Checklist

- Spec coverage: CLI, aliases, MinIO-only writes, verified write, optional
  processor promotion, docs, and agent instructions are all covered.
- Placeholder scan: clean for unresolved markers, real credentials, and credential IDs.
- Type consistency: helper names in tests match implementation names.
- Safety: no direct vault writes, no `Homelab/` prefix, no n8n workflow/schedule
  edits, no commit/deploy without approval.

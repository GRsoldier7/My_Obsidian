#!/usr/bin/env python3
"""Brain Dump Processor for ObsidianHomeOrchestrator.

Called by n8n every 5 minutes. Reads unprocessed brain dumps from
00_Inbox/brain-dumps/, sends them to Claude for extraction, writes
individual task files to 00_Inbox/processed/ and notes to domain folders,
then marks originals as processed.

Usage:
    python process_brain_dump.py --vault-path /path/to/vault
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_PER_CYCLE = 5

AREA_FOLDER_MAP: dict[str, str] = {
    "work": "20_Domains (Life and Work)/Career/Parallon",
    "consulting": "20_Domains (Life and Work)/Career/Consulting",
    "business": "20_Domains (Life and Work)/Personal/Business Ideas & Projects",
    "family": "20_Domains (Life and Work)/Personal/Family",
    "personal": "20_Domains (Life and Work)/Personal",
    "faith": "30_Knowledge Library/Bible Studies & Notes",
    "health": "30_Knowledge Library/Biohacking",
    "home": "20_Domains (Life and Work)/Personal/Home",
}

VALID_AREAS = set(AREA_FOLDER_MAP.keys())
VALID_PRIORITIES = {"A", "B", "C"}

DEFAULT_AREA = "personal"
DEFAULT_PRIORITY = "B"

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are an assistant that processes brain dumps for Aaron.

Context about Aaron:
- Business Analytics Manager at Parallon (area: work)
- AI automation consultant with active engagements (area: consulting)
- Business ventures including Echelon Seven startup (area: business)
- Husband and father — family decisions and relationships (area: family)
- Person of faith with Bible study and social media ministry (area: faith)
- Biohacking / supplements / fitness / hip health (area: health)
- Home projects, MI property, homelab tech tinkering (area: home)
- AI hobby projects, general life admin, miscellaneous (area: personal)

Given a brain dump, extract:
1. **Tasks** - actionable items with a short description, an area, a priority, \
and an optional due date.
2. **Notes** - non-actionable information, ideas, or reference material, each \
tagged with an area.

Valid areas: work, consulting, business, family, personal, faith, health, home
Valid priorities: A, B, C
If uncertain, default to area=personal and priority=B.

Respond with **only** valid JSON (no markdown fences) matching this schema:

{
  "tasks": [
    {
      "description": "string",
      "area": "string",
      "priority": "A|B|C",
      "due": "YYYY-MM-DD or null"
    }
  ],
  "notes": [
    {
      "title": "string",
      "content": "string (markdown)",
      "area": "string"
    }
  ]
}
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(text: str, max_len: int = 48) -> str:
    """Create a filename-safe slug from *text*."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter_dict, body) from a markdown file with YAML front matter."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 3 :].strip()
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm, body


def _rebuild_frontmatter(fm: dict[str, str], body: str) -> str:
    """Reconstruct the file content with updated front matter."""
    lines = [f"{k}: {v}" for k, v in fm.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body + "\n"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def find_unprocessed(vault: Path) -> list[Path]:
    """Return up to MAX_PER_CYCLE unprocessed brain-dump files."""
    dump_dir = vault / "00_Inbox" / "brain-dumps"
    if not dump_dir.is_dir():
        log.warning("Brain-dumps directory does not exist: %s", dump_dir)
        return []

    results: list[Path] = []
    for md in sorted(dump_dir.glob("*.md")):
        fm, _ = _parse_frontmatter(md.read_text(encoding="utf-8"))
        if fm.get("processed", "").lower() in ("false", "no", ""):
            results.append(md)
            if len(results) >= MAX_PER_CYCLE:
                break
    return results


def extract_with_claude(content: str) -> dict:
    """Send brain-dump content to Claude and return parsed JSON."""
    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if the model includes them despite instructions
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("Failed to parse Claude response as JSON: %s", exc)
        log.debug("Raw response:\n%s", raw)
        raise


def _validate_area(area: str) -> str:
    if area not in VALID_AREAS:
        log.warning("Invalid area '%s', defaulting to '%s'", area, DEFAULT_AREA)
        return DEFAULT_AREA
    return area


def _validate_priority(priority: str) -> str:
    priority = priority.upper()
    if priority not in VALID_PRIORITIES:
        log.warning("Invalid priority '%s', defaulting to '%s'", priority, DEFAULT_PRIORITY)
        return DEFAULT_PRIORITY
    return priority


def write_tasks(vault: Path, tasks: list[dict], source_file: str) -> int:
    """Write individual task files to 00_Inbox/processed/. Returns count written."""
    out_dir = vault / "00_Inbox" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    count = 0

    for i, task in enumerate(tasks):
        desc = task.get("description", "").strip()
        if not desc:
            continue

        area = _validate_area(task.get("area", DEFAULT_AREA))
        priority = _validate_priority(task.get("priority", DEFAULT_PRIORITY))
        due = task.get("due") or ""

        # Build the task line
        task_line = f"- [ ] {desc} [area:: {area}] [priority:: {priority}]"
        if due:
            task_line += f" [due:: {due}]"

        iso_now = now.isoformat()
        slug = _slugify(desc)
        timestamp = now.strftime("%Y-%m-%d-%H%M")
        filename = f"{timestamp}-{slug}.md"
        # Append index if multiple tasks share same slug within the same minute
        if (out_dir / filename).exists():
            filename = f"{timestamp}-{slug}-{i}.md"

        content = (
            f"---\n"
            f"created: {iso_now}\n"
            f"type: processed-task\n"
            f"source: brain-dump\n"
            f"source_file: {source_file}\n"
            f"---\n\n"
            f"{task_line}\n"
        )

        (out_dir / filename).write_text(content, encoding="utf-8")
        log.info("Wrote task: %s", filename)
        count += 1

    return count


def write_notes(vault: Path, notes: list[dict], source_file: str) -> int:
    """Write note files to their domain folders. Returns count written."""
    now = datetime.now(timezone.utc)
    count = 0

    for i, note in enumerate(notes):
        title = note.get("title", "").strip() or f"Note {i + 1}"
        body = note.get("content", "").strip()
        area = _validate_area(note.get("area", DEFAULT_AREA))

        folder = vault / AREA_FOLDER_MAP[area]
        folder.mkdir(parents=True, exist_ok=True)

        iso_now = now.isoformat()
        slug = _slugify(title)
        timestamp = now.strftime("%Y-%m-%d-%H%M")
        filename = f"{timestamp}-{slug}.md"
        if (folder / filename).exists():
            filename = f"{timestamp}-{slug}-{i}.md"

        content = (
            f"---\n"
            f"created: {iso_now}\n"
            f"type: brain-dump-note\n"
            f"source: brain-dump\n"
            f"source_file: {source_file}\n"
            f"area: {area}\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"{body}\n"
        )

        (folder / filename).write_text(content, encoding="utf-8")
        log.info("Wrote note: %s -> %s", filename, AREA_FOLDER_MAP[area])
        count += 1

    return count


def mark_processed(path: Path) -> None:
    """Set processed: true in the brain-dump file's front matter."""
    text = path.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)
    fm["processed"] = "true"
    fm["processed_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(_rebuild_frontmatter(fm, body), encoding="utf-8")
    log.info("Marked processed: %s", path.name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Process brain dumps from Obsidian vault")
    parser.add_argument("--vault-path", required=True, help="Absolute path to the Obsidian vault")
    args = parser.parse_args()

    vault = Path(args.vault_path)
    if not vault.is_dir():
        log.error("Vault path does not exist: %s", vault)
        sys.exit(1)

    dumps = find_unprocessed(vault)
    if not dumps:
        log.info("No unprocessed brain dumps found.")
        return

    log.info("Found %d unprocessed brain dump(s).", len(dumps))

    total_tasks = 0
    total_notes = 0

    for dump_path in dumps:
        log.info("Processing: %s", dump_path.name)
        try:
            text = dump_path.read_text(encoding="utf-8")
            _, body = _parse_frontmatter(text)
            if not body.strip():
                log.warning("Empty body in %s, skipping.", dump_path.name)
                mark_processed(dump_path)
                continue

            result = extract_with_claude(body)
            tasks = result.get("tasks", [])
            notes = result.get("notes", [])

            tc = write_tasks(vault, tasks, dump_path.name)
            nc = write_notes(vault, notes, dump_path.name)
            total_tasks += tc
            total_notes += nc

            mark_processed(dump_path)

        except Exception:
            log.exception("Error processing %s", dump_path.name)
            continue

    log.info(
        "Cycle complete. Processed %d dump(s), created %d task(s) and %d note(s).",
        len(dumps),
        total_tasks,
        total_notes,
    )


if __name__ == "__main__":
    main()

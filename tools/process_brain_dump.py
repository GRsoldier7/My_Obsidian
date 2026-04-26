#!/usr/bin/env python3
"""
tools/process_brain_dump.py
Section-aware brain dump processor for ObsidianHomeOrchestrator.

Reads brain dump files from MinIO (00_Inbox/brain-dumps/), parses each
section individually, sends real content to OpenRouter for extraction,
writes tasks/notes to vault, and logs every run.

Usage:
    python3 tools/process_brain_dump.py
    python3 tools/process_brain_dump.py --dry-run
    python3 tools/process_brain_dump.py --file "BrainDump — Personal.md"
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Configuration ────────────────────────────────────────────────────────────

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")  # Required: set in .env
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")  # Required: set in .env
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model cascade: first working model wins. Free tier only.
EXTRACT_MODELS = [
    "google/gemma-3-4b-it:free",          # small, fast, follows instructions
    "meta-llama/llama-3.3-70b-instruct:free",  # better quality when available
    "nvidia/nemotron-3-super-120b-a12b:free",  # large fallback
]

BRAIN_DUMPS_PREFIX = "00_Inbox/brain-dumps/"
PROCESSED_PREFIX = "00_Inbox/processed/"
ARTICLES_FILE = "00_Inbox/articles-to-process.md"
MTL_KEY = "10_Active Projects/Active Personal/!!! MASTER TASK LIST.md"
LOGS_PREFIX = "99_System/logs/"
METRICS_KEY = "99_System/metrics/brain-dump-extraction.jsonl"
REVIEW_QUEUE_KEY = "00_Inbox/review-queue.md"
DAILY_NOTES_PREFIX = "40_Timeline_Weekly/Daily/"

# Confidence threshold below which items go to review queue (Layer 3).
CONFIDENCE_THRESHOLD = 0.6
# Fuzzy-match similarity threshold for MTL dedup (Layer 3).
FUZZY_DEDUP_THRESHOLD = 0.85

VALID_AREAS = {"faith", "family", "business", "consulting", "work", "health", "home", "personal"}
VALID_PRIORITIES = {"A", "B", "C"}

AREA_FOLDER_MAP = {
    "work": "20_Domains (Life and Work)/Career/Parallon",
    "consulting": "20_Domains (Life and Work)/Career/Consulting",
    "business": "20_Domains (Life and Work)/Personal/Business Ideas & Projects",
    "family": "20_Domains (Life and Work)/Personal/Family",
    "personal": "20_Domains (Life and Work)/Personal",
    "faith": "30_Knowledge Library/Bible Studies & Notes",
    "health": "30_Knowledge Library/Biohacking",
    "home": "20_Domains (Life and Work)/Personal/Home",
}

Q2_ROCKS_CONTEXT = """
Q2 2026 Quarterly Rocks (use these for priority scoring):
- Faith: Launch social media Bible study (4 sessions delivered)
- Family: Complete Marriage Alignment Questionnaire + bi-weekly check-in
- Business: Ship MVP — website live, offer defined, 3 outreach conversations (Echelon Seven)
- Work: Deliver Union project + position for exit (Parallon)
- Health: Make hip decision + 3x/week gym for 8 weeks

Priority A = directly advances one of the 5 Q2 Rocks above
Priority B = important but doesn't directly move a quarterly rock
Priority C = nice-to-have, research, or low-urgency
""".strip()

TASK_FORMAT_PATTERN = re.compile(
    r"^- \[ \] .+\[area:: (?:faith|family|business|consulting|work|health|home|personal)\]"
    r"( \[priority:: [ABC]\])?( \[due:: \d{4}-\d{2}-\d{2}\])?"
    r"( \[explore:: (?:true|false)\])?"
    r"( \[source:: \[\[[^\]]+\]\]\])?$"
)

SECTION_HEADERS = [
    "## ⚡ Quick Notes",
    "## 🎯 Needle Movers",
    "## ✅ To Do's",
    "## 📰 Articles & Resources to Follow Up On",
    "## 🗂️ Things to Organize & Follow Up On",
    "## 💡 Ideas & Possibilities",
    "## 🔁 Recurring / Rhythms",
]

# Map section header → extraction type
SECTION_TYPE_MAP = {
    "Quick Notes": "notes",
    "Needle Movers": "tasks",
    "To Do's": "tasks",
    "Articles & Resources to Follow Up On": "articles",
    "Things to Organize & Follow Up On": "tasks",
    "Ideas & Possibilities": "notes",
    "Recurring / Rhythms": "tasks",
}


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class RunLog:
    workflow: str = "brain-dump-processor"
    run_date: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    status: str = "success"
    files_discovered: int = 0
    files_with_content: int = 0
    items_extracted: int = 0
    tasks_written: int = 0
    notes_written: int = 0
    articles_queued: int = 0
    write_verifications_pass: int = 0
    write_verifications_fail: int = 0
    files_processed: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    quality_rejections: list = field(default_factory=list)
    # Layer 3 — intent routing + confidence gating telemetry
    candidates_seen: int = 0
    items_routed: dict = field(default_factory=lambda: {
        "mtl": 0, "daily_note": 0, "captured_references": 0, "review_queue": 0
    })
    ai_calls: int = 0
    dedup_skips: int = 0
    low_confidence: int = 0


# ── MinIO helpers ────────────────────────────────────────────────────────────

def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30),
        region_name="us-east-1",
    )


def s3_get(s3, key: str) -> str:
    resp = s3.get_object(Bucket=MINIO_BUCKET, Key=key)
    return resp["Body"].read().decode("utf-8")


def s3_put_verified(s3, key: str, body: str, dry_run: bool = False) -> bool:
    """Write to MinIO and verify the write succeeded. Returns True on success."""
    if dry_run:
        logging.info(f"[DRY RUN] Would write: {key}")
        return True
    try:
        s3.put_object(Bucket=MINIO_BUCKET, Key=key, Body=body.encode("utf-8"))
        r = s3.head_object(Bucket=MINIO_BUCKET, Key=key)
        return r["ContentLength"] > 0
    except Exception as e:
        logging.error(f"WRITE_VERIFY_FAIL: {key}: {e}")
        return False


def discover_brain_dumps(s3) -> list[dict]:
    """List all non-empty files in 00_Inbox/brain-dumps/."""
    resp = s3.list_objects_v2(Bucket=MINIO_BUCKET, Prefix=BRAIN_DUMPS_PREFIX)
    files = []
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        name = key.split("/")[-1]
        # Skip folder placeholders and zero-byte files
        if not name or name.endswith("/") or obj["Size"] == 0:
            continue
        files.append({"key": key, "name": name, "size": obj["Size"]})
    return files


# ── Section parsing ──────────────────────────────────────────────────────────

def parse_sections(content: str) -> dict[str, str]:
    """Split markdown content into a dict of {section_name: section_body}."""
    sections = {}
    current_header = "_frontmatter"
    current_lines = []

    for line in content.splitlines():
        stripped = line.strip()
        # Detect H2 section headers (## ...)
        if stripped.startswith("## "):
            sections[current_header] = "\n".join(current_lines)
            current_header = stripped[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_header] = "\n".join(current_lines)
    return sections


def is_section_empty(section_content: str) -> bool:
    """
    Return True if section has no real user content.

    Empty means: only HTML comments, template placeholder lines,
    Obsidian inline field syntax (=this.field), horizontal rules,
    italic/bold placeholder text, or whitespace.
    """
    lines = section_content.splitlines()
    real_lines = []
    in_comment = False

    for line in lines:
        stripped = line.strip()

        # Multi-line HTML comment handling
        if "<!--" in stripped:
            in_comment = True
        if "-->" in stripped:
            in_comment = False
            continue
        if in_comment:
            continue

        # Skip empty lines
        if not stripped:
            continue
        # Skip horizontal rules
        if re.match(r"^-{3,}$|^\*{3,}$|^_{3,}$", stripped):
            continue
        # Skip Obsidian inline field placeholders
        if stripped.startswith("=this."):
            continue
        # Skip italic/bold placeholder text (common in templates)
        if re.match(r"^\*[^*]+\*$|^_[^_]+_$", stripped):
            continue
        # Skip lines that are only a tag reference
        if re.match(r"^\*Tags:.*\*$", stripped):
            continue
        # Skip blockquote instructions (> **How to use:**)
        if stripped.startswith(">"):
            continue
        # Skip format example lines (Format: - [ ] ...)
        if "Format:" in stripped:
            continue

        real_lines.append(stripped)

    return len(real_lines) == 0


def _strip_yaml_frontmatter(text: str) -> str:
    """Strip YAML front matter block (--- ... ---) and common template boilerplate.

    Also removes:
    - H1 headings (# Title) — brain dump file titles
    - Blockquote lines (> ...) — "How to use" template instructions
    - Horizontal rules (--- / ***)
    Returns the remaining user-authored body text.
    """
    text = text.strip()
    # Strip YAML block
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:].strip()
    # Strip line-by-line boilerplate
    clean_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # H1 headings (file title)
        if re.match(r"^#\s+", stripped):
            continue
        # Blockquote instructions
        if stripped.startswith(">"):
            continue
        # Horizontal rules
        if re.match(r"^-{3,}$|^\*{3,}$|^_{3,}$", stripped):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def extract_real_sections(sections: dict[str, str]) -> dict[str, str]:
    """Return only sections that have real user content.

    For files with no ## section headers (e.g. plain-text brain dumps, ad-hoc
    notes like Coding.md or Website & Business.md), all content lands in
    '_frontmatter'.  If no named sections have real content we fall back to
    treating the body of '_frontmatter' (after stripping the YAML block and
    template boilerplate) as a generic 'To Do's' section so the content is not
    silently discarded.

    Structured brain dump templates (Faith, Family, etc.) have ## sections and
    will never trigger the fallback even if the frontmatter body has a H1 title,
    because the fallback only fires when real{} is still empty after the named
    section pass.
    """
    real = {}
    for header, body in sections.items():
        if header.startswith("_"):
            continue
        if is_section_empty(body):
            continue
        # Only process known brain dump sections
        header_clean = header.lstrip("⚡🎯✅📰🗂️💡🔁 ").strip()
        for known in SECTION_TYPE_MAP:
            if known in header_clean or header_clean in known:
                real[header] = body
                break

    # Fallback: header-less files — treat stripped body as a task section.
    # Only activates when NO named sections were found (i.e. truly header-less
    # files like Coding.md, Website & Business.md, Bible post on Social Media.md).
    if not real and "_frontmatter" in sections:
        body = _strip_yaml_frontmatter(sections["_frontmatter"])
        if not is_section_empty(body):
            real["✅ To Do's"] = body

    return real


def infer_area_from_filename(filename: str) -> str:
    """Infer domain area from brain dump filename."""
    name_lower = filename.lower()
    if "faith" in name_lower or "bible" in name_lower:
        return "faith"
    if "family" in name_lower:
        return "family"
    if "business" in name_lower or "echelon" in name_lower or "website" in name_lower:
        return "business"
    if "consulting" in name_lower:
        return "consulting"
    if "work" in name_lower or "parallon" in name_lower:
        return "work"
    if "health" in name_lower:
        return "health"
    if "home" in name_lower:
        return "home"
    if "coding" in name_lower:
        return "personal"
    return "personal"


def section_type(header: str) -> str:
    """Return 'tasks', 'articles', or 'notes' for a section header."""
    header_clean = header.lstrip("⚡🎯✅📰🗂️💡🔁 ").strip()
    for known, stype in SECTION_TYPE_MAP.items():
        if known in header_clean or header_clean in known:
            return stype
    return "notes"


# ── Q2 Rock keyword scoring ──────────────────────────────────────────────────

Q2_ROCK_KEYWORDS = {
    "faith": ["bible", "bible study", "social media", "session", "church", "prayer", "gospel", "ministry"],
    "family": ["christy", "marriage", "questionnaire", "bi-weekly", "kids", "family"],
    "business": ["echelon", "website", "offer", "outreach", "mvp", "client", "echelon seven"],
    "work": ["union", "parallon", "project", "deliver", "exit"],
    "health": ["hip", "gym", "3x", "crossfit", "workout", "decision", "biohacking"],
    "consulting": ["client", "sow", "proposal", "engagement", "scope", "invoice", "billable", "retainer", "deliverable", "consulting"],
    "home": ["house", "michigan", "mi property", "generator", "ups", "photo", "repair", "maintenance", "basement", "hvac", "yard"],
    "personal": ["ai project", "hobby", "side project", "experiment", "learning", "reading", "self", "tinkering", "personal"],
}

def infer_priority(text: str) -> str:
    """Return A if text matches Q2 Rock keywords, else B."""
    lower = text.lower()
    for keywords in Q2_ROCK_KEYWORDS.values():
        if any(kw in lower for kw in keywords):
            return "A"
    return "B"


def _clean_task_text(raw: str) -> str:
    """Strip existing metadata tags from task text to rebuild in canonical order."""
    # Remove [area:: ...], [priority:: ...], [due:: ...]
    cleaned = re.sub(r"\s*\[(area|priority|due)::[^\]]*\]", "", raw).strip()
    return cleaned


def _infer_due(raw: str) -> str | None:
    """Extract due date if present in the task text."""
    m = re.search(r"\[due::\s*(\d{4}-\d{2}-\d{2})\]", raw)
    return m.group(1) if m else None


def _build_task(desc: str, area: str, priority: str, due: str | None = None,
                explore: bool = False) -> str:
    """Build a canonical task line."""
    task = f"- [ ] {desc} [area:: {area}] [priority:: {priority}]"
    if due:
        task += f" [due:: {due}]"
    if explore:
        task += " [explore:: true]"
    return task


# Shorthand-date suffix:  "... - 20260420"  (8 digits, optionally space-padded)
SHORTHAND_DATE_RE = re.compile(r"\s*[-—]\s*(\d{4})(\d{2})(\d{2})\s*$")
# Loose imperative-verb start (any TitleCase or imperative verb).
# Lines like "Flush out X", "Re-apply", "Dig into Y", "Fine Tune Z" all match.
IMPERATIVE_LINE_RE = re.compile(
    r"^([A-Z][a-z]+(?:[-\s][A-Za-z]+)?)\b"  # Word or hyphenated/two-word lead
)
# Lines that should never be treated as tasks even if they start TitleCase.
TASK_BLOCKLIST = (
    "## ", "# ", "*Tags:", "*Last", "*Updated", "Format:", "How to use",
)


def normalize_shorthand_dates(text: str) -> str:
    """Convert trailing `- YYYYMMDD` (or `— YYYYMMDD`) into `[due:: YYYY-MM-DD]`.

    Validates as a real date. Random 8-digit numbers (e.g. `12345678`) pass
    through unchanged because they fail the date validity check.
    """
    m = SHORTHAND_DATE_RE.search(text)
    if not m:
        return text
    yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
    try:
        datetime(int(yyyy), int(mm), int(dd))
    except ValueError:
        return text
    return SHORTHAND_DATE_RE.sub(f" [due:: {yyyy}-{mm}-{dd}]", text)


def _is_imperative_prose(line: str) -> bool:
    """Return True if the line looks like an actionable prose statement.

    Catches the operator's writing patterns that the old verb whitelist missed:
    "Flush out ICP...", "Fine Tune E7...", "Re-apply to Google...", "Dig into ICP...".

    Heuristic:
      • Starts with a Title-Case word (or hyphenated like "Re-apply") OR a
        known imperative phrase ("I need to", "Need to").
      • Is at least 10 chars long (filters short fragments).
      • Is not a markdown heading or template artifact.
    """
    if len(line) < 10:
        return False
    if any(line.startswith(b) for b in TASK_BLOCKLIST):
        return False
    if line.startswith("#") or line.startswith("|"):
        return False
    if re.match(r"^[Ii]\s+(need|should|must|want|have)\s+to\b", line):
        return True
    if re.match(r"^Need\s+to\b", line, re.IGNORECASE):
        return True
    return bool(IMPERATIVE_LINE_RE.match(line))


def regex_extract_tasks(section_body: str, file_area: str) -> list[str]:
    """
    Extract tasks from section content using regex — zero AI cost.
    Always rebuilds canonical format: - [ ] desc [area:: X] [priority:: X]
    """
    tasks = []
    for raw_line in section_body.splitlines():
        # Normalize the raw line first so trailing `- YYYYMMDD` shorthand
        # becomes a real `[due:: YYYY-MM-DD]` tag before any extraction logic.
        line = normalize_shorthand_dates(raw_line.strip())
        stripped = line
        if not stripped or is_section_empty(stripped):
            continue
        if stripped.startswith("<!--") or stripped.startswith(">"):
            continue
        # Skip italic template text
        if re.match(r"^\*[^*]+\*$|^_[^_]+_$", stripped):
            continue

        # Existing checkbox task: "- [ ] ..." or "* [ ] ..."
        if re.match(r"^[-*]\s*\[ \]\s+", stripped):
            raw_text = re.sub(r"^[-*]\s*\[ \]\s+", "", stripped).strip()
            due = _infer_due(raw_text)
            desc = _clean_task_text(raw_text)
            if not desc:
                continue
            priority = infer_priority(desc)
            tasks.append(_build_task(desc, file_area, priority, due))
            continue

        # Bullet without checkbox: "- item" or "* item"
        if re.match(r"^[-*]\s+\S", stripped):
            raw_text = re.sub(r"^[-*]\s+", "", stripped).strip()
            if len(raw_text) < 5:
                continue
            due = _infer_due(raw_text)
            desc = _clean_task_text(raw_text)
            priority = infer_priority(desc)
            tasks.append(_build_task(desc, file_area, priority, due))
            continue

        # Plain sentence with explicit inline priority marker: "Do thing - A"
        # ("Apply to Reggie program ASAP - A")
        priority_match = re.search(
            r"\s+-\s+([ABC])(?:\s+-\s+due\s+(\d{4}-\d{2}-\d{2}))?$", stripped
        )
        if priority_match and len(stripped) >= 10:
            explicit_priority = priority_match.group(1)
            due_date = priority_match.group(2)
            desc = stripped[:priority_match.start()].strip()
            desc = _clean_task_text(desc)
            if len(desc) >= 5:
                tasks.append(_build_task(desc, file_area, explicit_priority, due_date))
                continue

        # Imperative-prose lines — broad heuristic (replaces narrow verb whitelist).
        if _is_imperative_prose(stripped):
            due = _infer_due(stripped)
            desc = _clean_task_text(stripped)
            if len(desc) < 5:
                continue
            priority = infer_priority(desc)
            tasks.append(_build_task(desc, file_area, priority, due))
            continue

    return tasks


# ── Explore-intent auto-tag ──────────────────────────────────────────────────

EXPLORE_INTENT_RE = re.compile(
    r"\b(research|investigate|explore|look\s+into|dig\s+into|study|"
    r"evaluate|deep\s+dive)\b",
    re.IGNORECASE,
)


def _ensure_explore_tag(task: str) -> str:
    """If the task description has research/explore intent and the AI did
    not already include `[explore:: true]`, append it."""
    if "[explore::" in task:
        return task
    # Look only at the description portion (between "- [ ]" and the first "[area::")
    desc_match = re.match(r"^- \[ \] (.+?)\s*\[area::", task)
    desc = desc_match.group(1) if desc_match else task
    if EXPLORE_INTENT_RE.search(desc):
        return task + " [explore:: true]"
    return task


def extract_tasks_with_ai_fallback(client: Any, section_body: str,
                                    file_area: str, today: str) -> list[str]:
    """AI fallback path. Always called when regex returns 0 tasks (and AI is the
    gold path on every brain dump for richer extraction).

    Auto-tags research/investigate/explore-intent items with [explore:: true].
    Returns canonical-format task lines only — invalid lines are dropped.
    """
    if client is None:
        return []
    raw = extract_tasks_from_section(client, "AI fallback", section_body, file_area, today)
    out = []
    for task in raw:
        task = _ensure_explore_tag(task.strip())
        # Validate canonical shape, but tolerate trailing [explore:: true]
        base = re.sub(r"\s*\[explore::[^\]]+\]\s*$", "", task).strip()
        if validate_task_line(base):
            out.append(task)
    return out


# ── OpenRouter AI extraction ─────────────────────────────────────────────────

def openrouter_client() -> Any:
    api_key = OPENROUTER_API_KEY
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "openai package is required for OpenRouter calls. Install dependencies from requirements.txt."
        ) from exc
    return OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)


def _chat_with_fallback(client: Any, prompt: str, max_tokens: int = 600) -> str | None:
    """Try models in cascade order. Return response text or None if all fail."""
    for model in EXTRACT_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.1,
            )
            text = resp.choices[0].message.content
            if text:
                logging.debug(f"Used model: {model}")
                return text.strip()
        except Exception as e:
            logging.warning(f"Model {model} failed: {type(e).__name__}: {str(e)[:120]}")
    logging.error("All models in cascade failed")
    return None


def extract_tasks_from_section(client: Any, section_header: str, section_body: str,
                                file_area: str, today: str) -> list[str]:
    """Ask OpenRouter to extract canonical tasks from a section."""
    prompt = f"""Extract tasks from this brain dump section into Obsidian task format.

EXACT FORMAT: - [ ] description [area:: AREA] [priority:: PRIORITY]
Example: - [ ] Call dentist [area:: health] [priority:: B]

{Q2_ROCKS_CONTEXT}

Rules:
- area must be one of: faith, family, business, consulting, work, health, home, personal
- priority: A=directly advances Q2 Rock above, B=important, C=nice-to-have
- ONLY output task lines, nothing else — no explanations, no headers
- If no real tasks exist, output: NONE
- Do NOT add explanatory text or reasoning before/after the tasks

File domain: {file_area} | Today: {today} | Section: {section_header}

CONTENT:
{section_body}"""

    text = _chat_with_fallback(client, prompt, max_tokens=600)
    if not text or text.strip() == "NONE":
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("- [ ]")]


def extract_notes_from_section(client: OpenAI, section_header: str, section_body: str,
                                file_area: str, today: str) -> list[dict]:
    """Extract notes/ideas from a section. Returns list of {title, content, area}."""
    prompt = f"""Extract notes from this brain dump section. Output one JSON object per line.

Format per note: {{"title": "short title", "content": "the idea/note text", "area": "AREA"}}
Valid areas: faith, family, business, consulting, work, health, home, personal
If no real notes, output: NONE

File domain: {file_area} | Section: {section_header}

CONTENT:
{section_body}"""

    text = _chat_with_fallback(client, prompt, max_tokens=400)
    if not text or text.strip() == "NONE":
        return []
    notes = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                note = json.loads(line)
                if "title" in note and "content" in note and "area" in note:
                    notes.append(note)
            except json.JSONDecodeError:
                pass
    return notes


def extract_articles_from_section(client: OpenAI, section_body: str,
                                   file_area: str, today: str) -> list[str]:
    """Extract article URLs. Returns markdown link lines for articles-to-process.md."""
    prompt = f"""Extract URLs from this brain dump section.

For each URL, output: - [Title or description](URL) — brief context
If no URLs found, output: NONE

CONTENT:
{section_body}"""

    text = _chat_with_fallback(client, prompt, max_tokens=300)
    if not text or text.strip() == "NONE":
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("- [")]


# ── Quality gate ─────────────────────────────────────────────────────────────

def validate_task_line(line: str) -> bool:
    """Validate canonical task format."""
    return bool(TASK_FORMAT_PATTERN.match(line.strip()))


def quality_gate_tasks(tasks: list[str]) -> tuple[list[str], list[dict]]:
    """Split tasks into valid and rejected. Returns (valid, rejections)."""
    valid = []
    rejections = []
    for task in tasks:
        if validate_task_line(task):
            valid.append(task)
        else:
            rejections.append({"item": task[:80], "reason": "invalid canonical format"})
    return valid, rejections


# ── Write outputs ─────────────────────────────────────────────────────────────

def write_task_file(s3, tasks: list[str], source_file: str, area: str,
                    today: str, dry_run: bool) -> int:
    """Write extracted tasks to a file in 00_Inbox/processed/."""
    if not tasks:
        return 0
    slug = source_file.replace(".md", "").replace(" ", "-").replace("—", "").strip("-")
    key = f"{PROCESSED_PREFIX}{today}-{slug}-tasks.md"
    content = f"""---
source: {source_file}
area: {area}
processed: {today}
type: extracted-tasks
---

# Extracted Tasks — {source_file} ({today})

{chr(10).join(tasks)}
"""
    ok = s3_put_verified(s3, key, content, dry_run)
    return len(tasks) if ok else 0


def append_tasks_to_mtl(s3, tasks: list[str], source_file: str, today: str,
                        dry_run: bool) -> int:
    """Append extracted tasks to the Master Task List.

    Reads MTL, deduplicates against existing tasks, appends new ones
    under the appropriate priority section, writes back with verification.
    Returns count of tasks actually appended (after dedup).
    """
    if not tasks:
        return 0

    # Read current MTL
    try:
        mtl = s3_get(s3, MTL_KEY)
    except Exception as e:
        logging.error(f"Failed to read MTL for append: {e}")
        return 0

    # Extract existing task descriptions for dedup
    existing = set()
    for line in mtl.splitlines():
        m = re.match(r'^- \[[ x]\] (.+?)(?:\s*\[area::|\s*$)', line)
        if m:
            existing.add(m.group(1).strip().lower())

    # Filter out duplicates
    new_tasks = []
    for task in tasks:
        m = re.match(r'^- \[ \] (.+?)(?:\s*\[area::|\s*$)', task)
        if m:
            desc = m.group(1).strip().lower()
            if desc not in existing:
                new_tasks.append(task)
                existing.add(desc)
            else:
                logging.info(f"      dedup: skipping '{desc[:50]}...' (already in MTL)")

    if not new_tasks:
        logging.info(f"      all {len(tasks)} tasks already in MTL (deduped)")
        return 0

    # Append to end of MTL with a source marker
    append_block = (
        f"\n\n## Brain Dump Capture — {today} ({source_file})\n"
        + "\n".join(new_tasks)
        + "\n"
    )
    updated_mtl = mtl.rstrip() + append_block

    if dry_run:
        logging.info(f"      [dry-run] would append {len(new_tasks)} tasks to MTL")
        return len(new_tasks)

    ok = s3_put_verified(s3, MTL_KEY, updated_mtl, dry_run=False)
    if ok:
        logging.info(f"      appended {len(new_tasks)} tasks to MTL")
    else:
        logging.error(f"      FAILED to append tasks to MTL")
    return len(new_tasks) if ok else 0


def write_note_file(s3, note: dict, source_file: str, today: str, dry_run: bool) -> bool:
    """Write a single note to its domain folder."""
    area = note.get("area", "personal")
    if area not in AREA_FOLDER_MAP:
        area = "personal"
    folder = AREA_FOLDER_MAP[area]
    title_slug = re.sub(r"[^\w\s-]", "", note.get("title", "note")).strip()
    title_slug = re.sub(r"\s+", "-", title_slug)[:50]
    key = f"{folder}/{today}-{title_slug}.md"
    content = f"""---
source: {source_file}
area: {area}
created: {today}
type: note
---

# {note.get('title', 'Note')}

{note.get('content', '')}
"""
    return s3_put_verified(s3, key, content, dry_run)


def append_articles(s3, article_lines: list[str], today: str, dry_run: bool):
    """Append article URLs to the articles-to-process.md queue file."""
    if not article_lines:
        return
    try:
        existing = s3_get(s3, ARTICLES_FILE)
    except ClientError:
        existing = f"# Articles to Process\n\n"

    new_content = existing.rstrip() + f"\n\n## Added {today}\n\n" + "\n".join(article_lines) + "\n"
    s3_put_verified(s3, ARTICLES_FILE, new_content, dry_run)


SECTION_TEMPLATES = {
    "Quick Notes": "*Raw thoughts, observations, things on your mind right now*\n\n<!-- Add notes here -->",
    "Needle Movers": "*Big moves that could change the game*\n\n<!-- Format: - [ ] <what> -->",
    "To Do's": "*Specific actions, tasks, follow-ups*\n\n<!-- Format: - [ ] <task> [priority:: A/B/C] [due:: YYYY-MM-DD] -->",
    "Articles & Resources to Follow Up On": "*Links, articles, books, videos, tools to explore*\n\n<!-- Add links here -->",
    "Things to Organize & Follow Up On": "*Loose ends, conversations to close, things in limbo*\n\n<!-- Add items here -->",
    "Ideas & Possibilities": "*Half-baked ideas, what-ifs, experiments worth exploring*\n\n<!-- Add ideas here -->",
    "Recurring / Rhythms": "*Regular things in this domain that need attention or a new rhythm*\n\n<!-- Add here -->",
}


def reset_to_template(content: str, extracted_headers: list[str], today: str) -> str:
    """
    Clear extracted sections back to empty template state.
    Leaves the file ready for the user to fill in again.
    Updates frontmatter last_processed and resets status to empty.
    """
    # Update frontmatter
    content = re.sub(r"^last_processed:.*$", f"last_processed: {today}", content, flags=re.MULTILINE)
    content = re.sub(r"^status:.*$", "status: empty", content, flags=re.MULTILINE)

    # Clear each extracted section back to template placeholder
    for header in extracted_headers:
        # Find the section header in content
        header_clean = header.lstrip("⚡🎯✅📰🗂️💡🔁 ").strip()
        # Look for matching template
        template = None
        for known, tmpl in SECTION_TEMPLATES.items():
            if known in header_clean or header_clean in known:
                template = tmpl
                break
        if not template:
            continue

        # Find the section and replace its body (between this ## and next ##)
        pattern = rf"(## {re.escape(header)}\n).*?(?=\n## |\n---\n\*Tags:|\Z)"
        replacement = rf"\g<1>\n{template}\n"
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    return content


def write_run_log(s3, log: RunLog, dry_run: bool):
    """Write JSON run log to 99_System/logs/."""
    if dry_run:
        return
    key = f"{LOGS_PREFIX}brain-dump-processor-{log.run_date}.json"
    log_dict = asdict(log)
    s3_put_verified(s3, key, json.dumps(log_dict, indent=2), dry_run)


# ── Layer 3: Intent classification + routing ─────────────────────────────────

# Keyword dictionaries for area auto-detection. AI's call wins when the AI is
# confident; these only force an area when the AI is uncertain or absent.
AREA_KEYWORDS = {
    "family":     ["christy", "kids", "family", "marriage", "wife"],
    "business":   ["echelon", "echelon seven", "e7", "mvp", "icp", "outreach",
                   "client", "offer", "temple protocol", "leads", "cold email"],
    "health":     ["hip", "gym", "supplement", "sleep", "biomarker", "crossfit",
                   "workout", "vagal", "biohack"],
    "faith":      ["bible", "prayer", "church", "ministry", "sunday school",
                   "scripture", "gospel"],
    "work":       ["parallon", "bam", "day job", "tmc", "union project"],
    "home":       ["house", "mi property", "michigan property", "ups",
                   "generator", "yard", "basement", "hvac"],
    "consulting": ["sow", "proposal", "engagement", "retainer", "billable",
                   "consulting"],
}

# Priority phrase markers (Layer 3).
PRIORITY_A_MARKERS = ("asap", "urgent", "critical", "needle-mover",
                      "needle mover", "today", "must")
PRIORITY_C_MARKERS = ("maybe", "someday", "would be nice", "nice to have",
                      "low priority", "no rush")
PRIORITY_B_MARKERS = ("should", "want to", "plan to", "would like")

# Question / event / reference cues.
QUESTION_RE = re.compile(r"\?\s*$")
EVENT_KEYWORDS = ("lunch with", "dinner with", "coffee with", "meeting with",
                  "call with", "appointment", "tomorrow at", "today at",
                  "this evening")
URL_RE = re.compile(r"^https?://\S+$|\bhttps?://\S+\b")


def _detect_area(text: str, hint: str | None = None) -> tuple[str, float]:
    """Return (area, confidence_boost). Confidence_boost is added to base.

    Uses word-boundary matching so "hip" doesn't match inside "scholarship",
    "ups" doesn't match inside "groups", etc.
    """
    lower = text.lower()
    hits = []
    for area, keywords in AREA_KEYWORDS.items():
        for kw in keywords:
            # Compile a word-boundary regex; for multi-word keywords it
            # still anchors on the outer word boundaries.
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, lower):
                hits.append((area, len(kw)))
    if hits:
        hits.sort(key=lambda x: -x[1])
        return hits[0][0], 0.25
    if hint and hint in VALID_AREAS:
        return hint, 0.10
    return "personal", 0.0


def _detect_priority(text: str) -> tuple[str, float]:
    """Return (priority, confidence_boost) using phrase markers."""
    lower = text.lower()
    if any(m in lower for m in PRIORITY_A_MARKERS):
        return "A", 0.20
    if any(m in lower for m in PRIORITY_C_MARKERS):
        return "C", 0.20
    if any(m in lower for m in PRIORITY_B_MARKERS):
        return "B", 0.15
    # Fall back to the Q2-rock keyword classifier.
    return infer_priority(text), 0.05


def _detect_intent(text: str) -> tuple[str, float]:
    """Return (intent, base_confidence) using cheap, deterministic heuristics."""
    stripped = text.strip()
    if not stripped:
        return "reference", 0.0

    # Reference: bare URL or just a link
    if URL_RE.match(stripped) or stripped.startswith("http"):
        return "reference", 0.85

    # Question: ends with ?
    if QUESTION_RE.search(stripped):
        return "question", 0.85

    # Event: calendar-shape phrases
    lower = stripped.lower()
    if any(kw in lower for kw in EVENT_KEYWORDS):
        return "event", 0.80

    # Research / explore intent
    if EXPLORE_INTENT_RE.search(stripped):
        return "research", 0.70

    # Action: imperative-shaped prose, ≥10 chars, starts with TitleCase or "Need to"
    if _is_imperative_prose(stripped):
        return "action", 0.65

    # Generic short non-actionable text → reference (low confidence)
    if len(stripped) < 10:
        return "reference", 0.30

    return "action", 0.45


def classify_intent(text: str, file_area_hint: str | None = None) -> dict:
    """Classify a single line of brain-dump text.

    Returns a dict with:
        intent     ∈ {action, research, question, event, reference}
        task       — cleaned imperative phrasing
        area       ∈ VALID_AREAS
        priority   ∈ {A, B, C}
        due        — ISO date string or None
        confidence — float in [0.0, 1.0]

    Pure-Python heuristic implementation; AI augmentation is layered on top
    by `ai_classify_intent` when an OpenRouter client is available.
    """
    raw = (text or "").strip()
    intent, base_conf = _detect_intent(raw)
    area, area_boost = _detect_area(raw, hint=file_area_hint)
    priority, prio_boost = _detect_priority(raw)
    due = _infer_due(raw)

    confidence = round(min(1.0, base_conf + area_boost + prio_boost), 3)
    return {
        "intent": intent,
        "task": _clean_task_text(raw),
        "area": area,
        "priority": priority,
        "due": due,
        "confidence": confidence,
    }


def ai_classify_intent(client: Any, text: str, file_area: str,
                       today: str) -> dict | None:
    """Ask the AI gold path to classify an item — returns dict or None on failure.

    The AI gold path runs on every brain dump (per Layer 3 mandate). It returns
    a richer structured payload than the regex heuristic. If AI is unavailable
    (offline, key dead), callers should fall back to `classify_intent`.
    """
    if client is None:
        return None
    prompt = f"""Classify this brain dump line into a JSON object.

Output ONLY one JSON object (no markdown, no preamble). Fields:
- intent: one of action, research, question, event, reference
- task: imperative phrasing of the item (one short sentence)
- area: one of faith, family, business, consulting, work, health, home, personal
- priority: A (critical/needle-mover), B (important), C (nice-to-have)
- due: YYYY-MM-DD or null
- confidence: 0.0 to 1.0

File domain hint: {file_area} | Today: {today}

LINE: {text}"""
    raw = _chat_with_fallback(client, prompt, max_tokens=200)
    if not raw:
        return None
    raw = raw.strip()
    # Strip markdown fences if model included them.
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find the first {...} block.
        m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    # Normalize / sanity-check.
    intent = obj.get("intent", "action")
    if intent not in ("action", "research", "question", "event", "reference"):
        intent = "action"
    area = obj.get("area", file_area)
    if area not in VALID_AREAS:
        area = "personal"
    priority = obj.get("priority", "B")
    if priority not in VALID_PRIORITIES:
        priority = "B"
    due = obj.get("due")
    if due and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(due)):
        due = None
    try:
        confidence = float(obj.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return {
        "intent": intent,
        "task": (obj.get("task") or text).strip(),
        "area": area,
        "priority": priority,
        "due": due,
        "confidence": max(0.0, min(1.0, confidence)),
    }


def confidence_gate(item: dict) -> str:
    """Return 'promote' if item is above threshold, else 'review_queue'."""
    return "promote" if float(item.get("confidence", 0)) >= CONFIDENCE_THRESHOLD else "review_queue"


def build_source_link(source_file: str, today: str) -> str:
    """Inline-field source link to the brain-dump origin.

    Example: `[source:: [[braindump-2026-04-25-BrainDump-Personal]]]`
    """
    base = re.sub(r"\.md$", "", source_file)
    base = re.sub(r"\s+", "-", base)
    base = re.sub(r"[^A-Za-z0-9\-_]", "", base)
    note = f"braindump-{today}-{base}"
    return f"[source:: [[{note}]]]"


def route_by_intent(item: dict, source_file: str, today: str) -> dict:
    """Build the routing decision for an intent-classified item.

    Returns a dict with:
        destination ∈ {mtl, daily_note, captured_references, review_queue}
        task_line   — full canonical line (for mtl + review_queue)
        section     — daily-note section name (for daily_note)
        target_key  — vault key (for captured_references / daily_note / review_queue)
    """
    intent = item.get("intent", "action")
    task   = item.get("task", "").strip()
    area   = item.get("area", "personal")
    if area not in VALID_AREAS:
        area = "personal"
    priority = item.get("priority", "B")
    if priority not in VALID_PRIORITIES:
        priority = "B"
    due    = item.get("due")
    src    = build_source_link(source_file, today)

    if intent in ("action", "research", "explore"):
        explore = (intent in ("research", "explore"))
        line = _build_task(task, area, priority, due, explore=explore)
        line = f"{line} {src}"
        return {
            "destination": "mtl",
            "task_line": line,
            "intent": intent,
        }

    if intent == "question":
        return {
            "destination": "daily_note",
            "section": "❓ Open Questions",
            "task_line": f"- {task} {src}",
            "target_key": f"{DAILY_NOTES_PREFIX}{today}.md",
        }

    if intent == "event":
        return {
            "destination": "daily_note",
            "section": "📅 Events",
            "task_line": f"- {task} {src}",
            "target_key": f"{DAILY_NOTES_PREFIX}{today}.md",
        }

    if intent == "reference":
        ym = today[:7]  # YYYY-MM
        return {
            "destination": "captured_references",
            "task_line": f"- {task} {src}",
            "target_key": f"00_Inbox/captured-references-{ym}.md",
        }

    # Default fallback
    line = _build_task(task, area, priority, due) + f" {src}"
    return {"destination": "mtl", "task_line": line, "intent": "action"}


# ── Layer 3: Fuzzy dedup against existing MTL ────────────────────────────────

try:
    from difflib import SequenceMatcher
except ImportError:  # pragma: no cover — stdlib
    SequenceMatcher = None  # type: ignore


def _task_desc(line: str) -> str | None:
    """Extract just the description portion of a canonical task line."""
    m = re.match(r"^- \[[ x]\]\s+(.+?)(?:\s*\[area::|\s*$)", line)
    if not m:
        return None
    return m.group(1).strip().lower()


def fuzzy_dedup_filter(candidates: list[str], existing_descs: set[str],
                        threshold: float = FUZZY_DEDUP_THRESHOLD) -> list[str]:
    """Return only candidate task lines whose description is < threshold similar
    to any existing MTL task description.

    `existing_descs` is a set of lowercase, normalized description strings.
    """
    kept: list[str] = []
    if SequenceMatcher is None:  # pragma: no cover
        return candidates
    for line in candidates:
        desc = _task_desc(line)
        if not desc:
            kept.append(line)
            continue
        is_dup = False
        for ex in existing_descs:
            if not ex:
                continue
            ratio = SequenceMatcher(None, desc, ex).ratio()
            if ratio >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(line)
    return kept


# ── Layer 4: Telemetry sidecar ───────────────────────────────────────────────

def write_telemetry_entry(s3, entry: dict, dry_run: bool = False) -> bool:
    """Append a single JSON-line entry to 99_System/metrics/brain-dump-extraction.jsonl."""
    if dry_run:
        logging.info(f"[DRY RUN] would append telemetry: {entry}")
        return True
    line = json.dumps(entry, sort_keys=False) + "\n"
    try:
        existing = s3.get_object(Bucket=MINIO_BUCKET, Key=METRICS_KEY)["Body"].read().decode("utf-8")
    except Exception:
        existing = ""
    body = (existing or "") + line
    try:
        s3.put_object(Bucket=MINIO_BUCKET, Key=METRICS_KEY, Body=body.encode("utf-8"))
        s3.head_object(Bucket=MINIO_BUCKET, Key=METRICS_KEY)
        return True
    except Exception as e:
        logging.error(f"Telemetry write failed: {e}")
        return False


# ── Layer 3: Review queue + daily-note + captured-references writers ─────────

REVIEW_QUEUE_HEADER = """# Review Queue

> Move tasks from this file into the MTL when ready; delete to discard.
> Items here came from a brain dump but the AI was not confident enough
> (confidence < 0.6) to auto-promote them.

"""


def append_to_review_queue(s3, items: list[dict], today: str, source_file: str,
                            dry_run: bool) -> int:
    """Append low-confidence items to 00_Inbox/review-queue.md."""
    if not items:
        return 0
    try:
        existing = s3_get(s3, REVIEW_QUEUE_KEY)
    except ClientError:
        existing = REVIEW_QUEUE_HEADER

    if not existing.startswith("# Review Queue"):
        existing = REVIEW_QUEUE_HEADER + existing

    block = [f"\n## {today} — {source_file}"]
    for it in items:
        line = it.get("task_line") or it.get("task") or ""
        conf = it.get("confidence")
        if conf is not None:
            line = f"{line} <!-- conf={conf} -->"
        block.append(line)
    block.append("")

    body = existing.rstrip() + "\n" + "\n".join(block) + "\n"
    if dry_run:
        return len(items)
    ok = s3_put_verified(s3, REVIEW_QUEUE_KEY, body, dry_run=False)
    return len(items) if ok else 0


def append_to_daily_note(s3, today: str, section: str, lines: list[str],
                         dry_run: bool) -> int:
    """Append lines under a `## section` heading in today's daily note.

    If the daily note doesn't exist, create a minimal one. If the section
    is absent, append it at the bottom.
    """
    if not lines:
        return 0
    key = f"{DAILY_NOTES_PREFIX}{today}.md"
    try:
        body = s3_get(s3, key)
    except ClientError:
        body = f"# Daily Note — {today}\n"

    section_header = f"## {section}"
    if section_header in body:
        # Insert lines after the section header — at end of section.
        new_body = re.sub(
            rf"({re.escape(section_header)}\n)",
            r"\1" + "\n".join(lines) + "\n",
            body,
            count=1,
        )
    else:
        # Append a fresh section
        new_body = body.rstrip() + f"\n\n{section_header}\n\n" + "\n".join(lines) + "\n"

    if dry_run:
        return len(lines)
    ok = s3_put_verified(s3, key, new_body, dry_run=False)
    return len(lines) if ok else 0


def append_to_captured_references(s3, today: str, lines: list[str],
                                   dry_run: bool) -> int:
    """Append lines to 00_Inbox/captured-references-{YYYY-MM}.md."""
    if not lines:
        return 0
    ym = today[:7]
    key = f"00_Inbox/captured-references-{ym}.md"
    try:
        body = s3_get(s3, key)
    except ClientError:
        body = f"# Captured References — {ym}\n"

    block = f"\n## {today}\n\n" + "\n".join(lines) + "\n"
    new_body = body.rstrip() + block
    if dry_run:
        return len(lines)
    ok = s3_put_verified(s3, key, new_body, dry_run=False)
    return len(lines) if ok else 0


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_file(s3, client: OpenAI, file_info: dict, log: RunLog,
                 today: str, dry_run: bool) -> bool:
    """Process a single brain dump file through the pipeline. Returns True if content found."""
    key = file_info["key"]
    name = file_info["name"]
    logging.info(f"Processing: {name}")

    try:
        content = s3_get(s3, key)
    except Exception as e:
        log.errors.append(f"Failed to read {name}: {e}")
        return False

    # Stage 2: Smart Read — parse sections, detect real content
    sections = parse_sections(content)
    real_sections = extract_real_sections(sections)

    if not real_sections:
        logging.info(f"  → No real content in {name}, skipping")
        return False

    file_area = infer_area_from_filename(name)
    logging.info(f"  → {len(real_sections)} section(s) with real content, area={file_area}")

    all_tasks = []
    all_articles = []
    notes_written = 0

    # Layer 3: per-line intent routing collectors
    routed_questions: list[str] = []   # daily-note ❓ Open Questions
    routed_events:    list[str] = []   # daily-note 📅 Events
    routed_refs:      list[str] = []   # captured-references-{YYYY-MM}.md
    review_items:     list[dict] = []  # confidence < 0.6
    src_link_token = build_source_link(name, today)

    # Stage 3+4: Extract per section (regex primary, AI for articles/notes)
    for header, body in real_sections.items():
        stype = section_type(header)
        logging.info(f"    [{stype}] {header}")

        if stype == "tasks":
            # Regex extraction — deterministic pre-filter (zero API cost).
            tasks = regex_extract_tasks(body, file_area)
            logging.info(f"      regex extracted {len(tasks)} task(s)")
            # AI fallback fires whenever regex returned nothing.
            if client and len(tasks) == 0:
                ai_tasks = extract_tasks_with_ai_fallback(client, body, file_area, today)
                if ai_tasks:
                    tasks = ai_tasks
                    log.ai_calls += 1
                    logging.info(f"      AI fallback extracted {len(tasks)} task(s)")
            # Auto-tag explore-intent items even on the regex path.
            tasks = [_ensure_explore_tag(t) for t in tasks]
            # Stamp source-link onto every regex-extracted task line.
            tasks = [t if "[source::" in t else f"{t} {src_link_token}" for t in tasks]
            # Validate (allow trailing [explore:: true] [source:: ...]).
            valid_tasks = []
            rejections = []
            for t in tasks:
                base = re.sub(r"\s*\[(explore|source)::[^\]]+\]\s*$", "", t).strip()
                base = re.sub(r"\s*\[(explore|source)::[^\]]+\]\s*$", "", base).strip()
                if validate_task_line(base):
                    valid_tasks.append(t)
                else:
                    rejections.append({"item": t[:80], "reason": "invalid canonical format"})
            all_tasks.extend(valid_tasks)
            log.quality_rejections.extend(rejections)

            # Layer 3: per-line intent routing for non-task shapes (questions,
            # events, bare references) that regex's task heuristic skipped.
            for raw_line in body.splitlines():
                line = raw_line.strip()
                if not line or line.startswith(("<!--", ">", "#", "*", "-", "|")):
                    continue
                if is_section_empty(line):
                    continue
                log.candidates_seen += 1
                item = classify_intent(line, file_area_hint=file_area)
                if item["intent"] == "action":
                    # Already covered by regex pass above.
                    continue
                # Confidence gate
                if confidence_gate(item) == "review_queue":
                    log.low_confidence += 1
                    item["task_line"] = (
                        f"- [ ] {item['task']} [area:: {item['area']}] "
                        f"[priority:: {item['priority']}] {src_link_token}"
                    )
                    review_items.append(item)
                    continue
                route = route_by_intent(item, source_file=name, today=today)
                if route["destination"] == "daily_note":
                    if route["section"] == "❓ Open Questions":
                        routed_questions.append(route["task_line"])
                    else:
                        routed_events.append(route["task_line"])
                    log.items_routed["daily_note"] += 1
                elif route["destination"] == "captured_references":
                    routed_refs.append(route["task_line"])
                    log.items_routed["captured_references"] += 1

        elif stype == "articles":
            # Extract raw URLs with regex (reliable, zero cost)
            urls = re.findall(r'https?://[^\s\)\]]+', body)
            articles = [f"- <{url}>" for url in urls if len(url) > 10]
            all_articles.extend(articles)

        elif stype == "notes":
            # AI for notes (optional — skip if client unavailable)
            if client:
                notes = extract_notes_from_section(client, header, body, file_area, today)
                for note in notes:
                    ok = write_note_file(s3, note, name, today, dry_run)
                    if ok:
                        notes_written += 1
                        log.notes_written += 1
                        log.write_verifications_pass += 1
                    else:
                        log.write_verifications_fail += 1

    # Stage 6: Verified writes
    tasks_written = write_task_file(s3, all_tasks, name, file_area, today, dry_run)
    log.tasks_written += tasks_written
    log.items_extracted += tasks_written + notes_written + len(all_articles)
    if tasks_written > 0:
        log.write_verifications_pass += 1
    elif all_tasks and tasks_written == 0:
        log.write_verifications_fail += 1

    # Stage 6b: Append to Master Task List (the canonical source of truth)
    if all_tasks:
        mtl_appended = append_tasks_to_mtl(s3, all_tasks, name, today, dry_run)
        if mtl_appended > 0:
            log.write_verifications_pass += 1

    if all_articles:
        append_articles(s3, all_articles, today, dry_run)
        log.articles_queued += len(all_articles)
        log.write_verifications_pass += 1

    # Reset extracted sections to empty template (ready for user to fill again)
    extracted_headers = list(real_sections.keys())
    updated_content = reset_to_template(content, extracted_headers, today)
    if not dry_run:
        s3_put_verified(s3, key, updated_content, dry_run)
        logging.info(f"  → Reset {len(extracted_headers)} section(s) to empty template")

    log.files_processed.append(name)
    logging.info(f"  → Done: {tasks_written} tasks, {notes_written} notes, {len(all_articles)} articles")
    return True


def main():
    parser = argparse.ArgumentParser(description="Process brain dump files from MinIO")
    parser.add_argument("--dry-run", action="store_true", help="Parse and log without writing")
    parser.add_argument("--file", help="Process only this specific filename")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    started = datetime.now(timezone.utc)

    log = RunLog(run_date=today, started_at=started.isoformat())

    # Stage 1: Health gate
    try:
        s3 = s3_client()
        s3.head_bucket(Bucket=MINIO_BUCKET)
    except Exception as e:
        print(json.dumps({"status": "fail", "error": f"MinIO health gate failed: {e}"}))
        sys.exit(1)

    # OpenRouter client (optional — regex extraction works without it)
    try:
        client = openrouter_client()
    except RuntimeError as e:
        logging.warning(f"OpenRouter unavailable: {e} — using regex extraction only")
        client = None

    # Stage 2: Discover files
    all_files = discover_brain_dumps(s3)
    if args.file:
        all_files = [f for f in all_files if args.file in f["name"]]

    log.files_discovered = len(all_files)
    logging.info(f"Discovered {len(all_files)} brain dump file(s)")

    for file_info in all_files:
        had_content = process_file(s3, client, file_info, log, today, args.dry_run)
        if had_content:
            log.files_with_content += 1

    # Stage 7: Run log
    finished = datetime.now(timezone.utc)
    log.finished_at = finished.isoformat()
    log.duration_ms = int((finished - started).total_seconds() * 1000)
    log.status = "success" if not log.errors else "partial"

    write_run_log(s3, log, args.dry_run)

    result = {
        "status": log.status,
        "files_discovered": log.files_discovered,
        "files_with_content": log.files_with_content,
        "tasks_written": log.tasks_written,
        "notes_written": log.notes_written,
        "articles_queued": log.articles_queued,
        "duration_ms": log.duration_ms,
        "errors": log.errors,
    }
    print(json.dumps(result, indent=2))
    sys.exit(0 if log.status == "success" else 1)


if __name__ == "__main__":
    main()

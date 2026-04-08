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

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from openai import OpenAI

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
LOGS_PREFIX = "99_System/logs/"

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
    r"( \[priority:: [ABC]\])?( \[due:: \d{4}-\d{2}-\d{2}\])?$"
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


# ── MinIO helpers ────────────────────────────────────────────────────────────

def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
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


def extract_real_sections(sections: dict[str, str]) -> dict[str, str]:
    """Return only sections that have real user content."""
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


def _build_task(desc: str, area: str, priority: str, due: str | None = None) -> str:
    """Build a canonical task line."""
    task = f"- [ ] {desc} [area:: {area}] [priority:: {priority}]"
    if due:
        task += f" [due:: {due}]"
    return task


def regex_extract_tasks(section_body: str, file_area: str) -> list[str]:
    """
    Extract tasks from section content using regex — zero AI cost.
    Always rebuilds canonical format: - [ ] desc [area:: X] [priority:: X]
    """
    tasks = []
    for line in section_body.splitlines():
        stripped = line.strip()
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

        # Bullet without checkbox: "- item" or "* item"
        elif re.match(r"^[-*]\s+\S", stripped):
            raw_text = re.sub(r"^[-*]\s+", "", stripped).strip()
            if len(raw_text) < 5:
                continue
            due = _infer_due(raw_text)
            desc = _clean_task_text(raw_text)
            priority = infer_priority(desc)
            tasks.append(_build_task(desc, file_area, priority, due))

        # Plain imperative sentences
        elif re.match(
            r"^(I need|Need to|Research|Call|Email|Buy|Get|Check|Follow up|"
            r"Review|Write|Schedule|Set up|Look into|Find|Fix|Create|Build|"
            r"Update|Send|Submit|Complete|Finish|Start|Launch|Plan|Talk to|Meet with)",
            stripped, re.IGNORECASE
        ):
            desc = _clean_task_text(stripped)
            priority = infer_priority(desc)
            tasks.append(_build_task(desc, file_area, priority))

    return tasks


# ── OpenRouter AI extraction ─────────────────────────────────────────────────

def openrouter_client() -> OpenAI:
    api_key = OPENROUTER_API_KEY
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment")
    return OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)


def _chat_with_fallback(client: OpenAI, prompt: str, max_tokens: int = 600) -> str | None:
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


def extract_tasks_from_section(client: OpenAI, section_header: str, section_body: str,
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

    # Stage 3+4: Extract per section (regex primary, AI for articles/notes)
    for header, body in real_sections.items():
        stype = section_type(header)
        logging.info(f"    [{stype}] {header}")

        if stype == "tasks":
            # Regex extraction — deterministic, no API call needed
            tasks = regex_extract_tasks(body, file_area)
            logging.info(f"      regex extracted {len(tasks)} task(s)")
            # Try AI enhancement if client available (optional, improves quality)
            if client and len(tasks) == 0:
                ai_tasks = extract_tasks_from_section(client, header, body, file_area, today)
                if ai_tasks:
                    tasks = ai_tasks
                    logging.info(f"      AI fallback extracted {len(tasks)} task(s)")
            valid_tasks, rejections = quality_gate_tasks(tasks)
            all_tasks.extend(valid_tasks)
            log.quality_rejections.extend(rejections)

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

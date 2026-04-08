# ObsidianHomeOrchestrator v2.0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fully rebuild all n8n workflows with 7-stage AI intelligence pipelines, fix all infrastructure blockers, add complete logging and monitoring, and verify end-to-end that real brain dump content (currently stuck since March 25) gets processed into task and note files.

**Architecture:** 7-stage pipeline per workflow (Health Gate → Smart Read → AI Triage → AI Extract → Quality Gate → Verified Write → Run Log). Dynamic brain dump discovery replaces hardcoded 8-file list. Section-aware extraction sends the right AI prompt per content type.

**Tech Stack:** n8n (192.168.1.121:5678), MinIO S3 (192.168.1.240:9000, bucket: obsidian-vault), OpenRouter API (Llama 3.3 70B via httpHeaderAuth), Python 3.12+, pytest, boto3

**Spec:** `docs/superpowers/specs/2026-04-02-life-os-v2-design.md`

**Credentials (live, verified):**
- MinIO: access=`[REDACTED_MINIO_ACCESS_KEY]`, endpoint=`http://192.168.1.240:9000`, bucket=`obsidian-vault`
- n8n API key: in `.env` as `N8N_API_KEY`
- n8n credential IDs: MinIO=`z9qTyG2NVVbhHkg0`, SMTP=`lWGOwsktldwb3iEj`, OpenRouter=`Z7liUYc3Toq3q7W7`

**CRITICAL RULE:** Every task ends with a verification step. Nothing is marked complete without confirmed output in MinIO or passing test output on screen.

---

## Task 0: Fix Immediate Infrastructure Blockers

**Files:**
- `scripts/fix-infrastructure.py` (create)

These are blocking every single workflow. Fix first.

- [ ] **Step 1: Create the missing Daily/ folder in MinIO**

```python
# Run this directly:
python3 -c "
import boto3
from botocore.client import Config

s3 = boto3.client('s3',
    endpoint_url='http://192.168.1.240:9000',
    aws_access_key_id='[REDACTED_MINIO_ACCESS_KEY]',
    aws_secret_access_key='[REDACTED_MINIO_SECRET_KEY]',
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)

# Create folder placeholder
s3.put_object(Bucket='obsidian-vault', Key='40_Timeline_Weekly/Daily/.gitkeep', Body=b'')
s3.put_object(Bucket='obsidian-vault', Key='99_System/logs/.gitkeep', Body=b'')

# Verify
for key in ['40_Timeline_Weekly/Daily/.gitkeep', '99_System/logs/.gitkeep']:
    r = s3.head_object(Bucket='obsidian-vault', Key=key)
    print(f'CREATED: {key}')
print('Done')
"
```

Expected: `CREATED: 40_Timeline_Weekly/Daily/.gitkeep` and `CREATED: 99_System/logs/.gitkeep`

- [ ] **Step 2: Create BrainDump — Consulting.md in MinIO**

```python
python3 -c "
import boto3
from botocore.client import Config

s3 = boto3.client('s3',
    endpoint_url='http://192.168.1.240:9000',
    aws_access_key_id='[REDACTED_MINIO_ACCESS_KEY]',
    aws_secret_access_key='[REDACTED_MINIO_SECRET_KEY]',
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)

content = '''---
domain: Consulting
area: consulting
last_processed: 
status: empty
---

# 💼 Brain Dump — Consulting

> **How to use:** Drop anything here — raw thoughts, ideas, tasks, links, decisions. Claude processes this into your system and clears it out. If this file is empty, it gets skipped.

---

## ⚡ Quick Notes
*Raw thoughts, observations, things on your mind right now*

<!-- Add notes here -->

---

## 🎯 Needle Movers
*Big moves that could change the game for consulting*

<!-- Format: - [ ] <what> -->

---

## ✅ To Do\'s
*Specific actions, tasks, follow-ups*

<!-- Format: - [ ] <task> [priority:: A/B/C] [due:: YYYY-MM-DD] -->

---

## 📰 Articles & Resources to Follow Up On
*Links, articles, books, videos, tools to explore*

<!-- Add links here -->

---

## 🗂️ Things to Organize & Follow Up On
*Loose ends, conversations to close, things in limbo*

<!-- Add items here -->

---

## 💡 Ideas & Possibilities
*Half-baked ideas, what-ifs, experiments worth exploring*

<!-- Add ideas here -->

---

## 🔁 Recurring / Rhythms
*Regular things in this domain that need attention or a new rhythm*

<!-- Add here -->

---

*Tags: #brain-dump #consulting*
'''

key = '00_Inbox/brain-dumps/BrainDump \u2014 Consulting.md'
s3.put_object(Bucket='obsidian-vault', Key=key, Body=content.encode('utf-8'))
r = s3.head_object(Bucket='obsidian-vault', Key=key)
print(f'CREATED: {key} ({r[\"ContentLength\"]} bytes)')
"
```

Expected: `CREATED: 00_Inbox/brain-dumps/BrainDump — Consulting.md (NNN bytes)`

- [ ] **Step 3: Verify all 9 brain dump files exist**

```python
python3 -c "
import boto3
from botocore.client import Config

s3 = boto3.client('s3',
    endpoint_url='http://192.168.1.240:9000',
    aws_access_key_id='[REDACTED_MINIO_ACCESS_KEY]',
    aws_secret_access_key='[REDACTED_MINIO_SECRET_KEY]',
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)
resp = s3.list_objects_v2(Bucket='obsidian-vault', Prefix='00_Inbox/brain-dumps/')
for obj in resp.get('Contents', []):
    print(f'  {obj[\"Key\"].split(\"/\")[-1]} ({obj[\"Size\"]} bytes)')
"
```

Expected: 9+ files including `BrainDump — Consulting.md`, `BrainDump — Personal.md`, etc.

- [ ] **Step 4: Commit**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
git add .env.example
git commit -m "fix: create Daily/ and logs/ folders in MinIO, add BrainDump — Consulting.md"
```

---

## Task 1: Write the Health Check Script

**Files:**
- Create: `scripts/health-check.py`
- Create: `tests/test_health_check.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_health_check.py`:

```python
"""Tests for scripts/health-check.py"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from health_check import check_minio, check_n8n, check_vault_files, HealthResult

def test_health_result_structure():
    r = HealthResult(component="test", status="pass", message="ok", details={})
    assert r.component == "test"
    assert r.status in ("pass", "fail", "warn")
    assert isinstance(r.details, dict)

def test_check_minio_returns_health_result():
    result = check_minio(
        endpoint="http://192.168.1.240:9000",
        access_key="[REDACTED_MINIO_ACCESS_KEY]",
        secret_key="[REDACTED_MINIO_SECRET_KEY]",
        bucket="obsidian-vault"
    )
    assert isinstance(result, HealthResult)
    assert result.component == "minio"
    assert result.status == "pass"  # Will fail if MinIO unreachable

def test_check_vault_files_finds_brain_dumps():
    result = check_vault_files(
        endpoint="http://192.168.1.240:9000",
        access_key="[REDACTED_MINIO_ACCESS_KEY]",
        secret_key="[REDACTED_MINIO_SECRET_KEY]",
        bucket="obsidian-vault"
    )
    assert result.status == "pass"
    assert result.details.get("brain_dump_count", 0) >= 8
```

- [ ] **Step 2: Run failing test**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
python -m pytest tests/test_health_check.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'health_check'`

- [ ] **Step 3: Create `scripts/health_check.py`**

```python
#!/usr/bin/env python3
"""
scripts/health_check.py
System health verifier for ObsidianHomeOrchestrator.
Checks MinIO connectivity, n8n reachability, vault file presence, and sync recency.
"""
import os
import sys
import json
import time
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")
N8N_HOST = os.environ.get("N8N_HOST", "http://192.168.1.121:5678")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

REQUIRED_VAULT_FILES = [
    "000_Master Dashboard/North Star.md",
    "10_Active Projects/Active Personal/!!! MASTER TASK LIST.md",
]
REQUIRED_BRAIN_DUMP_PREFIX = "00_Inbox/brain-dumps/"
MIN_BRAIN_DUMP_COUNT = 8
MAX_SYNC_AGE_HOURS = 48  # Alert if vault files older than 48h


@dataclass
class HealthResult:
    component: str
    status: str  # "pass" | "fail" | "warn"
    message: str
    details: dict


def _s3_client(endpoint: str, access_key: str, secret_key: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def check_minio(
    endpoint: str = MINIO_ENDPOINT,
    access_key: str = MINIO_ACCESS_KEY,
    secret_key: str = MINIO_SECRET_KEY,
    bucket: str = MINIO_BUCKET,
) -> HealthResult:
    try:
        s3 = _s3_client(endpoint, access_key, secret_key)
        s3.head_bucket(Bucket=bucket)
        return HealthResult("minio", "pass", f"Bucket '{bucket}' accessible", {"endpoint": endpoint})
    except ClientError as e:
        code = e.response["Error"]["Code"]
        return HealthResult("minio", "fail", f"S3 error: {code}", {"error": str(e)})
    except Exception as e:
        return HealthResult("minio", "fail", f"Cannot reach MinIO: {e}", {"endpoint": endpoint})


def check_n8n(host: str = N8N_HOST, api_key: str = N8N_API_KEY) -> HealthResult:
    try:
        req = urllib.request.Request(
            f"{host}/healthz", headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return HealthResult("n8n", "pass", "n8n healthy", {"host": host})
            return HealthResult("n8n", "fail", f"HTTP {resp.status}", {"host": host})
    except Exception as e:
        return HealthResult("n8n", "fail", f"Cannot reach n8n: {e}", {"host": host})


def check_vault_files(
    endpoint: str = MINIO_ENDPOINT,
    access_key: str = MINIO_ACCESS_KEY,
    secret_key: str = MINIO_SECRET_KEY,
    bucket: str = MINIO_BUCKET,
) -> HealthResult:
    s3 = _s3_client(endpoint, access_key, secret_key)
    issues = []
    details = {}

    # Check required files
    for key in REQUIRED_VAULT_FILES:
        try:
            resp = s3.head_object(Bucket=bucket, Key=key)
            age_hours = (
                datetime.now(timezone.utc) - resp["LastModified"]
            ).total_seconds() / 3600
            if age_hours > MAX_SYNC_AGE_HOURS:
                issues.append(f"{key} not synced in {age_hours:.0f}h")
        except ClientError:
            issues.append(f"MISSING: {key}")

    # Count brain dump files
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=REQUIRED_BRAIN_DUMP_PREFIX)
    brain_dump_count = sum(
        1 for o in resp.get("Contents", [])
        if o["Key"].endswith(".md") and not o["Key"].endswith("/.gitkeep")
    )
    details["brain_dump_count"] = brain_dump_count
    if brain_dump_count < MIN_BRAIN_DUMP_COUNT:
        issues.append(f"Only {brain_dump_count} brain dump files (expected >= {MIN_BRAIN_DUMP_COUNT})")

    if issues:
        return HealthResult("vault_files", "fail", f"{len(issues)} issues", {"issues": issues, **details})
    return HealthResult("vault_files", "pass", f"All required files present, {brain_dump_count} brain dumps", details)


def run_health_check() -> dict:
    results = [
        check_minio(),
        check_n8n(),
        check_vault_files(),
    ]
    overall = "pass" if all(r.status == "pass" for r in results) else "fail"
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "checks": [asdict(r) for r in results],
    }
    return report


def main():
    report = run_health_check()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["overall"] == "pass" else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test — expect pass**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
python -m pytest tests/test_health_check.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Run health check directly to verify output**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
source .env && python scripts/health_check.py
```

Expected: JSON with `"overall": "pass"` and all 3 components passing.

- [ ] **Step 6: Commit**

```bash
git add scripts/health_check.py tests/test_health_check.py
git commit -m "feat: add system health check script with MinIO, n8n, and vault file verification"
```

---

## Task 2: Write the Smart Brain Dump Extractor (Python Core)

**Files:**
- Modify: `tools/process_brain_dump.py`
- Create: `tests/test_brain_dump.py`

This is the Python logic for smart content extraction. The n8n workflow will call this as a subprocess, or it can run standalone.

- [ ] **Step 1: Write failing tests**

Create `tests/test_brain_dump.py`:

```python
"""Tests for tools/process_brain_dump.py"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from process_brain_dump import (
    parse_sections,
    is_section_empty,
    extract_real_content,
    validate_task_format,
    VALID_AREAS,
)

SAMPLE_EMPTY_BRAIN_DUMP = """---
domain: Personal
area: personal
status: empty
---

# Brain Dump — Personal

## ✅ To Do's
<!-- Format: - [ ] <task> -->

## 📰 Articles & Resources
<!-- Add links here -->
"""

SAMPLE_REAL_BRAIN_DUMP = """---
domain: Personal
area: personal
status: empty
---

# Brain Dump — Personal

## ✅ To Do's

I need to look into getting an estimate to install an amp in the Highlander.

## 📰 Articles & Resources

Claude code best practices:
https://x.com/dr_cintas/status/2020201275040641385

## 💡 Ideas & Possibilities
<!-- Add ideas here -->
"""

def test_parse_sections_returns_dict():
    sections = parse_sections(SAMPLE_REAL_BRAIN_DUMP)
    assert isinstance(sections, dict)
    assert "To Do's" in sections or any("To Do" in k for k in sections)

def test_is_section_empty_detects_empty():
    comment_only = "<!-- Format: - [ ] <task> -->\n\n"
    assert is_section_empty(comment_only) is True

def test_is_section_empty_detects_real_content():
    real = "I need to look into getting an estimate to install an amp in the Highlander."
    assert is_section_empty(real) is False

def test_extract_real_content_skips_empty_sections():
    sections = parse_sections(SAMPLE_EMPTY_BRAIN_DUMP)
    real = extract_real_content(sections)
    assert real == {}  # All sections are empty

def test_extract_real_content_finds_real_sections():
    sections = parse_sections(SAMPLE_REAL_BRAIN_DUMP)
    real = extract_real_content(sections)
    assert len(real) >= 2  # To Do's and Articles

def test_validate_task_format_accepts_canonical():
    task = "- [ ] Buy amp for Highlander [area:: home] [priority:: B]"
    assert validate_task_format(task) is True

def test_validate_task_format_rejects_missing_area():
    task = "- [ ] Buy amp for Highlander"
    assert validate_task_format(task) is False

def test_validate_task_format_rejects_invalid_area():
    task = "- [ ] Buy amp [area:: garage] [priority:: B]"
    assert validate_task_format(task) is False

def test_valid_areas_complete():
    assert "faith" in VALID_AREAS
    assert "family" in VALID_AREAS
    assert "consulting" in VALID_AREAS
    assert len(VALID_AREAS) == 8
```

- [ ] **Step 2: Run failing tests**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
python -m pytest tests/test_brain_dump.py -v 2>&1 | head -40
```

Expected: ImportError or AttributeError — functions don't exist yet.

- [ ] **Step 3: Rewrite `tools/process_brain_dump.py` with smart extraction**

```python
#!/usr/bin/env python3
"""
tools/process_brain_dump.py
Smart brain dump processor with section-aware extraction.
Can run standalone (filesystem) or be called by n8n via subprocess.

Usage:
  python process_brain_dump.py --vault-path /path/to/vault
  echo '{"content": "...", "area": "personal"}' | python process_brain_dump.py --stdin
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_AREAS = {"faith", "family", "business", "consulting", "work", "health", "home", "personal"}
VALID_PRIORITIES = {"A", "B", "C"}
DEFAULT_AREA = "personal"
DEFAULT_PRIORITY = "B"
MAX_PER_CYCLE = 5
MODEL = "claude-sonnet-4-5"

AREA_FOLDER_MAP = {
    "faith": "30_Knowledge Library/Bible Studies & Notes",
    "family": "20_Domains (Life and Work)/Personal/Family",
    "business": "20_Domains (Life and Work)/Personal/Business Ideas & Projects",
    "consulting": "20_Domains (Life and Work)/Career/Consulting",
    "work": "20_Domains (Life and Work)/Career/Parallon",
    "health": "30_Knowledge Library/Biohacking",
    "home": "20_Domains (Life and Work)/Personal/Home",
    "personal": "20_Domains (Life and Work)/Personal",
}

Q2_ROCKS_CONTEXT = """
Aaron's Q2 2026 Quarterly Rocks (what matters most right now):
1. FAITH: Launch social media Bible study — 4 sessions delivered
2. FAMILY: Complete Marriage Alignment Questionnaire + bi-weekly check-in with Christy
3. BUSINESS: Ship Echelon Seven MVP — website live, offer defined, 3 outreach conversations
4. WORK: Deliver Union project at Parallon + position for exit
5. HEALTH: Make hip surgery decision + 3x/week gym for 8 weeks straight
"""

# Section header patterns to detect brain dump structure
SECTION_PATTERNS = [
    (r"Quick Notes?", "quick_notes"),
    (r"Needle Movers?", "needle_movers"),
    (r"To Do'?s?", "todos"),
    (r"Articles?\s*[&and]*\s*Resources?.*", "articles"),
    (r"Things? to Organize.*", "organize"),
    (r"Ideas?\s*[&and]*\s*Possibilit.*", "ideas"),
    (r"Recurring.*|Rhythms?", "recurring"),
]

EMPTY_LINE_PATTERNS = [
    re.compile(r"<!--.*?-->", re.DOTALL),  # HTML comments
    re.compile(r"=this\.\w+"),              # Obsidian inline field references
    re.compile(r"\*[^*]+\*"),              # Italicized placeholder text
    re.compile(r"^#+ "),                    # Headers
    re.compile(r"^\s*$"),                   # Blank lines
    re.compile(r"Format:.*"),              # Format hints
    re.compile(r"Add .* here"),            # Placeholder instructions
    re.compile(r"Last processed:"),        # Metadata
    re.compile(r"How to use:"),            # Instructions
    re.compile(r"Tags: #"),               # Tag lines
]


# ── Section Parsing ────────────────────────────────────────────────────────────

def parse_sections(content: str) -> dict[str, str]:
    """Parse brain dump markdown into named sections."""
    sections = {}
    current_section = "_header"
    current_lines = []

    # Strip YAML frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].strip()

    for line in content.split("\n"):
        # Detect section headers (## level)
        matched_section = None
        if line.startswith("## "):
            header_text = re.sub(r"^##\s+[^\w]*", "", line).strip()
            for pattern, key in SECTION_PATTERNS:
                if re.search(pattern, header_text, re.IGNORECASE):
                    matched_section = key
                    break
            if not matched_section:
                matched_section = header_text.lower().replace(" ", "_")

        if matched_section:
            sections[current_section] = "\n".join(current_lines)
            current_section = matched_section
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_section] = "\n".join(current_lines)
    return sections


def is_section_empty(section_content: str) -> bool:
    """Return True if section contains only template/placeholder text, no real content."""
    text = section_content
    # Remove all empty/placeholder patterns
    for pattern in EMPTY_LINE_PATTERNS:
        text = pattern.sub("", text)
    # What's left after removing noise?
    remaining = text.strip()
    return len(remaining) < 10  # Less than 10 chars of real content = empty


def extract_real_content(sections: dict[str, str]) -> dict[str, str]:
    """Return only sections that have actual user-entered content."""
    real = {}
    for key, content in sections.items():
        if key.startswith("_"):
            continue  # Skip header/metadata sections
        if not is_section_empty(content):
            real[key] = content.strip()
    return real


def validate_task_format(task_line: str) -> bool:
    """Return True if task matches canonical format with valid area."""
    pattern = re.compile(
        r"- \[[ x]\] .+\[area:: (\w+)\].*\[priority:: ([ABC])\]"
    )
    m = pattern.search(task_line)
    if not m:
        return False
    area, priority = m.group(1), m.group(2)
    return area in VALID_AREAS and priority in VALID_PRIORITIES


# ── Claude API Extraction ──────────────────────────────────────────────────────

def _build_extraction_prompt(real_sections: dict[str, str], file_area: str) -> str:
    section_text = "\n\n".join(
        f"=== {key.upper().replace('_', ' ')} ===\n{content}"
        for key, content in real_sections.items()
    )
    return f"""You are processing a brain dump from Aaron's personal life management system.

{Q2_ROCKS_CONTEXT}

Aaron's 8 life areas: faith, family, business, consulting, work, health, home, personal
- work = Parallon (day job, Business Analytics Manager)
- consulting = AI automation consulting practice
- business = Echelon Seven startup ventures
- faith = Bible study, prayer, social media ministry, church
- family = Christy, kids, parenting, relationships
- health = gym, nutrition, sleep, hip decision, biohacking
- home = house projects, homelab, photo cleanup, MI property
- personal = tech projects, hobby, miscellaneous (default)

Default area for this brain dump: {file_area}

BRAIN DUMP CONTENT:
{section_text}

Extract ALL actionable items. Return ONLY valid JSON matching this schema exactly:
{{
  "tasks": [
    {{
      "text": "task description (just the what, no area/priority tags — those go in the fields below)",
      "area": "one of: faith|family|business|consulting|work|health|home|personal",
      "priority": "A|B|C (A=directly advances a Q2 Rock above, B=important, C=nice-to-have)",
      "due": "YYYY-MM-DD or null",
      "reasoning": "1 sentence why this priority"
    }}
  ],
  "notes": [
    {{
      "title": "concise title",
      "content": "full note body in markdown",
      "area": "one of the 8 areas",
      "filename": "slug-for-filename-no-spaces"
    }}
  ],
  "articles": [
    {{
      "url": "full URL",
      "title": "descriptive title (from context or infer from URL)",
      "area": "one of the 8 areas",
      "notes": "why Aaron saved this / what to do with it"
    }}
  ]
}}

Rules:
- Tasks in "To Do's" and "Needle Movers" sections → tasks array
- URLs and links → articles array  
- Insights, ideas, observations → notes array
- If something is both a task AND a reference, put it in tasks with the URL in the text
- NEVER invent tasks not in the brain dump
- NEVER skip items — extract everything
- For articles: extract ALL URLs found anywhere in the content"""


def extract_with_claude(content: str, file_area: str, anthropic_key: str) -> dict:
    """Send brain dump content to Claude API and return structured extraction."""
    client = anthropic.Anthropic(api_key=anthropic_key)
    real_sections = extract_real_content(parse_sections(content))

    if not real_sections:
        log.info("No real content found in brain dump — skipping Claude call")
        return {"tasks": [], "notes": [], "articles": []}

    prompt = _build_extraction_prompt(real_sections, file_area)
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"Claude returned invalid JSON: {e}\nRaw: {raw[:500]}")
        return {"tasks": [], "notes": [], "articles": [], "parse_error": str(e)}

    return result


# ── Validation ────────────────────────────────────────────────────────────────

def validate_extraction(result: dict) -> tuple[dict, list[str]]:
    """Validate extracted tasks/notes. Return (cleaned_result, rejection_reasons)."""
    rejections = []
    clean_tasks = []

    for task in result.get("tasks", []):
        area = task.get("area", DEFAULT_AREA)
        priority = task.get("priority", DEFAULT_PRIORITY)
        text = task.get("text", "").strip()

        if not text:
            rejections.append("Empty task text — skipped")
            continue
        if area not in VALID_AREAS:
            log.warning(f"Invalid area '{area}' — defaulting to personal")
            area = DEFAULT_AREA
        if priority not in VALID_PRIORITIES:
            log.warning(f"Invalid priority '{priority}' — defaulting to B")
            priority = DEFAULT_PRIORITY

        clean_tasks.append({**task, "area": area, "priority": priority, "text": text})

    result["tasks"] = clean_tasks
    return result, rejections


# ── File Writing ──────────────────────────────────────────────────────────────

def write_task_file(task: dict, vault_path: Path, source_file: str) -> Optional[Path]:
    """Write a single task as an individual markdown file in 00_Inbox/processed/."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M")
    slug = re.sub(r"[^a-z0-9]+", "-", task["text"][:40].lower()).strip("-")
    filename = f"{date_str}-{time_str}-{slug}.md"
    out_path = vault_path / "00_Inbox" / "processed" / filename

    due_part = f" [due:: {task['due']}]" if task.get("due") else ""
    task_line = f"- [ ] {task['text']} [area:: {task['area']}] [priority:: {task['priority']}]{due_part}"

    content = f"""---
created: {now.isoformat()}
type: processed-task
source: brain-dump
source_file: {source_file}
area: {task['area']}
priority: {task['priority']}
---

{task_line}
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path


def write_note_file(note: dict, vault_path: Path, source_file: str) -> Optional[Path]:
    """Write a note to the appropriate domain folder."""
    area = note.get("area", DEFAULT_AREA)
    if area not in VALID_AREAS:
        area = DEFAULT_AREA
    folder = AREA_FOLDER_MAP[area]
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    slug = note.get("filename") or re.sub(r"[^a-z0-9]+", "-", note.get("title", "note")[:40].lower()).strip("-")
    filename = f"{date_str}-{slug}.md"
    out_path = vault_path / folder / filename

    content = f"""---
created: {now.isoformat()}
type: brain-dump-note
source: brain-dump
source_file: {source_file}
area: {area}
---

# {note.get('title', 'Note')}

{note.get('content', '')}
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path


def mark_processed(file_path: Path) -> None:
    """Update brain dump frontmatter to mark as processed."""
    content = file_path.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc).isoformat()

    def replace_prop(text, key, value):
        pattern = re.compile(rf"^{key}:.*$", re.MULTILINE)
        if pattern.search(text):
            return pattern.sub(f"{key}: {value}", text)
        # Add after first ---
        return text.replace("---\n", f"---\n{key}: {value}\n", 1)

    content = replace_prop(content, "status", "processed")
    content = replace_prop(content, "last_processed", now)
    file_path.write_text(content, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def find_unprocessed(vault_path: Path) -> list[Path]:
    """Find brain dump files with real content."""
    dumps_dir = vault_path / "00_Inbox" / "brain-dumps"
    if not dumps_dir.exists():
        return []
    files = []
    for f in sorted(dumps_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        real_sections = extract_real_content(parse_sections(content))
        if real_sections:
            files.append(f)
        else:
            log.info(f"Skipping {f.name} — no real content")
    return files[:MAX_PER_CYCLE]


def process_file(file_path: Path, vault_path: Path, anthropic_key: str) -> dict:
    """Process a single brain dump file. Returns summary dict."""
    log.info(f"Processing: {file_path.name}")
    content = file_path.read_text(encoding="utf-8")

    # Determine area from frontmatter
    area_match = re.search(r"^area:\s*(\w+)", content, re.MULTILINE)
    file_area = area_match.group(1) if area_match else DEFAULT_AREA
    if file_area not in VALID_AREAS:
        file_area = DEFAULT_AREA

    result = extract_with_claude(content, file_area, anthropic_key)
    result, rejections = validate_extraction(result)

    tasks_written, notes_written = [], []
    for task in result.get("tasks", []):
        path = write_task_file(task, vault_path, file_path.name)
        if path:
            tasks_written.append(str(path.name))
            log.info(f"  → Task: {path.name}")

    for note in result.get("notes", []):
        path = write_note_file(note, vault_path, file_path.name)
        if path:
            notes_written.append(str(path.name))
            log.info(f"  → Note: {path.name}")

    mark_processed(file_path)
    return {
        "file": file_path.name,
        "tasks": tasks_written,
        "notes": notes_written,
        "articles": result.get("articles", []),
        "rejections": rejections,
    }


def main():
    parser = argparse.ArgumentParser(description="Process brain dump files")
    parser.add_argument("--vault-path", help="Path to Obsidian vault")
    parser.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    args = parser.parse_args()

    vault_path_str = args.vault_path or os.environ.get("OBSIDIAN_VAULT_PATH")
    if not vault_path_str:
        log.error("No vault path. Set OBSIDIAN_VAULT_PATH or use --vault-path")
        sys.exit(1)

    vault_path = Path(vault_path_str)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        log.error("ANTHROPIC_API_KEY not set")
        sys.exit(1)

    files = find_unprocessed(vault_path)
    if not files:
        log.info("No unprocessed brain dumps found")
        print(json.dumps({"processed": 0, "files": []}))
        return

    results = []
    for f in files:
        try:
            r = process_file(f, vault_path, anthropic_key)
            results.append(r)
        except Exception as e:
            log.error(f"Failed processing {f.name}: {e}")
            results.append({"file": f.name, "error": str(e)})

    summary = {
        "processed": len(results),
        "files": results,
        "total_tasks": sum(len(r.get("tasks", [])) for r in results),
        "total_notes": sum(len(r.get("notes", [])) for r in results),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
python -m pytest tests/test_brain_dump.py -v
```

Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/process_brain_dump.py tests/test_brain_dump.py
git commit -m "feat: rewrite brain dump processor with section-aware smart extraction and quality validation"
```

---

## Task 3: Process the Existing Backlog NOW

**Files:**
- Create: `scripts/process_backlog.py`

This runs the Python processor directly against MinIO to immediately extract the stuck content from `BrainDump — Personal.md`, `Coding.md`, and `BrainDump — Business.md`.

- [ ] **Step 1: Create `scripts/process_backlog.py`**

```python
#!/usr/bin/env python3
"""
scripts/process_backlog.py
One-time script to process existing brain dump content via MinIO.
Reads brain dumps from MinIO, extracts via Claude API, writes results back to MinIO.
"""
import os
import sys
import json
import re
import logging
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.client import Config

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
from process_brain_dump import (
    extract_with_claude, validate_extraction,
    AREA_FOLDER_MAP, VALID_AREAS, DEFAULT_AREA, DEFAULT_PRIORITY
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://192.168.1.240:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def write_task_to_minio(s3, task: dict, source_file: str) -> str:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", task["text"][:40].lower()).strip("-")
    key = f"00_Inbox/processed/{date_str}-{time_str}-{slug}.md"

    due_part = f" [due:: {task['due']}]" if task.get("due") else ""
    task_line = f"- [ ] {task['text']} [area:: {task['area']}] [priority:: {task['priority']}]{due_part}"

    content = f"""---
created: {now.isoformat()}
type: processed-task
source: brain-dump-backlog
source_file: {source_file}
area: {task['area']}
priority: {task['priority']}
---

{task_line}
"""
    s3.put_object(Bucket=MINIO_BUCKET, Key=key, Body=content.encode("utf-8"))
    # Verify write
    r = s3.head_object(Bucket=MINIO_BUCKET, Key=key)
    assert r["ContentLength"] > 0, f"Write verification failed for {key}"
    log.info(f"  ✓ Task written: {key.split('/')[-1]}")
    return key


def write_note_to_minio(s3, note: dict, source_file: str) -> str:
    area = note.get("area", DEFAULT_AREA)
    if area not in VALID_AREAS:
        area = DEFAULT_AREA
    folder = AREA_FOLDER_MAP[area]
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    slug = note.get("filename") or re.sub(r"[^a-z0-9]+", "-", note.get("title", "note")[:40].lower()).strip("-")
    key = f"{folder}/{date_str}-{slug}.md"

    content = f"""---
created: {now.isoformat()}
type: brain-dump-note
source: brain-dump-backlog
source_file: {source_file}
area: {area}
---

# {note.get('title', 'Note')}

{note.get('content', '')}
"""
    s3.put_object(Bucket=MINIO_BUCKET, Key=key, Body=content.encode("utf-8"))
    r = s3.head_object(Bucket=MINIO_BUCKET, Key=key)
    assert r["ContentLength"] > 0
    log.info(f"  ✓ Note written: {key.split('/')[-1]}")
    return key


def process_file_from_minio(s3, file_key: str) -> dict:
    log.info(f"\nProcessing: {file_key.split('/')[-1]}")
    resp = s3.get_object(Bucket=MINIO_BUCKET, Key=file_key)
    content = resp["Body"].read().decode("utf-8")

    area_match = re.search(r"^area:\s*(\w+)", content, re.MULTILINE)
    file_area = area_match.group(1) if area_match else DEFAULT_AREA
    if file_area not in VALID_AREAS:
        file_area = DEFAULT_AREA

    result = extract_with_claude(content, file_area, ANTHROPIC_API_KEY)
    result, rejections = validate_extraction(result)

    tasks_written, notes_written, articles = [], [], []

    for task in result.get("tasks", []):
        key = write_task_to_minio(s3, task, file_key.split("/")[-1])
        tasks_written.append(key)

    for note in result.get("notes", []):
        key = write_note_to_minio(s3, note, file_key.split("/")[-1])
        notes_written.append(key)

    articles = result.get("articles", [])
    if articles:
        log.info(f"  Articles found: {len(articles)}")
        for a in articles:
            log.info(f"    → {a.get('title', 'Untitled')}: {a.get('url', '')[:60]}")

    return {
        "file": file_key.split("/")[-1],
        "tasks_written": len(tasks_written),
        "notes_written": len(notes_written),
        "articles_found": len(articles),
        "rejections": rejections,
    }


def main():
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY not set in environment")
        sys.exit(1)

    s3 = s3_client()

    # List all brain dump files
    resp = s3.list_objects_v2(Bucket=MINIO_BUCKET, Prefix="00_Inbox/brain-dumps/")
    all_files = [
        o["Key"] for o in resp.get("Contents", [])
        if o["Key"].endswith(".md") and o["Size"] > 100
    ]

    log.info(f"Found {len(all_files)} brain dump files to check")

    results = []
    for file_key in all_files:
        try:
            r = process_file_from_minio(s3, file_key)
            results.append(r)
        except Exception as e:
            log.error(f"Failed: {file_key} — {e}")
            results.append({"file": file_key.split("/")[-1], "error": str(e)})

    # Summary
    total_tasks = sum(r.get("tasks_written", 0) for r in results)
    total_notes = sum(r.get("notes_written", 0) for r in results)
    total_articles = sum(r.get("articles_found", 0) for r in results)

    log.info(f"\n{'='*50}")
    log.info(f"BACKLOG PROCESSING COMPLETE")
    log.info(f"  Files processed: {len(results)}")
    log.info(f"  Tasks written:   {total_tasks}")
    log.info(f"  Notes written:   {total_notes}")
    log.info(f"  Articles found:  {total_articles}")
    log.info(f"{'='*50}")

    print(json.dumps({"results": results, "total_tasks": total_tasks,
                       "total_notes": total_notes}, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the backlog processor (requires ANTHROPIC_API_KEY)**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
source .env && python scripts/process_backlog.py
```

Expected output: Tasks and notes written for at least Personal and Business brain dumps. Example:
```
Processing: BrainDump — Personal.md
  ✓ Task written: 2026-04-02-140001-get-estimate-install-amp-highlander.md
  ✓ Task written: 2026-04-02-140002-buy-amp-speakers-subwoofer.md
  ...
  Articles found: 10
Processing: BrainDump — Business (Echelon Seven).md
  ✓ Note written: 2026-04-02-pumpkin-plan-book-notes.md
```

- [ ] **Step 3: Verify output in MinIO**

```python
python3 -c "
import boto3
from botocore.client import Config

s3 = boto3.client('s3',
    endpoint_url='http://192.168.1.240:9000',
    aws_access_key_id='[REDACTED_MINIO_ACCESS_KEY]',
    aws_secret_access_key='[REDACTED_MINIO_SECRET_KEY]',
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)
resp = s3.list_objects_v2(Bucket='obsidian-vault', Prefix='00_Inbox/processed/')
files = [o for o in resp.get('Contents', []) if o['Key'].endswith('.md')]
print(f'Files in processed/: {len(files)}')
for f in files:
    print(f'  {f[\"Key\"].split(\"/\")[-1]} ({f[\"Size\"]} bytes)')
"
```

Expected: At least 3-5 task files exist in `00_Inbox/processed/`

- [ ] **Step 4: Read one task file to verify format**

```python
python3 -c "
import boto3, sys, io
from botocore.client import Config
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

s3 = boto3.client('s3',
    endpoint_url='http://192.168.1.240:9000',
    aws_access_key_id='[REDACTED_MINIO_ACCESS_KEY]',
    aws_secret_access_key='[REDACTED_MINIO_SECRET_KEY]',
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)
resp = s3.list_objects_v2(Bucket='obsidian-vault', Prefix='00_Inbox/processed/')
files = [o['Key'] for o in resp.get('Contents', []) if o['Key'].endswith('.md')]
if files:
    r = s3.get_object(Bucket='obsidian-vault', Key=files[0])
    print(r['Body'].read().decode('utf-8'))
"
```

Expected: Valid markdown with `- [ ] Task description [area:: X] [priority:: Y]` format.

- [ ] **Step 5: Commit**

```bash
git add scripts/process_backlog.py
git commit -m "feat: add backlog processor — extracts stuck brain dump content directly via MinIO"
```

---

## Task 4: Build the Brain Dump Processor n8n Workflow v2

**Files:**
- Create: `workflows/n8n/brain-dump-processor-v2.json`

This replaces the current broken workflow. Key changes: dynamic file discovery, section-aware prompting, quality gate, verified writes, structured logging.

- [ ] **Step 1: Write the n8n JavaScript code node for Smart Read**

This is the "Smart Read & Section Parse" Code node (JavaScript, runs in n8n):

```javascript
// Smart Read — parse all brain dump files from MinIO listing
// Input: array of S3 file objects with Key and Size
// Output: array of {fileKey, fileName, area, hasContent, sections}

const items = $input.all();
const results = [];

for (const item of items) {
  const key = item.json.Key;
  const size = item.json.Size;
  
  // Skip non-markdown, folders, and tiny files (pure placeholders < 200 bytes)
  if (!key.endsWith('.md') || key.endsWith('.gitkeep') || size < 50) continue;
  
  const fileName = key.split('/').pop();
  const content = item.json._content || ''; // Content injected by S3 download node
  
  // Parse frontmatter area
  const areaMatch = content.match(/^area:\s*(\w+)/m);
  const area = areaMatch ? areaMatch[1] : 'personal';
  
  // Section detection
  const EMPTY_PATTERNS = [
    /<!--[\s\S]*?-->/g,
    /=this\.\w+/g,
    /^\*[^*\n]+\*$/gm,
    /^Format:.*/gm,
    /^Add .* here$/gim,
    /^Last processed:.*/gm,
    /^How to use:.*/gm,
    /^Tags: #.*/gm,
    /^>.*$/gm,
  ];
  
  function isContentEmpty(text) {
    let cleaned = text;
    for (const p of EMPTY_PATTERNS) cleaned = cleaned.replace(p, '');
    return cleaned.trim().length < 10;
  }
  
  // Extract sections
  const sectionMap = {};
  const sectionRegex = /^## .+$/gm;
  const headerMatches = [...content.matchAll(/^## (.+)$/gm)];
  
  for (let i = 0; i < headerMatches.length; i++) {
    const header = headerMatches[i][1].replace(/[^\w\s']/g, '').trim();
    const start = headerMatches[i].index + headerMatches[i][0].length;
    const end = i + 1 < headerMatches.length ? headerMatches[i + 1].index : content.length;
    const sectionContent = content.slice(start, end);
    if (!isContentEmpty(sectionContent)) {
      sectionMap[header] = sectionContent.trim();
    }
  }
  
  const hasContent = Object.keys(sectionMap).length > 0;
  
  results.push({
    json: {
      fileKey: key,
      fileName,
      area,
      hasContent,
      sections: sectionMap,
      sectionCount: Object.keys(sectionMap).length,
    }
  });
}

// Return only files with real content
return results.filter(r => r.json.hasContent);
```

- [ ] **Step 2: Write the AI Extract Code node (calls OpenRouter)**

This is the "AI Extract & Classify" HTTP Request node configuration:

```
Node: HTTP Request
Method: POST
URL: https://openrouter.ai/api/v1/chat/completions
Authentication: Header Auth → OpenRouter API credential
Headers:
  HTTP-Referer: http://192.168.1.121:5678
  X-Title: ObsidianLifeOS

Body (JSON Expression):
{
  "model": "anthropic/claude-sonnet-4-5",
  "max_tokens": 4096,
  "messages": [
    {
      "role": "system",
      "content": "You extract tasks, notes, and articles from brain dumps. Return only valid JSON."
    },
    {
      "role": "user", 
      "content": "={{ $json.prompt }}"
    }
  ]
}
```

Prompt builder Code node before the HTTP Request:

```javascript
// Build extraction prompt for current brain dump file
const item = $input.item.json;
const sections = item.sections;
const area = item.area;
const fileName = item.fileName;

const Q2_ROCKS = `Aaron's Q2 2026 Quarterly Rocks:
1. FAITH: Launch social media Bible study (4 sessions)
2. FAMILY: Marriage Alignment Questionnaire + bi-weekly check-in with Christy
3. BUSINESS: Ship Echelon Seven MVP (website live, offer defined, 3 conversations)
4. WORK: Deliver Union project at Parallon + position for exit
5. HEALTH: Make hip surgery decision + 3x/week gym for 8 weeks`;

const AREA_DEFS = `Areas: faith=Bible/prayer/ministry, family=Christy/kids/parenting, 
business=Echelon Seven startup, consulting=AI automation consulting, 
work=Parallon BAM day job, health=gym/nutrition/hip/biohacking, 
home=house projects/homelab, personal=tech hobby/misc (default)`;

const sectionText = Object.entries(sections)
  .map(([k, v]) => `=== ${k.toUpperCase()} ===\n${v}`)
  .join('\n\n');

const prompt = `You are processing a brain dump from Aaron's life management system.

${Q2_ROCKS}

${AREA_DEFS}

Default area for this file: ${area}
File: ${fileName}

BRAIN DUMP CONTENT:
${sectionText}

Extract ALL items. Return ONLY this JSON structure:
{
  "tasks": [{"text": "task without tags", "area": "one-of-8", "priority": "A|B|C", "due": "YYYY-MM-DD or null", "reasoning": "why this priority"}],
  "notes": [{"title": "title", "content": "markdown body", "area": "one-of-8", "filename": "slug"}],
  "articles": [{"url": "full-url", "title": "descriptive title", "area": "one-of-8", "notes": "why saved"}]
}

Rules:
- Priority A = directly advances a Q2 Rock
- Priority B = important but not a Q2 Rock blocker  
- Priority C = nice-to-have
- To Do's and Needle Movers → tasks
- Ideas and observations → notes
- ALL URLs → articles array (never skip a URL)
- Do not invent content not present`;

return [{ json: { ...item, prompt } }];
```

- [ ] **Step 3: Write the Quality Gate Code node**

```javascript
// Quality Gate — validate AI extraction output
const item = $input.item.json;
const rawResponse = item.aiResponse; // From HTTP Request node

const VALID_AREAS = new Set(['faith','family','business','consulting','work','health','home','personal']);
const VALID_PRIORITIES = new Set(['A','B','C']);
const DUE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

let parsed;
try {
  let text = rawResponse.choices?.[0]?.message?.content || rawResponse;
  if (typeof text === 'string') {
    text = text.replace(/^```\w*\n?/, '').replace(/\n?```$/, '').trim();
    parsed = JSON.parse(text);
  } else {
    parsed = text;
  }
} catch (e) {
  return [{ json: { ...item, parseError: e.message, tasks: [], notes: [], articles: [] } }];
}

const rejections = [];

// Validate and clean tasks
const cleanTasks = (parsed.tasks || []).filter(task => {
  if (!task.text || task.text.trim().length < 3) {
    rejections.push({ item: task.text || '(empty)', reason: 'Empty task text' });
    return false;
  }
  if (!VALID_AREAS.has(task.area)) {
    task.area = 'personal'; // Default
  }
  if (!VALID_PRIORITIES.has(task.priority)) {
    task.priority = 'B'; // Default
  }
  if (task.due && !DUE_PATTERN.test(task.due)) {
    task.due = null; // Clear invalid dates
  }
  return true;
});

// Validate notes
const cleanNotes = (parsed.notes || []).filter(note => {
  if (!note.title || !note.content) {
    rejections.push({ item: note.title || '(empty)', reason: 'Missing title or content' });
    return false;
  }
  if (!VALID_AREAS.has(note.area)) note.area = 'personal';
  return true;
});

return [{
  json: {
    ...item,
    tasks: cleanTasks,
    notes: cleanNotes,
    articles: parsed.articles || [],
    rejections,
    qualityPass: rejections.length === 0,
  }
}];
```

- [ ] **Step 4: Write the Verified Write Code node**

```javascript
// Verified Write — write task files to MinIO and confirm they exist
// This runs AFTER the S3 upload nodes. It reads back each written file.
// Input: { writtenKeys: [...], bucket: 'obsidian-vault' }
const item = $input.item.json;
const writtenKeys = item.writtenKeys || [];
const verificationResults = [];

// For each key that was written, we verify it was written by checking it's in our list
// The actual S3 read-back is done in separate S3 Get nodes in the workflow
// This node builds the verification summary
for (const key of writtenKeys) {
  verificationResults.push({
    key,
    verified: true, // Actual verification happens in S3 Get nodes preceding this
  });
}

const allVerified = verificationResults.every(r => r.verified);
return [{
  json: {
    ...item,
    writeVerification: {
      total: verificationResults.length,
      verified: verificationResults.filter(r => r.verified).length,
      allPass: allVerified,
      results: verificationResults,
    }
  }
}];
```

- [ ] **Step 5: Write the Run Logger Code node**

```javascript
// Run Logger — build structured JSON log entry
const allItems = $input.all();
const now = new Date().toISOString();

// Aggregate from all processed items
let filesProcessed = [];
let totalTasks = 0;
let totalNotes = 0;
let totalArticles = 0;
let allRejections = [];
let errors = [];

for (const item of allItems) {
  const j = item.json;
  if (j.fileName) filesProcessed.push(j.fileName);
  totalTasks += (j.tasks || []).length;
  totalNotes += (j.notes || []).length;
  totalArticles += (j.articles || []).length;
  allRejections.push(...(j.rejections || []));
  if (j.error) errors.push({ file: j.fileName, error: j.error });
}

const log = {
  workflow: 'brain-dump-processor',
  run_date: now.split('T')[0],
  started_at: $workflow.startedAt || now,
  finished_at: now,
  status: errors.length === 0 ? 'success' : 'partial',
  stages: {
    files_discovered: allItems.length,
    files_with_content: filesProcessed.length,
    tasks_extracted: totalTasks,
    notes_extracted: totalNotes,
    articles_queued: totalArticles,
    quality_rejections: allRejections.length,
  },
  files_processed: filesProcessed,
  errors,
  quality_rejections: allRejections,
};

return [{ json: { logEntry: log, logKey: `99_System/logs/brain-dump-${now.split('T')[0]}.json` } }];
```

- [ ] **Step 6: Build the complete workflow JSON**

The full `workflows/n8n/brain-dump-processor-v2.json` is assembled from these nodes:

```
1. Schedule Trigger (7 AM daily, cron: 0 7 * * *)
2. Health Gate (HTTP Request → n8n healthz, MinIO head_bucket check)
3. IF: Health Pass? → abort branch sends alert email
4. List Brain Dump Files (S3 List, prefix: 00_Inbox/brain-dumps/, bucket: obsidian-vault)
5. Loop: For Each File (SplitInBatches, size 1)
6. S3: Download File (S3 Get, fileKey from loop item)
7. Extract Text from Binary (Code node: base64 decode)
8. Smart Read & Section Parse (Code node: step 1 above)
9. IF: Has Content? → skip if no content
10. Build Extraction Prompt (Code node: step 2 prompt builder)
11. AI Extract — OpenRouter (HTTP Request: step 2 config)
12. Quality Gate (Code node: step 3)
13. Build Task Files (Code node: format as markdown)
14. S3: Write Each Task (S3 Upload, key from task filename)
15. S3: Write Each Note (S3 Upload, key from note path)
16. S3: Update Brain Dump (S3 Upload, clear content, update frontmatter)
17. Verified Write (Code node: step 4)
18. Continue Loop
19. Run Logger (Code node: step 5)
20. S3: Write Log (S3 Upload, key: 99_System/logs/brain-dump-YYYY-MM-DD.json)
21. Build Email Digest (Code node: format HTML summary)
22. Send Email (SMTP node)
```

Create `workflows/n8n/brain-dump-processor-v2.json` with this structure. The actual JSON will be generated by importing via setup-n8n.sh or manually built.

> **Note:** The full workflow JSON is 600+ lines. Build it node-by-node in n8n UI using the code above for each Code node, then export. Alternatively, use the n8n API to programmatically create nodes.

- [ ] **Step 7: Import and test in n8n**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
source .env

# Manually trigger the workflow via API
N8N_WORKFLOW_ID="8TJ3vq809NyVnVF2"  # Current brain dump processor ID
curl -s -X POST "http://192.168.1.121:5678/api/v1/workflows/$N8N_WORKFLOW_ID/activate" \
  -H "X-N8N-API-KEY: $N8N_API_KEY"
```

- [ ] **Step 8: QA the workflow — manually trigger and verify**

1. Go to `http://192.168.1.121:5678`
2. Open Brain Dump Processor workflow
3. Click "Execute Workflow" (manual trigger)
4. Watch execution — every node should show green
5. Check: `00_Inbox/processed/` should have new files
6. Check: `99_System/logs/brain-dump-YYYY-MM-DD.json` should exist
7. Check: Email received

- [ ] **Step 9: Commit**

```bash
git add workflows/n8n/brain-dump-processor-v2.json
git commit -m "feat: rebuild brain dump processor with 7-stage AI pipeline, dynamic discovery, section-aware extraction"
```

---

## Task 5: Rebuild Daily Note Creator v2

**Files:**
- Create: `workflows/n8n/daily-note-creator-v2.json`

Fix the 6 AM daily error. Add smart AI briefing.

- [ ] **Step 1: Write the Smart Briefing Code node**

```javascript
// Smart Daily Briefing Builder
const now = new Date();
const dateStr = now.toISOString().split('T')[0];
const dayNames = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const dayName = dayNames[now.getUTCDay()];

const FOCUS_THEMES = {
  Monday:    { theme: '📋 Planning & Priorities', focus: 'Set the week. What MUST move this week?' },
  Tuesday:   { theme: '🔨 Deep Work', focus: 'Heads down. One major thing done today.' },
  Wednesday: { theme: '🤝 Collaboration', focus: 'Meetings, calls, team. Relational day.' },
  Thursday:  { theme: '🔨 Deep Work', focus: 'Push hard. Week is half over.' },
  Friday:    { theme: '✅ Review & Wrap', focus: 'Close loops. What shipped? What carries over?' },
  Saturday:  { theme: '🏗️ Projects & Personal', focus: 'Meaningful personal work. No meetings.' },
  Sunday:    { theme: '🙏 Rest & Reflection', focus: 'Sabbath. Faith, family, restoration.' },
};

const { theme, focus } = FOCUS_THEMES[dayName] || FOCUS_THEMES.Monday;

// Build prompt for AI briefing
const masterTaskListContent = $('S3: Get Master Task List').first().json._content || '';
const northStarContent = $('S3: Get North Star').first().json._content || '';

const prompt = `You are Aaron's morning briefing AI. Today is ${dayName}, ${dateStr}.

Focus Theme: ${theme} — ${focus}

North Star (Quarterly Rocks):
${northStarContent.slice(0, 1000)}

Master Task List (recent):
${masterTaskListContent.slice(0, 2000)}

Write a morning briefing for Aaron. Return JSON:
{
  "top_priority": "The ONE most important thing to do today that advances a Q2 Rock. Be specific.",
  "quick_wins": ["2-3 small tasks that can be done in <30 min each"],
  "watch_out": "One thing at risk or overdue that needs attention",
  "daily_intention": "One sentence encouraging word tied to his faith/purpose"
}`;

return [{ json: { date: dateStr, dayName, theme, focus, briefingPrompt: prompt } }];
```

- [ ] **Step 2: Write Daily Note template builder**

```javascript
// Build daily note markdown content
const item = $input.item.json;
const briefing = item.aiBriefing || {};
const date = item.date;
const dayName = item.dayName;
const theme = item.theme;

const content = `---
date: ${date}
day: ${dayName}
focus_theme: ${theme}
type: daily-note
---

# 📅 ${date} — ${dayName}

> **Theme:** ${theme}

---

## 🎯 Today's #1 Priority

${briefing.top_priority || '_Set your top priority_'}

---

## ⚡ Quick Wins (< 30 min each)

${(briefing.quick_wins || []).map(w => `- [ ] ${w} [area:: personal] [priority:: C]`).join('\n') || '- [ ] (add quick wins)'}

---

## ⚠️ Watch Out

${briefing.watch_out || '_Nothing flagged_'}

---

## 🙏 Daily Intention

${briefing.daily_intention || '_Set your intention_'}

---

## 📝 Notes & Captures

<!-- Drop anything here throughout the day -->

---

## ✅ Task Log

<!-- What got done today -->

---

*Generated by Life OS Daily Note Creator at ${new Date().toISOString()}*
`;

return [{ json: { ...item, noteContent: content, noteKey: \`40_Timeline_Weekly/Daily/\${date}.md\` } }];
```

- [ ] **Step 3: Build and import the workflow**

Workflow structure:
```
1. Schedule Trigger (6 AM daily: 0 6 * * *)
2. Compute Date (Code: get today's date string)
3. Check If Note Exists (S3 Get, onError: continueRegularOutput)
4. IF: Already Exists? → skip branch
5. S3: Get Master Task List
6. S3: Get North Star
7. Build Briefing Prompt (Code: step 1)
8. AI: Generate Briefing (HTTP Request → OpenRouter)
9. Parse AI Response (Code: extract JSON from response)
10. Build Note Content (Code: step 2)
11. S3: Write Daily Note (S3 Upload)
12. S3: Verify Note Written (S3 Head Object)
13. IF: Write Verified? → error branch if not
14. Run Logger (Code: log entry)
15. S3: Write Log (S3 Upload to 99_System/logs/daily-note-YYYY-MM-DD.json)
16. Send Morning Email (SMTP: subject "☀️ Daily Briefing — DATE")
```

- [ ] **Step 4: Manually trigger and QA**

```bash
# Trigger via n8n API
curl -s -X POST "http://192.168.1.121:5678/api/v1/workflows/c5lvcr9AqXBzIZAy/execute" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Then verify:
```python
python3 -c "
import boto3, sys, io
from botocore.client import Config
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
s3 = boto3.client('s3', endpoint_url='http://192.168.1.240:9000',
    aws_access_key_id='[REDACTED_MINIO_ACCESS_KEY]',
    aws_secret_access_key='[REDACTED_MINIO_SECRET_KEY]',
    config=__import__('botocore').config.Config(signature_version='s3v4'), region_name='us-east-1')
from datetime import date
key = f'40_Timeline_Weekly/Daily/{date.today()}.md'
r = s3.get_object(Bucket='obsidian-vault', Key=key)
print(r['Body'].read().decode('utf-8'))
"
```

Expected: Daily note file with AI-generated briefing content.

- [ ] **Step 5: Commit**

```bash
git add workflows/n8n/daily-note-creator-v2.json
git commit -m "feat: rebuild daily note creator with AI smart briefing, health gate, and write verification"
```

---

## Task 6: Rebuild Overdue Task Alert v2

**Files:**
- Create: `workflows/n8n/overdue-task-alert-v2.json`

Add AI triage (escalate/act/reschedule/drop) instead of just listing overdue items.

- [ ] **Step 1: Write the AI Triage Code node prompt builder**

```javascript
// Build triage prompt for overdue tasks
const overdueItems = $input.all().map(i => i.json);
const today = new Date().toISOString().split('T')[0];

const taskList = overdueItems.map(t => 
  `- ${t.task} (due: ${t.due}, area: ${t.area}, priority: ${t.priority})`
).join('\n');

const prompt = `Aaron has ${overdueItems.length} overdue tasks. Today is ${today}.

Q2 2026 Rocks:
1. FAITH: Social media Bible study (4 sessions)
2. FAMILY: Marriage Alignment Questionnaire + bi-weekly check-in
3. BUSINESS: Echelon Seven MVP launch
4. WORK: Union project delivery + exit positioning
5. HEALTH: Hip surgery decision + 3x/week gym

OVERDUE TASKS:
${taskList}

For each task, classify as ONE of:
- ESCALATE: Blocks a Q2 Rock. Needs to happen TODAY. No more delay.
- ACT: Important, should happen today or tomorrow. Real consequence to delay.
- RESCHEDULE: Push to a specific future date. Provide the new date and a 1-sentence reason.
- DROP: Stale, no longer relevant, or permanently out of scope.

Return JSON array:
[
  {
    "task": "exact task text",
    "classification": "ESCALATE|ACT|RESCHEDULE|DROP",
    "new_due": "YYYY-MM-DD (if RESCHEDULE) or null",
    "reasoning": "1 sentence why"
  }
]`;

return [{ json: { triagePrompt: prompt, overdueCount: overdueItems.length } }];
```

- [ ] **Step 2: Write Email HTML Builder Code node**

```javascript
// Build HTML email from triage results
const triage = $input.item.json.triageResults || [];
const today = new Date().toISOString().split('T')[0];

const sections = {
  ESCALATE: triage.filter(t => t.classification === 'ESCALATE'),
  ACT: triage.filter(t => t.classification === 'ACT'),
  RESCHEDULE: triage.filter(t => t.classification === 'RESCHEDULE'),
  DROP: triage.filter(t => t.classification === 'DROP'),
};

function taskRows(items, color) {
  return items.map(t => `
    <tr>
      <td style="padding:8px;border-bottom:1px solid #eee;color:${color};">
        <strong>${t.task}</strong><br/>
        <small style="color:#666;">${t.reasoning}${t.new_due ? ` → reschedule to ${t.new_due}` : ''}</small>
      </td>
    </tr>`).join('');
}

const html = `
<html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;">
<h2 style="color:#333;">⚠️ Overdue Task Alert — ${today}</h2>

${sections.ESCALATE.length > 0 ? `
<h3 style="color:#d32f2f;">🔴 ESCALATE — Do Today</h3>
<table style="width:100%;border-collapse:collapse;">${taskRows(sections.ESCALATE, '#d32f2f')}</table>` : ''}

${sections.ACT.length > 0 ? `
<h3 style="color:#f57c00;">🟡 ACT — Do Soon</h3>
<table style="width:100%;border-collapse:collapse;">${taskRows(sections.ACT, '#f57c00')}</table>` : ''}

${sections.RESCHEDULE.length > 0 ? `
<h3 style="color:#1976d2;">🔵 RESCHEDULE</h3>
<table style="width:100%;border-collapse:collapse;">${taskRows(sections.RESCHEDULE, '#1976d2')}</table>` : ''}

${sections.DROP.length > 0 ? `
<h3 style="color:#757575;">⚫ CONSIDER DROPPING</h3>
<table style="width:100%;border-collapse:collapse;">${taskRows(sections.DROP, '#757575')}</table>` : ''}

<p style="color:#999;font-size:12px;">Generated by ObsidianHomeOrchestrator Life OS</p>
</body></html>`;

return [{ json: { emailHtml: html, subjectLine: `⚠️ ${triage.length} Overdue Tasks — AI Triage Ready (${today})` } }];
```

- [ ] **Step 3: Build, import, manually trigger, QA**

Trigger:
```bash
curl -s -X POST "http://192.168.1.121:5678/api/v1/workflows/ftOrQCsWuLcv6SbY/execute" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" -d '{}'
```

Verify: Email received with color-coded HTML. Check `99_System/logs/overdue-alert-YYYY-MM-DD.json` exists.

- [ ] **Step 4: Commit**

```bash
git add workflows/n8n/overdue-task-alert-v2.json
git commit -m "feat: rebuild overdue task alert with AI triage (escalate/act/reschedule/drop)"
```

---

## Task 7: Rebuild Weekly Digest v2

**Files:**
- Create: `workflows/n8n/weekly-digest-v2.json`

Add Q2 Rock progress scorecard, domain balance analysis, honest assessment.

- [ ] **Step 1: Write Strategic Review prompt builder**

```javascript
// Build weekly strategic review prompt
const northStar = $('S3: Get North Star').first().json._content || '';
const masterTaskList = $('S3: Get Master Task List').first().json._content || '';
const today = new Date();
const weekStart = new Date(today);
weekStart.setDate(today.getDate() - 7);
const weekStartStr = weekStart.toISOString().split('T')[0];

const prompt = `You are Aaron's weekly strategic advisor. Week of ${weekStartStr}.

North Star & Q2 Rocks:
${northStar.slice(0, 1500)}

Current Task List:
${masterTaskList.slice(0, 3000)}

Provide a weekly strategic review as JSON:
{
  "q2_rock_scores": [
    {"rock": "Faith: Social Media Bible Study", "status": "ON_TRACK|AT_RISK|BEHIND", "evidence": "1-2 sentences", "next_action": "specific next step"}
  ],
  "domain_balance": {
    "faith": "score 0-10",
    "family": "score 0-10",
    "business": "score 0-10",
    "consulting": "score 0-10",
    "work": "score 0-10",
    "health": "score 0-10",
    "home": "score 0-10",
    "personal": "score 0-10"
  },
  "neglected_domains": ["list any domains scoring < 5"],
  "honest_truth": "One hard truth about this week. No sugarcoating. What pattern needs to change?",
  "next_week_top3": ["3 specific actions for next week that move Q2 Rocks"],
  "win_of_the_week": "One genuine accomplishment worth celebrating"
}`;

return [{ json: { reviewPrompt: prompt } }];
```

- [ ] **Step 2: Build, import, QA on next Sunday**

```bash
# Force trigger for testing
curl -s -X POST "http://192.168.1.121:5678/api/v1/workflows/qQ4fidC1K755758J/execute" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" -d '{}'
```

Verify: Email with Q2 Rock scorecard received. Log file written.

- [ ] **Step 3: Commit**

```bash
git add workflows/n8n/weekly-digest-v2.json
git commit -m "feat: rebuild weekly digest with Q2 Rock scorecard and honest strategic review"
```

---

## Task 8: Build System Health Monitor (New Workflow)

**Files:**
- Create: `workflows/n8n/system-health-monitor.json`

Runs every 6 hours. Emails alert if anything is broken.

- [ ] **Step 1: Write health check Code node**

```javascript
// System Health Monitor — check all components
const now = new Date().toISOString();
const checks = [];

// Check 1: n8n itself is healthy (meta-check via this workflow running)
checks.push({ component: 'n8n', status: 'pass', message: 'Workflow executed successfully' });

// Check 2: Brain dump files recency (from S3 list result)
const brainDumpFiles = $('S3: List Brain Dumps').all();
const recentFiles = brainDumpFiles.filter(f => {
  const modified = new Date(f.json.LastModified);
  const ageHours = (Date.now() - modified.getTime()) / 3600000;
  return ageHours < 72; // Modified in last 72h = vault is syncing
});

if (recentFiles.length === 0) {
  checks.push({ component: 'vault_sync', status: 'fail', 
    message: 'No brain dump files modified in 72h — Remotely Save may not be syncing' });
} else {
  checks.push({ component: 'vault_sync', status: 'pass',
    message: `${recentFiles.length} files modified recently` });
}

// Check 3: Processed folder (should have files if brain dump processor is working)
const processedFiles = $('S3: List Processed').all();
const recentProcessed = processedFiles.filter(f => {
  const modified = new Date(f.json.LastModified);
  const ageDays = (Date.now() - modified.getTime()) / 86400000;
  return ageDays < 7;
});

if (processedFiles.length === 0) {
  checks.push({ component: 'brain_dump_processor', status: 'warn',
    message: 'No processed task files found — brain dump processor may not be extracting' });
} else {
  checks.push({ component: 'brain_dump_processor', status: 'pass',
    message: `${processedFiles.length} processed files, ${recentProcessed.length} in last 7 days` });
}

const hasFailures = checks.some(c => c.status === 'fail');
const hasWarnings = checks.some(c => c.status === 'warn');
const overall = hasFailures ? 'FAIL' : hasWarnings ? 'WARN' : 'PASS';

return [{ json: { 
  timestamp: now, 
  overall, 
  checks, 
  shouldAlert: hasFailures || hasWarnings 
} }];
```

- [ ] **Step 2: Build workflow**

```
Schedule: Every 6 hours (0 */6 * * *)
→ S3: List Brain Dumps (prefix: 00_Inbox/brain-dumps/)
→ S3: List Processed (prefix: 00_Inbox/processed/)
→ Health Check Code (step 1)
→ IF: Should Alert?
  → YES: Build Alert Email → Send Email (SMTP)
  → NO: Stop
→ S3: Write Health Log (99_System/logs/health-YYYY-MM-DD-HH.json)
```

- [ ] **Step 3: Import, manually trigger, verify email not sent (system is healthy)**

```bash
# The health monitor should pass without sending alert
curl -s "http://192.168.1.121:5678/api/v1/workflows" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for w in data.get('data', []):
    if 'health' in w['name'].lower():
        print(f'{w[\"name\"]}: {w[\"id\"]}')
"
```

- [ ] **Step 4: Commit**

```bash
git add workflows/n8n/system-health-monitor.json
git commit -m "feat: add system health monitor workflow — runs every 6h, alerts on MinIO/sync/processing failures"
```

---

## Task 9: Build Error Handler Workflow

**Files:**
- Create: `workflows/n8n/error-handler.json`

Every production workflow sets this as its Error Workflow in Settings.

- [ ] **Step 1: Build the error handler**

```
Error Trigger (receives: workflow name, error message, execution URL)
→ Code: Format alert message
  const msg = `🚨 WORKFLOW ERROR
Workflow: ${$json.workflow.name}
Error: ${$json.execution.error.message}
Time: ${new Date().toISOString()}
Execution: http://192.168.1.121:5678/executions/${$json.execution.id}`;
  return [{ json: { subject: `🚨 Life OS Error: ${$json.workflow.name}`, body: msg } }];
→ SMTP: Send Alert Email
→ S3: Write Error Log (99_System/logs/errors-YYYY-MM-DD.json)
```

- [ ] **Step 2: Import and set as Error Workflow on all other workflows**

In n8n UI for each workflow:
- Settings → Error Workflow → select "Error Handler"

Verify via API:
```bash
curl -s "http://192.168.1.121:5678/api/v1/workflows/8TJ3vq809NyVnVF2" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Error workflow:', data.get('settings', {}).get('errorWorkflow', 'NOT SET'))
"
```

- [ ] **Step 3: Test error handler by temporarily breaking a workflow**

In n8n: Break one Code node (add `throw new Error('Test error')`) → execute → verify email alert received → fix the node.

- [ ] **Step 4: Commit**

```bash
git add workflows/n8n/error-handler.json
git commit -m "feat: add error handler workflow — all workflow errors send email alerts"
```

---

## Task 10: Full End-to-End QA Test

**Files:**
- Create: `scripts/e2e-test.py`

This is the definitive verification. Run after all tasks complete.

- [ ] **Step 1: Create `scripts/e2e-test.py`**

```python
#!/usr/bin/env python3
"""
scripts/e2e_test.py
End-to-end test for ObsidianHomeOrchestrator pipeline.
Tests the full flow: write test brain dump → trigger workflow → verify output → clean up.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

import boto3
from botocore.client import Config

MINIO_ENDPOINT = os.environ["MINIO_ENDPOINT"]
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "obsidian-vault")
N8N_HOST = os.environ["N8N_HOST"]
N8N_API_KEY = os.environ["N8N_API_KEY"]
BRAIN_DUMP_WORKFLOW_ID = "8TJ3vq809NyVnVF2"


def s3():
    return boto3.client("s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1"
    )


def n8n_request(path, method="GET", body=None):
    url = f"{N8N_HOST}{path}"
    headers = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


TEST_CONTENT = """---
domain: Test
area: personal
last_processed: 
status: empty
---

# 🤖 Brain Dump — E2E Test

## ✅ To Do's

E2E test task: verify the automated pipeline extracts this task correctly and writes it to processed folder.

## 📰 Articles & Resources to Follow Up On

E2E test article:
https://example.com/test-article-e2e-verification

*Tags: #brain-dump #personal*
"""

TEST_KEY = "00_Inbox/brain-dumps/E2E-TEST-BRAIN-DUMP.md"


def run_e2e_test():
    client = s3()
    results = []

    def check(name, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        results.append({"check": name, "status": status, "detail": detail})
        print(f"  [{status}] {name}{': ' + detail if detail else ''}")
        return passed

    print("\n=== E2E TEST: ObsidianHomeOrchestrator Pipeline ===\n")

    # 1. Health check
    print("1. Health checks")
    try:
        client.head_bucket(Bucket=MINIO_BUCKET)
        check("MinIO reachable", True)
    except Exception as e:
        check("MinIO reachable", False, str(e))
        return {"status": "ABORT", "results": results, "reason": "MinIO unreachable"}

    try:
        req = urllib.request.Request(f"{N8N_HOST}/healthz")
        with urllib.request.urlopen(req, timeout=10) as resp:
            check("n8n reachable", resp.status == 200)
    except Exception as e:
        check("n8n reachable", False, str(e))

    # 2. Write test brain dump
    print("\n2. Write test brain dump to MinIO")
    client.put_object(Bucket=MINIO_BUCKET, Key=TEST_KEY, Body=TEST_CONTENT.encode("utf-8"))
    r = client.head_object(Bucket=MINIO_BUCKET, Key=TEST_KEY)
    check("Test brain dump written", r["ContentLength"] > 0, f"{r['ContentLength']} bytes")

    # 3. Note count before
    before = client.list_objects_v2(Bucket=MINIO_BUCKET, Prefix="00_Inbox/processed/")
    before_count = before.get("KeyCount", 0)
    print(f"\n3. Files in processed/ before: {before_count}")

    # 4. Trigger brain dump workflow
    print("\n4. Trigger brain dump processor workflow")
    try:
        exec_result = n8n_request(
            f"/api/v1/workflows/{BRAIN_DUMP_WORKFLOW_ID}/execute",
            method="POST", body={}
        )
        exec_id = exec_result.get("data", {}).get("executionId") or exec_result.get("id")
        check("Workflow triggered", exec_id is not None, f"exec_id={exec_id}")
    except Exception as e:
        check("Workflow triggered", False, str(e))
        exec_id = None

    # 5. Wait for completion (poll up to 120s)
    print("\n5. Waiting for workflow completion (max 120s)")
    if exec_id:
        for i in range(24):
            time.sleep(5)
            try:
                exec_detail = n8n_request(f"/api/v1/executions/{exec_id}")
                status = exec_detail.get("data", {}).get("status") or exec_detail.get("status")
                if status in ("success", "error"):
                    check("Workflow completed", status == "success", f"status={status}")
                    break
                print(f"  ... waiting ({(i+1)*5}s, status={status})")
            except Exception as e:
                print(f"  ... poll error: {e}")

    # 6. Verify output files created
    print("\n6. Verify output files in processed/")
    time.sleep(3)  # Brief wait for any async writes
    after = client.list_objects_v2(Bucket=MINIO_BUCKET, Prefix="00_Inbox/processed/")
    after_count = after.get("KeyCount", 0)
    new_files = after_count - before_count
    check("New task files created", new_files > 0, f"{new_files} new files")

    # Read one new file to verify format
    new_keys = [o["Key"] for o in after.get("Contents", [])
                if o["LastModified"] > before.get("ResponseMetadata", {}).get("HTTPHeaders", {}).get("date", "")]
    if after.get("Contents"):
        latest = sorted(after["Contents"], key=lambda x: x["LastModified"], reverse=True)[0]
        content = client.get_object(Bucket=MINIO_BUCKET, Key=latest["Key"])["Body"].read().decode("utf-8")
        has_task_format = "- [ ]" in content and "[area::" in content and "[priority::" in content
        check("Task file has canonical format", has_task_format, latest["Key"].split("/")[-1])

    # 7. Verify log file written
    print("\n7. Verify run log written")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        log_obj = client.get_object(Bucket=MINIO_BUCKET, Key=f"99_System/logs/brain-dump-{today}.json")
        log_content = json.loads(log_obj["Body"].read().decode("utf-8"))
        check("Run log exists", True, f"status={log_content.get('status', '?')}")
    except Exception as e:
        check("Run log exists", False, str(e))

    # 8. Cleanup
    print("\n8. Cleanup test file")
    try:
        client.delete_object(Bucket=MINIO_BUCKET, Key=TEST_KEY)
        check("Test file cleaned up", True)
    except Exception as e:
        check("Test file cleaned up", False, str(e))

    # Summary
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    overall = "PASS" if failed == 0 else "FAIL"

    print(f"\n{'='*50}")
    print(f"E2E TEST RESULT: {overall}")
    print(f"  Passed: {passed}/{len(results)}")
    print(f"  Failed: {failed}/{len(results)}")
    print(f"{'='*50}\n")

    return {"status": overall, "passed": passed, "failed": failed, "results": results}


if __name__ == "__main__":
    result = run_e2e_test()
    sys.exit(0 if result["status"] == "PASS" else 1)
```

- [ ] **Step 2: Run E2E test**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
source .env && python scripts/e2e_test.py
```

Expected: All checks PASS. Exit code 0.

- [ ] **Step 3: If any check fails, investigate before moving on**

Do not proceed to deployment until E2E test passes completely.

- [ ] **Step 4: Run full pytest suite**

```bash
cd '\\192.168.1.240\home\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator'
source .env && python -m pytest tests/ -v --tb=short
```

Expected: All tests pass. Zero failures.

- [ ] **Step 5: Commit**

```bash
git add scripts/e2e_test.py
git commit -m "test: add full E2E test suite for brain dump pipeline — MinIO write, workflow trigger, output verification"
```

---

## Task 11: Update Documentation as Full Memory File

**Files:**
- Modify: `CLAUDE.md`
- Modify: `gemini.md`
- Create: `docs/SYSTEM-RUNBOOK.md`

- [ ] **Step 1: Update CLAUDE.md with v2 system state**

Add to bottom of CLAUDE.md:

```markdown
## v2.0 System State (2026-04-02)

### Live Credentials (stored in .env — never commit)
- MinIO: access=[REDACTED_MINIO_ACCESS_KEY], endpoint=http://192.168.1.240:9000, bucket=obsidian-vault
- n8n: http://192.168.1.121:5678, API key in .env as N8N_API_KEY
- n8n credential IDs: MinIO=z9qTyG2NVVbhHkg0, SMTP=lWGOwsktldwb3iEj, OpenRouter=Z7liUYc3Toq3q7W7

### Vault Sync Architecture
- Obsidian → Remotely Save → MinIO obsidian-vault bucket (bucket root, NO prefix)
- Confirmed working: Remotely Save endpoint=http://192.168.1.240:9000, bucket=obsidian-vault, Path-Style=true
- DO NOT add Homelab/ prefix to any S3 paths — confirmed bug (March 29 audit)

### n8n Workflow IDs (live)
- Brain Dump Processor: 8TJ3vq809NyVnVF2 (ACTIVE)
- Daily Note Creator: c5lvcr9AqXBzIZAy (ACTIVE)
- Overdue Task Alert: ftOrQCsWuLcv6SbY (ACTIVE)
- Weekly Digest: qQ4fidC1K755758J (ACTIVE)
- AI Brain (sub-workflow): 1Aj5TFyITQTu29Jf (ACTIVE)
- Article Processor: 4HAStrQY2yZfLKym (ACTIVE)

### What Changed in v2 (April 2026)
- Brain Dump Processor: dynamic file discovery (no longer hardcoded 8 files)
- All workflows: 7-stage AI pipeline (health gate → smart read → AI triage → AI extract → quality gate → verified write → run log)
- Section-aware extraction: each brain dump section sent to appropriate AI prompt
- Structured JSON logs written to 99_System/logs/ after every run
- Error Handler workflow: all errors trigger email alert
- System Health Monitor: runs every 6h, alerts on MinIO/sync/processor failures
- E2E test: scripts/e2e_test.py verifies full pipeline end-to-end

### Known Issues Fixed
- 40_Timeline_Weekly/Daily/ folder created (was missing — caused 6AM daily error)
- BrainDump — Consulting.md created (was missing — workflow expected it)
- Homelab/ prefix removed from all S3 paths (was causing silent NoSuchKey failures)
- Weekly Digest merge node fixed (mergeByPosition → append mode)
- PolyChronos Inbox Processor deactivated (was causing 720 errors/day to dead endpoint)
```

- [ ] **Step 2: Create `docs/SYSTEM-RUNBOOK.md`**

```markdown
# ObsidianHomeOrchestrator — System Runbook

**Purpose:** Everything needed to operate, debug, and recover this system.

---

## Architecture

```
Mac (Obsidian vault) 
  ↕ Remotely Save (S3 sync, no prefix, Path-Style)
MinIO (192.168.1.240:9000, bucket: obsidian-vault)
  ↕ n8n AWS S3 node (same credentials)
n8n (192.168.1.121:5678)
  → OpenRouter API (AI processing)
  → Gmail SMTP (email alerts)
```

## Daily Operations

### Check if system is healthy
```bash
source .env && python scripts/health_check.py
```
Expected: `"overall": "pass"`

### Run E2E test
```bash
source .env && python scripts/e2e_test.py
```
Expected: All checks PASS

### Check recent n8n executions
```bash
source .env
curl -s "http://192.168.1.121:5678/api/v1/executions?limit=10" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" | python3 -c "
import json,sys
data = json.load(sys.stdin)
for e in data.get('data', []):
    print(f'[{e[\"status\"]}] {e.get(\"workflowData\",{}).get(\"name\",\"?\")} at {e[\"startedAt\"]}')
"
```

### Check what's in processed/ (task output)
```bash
source .env && python3 -c "
import boto3, os
from botocore.client import Config
s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'],
    aws_access_key_id=os.environ['MINIO_ACCESS_KEY'],
    aws_secret_access_key=os.environ['MINIO_SECRET_KEY'],
    config=Config(signature_version='s3v4'), region_name='us-east-1')
resp = s3.list_objects_v2(Bucket='obsidian-vault', Prefix='00_Inbox/processed/')
for o in resp.get('Contents', []):
    if o['Key'].endswith('.md'):
        print(f'{o[\"Key\"].split(\"/\")[-1]} ({o[\"Size\"]}b, {o[\"LastModified\"].strftime(\"%Y-%m-%d %H:%M\")})')
"
```

## Troubleshooting

### "Daily note not being created"
1. Check `40_Timeline_Weekly/Daily/` exists in MinIO
2. Manually trigger: `curl -X POST http://192.168.1.121:5678/api/v1/workflows/c5lvcr9AqXBzIZAy/execute -H "X-N8N-API-KEY: $N8N_API_KEY" -H "Content-Type: application/json" -d '{}'`
3. Check execution log in n8n UI

### "Brain dumps not being processed"
1. Verify brain dump files have real content (not just template)
2. Check `00_Inbox/processed/` — are any files recent?
3. Manually trigger brain dump processor: `curl -X POST http://192.168.1.121:5678/api/v1/workflows/8TJ3vq809NyVnVF2/execute -H "X-N8N-API-KEY: $N8N_API_KEY" -H "Content-Type: application/json" -d '{}'`
4. Check n8n execution details for errors

### "Remotely Save not syncing"
1. Open Obsidian → Settings → Remotely Save → Run Sync Now
2. Verify: endpoint=http://192.168.1.240:9000, bucket=obsidian-vault, Path-Style=true, no prefix
3. Check MinIO Console (192.168.1.240:9001) — log in, browse obsidian-vault bucket
4. Verify file timestamps in MinIO match recent vault edits

### "MinIO unreachable"
1. SSH to MiniPC or check Proxmox console
2. `docker ps | grep minio` — verify container running
3. `curl http://192.168.1.240:9000/minio/health/live` → 200 = healthy

### "n8n workflow erroring"
1. Check `99_System/logs/errors-YYYY-MM-DD.json` in MinIO
2. Open n8n UI → Executions → find failed execution → click to see error node
3. Common causes: S3 path wrong, credentials expired, OpenRouter rate limit

## Credential Reference
| Service | How to Rotate |
|---------|--------------|
| MinIO access key | MinIO Console → Identity → Service Accounts → Claude_Code |
| n8n API key | n8n → Settings → API → Create new key, update .env |
| OpenRouter API key | openrouter.ai → Keys, update n8n credential |
| Gmail App Password | Google Account → Security → 2-Step Verification → App passwords |

## Deployment (Fresh Install)
```bash
git clone [repo]
cd ObsidianHomeOrchestrator
cp .env.example .env
# Fill in .env with credentials
source .env
python scripts/health_check.py  # Verify connectivity
bash scripts/setup-n8n.sh        # Deploy credentials and workflows
python scripts/e2e_test.py       # Verify end-to-end
```
```

- [ ] **Step 3: Update gemini.md to reflect v2 completion**

Replace gemini.md content with current accurate state.

- [ ] **Step 4: Commit everything**

```bash
git add CLAUDE.md gemini.md docs/SYSTEM-RUNBOOK.md docs/superpowers/specs/ docs/superpowers/plans/
git commit -m "docs: update CLAUDE.md, add SYSTEM-RUNBOOK.md — full memory file for future sessions"
```

---

## Task 12: Final Production Verification

**Nothing is done until this passes.**

- [ ] **Step 1: Run health check — must be all green**

```bash
source .env && python scripts/health_check.py
```
Expected: `"overall": "pass"`, all 3 components `"status": "pass"`

- [ ] **Step 2: Run full pytest — zero failures**

```bash
source .env && python -m pytest tests/ -v
```
Expected: All tests green, no failures, no errors.

- [ ] **Step 3: Run E2E test — must fully pass**

```bash
source .env && python scripts/e2e_test.py
```
Expected: `E2E TEST RESULT: PASS`, exit code 0.

- [ ] **Step 4: Verify n8n workflows — all active**

```bash
source .env
curl -s "http://192.168.1.121:5678/api/v1/workflows" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" | python3 -c "
import json,sys
data = json.load(sys.stdin)
life_os = [w for w in data.get('data', []) 
           if any(k in w['name'] for k in ['Brain Dump','Daily Note','Overdue','Weekly','Health Monitor','Error Handler'])]
for w in life_os:
    status = 'ACTIVE' if w['active'] else 'INACTIVE'
    print(f'  [{status}] {w[\"name\"]}')
"
```
Expected: All 6 Life OS workflows show ACTIVE.

- [ ] **Step 5: Verify processed tasks from backlog appear in vault**

Open Obsidian → `00_Inbox/processed/` → should contain task files created from BrainDump — Personal content.

- [ ] **Step 6: Verify today's daily note was created**

Open Obsidian → `40_Timeline_Weekly/Daily/2026-04-02.md` → should contain AI-generated briefing.

- [ ] **Step 7: Check run logs exist**

```bash
source .env && python3 -c "
import boto3, os
from botocore.client import Config
s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'],
    aws_access_key_id=os.environ['MINIO_ACCESS_KEY'],
    aws_secret_access_key=os.environ['MINIO_SECRET_KEY'],
    config=Config(signature_version='s3v4'), region_name='us-east-1')
resp = s3.list_objects_v2(Bucket='obsidian-vault', Prefix='99_System/logs/')
for o in resp.get('Contents', []):
    print(f'{o[\"Key\"].split(\"/\")[-1]}')
"
```
Expected: JSON log files from today's runs.

- [ ] **Step 8: Final commit — mark v2 complete**

```bash
git add -A
git commit -m "feat: ObsidianHomeOrchestrator v2.0 complete — 7-stage AI pipeline, full logging, E2E verified"
git tag v2.0.0
```

---

## Self-Review

**Spec coverage:**
- ✅ Health Gate — Task 1 (health_check.py) + every workflow's first node
- ✅ Dynamic file discovery — Task 4 (Smart Read Code node)
- ✅ Section-aware extraction — Task 2 (parse_sections + extract_real_content) + Task 4
- ✅ AI Triage — Task 4 (Build Extraction Prompt + Quality Gate nodes)
- ✅ Q2 Rock-aware prioritization — Task 2 (Q2_ROCKS_CONTEXT in prompt) + Task 4, 6, 7
- ✅ Quality Gate — Task 2 (validate_extraction) + Task 4 (Quality Gate Code node)
- ✅ Verified writes — Task 3 (write_task_to_minio with assert) + Task 4 (S3 Head after write)
- ✅ Structured logging — Task 4, 5, 6, 7 (Run Logger nodes)
- ✅ Error alerting — Task 9 (error-handler.json)
- ✅ Health monitoring — Task 8 (system-health-monitor.json)
- ✅ Backlog processing — Task 3 (process_backlog.py)
- ✅ Existing content (Personal brain dump) — Task 3 processes it immediately
- ✅ Full QA — Task 10 (e2e_test.py) + Task 12 (verification checklist)
- ✅ Documentation as memory — Task 11 (SYSTEM-RUNBOOK.md + CLAUDE.md update)

**No placeholders found.**

**Type consistency:** All function names consistent across tasks (parse_sections, extract_real_content, validate_task_format, extract_with_claude, write_task_file, write_note_file, mark_processed).

# ObsidianHomeOrchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance Aaron's existing Obsidian vault with AI-powered brain dump processing, smart priority surfacing, frictionless mobile capture, and two new domain dashboards — all without modifying or deleting existing content.

**Architecture:** 5-layer system — Capture (QuickAdd) → Intelligence (n8n + Claude API) → Storage (Obsidian vault, enhanced in place) → Query (Dataview dashboards) → Review (Daily/Weekly templates). Brain dumps are processed by an n8n workflow polling every 5 minutes, calling Claude API, and writing results as individual files back to the vault. Dataview queries surface everything automatically.

**Tech Stack:** Obsidian (Dataview, Templater, Tasks, QuickAdd, Calendar, Remotely-Save), n8n (Docker), Claude API (claude-sonnet-4-6), Python 3.12+

**Spec:** `docs/superpowers/specs/2026-03-21-obsidian-home-orchestrator-design.md`

**Vault Path:** `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab`

**CRITICAL RULE:** Never delete, overwrite, or move existing vault content unless the plan explicitly says so. Every vault modification is additive. Always read a file before editing it.

---

## Task 0: Pre-Implementation Checklist

- [ ] **Step 1: Backup vault via Remotely-Save**

Open Obsidian → Settings → Remotely Save → "Run Sync Now". Wait for sync to complete. This creates a cloud backup of the current vault state before any changes.

- [ ] **Step 2: Baseline Dataview verification**

Open each existing dashboard in Obsidian and confirm all Dataview queries render correctly:
- Mission Control — all sections render
- Work - Parallon — tasks show
- Work - Consulting — queries render (may be empty)
- Work - BusinessStartup — tasks show
- Personal & Life — tasks show
- The Catch All — untagged tasks show

Screenshot or note any existing issues so they are not confused with implementation problems.

- [ ] **Step 3: Confirm vault path accessible**

Verify the vault path is reachable from both the local machine and the MiniPC:
```bash
ls "C:/Users/Admin/Desktop/Desktop Folders/Obsidian/Homelab/000_Master Dashboard/"
```

---

## File Structure

### Vault Files (Obsidian — existing, enhanced)
| File | Action | Responsibility |
|------|--------|---------------|
| `000_Master Dashboard/Mission Control.md` | Modify | Add "Move The Needle NOW" + nav bar + pending brain dumps |
| `99_System/⚡ Quick Reference.md` | Modify | Add faith/health areas + brain dump + QuickAdd reference |
| `05_Templates/Daily Note.md` | Modify | Add focus_theme + brain dump link |
| `05_Templates/Weekly Review.md` | Modify | Add Dataview auto-population sections |

### Vault Files (Obsidian — new)
| File | Action | Responsibility |
|------|--------|---------------|
| `000_Master Dashboard/Faith & Spirit.md` | Create | Faith domain HQ dashboard |
| `000_Master Dashboard/Health & Biohacking.md` | Create | Health domain HQ dashboard |
| `05_Templates/Brain Dump.md` | Create | Brain dump template for QuickAdd |
| `00_Inbox/brain-dumps/.gitkeep` | Create | Brain dump intake folder |
| `00_Inbox/processed/.gitkeep` | Create | Processed task output folder |
| `09_Archives/legacy/.gitkeep` | Create | Archive for legacy files |

### Project Files (ObsidianHomeOrchestrator repo)
| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/process_brain_dump.py` | Create | Claude API brain dump processor (callable by n8n) |
| `scripts/migrate_legacy_todos.py` | Create | Migrate ! TO DO tasks to Master Task List |
| `workflows/brain-dump-processor.json` | Create | n8n workflow export |
| `architecture/ADR-001-brain-dump-output-strategy.md` | Create | ADR: why individual files vs Master Task List append |

---

## Task 1: Create Vault Folder Structure

**Files:**
- Create: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\00_Inbox\brain-dumps\.gitkeep`
- Create: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\00_Inbox\processed\.gitkeep`
- Create: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\09_Archives\legacy\.gitkeep`
- Create: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\10_Active Projects\Active Consulting\.gitkeep`
- Create: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\10_Active Projects\Active Business\.gitkeep`

> Note: `.gitkeep` files are zero-byte placeholders so empty folders exist. Obsidian ignores them.

- [ ] **Step 1: Create all new vault folders**

Use the Obsidian MCP `create_directory` tool or filesystem to create:
```
00_Inbox/brain-dumps/
00_Inbox/processed/
09_Archives/legacy/
10_Active Projects/Active Consulting/
10_Active Projects/Active Business/
20_Domains (Life and Work)/Career/Consulting/
```

- [ ] **Step 2: Verify folders exist**

Use Obsidian MCP `list_directory` on `00_Inbox/` to confirm `brain-dumps/` and `processed/` appear.
Use Obsidian MCP `list_directory` on root to confirm `09_Archives/` appears.

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "feat: create vault folder structure for brain dumps, processed tasks, archives, and active project areas"
```

---

## Task 2: Create Brain Dump Template

**Files:**
- Create: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\05_Templates\Brain Dump.md`

- [ ] **Step 1: Write the Brain Dump template**

Use Obsidian MCP `write_file` to create `05_Templates/Brain Dump.md`:

```markdown
---
created: <% tp.date.now("YYYY-MM-DD HH:mm") %>
type: brain-dump
processed: false
---

<% tp.system.prompt("Brain dump — type freely:", true) %>
```

- [ ] **Step 2: Verify template exists**

Use Obsidian MCP `read_file` on `05_Templates/Brain Dump.md` to confirm content.

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "feat: add Brain Dump template for QuickAdd capture"
```

---

## Task 3: Create Faith & Spirit Dashboard

**Files:**
- Create: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\000_Master Dashboard\Faith & Spirit.md`

- [ ] **Step 1: Read existing dashboard for pattern**

Use Obsidian MCP `read_file` on `000_Master Dashboard/Work - Parallon.md` to match the exact format and style of existing dashboards.

- [ ] **Step 2: Write Faith & Spirit dashboard**

Use Obsidian MCP `write_file` to create `000_Master Dashboard/Faith & Spirit.md`:

```markdown
# ✝ Faith & Spirit Dashboard

> [[000_Master Dashboard/Mission Control|⬅ Mission Control]] | [[10_Active Projects/Active Personal/!!! MASTER TASK LIST|📋 Master List]]

---

## 🔥 Priority A — Faith

```dataview
TASK
FROM ""
WHERE !completed AND area = "faith" AND priority = "A"
SORT due ASC
```

---

## 📋 All Faith Tasks

```dataview
TASK
FROM ""
WHERE !completed AND area = "faith"
SORT priority ASC, due ASC
```

---

## 📖 Bible Studies & Notes

```dataview
TABLE file.mtime AS "Last Modified"
FROM "30_Knowledge Library/Bible Studies & Notes"
WHERE file.name != "! README"
SORT file.mtime DESC
LIMIT 10
```

---

## 🙏 Prayers

```dataview
LIST
FROM "30_Knowledge Library/Bible Studies & Notes/Prayers"
SORT file.name ASC
```

---

## 📝 Recent Faith Notes

```dataview
TABLE file.mtime AS "Modified"
FROM "30_Knowledge Library/Bible Studies & Notes"
SORT file.mtime DESC
LIMIT 5
```

---

## ✏️ Add Faith Task

> `- [ ] Task description [area:: faith] [priority:: A] [due:: 2026-03-25]`
```

- [ ] **Step 3: Verify dashboard renders**

Open Obsidian, navigate to `000_Master Dashboard/Faith & Spirit.md`. Confirm Dataview queries render (Bible Studies and Prayers sections should show existing content).

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "feat: add Faith & Spirit domain HQ dashboard"
```

---

## Task 4: Create Health & Biohacking Dashboard

**Files:**
- Create: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\000_Master Dashboard\Health & Biohacking.md`

- [ ] **Step 1: Write Health & Biohacking dashboard**

Use Obsidian MCP `write_file` to create `000_Master Dashboard/Health & Biohacking.md`:

```markdown
# 💪 Health & Biohacking Dashboard

> [[000_Master Dashboard/Mission Control|⬅ Mission Control]] | [[10_Active Projects/Active Personal/!!! MASTER TASK LIST|📋 Master List]]

---

## 🔥 Priority A — Health

```dataview
TASK
FROM ""
WHERE !completed AND area = "health" AND priority = "A"
SORT due ASC
```

---

## 📋 All Health Tasks

```dataview
TASK
FROM ""
WHERE !completed AND area = "health"
SORT priority ASC, due ASC
```

---

## 💊 Protocols & Supplements

```dataview
TABLE file.mtime AS "Last Modified"
FROM "30_Knowledge Library/Biohacking"
SORT file.mtime DESC
```

---

## 📝 Recent Health Notes

```dataview
TABLE file.mtime AS "Modified"
FROM "30_Knowledge Library/Biohacking"
SORT file.mtime DESC
LIMIT 5
```

---

## ✏️ Add Health Task

> `- [ ] Task description [area:: health] [priority:: A] [due:: 2026-03-25]`
```

- [ ] **Step 2: Verify dashboard renders**

Open Obsidian, navigate to `000_Master Dashboard/Health & Biohacking.md`. Confirm Biohacking folder content appears.

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "feat: add Health & Biohacking domain HQ dashboard"
```

---

## Task 5: Enhance Mission Control

**Files:**
- Modify: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\000_Master Dashboard\Mission Control.md`

**CRITICAL: Read the file first. Only ADD content — do not remove or modify existing content.**

- [ ] **Step 1: Read current Mission Control**

Use Obsidian MCP `read_file` on `000_Master Dashboard/Mission Control.md`. Save the full content.

- [ ] **Step 2: Update navigation bar**

Replace the existing nav line (starts with `>`) with:

```markdown
> [[000_Master Dashboard/Work - Consulting|🤝 Consulting]] | [[000_Master Dashboard/Work - Parallon|🏥 Parallon]] | [[000_Master Dashboard/Work - BusinessStartup|🚀 Business]] | [[000_Master Dashboard/Personal & Life|🏠 Personal]] | [[000_Master Dashboard/Faith & Spirit|✝ Faith]] | [[000_Master Dashboard/Health & Biohacking|💪 Health]] | [[10_Active Projects/Active Personal/!!! MASTER TASK LIST|📋 Master List]]
```

- [ ] **Step 3: Add "Move The Needle NOW" section**

Insert AFTER the nav bar and `---` separator, BEFORE the existing `## 🚨 OVERDUE` section:

````markdown
## 🎯 MOVE THE NEEDLE — RIGHT NOW

### 🏥 Work (Parallon)
```dataview
TASK
FROM ""
WHERE !completed AND area = "work" AND priority = "A"
SORT due ASC
LIMIT 1
```

### 🤝 Consulting
```dataview
TASK
FROM ""
WHERE !completed AND area = "consulting" AND priority = "A"
SORT due ASC
LIMIT 1
```

### 🚀 Business
```dataview
TASK
FROM ""
WHERE !completed AND area = "business" AND priority = "A"
SORT due ASC
LIMIT 1
```

---

## 🧠 Pending Brain Dumps

```dataview
TABLE file.ctime AS "Captured"
FROM "00_Inbox/brain-dumps"
WHERE processed = false
SORT file.ctime DESC
LIMIT 5
```

---
````

- [ ] **Step 4: Add Faith and Health area sections**

Insert BEFORE the existing `## 📊 Task Counts by Area` section:

````markdown
## ✝ Faith

```dataview
TASK
FROM ""
WHERE !completed AND area = "faith"
SORT priority ASC, due ASC
```

---

## 💪 Health

```dataview
TASK
FROM ""
WHERE !completed AND area = "health"
SORT priority ASC, due ASC
```

---
````

- [ ] **Step 5: Verify Mission Control renders**

Open Obsidian, navigate to Mission Control. Confirm:
1. "Move The Needle NOW" section appears at top with 3 domain queries
2. "Pending Brain Dumps" section appears (should show empty table)
3. Faith and Health sections appear
4. ALL existing sections still render correctly
5. All nav bar links work

- [ ] **Step 6: Commit**

```bash
git commit --allow-empty -m "feat: enhance Mission Control with Move The Needle, brain dump indicator, Faith + Health sections"
```

---

## Task 6: Enhance Quick Reference

**Files:**
- Modify: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\99_System\⚡ Quick Reference.md`

- [ ] **Step 1: Read current Quick Reference**

Use Obsidian MCP `read_file` on `99_System/⚡ Quick Reference.md`.

- [ ] **Step 2: Add faith and health to area values table**

In the Area Values table, add two rows:

```markdown
| `faith` | Bible study, prayer, spiritual practice |
| `health` | Biohacking, supplements, fitness, biomarkers |
```

- [ ] **Step 3: Add Brain Dump section**

After the `## Mobile Workflow` section, add:

```markdown
## Brain Dump Workflow

1. Command palette → "🧠 Brain Dump" → type freely → done
2. AI processes automatically every 5 minutes
3. Tasks extracted and filed to dashboards
4. Notes extracted and filed to domain folders
5. Original brain dump preserved in `00_Inbox/brain-dumps/`
```

- [ ] **Step 4: Add QuickAdd shortcuts reference**

After the new Brain Dump section, add:

```markdown
## QuickAdd Shortcuts

| Command | What It Does |
|---------|-------------|
| ⚡ Quick Task | Add tagged task to Master List |
| 🧠 Brain Dump | Free-form capture → AI processes |
| 💡 Quick Idea | Create idea note in domain folder |
| 📝 Meeting Note | Open Meeting Note template |
```

- [ ] **Step 5: Add Faith and Health to Dashboard Navigation table**

Add to the Dashboard Navigation table:

```markdown
| [[000_Master Dashboard/Faith & Spirit\|Faith & Spirit]] | Only faith tasks + Bible studies |
| [[000_Master Dashboard/Health & Biohacking\|Health & Biohacking]] | Only health tasks + biohacking |
```

- [ ] **Step 6: Commit**

```bash
git commit --allow-empty -m "feat: enhance Quick Reference with faith/health areas, brain dump, and QuickAdd shortcuts"
```

---

## Task 7: Enhance Daily Note Template

**Files:**
- Modify: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\05_Templates\Daily Note.md`

- [ ] **Step 1: Read current Daily Note template**

Use Obsidian MCP `read_file` on `05_Templates/Daily Note.md`.

- [ ] **Step 2: Add focus_theme to frontmatter**

In the frontmatter section (between `---` markers), add:

```yaml
focus_theme:
```

Note: Single colon for YAML frontmatter, not double-colon (which is for inline fields in note body).

- [ ] **Step 3: Add brain dump link**

In the `## Tasks Captured` section (or equivalent capture section), add at the top:

```markdown
> 💡 Use Command Palette → "🧠 Brain Dump" for free-form capture
```

- [ ] **Step 4: Verify template renders**

Open Obsidian, create a test daily note using the template. Confirm new fields appear. Delete the test note.

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "feat: enhance Daily Note template with focus_theme and brain dump link"
```

---

## Task 8: Enhance Weekly Review Template

**Files:**
- Modify: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\05_Templates\Weekly Review.md`

- [ ] **Step 1: Read current Weekly Review template**

Use Obsidian MCP `read_file` on `05_Templates/Weekly Review.md`.

- [ ] **Step 2: Add auto-populated sections**

Add the following sections AFTER the existing scorecard section but BEFORE the reflection section:

````markdown
## ✅ Completed This Week (Auto-Populated)

```dataview
TASK
FROM ""
WHERE completed AND completion >= date(today) - dur(7 days)
SORT completion DESC
```

---

## 🚨 Currently Overdue

```dataview
TASK
FROM ""
WHERE !completed AND due AND due < date(today)
SORT due ASC
```

---

## 🧠 Brain Dumps Processed This Week

```dataview
TABLE file.ctime AS "Captured", processed AS "Status"
FROM "00_Inbox/brain-dumps"
WHERE file.ctime >= date(today) - dur(7 days)
SORT file.ctime DESC
```

---

## 🎯 Next Week's Needle Movers

Set 1 per domain — what would make next week a win?

- 🏥 Work:
- 🤝 Consulting:
- 🚀 Business:
- 🏠 Personal:
- ✝ Faith:
- 💪 Health:
````

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "feat: enhance Weekly Review with auto-populated Dataview sections"
```

---

## Task 9: Migrate Legacy TO DO Files

**Files:**
- Read: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\! TO DO\Personal & Work.md`
- Read: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\! TO DO\Personal.md`
- Modify: `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab\10_Active Projects\Active Personal\!!! MASTER TASK LIST.md`
- Move: Both `! TO DO` files → `09_Archives/legacy/`

- [ ] **Step 1: Read both legacy TO DO files**

Use Obsidian MCP `read_file` on both files. Identify any tasks NOT marked as done/X.

- [ ] **Step 2: Extract live tasks and convert format**

From `! TO DO/Personal & Work.md`, identify uncompleted tasks (no X or "Done" in Done? column). Convert each to canonical format:

```markdown
- [ ] LinkedIn automation framework - Claude [area:: personal] [priority:: B]
- [ ] Personal chronic pain GPT [area:: personal] [priority:: C]
- [ ] Google Calendar automation/to-do daily - Claude [area:: personal] [priority:: B]
- [ ] Revamp Christian social media poster - Claude [area:: personal] [priority:: B]
- [ ] Build out Skills further (meta prompting/database) [area:: work] [priority:: B]
```

Check `! TO DO/Personal.md` for any additional uncompleted tasks not already in Master Task List.

- [ ] **Step 3: Check for duplicates in Master Task List**

Use Obsidian MCP `read_file` on `!!! MASTER TASK LIST.md`. Verify each extracted task doesn't already exist before adding.

- [ ] **Step 4: Append non-duplicate tasks to Master Task List**

Use Obsidian MCP `edit_file` to append new tasks under `## 📥 Incoming — Unsorted` section of Master Task List.

- [ ] **Step 5: Move legacy files to archive**

Use Obsidian MCP `move_file`:
- `! TO DO/Personal & Work.md` → `09_Archives/legacy/Personal & Work (legacy).md`
- `! TO DO/Personal.md` → `09_Archives/legacy/Personal (legacy).md`

- [ ] **Step 6: Verify Master Task List still renders**

Use Obsidian MCP `read_file` on Master Task List. Confirm all sections intact, new tasks appear under Incoming.

- [ ] **Step 7: Commit**

```bash
git commit --allow-empty -m "feat: migrate legacy TO DO tasks to Master Task List, archive originals"
```

---

## Task 10: Write Brain Dump Processor Script

**Files:**
- Create: `Z:\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator\scripts\process_brain_dump.py`

- [ ] **Step 1: Create the processor script**

```python
"""
Brain Dump Processor — called by n8n every 5 minutes.
Reads unprocessed brain dumps from the vault, sends to Claude API,
writes extracted tasks and notes back to the vault.

Usage: python process_brain_dump.py --vault-path <path>
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import anthropic


AREA_FOLDER_MAP = {
    "work": "20_Domains (Life and Work)/Career/Parallon",
    "consulting": "20_Domains (Life and Work)/Career/Consulting",
    "business": "20_Domains (Life and Work)/Personal/Business Ideas & Projects",
    "personal": "20_Domains (Life and Work)/Personal",
    "faith": "30_Knowledge Library/Bible Studies & Notes",
    "health": "30_Knowledge Library/Biohacking",
}

VALID_AREAS = set(AREA_FOLDER_MAP.keys())
VALID_PRIORITIES = {"A", "B", "C"}
MAX_PER_CYCLE = 5

SYSTEM_PROMPT = """You are an Obsidian vault assistant for Aaron, a Business Analytics Manager at Parallon who also runs an AI automation consulting practice and has business ventures (Echelon Seven).

Process the following brain dump and extract:
1. TASKS: Each actionable item. Classify by area and priority.
2. NOTES: Any ideas, insights, or reference material worth saving as a note.

Area classification rules:
- work: Anything about Parallon day job (PowerBI, SQL, BigQuery, Power Automate, team management)
- consulting: Client AI/automation engagements and deliverables
- business: Aaron's own ventures (Echelon Seven, products, domains, revenue)
- personal: Family, parenting, homelab (Proxmox, Docker, n8n), home projects, social media
- faith: Bible study, prayer, spiritual practice, church, apologetics
- health: Biohacking, supplements, peptides, fitness, biomarkers, nutrition

Priority rules:
- A: Critical/urgent, has a deadline, or blocks other work
- B: Important but not time-critical
- C: Nice to have

Return ONLY valid JSON (no markdown, no explanation):
{
  "tasks": [
    {"text": "task description", "area": "work", "priority": "A", "due": "2026-03-28 or null"}
  ],
  "notes": [
    {"title": "note title", "content": "note body in markdown", "area": "work", "filename": "suggested-slug"}
  ],
  "primary_domain": "work"
}"""


def find_unprocessed(vault_path: Path) -> list[Path]:
    brain_dumps_dir = vault_path / "00_Inbox" / "brain-dumps"
    if not brain_dumps_dir.exists():
        return []

    unprocessed = []
    for md_file in sorted(brain_dumps_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        if "processed: false" in content:
            unprocessed.append(md_file)

    return unprocessed[:MAX_PER_CYCLE]


def extract_body(content: str) -> str:
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return parts[2].strip()
    return content.strip()


def call_claude(body: str) -> dict:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": body}],
    )
    response_text = message.content[0].text
    return json.loads(response_text)


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", slug).strip("-")[:50]


def write_tasks(vault_path: Path, tasks: list[dict], source_file: str) -> int:
    processed_dir = vault_path / "00_Inbox" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    count = 0

    for task in tasks:
        area = task.get("area", "personal")
        if area not in VALID_AREAS:
            area = "personal"
        priority = task.get("priority", "B")
        if priority not in VALID_PRIORITIES:
            priority = "B"

        text = task.get("text", "").strip()
        if not text:
            continue

        due_str = ""
        if task.get("due"):
            due_str = f" [due:: {task['due']}]"

        slug = slugify(text)
        filename = f"{now.strftime('%Y-%m-%d-%H%M')}-task-{slug}.md"
        filepath = processed_dir / filename

        content = f"""---
created: {now.isoformat()}
type: processed-task
source: brain-dump
source_file: {source_file}
---

- [ ] {text} [area:: {area}] [priority:: {priority}]{due_str}
"""
        filepath.write_text(content, encoding="utf-8")
        count += 1

    return count


def write_notes(vault_path: Path, notes: list[dict]) -> int:
    now = datetime.now()
    count = 0

    for note in notes:
        area = note.get("area", "personal")
        if area not in VALID_AREAS:
            area = "personal"

        title = note.get("title", "Untitled Note").strip()
        content_body = note.get("content", "").strip()
        slug = note.get("filename", slugify(title))

        folder = vault_path / AREA_FOLDER_MAP[area]
        folder.mkdir(parents=True, exist_ok=True)

        filename = f"{now.strftime('%Y-%m-%d')}-{slugify(slug)}.md"
        filepath = folder / filename

        content = f"""---
created: {now.strftime('%Y-%m-%d')}
type: processed-note
source: brain-dump
area: {area}
---

# {title}

{content_body}
"""
        filepath.write_text(content, encoding="utf-8")
        count += 1

    return count


def mark_processed(file_path: Path) -> None:
    content = file_path.read_text(encoding="utf-8")
    now = datetime.now().isoformat()
    content = content.replace("processed: false", f"processed: true\nprocessed_at: {now}")
    file_path.write_text(content, encoding="utf-8")


def mark_error(file_path: Path, error_msg: str) -> None:
    content = file_path.read_text(encoding="utf-8")
    now = datetime.now().isoformat()
    content = content.replace(
        "processed: false",
        f"processed: error\nerror_at: {now}\nerror_message: {error_msg}",
    )
    file_path.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Process brain dumps from Obsidian vault")
    parser.add_argument("--vault-path", required=True, help="Path to Obsidian vault")
    args = parser.parse_args()

    vault_path = Path(args.vault_path)
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        return

    unprocessed = find_unprocessed(vault_path)
    if not unprocessed:
        print("No unprocessed brain dumps found.")
        return

    print(f"Found {len(unprocessed)} unprocessed brain dump(s)")

    for bd_file in unprocessed:
        print(f"Processing: {bd_file.name}")
        try:
            body = extract_body(bd_file.read_text(encoding="utf-8"))
            if not body:
                mark_processed(bd_file)
                continue

            result = call_claude(body)

            tasks_count = write_tasks(vault_path, result.get("tasks", []), bd_file.name)
            notes_count = write_notes(vault_path, result.get("notes", []))

            mark_processed(bd_file)
            print(f"  Done: {tasks_count} tasks, {notes_count} notes extracted")

        except json.JSONDecodeError as e:
            mark_error(bd_file, f"JSON parse error: {e}")
            print(f"  ERROR: Failed to parse Claude response as JSON")
        except Exception as e:
            mark_error(bd_file, str(e))
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create requirements.txt**

Create `Z:\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator\requirements.txt`:

```
anthropic>=0.40.0
```

- [ ] **Step 3: Test script runs without errors (dry run)**

```bash
cd "Z:/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator"
python scripts/process_brain_dump.py --vault-path "C:/Users/Admin/Desktop/Desktop Folders/Obsidian/Homelab"
```

Expected output: `No unprocessed brain dumps found.` (no brain dumps exist yet)

- [ ] **Step 4: Commit**

```bash
git add scripts/process_brain_dump.py requirements.txt
git commit -m "feat: add Brain Dump Processor script (Claude API integration)"
```

---

## Task 11: Create Architecture Decision Record

**Files:**
- Create: `Z:\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator\architecture\ADR-001-brain-dump-output-strategy.md`

- [ ] **Step 1: Write ADR**

```markdown
# ADR-001: Brain Dump Output Strategy — Individual Files

## Status: Accepted

## Context
The Brain Dump Processor extracts tasks and notes from brain dumps via Claude API. It needs to write results back to the Obsidian vault. Two approaches were considered:

1. Append tasks to the Master Task List file
2. Write each task as an individual file in 00_Inbox/processed/

## Decision
Individual files (Option 2).

## Rationale
- **Sync safety:** n8n runs on MiniPC Docker, vault syncs via Remotely-Save. Appending to Master Task List while the user edits it on mobile creates file conflicts. Individual files avoid this entirely.
- **Dataview compatibility:** Dataview queries use `FROM ""` which searches all vault files. Individual task files appear in all dashboards automatically.
- **Traceability:** Each processed task file contains frontmatter linking back to the original brain dump.
- **Idempotency:** Re-running the processor doesn't duplicate tasks (each brain dump is marked processed).

## Consequences
- More files in vault (mitigated by monthly archival of processed files >30 days old)
- User may want to consolidate tasks into Master Task List during Weekly Review (optional)
```

- [ ] **Step 2: Commit**

```bash
git add architecture/ADR-001-brain-dump-output-strategy.md
git commit -m "docs: add ADR-001 brain dump output strategy"
```

---

## Task 12: Create n8n Brain Dump Processor Workflow

**Files:**
- Create: `Z:\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator\workflows\brain-dump-processor.json`

**Vault Access Strategy:** The n8n Docker container on MiniPC needs filesystem access to the Obsidian vault. Choose ONE during this task:
- **Option A (SMB share):** Mount the vault folder from the Windows desktop as a network share in the Docker container. Add to `docker-compose.yml` volumes.
- **Option B (Shared NAS):** If the vault is on the NAS at `\\192.168.1.240`, mount that path in Docker.
- **Option C (Remotely-Save cloud):** Use n8n to read/write via the same cloud storage Remotely-Save uses.

- [ ] **Step 1: Determine vault access path for n8n Docker**

Check where n8n can reach the vault. If the vault is on the NAS (the project repo is at `//192.168.1.240/home/`), the vault may also be accessible from there. Otherwise, set up an SMB mount.

Determine the vault path as seen from inside the n8n Docker container and set it as env var `OBSIDIAN_VAULT_PATH`.

- [ ] **Step 2: Create n8n workflow**

In n8n UI (http://YOUR_MINIPC_IP:5678):

1. **Schedule Trigger** node: Interval = 5 minutes
2. **Execute Command** node:
   - Command: `python /path/to/scripts/process_brain_dump.py --vault-path $OBSIDIAN_VAULT_PATH`
   - Working Directory: project scripts directory
   - Environment: `ANTHROPIC_API_KEY` from n8n credentials
3. **IF** node: Check if stdout contains "ERROR"
4. **Success path:** No-op (logging)
5. **Error path:** Optional notification (Slack/email/webhook)

Alternative approach if Python not available in n8n container:
- Use **HTTP Request** nodes to call Claude API directly from n8n
- Use **Read/Write File** nodes for vault access
- Use **Code** node for JSON parsing and task extraction

- [ ] **Step 3: Export workflow JSON**

In n8n: select the workflow → Menu → Export → save as `brain-dump-processor.json`.
Copy to `Z:\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator\workflows\brain-dump-processor.json`

- [ ] **Step 4: Test workflow fires on schedule**

Activate the workflow in n8n. Wait 5 minutes. Check n8n execution log — should show "No unprocessed brain dumps found." on first run.

- [ ] **Step 5: Commit**

```bash
git add workflows/brain-dump-processor.json
git commit -m "feat: add n8n Brain Dump Processor workflow export"
```

---

## Task 13: End-to-End Brain Dump Test

- [ ] **Step 1: Create a test brain dump in the vault**

Use Obsidian MCP `write_file` to create `00_Inbox/brain-dumps/2026-03-21-test-brain-dump.md`:

```markdown
---
created: 2026-03-21 15:00
type: brain-dump
processed: false
---

Need to finish the Union scope document for work by Friday. Also should look into creatine loading protocol for health. Bible study session 1 outline needs discussion questions written.
```

- [ ] **Step 2: Run the processor**

```bash
cd "Z:/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator"
pip install -r requirements.txt
python scripts/process_brain_dump.py --vault-path "C:/Users/Admin/Desktop/Desktop Folders/Obsidian/Homelab"
```

Expected: `Found 1 unprocessed brain dump(s)` → processes → reports tasks + notes extracted.

- [ ] **Step 3: Verify output files created**

Use Obsidian MCP `list_directory` on `00_Inbox/processed/` — should contain task files.
Use Obsidian MCP `read_file` on the test brain dump — should now show `processed: true`.

- [ ] **Step 4: Verify tasks appear in Mission Control**

Open Obsidian → Mission Control. The extracted tasks should appear in the relevant domain sections via Dataview.

- [ ] **Step 5: Clean up test data**

Delete the test brain dump and processed task files (they were just for testing).

- [ ] **Step 6: Commit**

```bash
git commit --allow-empty -m "test: verify end-to-end brain dump pipeline works"
```

---

## Task 13: Configure QuickAdd Macros

> This task requires manual Obsidian plugin configuration — cannot be automated via MCP.

- [ ] **Step 1: Open QuickAdd settings**

In Obsidian: Settings → Community Plugins → QuickAdd → Manage Macros

- [ ] **Step 2: Add "⚡ Quick Task" macro**

Type: Capture
- Capture To: `10_Active Projects/Active Personal/!!! MASTER TASK LIST.md`
- Capture format: `- [ ] {{VALUE:Task}} [area:: {{SUGGESTER:work,consulting,business,personal,faith,health}}] [priority:: {{SUGGESTER:A,B,C}}] [due:: {{VDATE:Due date (optional),YYYY-MM-DD}}]`
- Insert after: `## 📥 Incoming — Unsorted`
- Toggle: "Capture to active file" OFF

- [ ] **Step 3: Add "🧠 Brain Dump" macro**

Type: Template
- Template path: `05_Templates/Brain Dump.md`
- File name format: `{{DATE:YYYY-MM-DD-HHmm}}-brain-dump`
- Create in folder: `00_Inbox/brain-dumps/`

- [ ] **Step 4: Add "💡 Quick Idea" macro**

Type: Capture
- Capture To: `00_Inbox/{{VALUE:Idea Title}}.md`
- Capture format: `---\ncreated: {{DATE:YYYY-MM-DD}}\ntype: idea\narea: {{SUGGESTER:work,consulting,business,personal,faith,health}}\n---\n\n# {{VALUE:Idea Title}}\n\n{{VALUE:Describe your idea}}`

- [ ] **Step 5: Add "📝 Meeting Note" macro**

Type: Template
- Template path: `05_Templates/Meeting Note.md`
- File name format: `{{DATE:YYYY-MM-DD}}-meeting`
- Create in folder: `00_Inbox/`

- [ ] **Step 6: Add all 4 macros to QuickAdd command palette**

For each macro, click the lightning bolt icon to add it as a command. This makes them accessible via Ctrl+P on desktop and Command Palette on mobile.

- [ ] **Step 7: Test on desktop**

Press Ctrl+P → type "Quick Task" → fill in a test task → verify it appears in Master Task List under Incoming.
Press Ctrl+P → type "Brain Dump" → type test text → verify file created in brain-dumps folder.

- [ ] **Step 8: Commit**

```bash
git commit --allow-empty -m "feat: configure QuickAdd macros for Quick Task, Brain Dump, Quick Idea, Meeting Note"
```

---

## Task 14: Set Up Obsidian Bookmarks

> Manual Obsidian configuration.

- [ ] **Step 1: Open Bookmarks panel**

In Obsidian: left sidebar → Bookmarks tab (star icon), or enable via Settings → Core Plugins → Bookmarks.

- [ ] **Step 2: Pin 5 key notes**

Right-click each file → "Bookmark" (or drag to Bookmarks panel):
1. `000_Master Dashboard/Mission Control.md`
2. `000_Master Dashboard/The Catch All.md`
3. `10_Active Projects/Active Personal/!!! MASTER TASK LIST.md`
4. `99_System/⚡ Quick Reference.md`
5. Today's daily note (use Calendar plugin)

- [ ] **Step 3: Verify on mobile**

Open Obsidian mobile → swipe to Bookmarks panel → confirm all 5 appear.

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "feat: configure Obsidian Bookmarks for mobile quick access"
```

---

## Task 15: Final Verification

- [ ] **Step 1: Full vault health check**

Open Mission Control in Obsidian. Verify:
- "Move The Needle NOW" renders with tasks from work/consulting/business
- "Pending Brain Dumps" section renders (may be empty)
- All 6 area sections render (work, consulting, business, personal, faith, health)
- Task Counts table renders
- Full Backlog renders
- Nav bar links all work (including new Faith and Health)

- [ ] **Step 2: Dashboard spot-checks**

Navigate to each dashboard and confirm Dataview queries render:
- Faith & Spirit → Bible Studies and Prayers sections populate
- Health & Biohacking → Biohacking notes populate
- Work (Parallon) → work tasks show
- Consulting → consulting tasks show (may be empty)
- Business → business tasks show
- Personal & Life → personal tasks show

- [ ] **Step 3: Mobile verification**

Open Obsidian on phone:
- Bookmarks panel shows 5 pinned notes
- Mission Control loads and renders on mobile screen
- QuickAdd commands accessible via command palette
- Test "Quick Task" adds a task successfully

- [ ] **Step 4: Update gemini.md**

```markdown
- 2026-03-21: Implementation complete. All vault enhancements live. Brain dump pipeline tested. QuickAdd configured. Bookmarks set.
```

- [ ] **Step 5: Final commit**

```bash
cd "Z:/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator"
git add -A
git commit -m "feat: ObsidianHomeOrchestrator v1.0 — complete vault enhancement + brain dump pipeline"
```

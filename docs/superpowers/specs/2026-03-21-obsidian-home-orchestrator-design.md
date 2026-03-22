# ObsidianHomeOrchestrator — Design Spec

## Overview

A Life Operating System that enhances Aaron's existing Obsidian vault with AI-powered brain dump processing, automatic priority surfacing, and frictionless mobile capture — enabling him to manage 3 active domains (Work at Parallon, AI Automation Consulting, Business Startup) plus Personal, Faith, and Health from one central hub.

## Design Principles

1. **Enhance in place** — existing vault content is sacred. Zero deletions, zero overwrites.
2. **Frictionless capture** — 3 taps max on mobile. Speed of input is non-negotiable.
3. **Automatic intelligence** — AI processes brain dumps with zero human review.
4. **Needle-movers first** — dashboards surface what matters, not everything.
5. **Mobile is first-class** — phone is a full capture + review device, not an afterthought.

## System Architecture

### 5-Layer Model

```
Layer 1: CAPTURE — QuickAdd shortcuts (Quick Task, Brain Dump, Quick Idea, Meeting Note)
Layer 2: INTELLIGENCE — n8n + Claude API (Brain Dump Processor, every 5 min)
Layer 3: STORAGE — Obsidian vault (existing structure enhanced in place)
Layer 4: QUERY — Dataview ("Move The Needle NOW" + domain dashboards)
Layer 5: REVIEW — Daily Note, Weekly Review, Monthly Audit, Quarterly Life OS Review
```

### Data Flow

```
Brain Dump (phone/laptop)
  → QuickAdd → 00_Inbox/brain-dumps/YYYY-MM-DD-HHmm-brain-dump.md
  → n8n picks up (5-min poll, processed: false filter)
  → Claude API extracts tasks + notes (with Aaron's personal context)
  → Tasks → individual files in 00_Inbox/processed/ (avoids sync conflicts)
  → Notes → domain folders in 20_Domains/
  → Original brain dump marked processed: true
  → Dataview auto-queries → tasks appear in all dashboards automatically

Quick Task (phone/laptop)
  → QuickAdd → appends formatted task to Master Task List
  → Dataview auto-queries → appears in area dashboard + Mission Control
```

## Component Specifications

### Component 1: Brain Dump Pipeline

**Entry Point:** QuickAdd macro "🧠 Brain Dump"
- Opens large text input (no formatting required)
- Saves to `00_Inbox/brain-dumps/YYYY-MM-DD-HHmm-brain-dump.md`
- Frontmatter: `type: brain-dump`, `processed: false`

**Processor:** n8n workflow "Brain Dump Processor"
- Trigger: Schedule node, every 5 minutes
- Step 1: Read files from vault `00_Inbox/brain-dumps/` where `processed: false`
- Step 2: For each file, send content to Claude API with system prompt
- Step 3: Parse JSON response (tasks array + notes array)
- Step 4: Write tasks as individual files to `00_Inbox/processed/`
- Step 5: Write notes to appropriate `20_Domains/` subfolder
- Step 6: Update original brain dump: `processed: true`, `processed_at: [timestamp]`

**Claude System Prompt Context:**
- Aaron is a Business Analytics Manager at Parallon (work)
- He runs an AI automation consulting practice (consulting)
- He has business ventures including Echelon Seven (business)
- He is a person of faith with active Bible study work (faith)
- He tracks biohacking, supplements, and fitness (health)
- Personal includes family/parenting, homelab, social media, home projects
- Task format: `- [ ] description [area:: X] [priority:: A/B/C] [due:: YYYY-MM-DD]`
- Area classification decision tree provided in prompt
- Default: area=personal, priority=B if uncertain

**Output Strategy — Individual Files (not Master Task List append):**
- Tasks → `00_Inbox/processed/YYYY-MM-DD-HHmm-task-[slug].md` with proper inline fields
- Notes → domain folders per area-to-folder mapping table (see below)
- Rationale: avoids sync conflicts with Master Task List, Dataview queries `FROM ""` so processed tasks appear in all dashboards automatically
- Quick Task (QuickAdd) deliberately appends directly to Master Task List — this is a single atomic write, so sync conflict risk is acceptable

**Processed Task File Template:**
```markdown
---
created: 2026-03-21T14:30:00
type: processed-task
source: brain-dump
source_file: 2026-03-21-1430-brain-dump.md
---

- [ ] Task description here [area:: work] [priority:: A] [due:: 2026-03-28]
```
Dataview picks up the task line from any file queried with `FROM ""`. The frontmatter provides traceability back to the original brain dump.

**Area-to-Folder Mapping Table (for n8n note routing):**

| Area Value | Target Folder | Notes |
|------------|--------------|-------|
| `work` | `20_Domains (Life and Work)/Career/Parallon/` | Parallon BAM role |
| `consulting` | `20_Domains (Life and Work)/Career/Consulting/` | Create if not exists |
| `business` | `20_Domains (Life and Work)/Personal/Business Ideas & Projects/` | Existing folder |
| `personal` | `20_Domains (Life and Work)/Personal/` | Existing folder |
| `faith` | `30_Knowledge Library/Bible Studies & Notes/` | Existing folder |
| `health` | `30_Knowledge Library/Biohacking/` | Existing folder |

New subfolders to create: `20_Domains (Life and Work)/Career/Consulting/`

**Claude API Response JSON Schema:**
```json
{
  "tasks": [
    {
      "text": "string — task description",
      "area": "string — one of: work, consulting, business, personal, faith, health",
      "priority": "string — one of: A, B, C",
      "due": "string|null — YYYY-MM-DD or null if not mentioned"
    }
  ],
  "notes": [
    {
      "title": "string — note title",
      "content": "string — note body in markdown",
      "area": "string — one of: work, consulting, business, personal, faith, health",
      "filename": "string — suggested filename slug"
    }
  ],
  "primary_domain": "string — the dominant area of this brain dump"
}
```
n8n must validate: area values are in the allowed set (whitelist), JSON parses correctly. If malformed, mark brain dump `processed: error` and retry next cycle.

**Per-Cycle Batch Limit:** Process max 5 brain dumps per n8n cycle to control Claude API costs and prevent burst charges.

**n8n-to-Vault File Access Strategy:**
The Obsidian vault lives on Aaron's Windows desktop at `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab`. n8n runs in Docker on the MiniPC. File access options (choose during implementation):

- **Option A (Recommended): Shared vault via Remotely-Save cloud storage.** Both desktop Obsidian and n8n access the vault through the same cloud intermediary (OneDrive/S3/Dropbox). n8n reads/writes to the cloud copy; Remotely-Save syncs to desktop and phone. Latency: ~5 min.
- **Option B: SMB/CIFS share.** Mount the vault folder as a network share accessible to the MiniPC Docker container. Direct filesystem access, lowest latency. Requires Windows file sharing configuration.
- **Option C: Vault on shared storage.** Move the vault to a NAS or shared path accessible to both Windows desktop and MiniPC Docker. Most reliable but requires vault path change.

**Sync Latency Note:** Regardless of access strategy, Remotely-Save syncs on app open or on timer (typically 5-30 min). Processed brain dump results may not appear on mobile immediately — users will see them next time they open Obsidian or when sync fires.

**Error Handling:**
- API failure → mark `processed: error, error_message: [reason]`, retry on next cycle
- Malformed JSON → same error handling, retry with simpler prompt on second attempt
- Pending brain dumps visible on Mission Control via Dataview query
- Original brain dump always preserved

### Component 2: Mission Control Enhancement

**New section added at the TOP (above existing content):**

```markdown
## 🎯 MOVE THE NEEDLE — RIGHT NOW

### 🏥 Work (Parallon)
```dataview
TASK
FROM ""
WHERE !completed AND area = "work" AND priority = "A"
SORT due ASC
LIMIT 1
`` `

### 🤝 Consulting
```dataview
TASK
FROM ""
WHERE !completed AND area = "consulting" AND priority = "A"
SORT due ASC
LIMIT 1
`` `

### 🚀 Business
```dataview
TASK
FROM ""
WHERE !completed AND area = "business" AND priority = "A"
SORT due ASC
LIMIT 1
`` `
```

**Additional new section:**

```markdown
## 🧠 Pending Brain Dumps
```dataview
TABLE file.ctime AS "Captured"
FROM "00_Inbox/brain-dumps"
WHERE processed = false
SORT file.ctime DESC
LIMIT 5
`` `
```

**Navigation bar update:** Add Faith & Health links:
```markdown
> [[000_Master Dashboard/Work - Consulting|🤝 Consulting]] | [[000_Master Dashboard/Work - Parallon|🏥 Parallon]] | [[000_Master Dashboard/Work - BusinessStartup|🚀 Business]] | [[000_Master Dashboard/Personal & Life|🏠 Personal]] | [[000_Master Dashboard/Faith & Spirit|✝ Faith]] | [[000_Master Dashboard/Health & Biohacking|💪 Health]] | [[10_Active Projects/Active Personal/!!! MASTER TASK LIST|📋 Master List]]
```

**Existing content below "Move The Needle" section: UNCHANGED.**

### Component 3: New Domain Dashboards

**Faith & Spirit Dashboard** (`000_Master Dashboard/Faith & Spirit.md`)
- Navigation back to Mission Control
- Priority A faith tasks (Dataview: `area = "faith"`)
- All faith tasks (Dataview: `area = "faith"`)
- Bible Studies section — Dataview pulling from `30_Knowledge Library/Bible Studies & Notes/`
- Prayers section — Dataview pulling from `Bible Studies & Notes/Prayers/`
- Recent faith notes (last 5 modified)
- Add Task snippet with `[area:: faith]`

**Faith Area Migration Note:** Existing Bible study tasks in Master Task List use `[area:: personal]`. These will NOT be re-tagged (preserve existing data). The Faith dashboard will query `area = "faith"` for new tasks going forward. Optionally, during Weekly Review, the user can re-tag existing Bible/prayer tasks from `personal` to `faith` at their discretion. The Weekly Review scorecard already has a "Spiritual" row — this maps to the `faith` area.

**Health & Biohacking Dashboard** (`000_Master Dashboard/Health & Biohacking.md`)
- Navigation back to Mission Control
- Priority A health tasks (Dataview)
- All health tasks (Dataview)
- Protocols & Supplements — Dataview pulling from `30_Knowledge Library/Biohacking/`
- Recent health notes (last 5 modified)
- Add Task snippet with `[area:: health]`

### Component 4: Mobile Experience

**QuickAdd Macros to Configure:**

1. **⚡ Quick Task** — Capture type
   - Prompts: task text, area (suggester: work/consulting/business/personal/faith/health), priority (suggester: A/B/C), due date (optional)
   - Output: appends to Master Task List in canonical format

2. **🧠 Brain Dump** — Template type
   - Prompts: large text VALUE
   - Output: creates file in `00_Inbox/brain-dumps/`

3. **💡 Quick Idea** — Template type
   - Prompts: idea title, area (suggester)
   - Output: creates note in `20_Domains/` or `00_Inbox/`

4. **📝 Meeting Note** — Template type
   - Uses existing `05_Templates/Meeting Note.md`

**Bookmarks to Pin:**
1. Mission Control
2. The Catch All
3. Master Task List
4. Today's Daily Note (Calendar plugin)
5. Quick Reference

### Component 5: Template Enhancements

**Daily Note (`05_Templates/Daily Note.md`) — additions only:**
- Add `focus_theme::` to frontmatter
- Add Brain Dump link in Tasks Captured section
- Streamline section headers for mobile readability

**Weekly Review (`05_Templates/Weekly Review.md`) — additions only:**
- Add Dataview: "Completed This Week" (auto-populated)
- Add Dataview: "Overdue Items" (auto-populated)
- Add Dataview: "Brain Dumps Processed This Week" count
- Add "Next Week's Needle Movers" section (1 per domain, manually set)
- Existing scorecard and reflection sections: UNCHANGED

**Quick Reference (`99_System/⚡ Quick Reference.md`) — additions only:**
- Add `faith` and `health` to area values table
- Add Brain Dump instructions
- Add QuickAdd shortcut reference

**Brain Dump Template (NEW: `05_Templates/Brain Dump.md`):**
```markdown
---
created: <% tp.date.now("YYYY-MM-DD HH:mm") %>
type: brain-dump
processed: false
---

<% tp.system.prompt("Brain dump — type freely:", true) %>
```
Note: The `true` parameter enables multiline input, which is essential for mobile brain dumps where `tp.system.prompt()` defaults to single-line.

### Component 6: Legacy Cleanup

**`! TO DO/Personal & Work.md`:**
- Extract any live (uncompleted) tasks
- Convert to canonical format with inline fields
- Add to Master Task List under "📥 Incoming — Unsorted"
- Move original file to `09_Archives/legacy/`

**`! TO DO/Personal.md`:**
- Same process as above

**`09_Archives/` folder:** Create if not exists, with `legacy/` subfolder.

## Vault Change Summary

| Change Type | Count | Details |
|-------------|-------|---------|
| Files Added | 3 | Faith & Spirit dashboard, Health & Biohacking dashboard, Brain Dump template |
| Folders Added | 5 | `00_Inbox/brain-dumps/`, `00_Inbox/processed/`, `10_Active Projects/Active Consulting/`, `10_Active Projects/Active Business/`, `09_Archives/legacy/` |
| Folders Added (conditional) | 1 | `20_Domains (Life and Work)/Career/Consulting/` (if not exists) |
| Files Enhanced | 5 | Mission Control, Daily Note template, Weekly Review template, Quick Reference, QuickAdd config |
| Files Archived | 2 | `! TO DO/Personal & Work.md`, `! TO DO/Personal.md` (moved to `09_Archives/legacy/`, tasks migrated first) |
| n8n Workflows | 1 | Brain Dump Processor |
| Content Deleted | 0 | Nothing |

## Pre-Implementation Checklist

- [ ] Backup vault via Remotely-Save sync before any changes
- [ ] Verify all existing Dataview queries render correctly (baseline)
- [ ] Test each change in isolation before proceeding to next component
- [ ] After all changes: verify all existing dashboards still render correctly
- [ ] Verify Mobile sync works end-to-end after changes

## Tech Stack

- **Vault:** Obsidian with Dataview, Templater, Tasks, QuickAdd, Calendar, omnisearch, remotely-save, linter
- **Automation:** n8n (self-hosted Docker on MiniPC)
- **AI:** Claude API (claude-sonnet-4-6) via n8n HTTP Request node
- **Sync:** Remotely-Save (existing — ensures phone ↔ desktop sync)
- **Infrastructure:** MiniPC Docker Compose (PostgreSQL, n8n, existing stack)

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Brain dump area misclassification | Context-rich Claude prompt with decision tree; default to personal/B; original always preserved |
| Sync conflicts (n8n writes while user edits) | Tasks written to individual files in processed/, not appended to Master Task List |
| n8n downtime | Brain dumps are just files — they wait; "Pending" count visible on Mission Control |
| Mobile Dataview performance | LIMIT 1 on needle-mover queries; LIMIT 5 on recent notes; fast rendering |
| Vault bloat from processed files | Monthly archive: processed files >30 days → 09_Archives/brain-dumps/ |
| Area ambiguity in brain dumps | Decision tree in Claude prompt: Parallon=work, client deliverables=consulting, Echelon Seven=business, etc. |

## Future Enhancements (not in scope for v1)

- Daily Note auto-creation (n8n, 6am)
- Weekly Summary auto-generation (n8n compiles week's completions)
- Health data API ingestion (Oura/Garmin → vault)
- Consulting time tracking webhook
- Overdue task alert (n8n → phone notification)

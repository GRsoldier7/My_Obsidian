# ObsidianHomeOrchestrator v2.0 — Intelligent Life OS Design Spec

**Date:** 2026-04-02  
**Status:** Approved — proceeding to implementation

---

## Problem Statement

The system has been running for 14 days and has never processed a single brain dump. Root causes (confirmed via live data):

1. **Daily Note Creator errors every morning at 6 AM CDT** — `40_Timeline_Weekly/Daily/` folder does not exist in MinIO
2. **Brain Dump Processor "succeeds" but extracts nothing** — content check only looks at byte length; template boilerplate (~1,200 bytes) passes the check; LLM receives template text and finds nothing actionable
3. **Workflow is hardcoded to 8 exact filenames** — extra brain dumps (Coding.md, Website & Business.md, Bible post on Social Media.md) are completely invisible
4. **BrainDump — Consulting.md does not exist** — workflow expects it, MinIO doesn't have it
5. **No logging** — silent success/failure, zero visibility
6. **No health monitoring** — failures accumulate undetected for days
7. **No QA or E2E tests** — nothing has ever been verified end-to-end

**Live confirmation (2026-04-02):**
- `00_Inbox/processed/` — completely empty, 0 files ever written
- `40_Timeline_Weekly/Daily/` — does not exist in MinIO bucket
- `BrainDump — Personal.md` — 4,721 bytes of real unprocessed content (car audio tasks, 10+ articles, YouTube links)
- `BrainDump — Business.md` — 1,478 bytes of real content (book recommendations, AI SEO link)
- `Coding.md` — 3,153 bytes of Claude Code tips (orphaned, never processed)

---

## Architecture: 7-Stage Intelligent Pipeline

Every workflow gets all 7 stages. No exceptions.

```
[1] HEALTH GATE    → Abort if MinIO/n8n unhealthy. Email alert.
[2] SMART READ     → Discover all files dynamically. Parse sections. Detect real content.
[3] AI TRIAGE      → Claude classifies each item: type, confidence, reasoning.
[4] AI EXTRACT     → Claude extracts tasks/notes/articles with Q2 Rock context.
[5] QUALITY GATE   → Validate canonical format. Reject malformed output.
[6] VERIFIED WRITE → Write to MinIO. Read back. Confirm file exists.
[7] RUN LOG        → JSON log to 99_System/logs/. Rich email digest.
```

---

## Design Principles

1. **Smart content detection** — Parse brain dump sections individually. Template placeholders ≠ content. A section with only HTML comments or `<!-- Add items here -->` is empty.
2. **Dynamic file discovery** — List `00_Inbox/brain-dumps/*` dynamically. Never hardcode filenames. New brain dump files are automatically picked up.
3. **Section-aware extraction** — "To Do's" section → task extraction prompt. "Articles & Resources" section → article processing prompt. "Quick Notes" → note routing. Different sections need different AI prompts.
4. **Q2 Rock-aware prioritization** — Every AI extraction call includes Aaron's Q2 Rocks as context. Priority A = directly advances a quarterly rock.
5. **Verified writes** — Write to MinIO, then immediately read back to confirm the file exists and is non-empty. Log WRITE_VERIFY_FAIL if confirmation fails.
6. **Full structured logging** — Every workflow run produces a JSON log at `99_System/logs/{workflow}-{YYYY-MM-DD}.json`.
7. **Full QA requirement** — Every task in the implementation plan has a verification step. Nothing marked complete without passing.

---

## Brain Dump File Structure (Canonical)

All brain dump files follow this section structure:

```markdown
---
domain: Personal
area: personal
last_processed:
status: empty
---

# 🤖 Brain Dump — Personal

## ⚡ Quick Notes
## 🎯 Needle Movers
## ✅ To Do's
## 📰 Articles & Resources to Follow Up On
## 🗂️ Things to Organize & Follow Up On
## 💡 Ideas & Possibilities
## 🔁 Recurring / Rhythms
```

**Content detection rules:**
- Section is EMPTY if it contains only: HTML comments (`<!-- ... -->`), template placeholder lines, Obsidian inline field syntax (`=this.field`), or whitespace
- Section has REAL CONTENT if it contains any non-comment, non-placeholder text line

**Section-to-AI-prompt mapping:**
| Section | AI Treatment |
|---------|-------------|
| Quick Notes | Extract as notes, route to domain folder |
| Needle Movers | Extract as Priority A tasks |
| To Do's | Extract as tasks with priority inference |
| Articles & Resources | Extract URLs + context, queue for article processor |
| Things to Organize | Extract as tasks or notes |
| Ideas & Possibilities | Extract as notes to domain folder |
| Recurring / Rhythms | Extract as B-priority tasks or system notes |

---

## Q2 2026 Rocks (Context for all AI calls)

```
Faith:    Launch social media Bible study (4 sessions delivered)
Family:   Complete Marriage Alignment Questionnaire + bi-weekly check-in
Business: Ship MVP — website live, offer defined, 3 outreach conversations (Echelon Seven)
Work:     Deliver Union project + position for exit (Parallon)
Health:   Make hip decision + 3x/week gym for 8 weeks
```

**Priority A rule:** Task directly advances one of the 5 Q2 Rocks above.
**Priority B rule:** Task is important but doesn't directly move a quarterly rock.
**Priority C rule:** Nice-to-have, research, or low-urgency.

---

## Canonical Task Format (never deviate)

```
- [ ] Task description [area:: faith] [priority:: A] [due:: 2026-MM-DD]
```

Valid areas: `faith`, `family`, `business`, `consulting`, `work`, `health`, `home`, `personal`
Valid priorities: `A`, `B`, `C`
Due date: `YYYY-MM-DD` format, or omit `[due:: ...]` entirely if no date

---

## Vault Paths (confirmed correct, no prefix)

All paths are relative to MinIO bucket `obsidian-vault` root (no `Homelab/` prefix):

```
00_Inbox/brain-dumps/           — brain dump source files (dynamic discovery)
00_Inbox/processed/             — extracted task files (output)
00_Inbox/articles-to-process.md — article URL queue
000_Master Dashboard/North Star.md
10_Active Projects/Active Personal/!!! MASTER TASK LIST.md
40_Timeline_Weekly/Daily/YYYY-MM-DD.md   — daily notes (folder must be created)
99_System/logs/                 — structured run logs (NEW)

Domain note output paths:
  faith:      30_Knowledge Library/Bible Studies & Notes/
  family:     20_Domains (Life and Work)/Personal/Family/
  business:   20_Domains (Life and Work)/Personal/Business Ideas & Projects/
  consulting: 20_Domains (Life and Work)/Career/Consulting/
  work:       20_Domains (Life and Work)/Career/Parallon/
  health:     30_Knowledge Library/Biohacking/
  home:       20_Domains (Life and Work)/Personal/Home/
  personal:   20_Domains (Life and Work)/Personal/
```

---

## Workflow Inventory

| Workflow | Schedule | Status | Change |
|----------|----------|--------|--------|
| Brain Dump Processor | 7 AM daily | ACTIVE (broken) | FULL REBUILD |
| Daily Note Creator | 6 AM daily | ACTIVE (erroring) | FULL REBUILD |
| Overdue Task Alert | 8 AM daily | ACTIVE (hollow) | FULL REBUILD |
| Weekly Digest | Sunday 6 PM | ACTIVE (hollow) | FULL REBUILD |
| AI Brain (sub-workflow) | On-demand | ACTIVE | REPLACE with inline |
| Article Processor | 8 AM + 7 PM | ACTIVE | REBUILD |
| System Health Monitor | Every 6 hours | MISSING | CREATE NEW |
| Error Handler | On error | MISSING | CREATE NEW |

---

## n8n Credentials (live, verified)

| Name | Type | Credential ID |
|------|------|--------------|
| MinIO S3 | aws | `z9qTyG2NVVbhHkg0` |
| Gmail SMTP (Aaron) | smtp | `lWGOwsktldwb3iEj` |
| OpenRouter API | httpHeaderAuth | `Z7liUYc3Toq3q7W7` |

New credential needed:
| Name | Type | Notes |
|------|------|-------|
| Anthropic Claude | httpHeaderAuth | For Claude API calls from n8n |

OpenRouter is kept for backwards compat but Claude is preferred for intelligence stages.

---

## Run Log Schema

Every workflow writes to `99_System/logs/{workflow-slug}-{YYYY-MM-DD}.json`:

```json
{
  "workflow": "brain-dump-processor",
  "run_date": "2026-04-02",
  "started_at": "2026-04-02T12:00:00.000Z",
  "finished_at": "2026-04-02T12:01:43.221Z",
  "duration_ms": 103221,
  "status": "success",
  "stages": {
    "health_gate": "pass",
    "files_discovered": 10,
    "files_with_content": 3,
    "items_triaged": 18,
    "items_quality_rejected": 1,
    "tasks_written": 7,
    "notes_written": 3,
    "articles_queued": 5,
    "write_verifications": "10/10",
    "email_sent": true
  },
  "files_processed": ["BrainDump — Personal.md", "Coding.md", "BrainDump — Business (Echelon Seven).md"],
  "errors": [],
  "quality_rejections": [
    {"item": "something vague", "reason": "area could not be determined with >70% confidence"}
  ]
}
```

---

## Files Created/Modified

### New Files
| Path | Purpose |
|------|---------|
| `scripts/health-check.py` | Verify MinIO, n8n, sync health |
| `scripts/e2e-test.py` | End-to-end pipeline test |
| `scripts/process-backlog.py` | One-time processor for existing brain dump content |
| `tests/test_brain_dump.py` | pytest suite for process_brain_dump.py |
| `tests/test_health_check.py` | pytest for health-check.py |
| `workflows/n8n/brain-dump-processor-v2.json` | Rebuilt workflow |
| `workflows/n8n/daily-note-creator-v2.json` | Rebuilt workflow |
| `workflows/n8n/overdue-task-alert-v2.json` | Rebuilt workflow |
| `workflows/n8n/weekly-digest-v2.json` | Rebuilt workflow |
| `workflows/n8n/article-processor-v2.json` | Rebuilt workflow |
| `workflows/n8n/system-health-monitor.json` | New workflow |
| `workflows/n8n/error-handler.json` | New workflow |

### Modified Files
| Path | Change |
|------|--------|
| `tools/process_brain_dump.py` | Add section-aware extraction, smart content detection |
| `scripts/setup-n8n.sh` | Add Anthropic credential, update workflow list to v2 |
| `.env.example` | Add ANTHROPIC_API_KEY |
| `gemini.md` | Update task status |
| `CLAUDE.md` | Update with v2 state |

---

## Testing Requirements

**Nothing is marked complete without:**
1. Unit test written and passing (pytest)
2. Integration test against live MinIO (read + write + verify)
3. n8n workflow manually triggered and verified in execution log
4. Output files confirmed to exist in MinIO with correct content
5. Email received and contents verified
6. JSON log file written to `99_System/logs/` with no errors

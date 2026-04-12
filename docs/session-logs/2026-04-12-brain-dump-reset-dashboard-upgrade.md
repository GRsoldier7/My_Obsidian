# Brain Dump Reset + Life OS Dashboard Upgrade

**Date:** 2026-04-12
**Branch:** polish/prod-ready
**Commit:** 069131a

## What Was Broken

1. **Brain dumps were never being cleared.** The processor extracted tasks/articles but left all the content in the template sections, causing them to pile up. Every time Aaron opened a brain dump file, old processed content was still there cluttering it.

2. **Live Dashboard showed 0 for everything** (from the filesystem-v2 binary bug fixed in c25a279) — and even after that fix, it showed plain counters with no actionable hierarchy.

## Brain Dump Reset Fix

**Old approach (broken):** Used regex to find and clear only the sections that were "extracted" during processing. Failed because:
- Emoji characters in section headers (`## ⚡ Quick Notes`) broke regex escaping
- Only cleared headers that matched the `isTask`/`isArticle` detector — missed others
- Left stale content in unmatched sections

**New approach:** Rebuild the entire template from scratch:
1. Extract H1 title from current file (preserves custom branding like "Brain Dump — Business (Echelon Seven)")
2. Extract tags footer line
3. Rebuild all 7 canonical sections with their placeholder comments
4. Update frontmatter: `last_processed: today`, `status: empty`

Result: Every brain dump returns to a perfectly clean, ready-to-use state after processing. Aaron comes back to a blank slate.

## Live Dashboard Upgrade

**Old dashboard:** Plain markdown tables with task counts. Zero urgency hierarchy.

**New dashboard:** 9-section Obsidian callout layout optimized for 30-second daily scan:

```
[!tip]     — #1 Priority Right Now (computed: most critical task)
[!danger]  — 🔥 Overdue (severity tiers: critical 8+d, high 4-7d, medium 1-3d)
[!warning] — 📅 Due Today
[!warning] — 🪨 Priority A with no due date (collapsed)
[!info]    — 📆 Upcoming 7 days (collapsed)
[!note]    — Q2 2026 Rocks with live Priority A count per domain (collapsed)
[!abstract]— Domain Pulse table: 🟢🟡🔴 health, open, overdue, A count (collapsed)
[!success] — ⚡ Quick Wins / Priority C tasks (collapsed)
[!example] — System Status (collapsed)
```

**Key improvements:**
- `#1 Priority` computed dynamically: overdue A > today's A > any overdue > any today > any Priority A
- Q2 Rock progress is now live: shows open Priority A task count per domain, not hardcoded percentages
- Domain health is color-coded: 🟢 no overdue, 🟡 1-2 overdue, 🔴 3+ overdue
- Collapsed sections keep the view clean — urgency visible at a glance, detail one click away

## Verification

- 135 pytest tests passed, 1 skipped
- Live webhook test: 39 tasks read, 7 domains, 7 Priority A rocks
- Both workflows deployed and active in n8n
- `audit_workflow_connections.py` passed (no email-to-log wiring)

# ObsidianHomeOrchestrator — Unified Master Plan (Claude + Codex)
**Date:** 2026-04-12 | Branch: polish/prod-ready

## What Each AI Contributed

**Claude:** Runtime artifact quality (filesystem-v2 binary bug, daily note gap, article queue starvation), brain dump reset redesign, Obsidian callout dashboard, Weekend Planner architectural design.

**Codex:** Code topology (email→log undefined filenames), deploy safety (fail-fast setup-n8n.sh), audit guardrails (audit_workflow_connections.py, test_workflow_templates.py, audit_workflow_credentials.py), integration test fixes.

## 4-Phase Implementation Roadmap

### Phase 0 — Fix Three P0 Open Bugs (Block daily value)
1. **Daily note IF node** — `Not Exists?` routing to skip; notes missing Apr 11–12. Fix: loosen `typeValidation` or rewrite existence check logic.
2. **Article enricher queue starvation** — 117 URLs, 0 enriched. Fix: randomize batch selection so blocked (Facebook/X) URLs don't starve legitimate ones.
3. **Dashboard callouts not persisting** — live hourly run overwrites with old plain-markdown. Fix: verify deployed node code via API; re-deploy if needed; assert `[!tip]` post-deploy.

### Phase 1 — Stabilize Existing Automation
4. Verify brain dump extraction + reset after 7AM CDT run
5. Verify morning briefing email with real task counts
6. Add undated Priority A reminder to daily note template (prompts due date scheduling)
7. Build `scripts/archive-completed-tasks.py` (move `- [x]` lines to monthly archive)

### Phase 2 — Weekend Planner (New Feature)
**Trigger:** Friday 5PM CDT (`0 22 * * 5` UTC)
**Pre-req (manual):** Google Calendar OAuth2 credential in n8n UI → record as `GCAL_CRED_ID` in `.env`
**New files:** `workflows/n8n/weekend-planner.json`, `tests/test_weekend_planner.py`, `docs/google-calendar-setup.md`
**Modified:** `scripts/setup-n8n.sh` (add `__GCAL_CRED_ID__` placeholder + workflow to WORKFLOWS array)

Node graph: Schedule → Set Weekend Dates → Fetch Calendar → S3: Read MTL → Build Weekend Plan → [Email (dead-end) + Build Log → Convert → S3 Log + Convert Note → S3 Vault Note]

Sunday constraint: Church 8:30–11:30 AM hard-blocked. Saturday deep work 8–12 AM = business (Echelon Seven). Sunday post-church 12–2 PM = faith + family.

Outputs: HTML email (morning-briefing.json style) + Obsidian vault note at `40_Timeline_Weekly/Weekend/YYYY-MM-DD-weekend-plan.md`

### Phase 3 — Long Tail
Telegram bot, legacy v1 workflow cleanup, Bitwarden MCP, article enricher v2 (failure-count state), Google Calendar write (v2).

## What NOT to Implement
Playwright NotebookLM auth, regex brain dump reset, email→log sequential wiring, Dataview queries in vault notes, hardcoded Q2 percentages, `|| echo '{}'` in setup scripts.

## System Scorecard After Phase 1 Target: 🟢 85%
Current 🟡 55% — daily note 🔴, articles 🔴, dashboard callouts 🟡, due dates 🔴

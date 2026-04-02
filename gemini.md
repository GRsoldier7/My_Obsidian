# ObsidianHomeOrchestrator — Project Map

## Status: Implementation In Progress (~85% Complete)

## Architecture
- **n8n:** Proxmox LXC at `192.168.1.121:5678`
- **Vault sync:** Obsidian → MinIO `obsidian-vault` bucket prefix `Homelab/` via Remotely Save
- **MinIO:** `192.168.1.240:9000` (S3 API) / `:9001` (console)
- **All n8n workflows use MinIO S3 — NOT filesystem** (see ADR-002)

## Timeline
- 2026-03-21: Project initialized. 19 skills deployed to .claude/commands/
- 2026-03-21: Vault restructured: 6 folders, 3 new files, 4 enhanced, 2 archived
- 2026-03-21: 3 n8n workflows built (brain-dump-processor, daily-note-creator, overdue-task-alert) — NOTE: these used fs module (broken in LXC)
- 2026-03-24: GAP ANALYSIS: Filesystem workflows broken; area taxonomy missing family/home; no weekly digest workflow built
- 2026-03-24: ADR-002 written. All workflows rebuilt for MinIO S3. Weekly digest workflow created.
- 2026-03-29: FULL AUDIT. Found 99.8% failure rate (5,541/5,554). Root causes: PolyChronos running every 2min to dead endpoint, MinIO credential had wrong access key, Weekly Digest merge node misconfigured.
- 2026-03-29: Fixed: new MinIO credential (Claude_Code key), deactivated PolyChronos, fixed merge node, exported all 7 live workflows to repo, added OpenRouter/Llama 3.3 integration, fully parameterized setup-n8n.sh with placeholder system.
- 2026-03-29: CRITICAL DISCOVERY: All S3 paths had `Homelab/` prefix but vault files are at bucket root (no prefix). Remotely Save syncs without prefix. Removed `Homelab/` from all workflow paths. Verified via boto3: North Star, MTL, Brain Dumps all readable.

## What's Actually Built (Correct State)
- [x] Vault folder structure (6 folders created)
- [x] North Star.md, Task Archive.md, Brain dump templates
- [x] Mission Control, Weekly Review, Daily Note, Personal & Life — enhanced
- [x] 8-area taxonomy defined (faith, family, business, consulting, work, health, home, personal)
- [x] ADR-001 (individual file output strategy)
- [x] ADR-002 (MinIO S3 architecture)
- [x] brain-dump-processor.json (rebuilt — MinIO S3, 8 areas, Claude AI)
- [x] daily-note-creator.json (rebuilt — MinIO S3)
- [x] overdue-task-alert.json (rebuilt — MinIO S3 + email)
- [x] n8n-weekly-digest-workflow.json (NEW — reads North Star + MTL, emails Sunday 6PM)
- [x] process_brain_dump.py (updated — 8 areas)
- [x] .env.example (updated — MinIO + SMTP vars)
- [x] CLAUDE.md (updated — 8 areas, current paths)

## Completed (2026-03-29 Audit)
- [x] MinIO S3 credential fixed in n8n (new access key: Claude_Code service account)
- [x] Gmail SMTP (Aaron) credential verified working
- [x] OpenRouter API credential verified working
- [x] All 6 workflows deployed to n8n and active
- [x] PolyChronos Inbox Processor deactivated (was causing 99.8% failure rate)
- [x] Weekly Digest merge node fixed (append mode)
- [x] Brain Dump Processor staticData bug fixed
- [x] Repo synced with live n8n state (7 workflow exports)
- [x] setup-n8n.sh fully rewritten (3 credentials, 6 workflows, placeholder hydration)
- [x] All credential IDs/emails replaced with placeholders in repo
- [x] .gitignore covers .claude/worktrees/
- [x] .env.example has OPENROUTER_API_KEY + consumer docs

## Remaining
- [ ] **Verify Remotely Save** is syncing to MinIO bucket `obsidian-vault` prefix `Homelab/`
- [ ] **Create 8 brain dump files** in vault with correct `domain:` frontmatter
- [ ] **QuickAdd macros** — Quick Task, Brain Dump, Quick Idea, Meeting Note
- [ ] **Bookmarks** — 5 pinned notes for mobile quick access
- [ ] **E2E test** — real brain dump → workflow run → verify tasks appear
- [ ] **Monitor** n8n failure rate over next 24-48h to confirm all fixes hold
- [ ] **PolyChronos** — needs valid endpoint before reactivation

## Q2 2026 Quarterly Rocks
1. 🙏 Faith: Launch social media Bible study (4 sessions delivered)
2. 💒 Family: Complete Marriage Alignment Questionnaire + bi-weekly check-in
3. 🚀 Business: Ship MVP (website live, offer defined, 3 outreach conversations)
4. 🏥 Work: Deliver Union project
5. 💪 Health: Make hip decision + 3x/week gym for 8 weeks

## Context Handoff (2026-03-29)
Full audit and fix session. All n8n credentials and workflows are now live and working. The repo workflow JSONs are templates with placeholders — run `source .env && bash scripts/setup-n8n.sh` for fresh deployments. Live workflows include OpenRouter/Llama 3.3 70B for AI-powered triage and briefings. See `docs/2026-03-29-n8n-audit-and-fix.md` for complete audit trail.

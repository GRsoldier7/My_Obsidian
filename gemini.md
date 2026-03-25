# ObsidianHomeOrchestrator — Project Map

## Status: Implementation In Progress (~65% Complete)

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

## Remaining (requires manual action in n8n / Obsidian)
- [ ] **Create MinIO credential in n8n** — name: `MinIO — obsidian-vault`, endpoint: `192.168.1.240:9000`
- [ ] **Create SMTP credential in n8n** — name: `Gmail SMTP`, Gmail App Password
- [ ] **Import all 4 workflows** into n8n, activate each
- [ ] **Verify Remotely Save** is syncing to MinIO bucket `obsidian-vault` prefix `Homelab/`
- [ ] **Create 8 brain dump files** in vault with correct `domain:` frontmatter
- [ ] **QuickAdd macros** — Quick Task, Brain Dump, Quick Idea, Meeting Note
- [ ] **Bookmarks** — 5 pinned notes for mobile quick access
- [ ] **E2E test** — real brain dump → workflow run → verify tasks appear

## Q2 2026 Quarterly Rocks
1. 🙏 Faith: Launch social media Bible study (4 sessions delivered)
2. 💒 Family: Complete Marriage Alignment Questionnaire + bi-weekly check-in
3. 🚀 Business: Ship MVP (website live, offer defined, 3 outreach conversations)
4. 🏥 Work: Deliver Union project
5. 💪 Health: Make hip decision + 3x/week gym for 8 weeks

## Context Handoff (2026-03-24)
Rebuilt all workflows to use MinIO S3 (ADR-002). User needs to: (1) set up n8n credentials for MinIO + SMTP, (2) import 4 workflow JSONs, (3) verify Remotely Save sync target. Weekly digest workflow is new and high-value — prioritize its setup.

# ObsidianHomeOrchestrator — Project Map

## Status: v2 Implementation In Progress (~75% Complete)

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

## v2 Overhaul (2026-04-02)
- [x] **Full design spec** — `docs/superpowers/specs/2026-04-02-life-os-v2-design.md`
- [x] **Implementation plan** — `docs/superpowers/plans/2026-04-02-life-os-v2-implementation.md`
- [x] **Infrastructure fixed** — Daily/, logs/ folders, BrainDump — Consulting.md created in MinIO
- [x] **Health check** — `scripts/health_check.py` (4/4 checks passing)
- [x] **Python pipeline** — `tools/process_brain_dump.py` fully rewritten: section-aware, regex extraction, OpenRouter cascade
- [x] **51 pytest tests** — all passing (`tests/test_brain_dump.py`, `tests/test_health_check.py`)
- [x] **First extraction** — 1 task + 21 articles written to MinIO (first output in 14 days)
- [x] **Backlog processed** — Personal + Business brain dumps extracted
- [x] **n8n workflow v2 JSONs** — all built and patched (2026-04-07)
- [x] **Email blank-body bug fixed** — emailFormat:html on overdue-v2, weekly-digest-v2, error-handler (2026-04-07)
- [x] **Security fix** — hardcoded MinIO creds removed from daily-note-creator-v2 (rotate key in MinIO console!)
- [x] **S3 log binary fix** — binary conversion nodes added to overdue-v2, weekly-digest-v2 so log writes succeed
- [x] **Cron timezone fix** — America/Chicago added to all 11 scheduleTrigger nodes
- [x] **Keyword expansion** — consulting/home/personal areas added to Q2_ROCK_KEYWORDS
- [x] **NEW: morning-briefing.json** — replaces separate overdue+daily emails; rich HTML; 7AM CDT
- [x] **NEW: telegram-capture.json** — Telegram bot webhook → brain dump / article queue (needs TELEGRAM_BOT_TOKEN)
- [x] **NEW: live-dashboard-updater.json** — hourly dashboard note at 000_Master Dashboard/Live Dashboard.md
- [x] **DONE: MinIO key rotated** — 2026-04-08. New key active. `.env` updated. n8n credential [MINIO_CRED_ID] still needs updating in n8n UI.
- [x] **All 11 workflows deployed and ACTIVE** — 2026-04-08. Fixed timezone-in-rule bug (not supported by this n8n version). Imported directly via n8n API.
- [ ] **Register Telegram webhook** — create bot via @BotFather, set TELEGRAM_BOT_TOKEN, run curl setWebhook
- [ ] **Disable v1 workflows** in n8n — brain-dump-processor, daily-note-creator, overdue-task-alert, weekly-digest (replaced by v2)
- [ ] **Disable overdue-task-alert-v2** once morning-briefing is live (it subsumes it)
- [ ] **E2E test** — `scripts/e2e_test.py`

## Context Handoff (2026-04-02)
v2 overhaul session. Root cause: system ran 14 days without processing a single brain dump. Fixed: section-aware extraction, smart content detection, regex extraction (zero AI cost), OpenRouter cascade for AI enhancement, verified writes, JSON run logs. Python pipeline proven working. n8n workflow v2 JSONs being built for import. API key needs regeneration for automated deployment. See design spec and implementation plan in `docs/superpowers/`.

## 2026-04-07 Session 2 — Full Security Audit + New Workflows

### Security Fixes (All Compromised Credentials Removed)
- [x] **CRITICAL**: Removed hardcoded MinIO key from `tools/process_brain_dump.py`
- [x] **CRITICAL**: Removed hardcoded MinIO key from `scripts/e2e_test.py`
- [x] **CRITICAL**: Removed hardcoded MinIO key from `scripts/health_check.py`
- [x] **CRITICAL**: Removed hardcoded MinIO key from `docs/superpowers/plans/2026-04-02-life-os-v2-implementation.md` (18 occurrences)
- [x] **CRITICAL**: Removed hardcoded MinIO key from `gemini.md`, `docs/2026-03-29-n8n-audit-and-fix.md`
- [x] **CRITICAL**: Removed hardcoded MinIO key + OpenRouter key from `workflows/n8n/job-search-pipeline.json`
- [x] **CRITICAL**: Removed hardcoded keys from `workflows/n8n/minio-http-upload-pattern.json` and `minio-upload-node-snippet.json`
- [x] Full repo scan: 215 files scanned → 0 remaining compromised credentials
- [x] Confirmed: `.env` is gitignored and NOT tracked in git

### Workflow Bug Fixes
- [x] **brain-dump-processor-v2.json** — Build Output Files now returns 3 binary fields (taskFile, resetFile, logFile); S3 upload nodes updated with correct binaryPropertyName. Silent empty-file writes fixed.
- [x] **e2e_test.py** — JSON parsing replaced: fragile `re.findall(r'\{[^{}]*\}')` → robust `stdout.rfind('{')` approach

### New Workflows Built
- [x] **link-enricher.json** — Hourly: reads articles-to-process.md, fetches og:title + og:description for unenriched URLs (max 8/run), writes back enriched lines. SSRF protection: blocks private IPs, localhost, metadata endpoints.
- [x] **vault-health-report.json** — Sunday 8PM CDT: lists brain dump files, article queue stats (enriched vs unenriched), processed-this-week count. HTML email with status badge (HEALTHY / OK / NEEDS ATTENTION).

### Security Hardening
- [x] **SSRF protection** added to link-enricher.json Parse node — blocks RFC-1918 private ranges, localhost, link-local, .internal/.local hostnames
- [x] **Telegram webhook verification** — verify-webhook-secret node added to telegram-capture.json. Checks X-Telegram-Bot-Api-Secret-Token header against $env.TELEGRAM_WEBHOOK_SECRET

### Setup Script Updated
- [x] **setup-n8n.sh** WORKFLOWS array updated: now imports all 11 v2 + new workflows
- [x] Next steps section updated with MinIO key rotation, Telegram setup, and webhook registration instructions

## Current Workflow Inventory (20 JSON files, all valid)
| File | Status | Description |
|------|--------|-------------|
| brain-dump-processor-v2.json | ✅ Ready | Daily 7AM — extracts tasks from brain dumps |
| daily-note-creator-v2.json | ✅ Ready | 6AM CDT — creates daily note from MTL |
| overdue-task-alert-v2.json | ✅ Ready | 8AM CDT — overdue task email |
| weekly-digest-v2.json | ✅ Ready | Sunday 6PM — weekly rock review |
| error-handler.json | ✅ Ready | Global error capture + email |
| morning-briefing.json | ✅ Ready | 7AM CDT — full daily briefing email |
| telegram-capture.json | ✅ Ready (+webhook auth) | Instant brain dump/article capture |
| live-dashboard-updater.json | ✅ Ready | Hourly — updates Obsidian dashboard |
| link-enricher.json | ✅ NEW | Hourly — enriches article URLs with titles |
| vault-health-report.json | ✅ NEW | Sunday 8PM — inbox health email |
| system-health-monitor.json | ✅ Ready | Every 6h — infra health check |

## Remaining Blockers (user action required)
1. **ROTATE MinIO key** — `[REDACTED_MINIO_ACCESS_KEY]` is compromised. MinIO console: http://192.168.1.240:9001 → Identity → Service Accounts → delete → create new → update n8n credential [MINIO_CRED_ID] AND update `.env`
2. **Import workflows** — re-import all 11 workflows via setup-n8n.sh or n8n UI
3. **Telegram setup** — create bot via @BotFather → set TELEGRAM_BOT_TOKEN + TELEGRAM_WEBHOOK_SECRET in n8n env → run setWebhook curl
4. **n8n env vars** — set WEBHOOK_URL, N8N_ENCRYPTION_KEY on Proxmox LXC CT-202
5. **Disable v1 workflows** — after v2 confirmed working
6. **E2E test** — `source .env && python3 scripts/e2e_test.py`

## 2026-04-08 Session 3 — MinIO Rotation, E2E Fix, Bitwarden MCP

### Completed
- [x] **MinIO key rotated** — New key active in `.env`. Old compromised key invalidated.
- [x] **E2E test fixed and passing** — 11/11 checks. Fixed `IndentationError` (orphaned duplicate code in `run_processor()`).
- [x] **`set -a` pattern established** — `.env` uses bare `VAR=value` (no `export`), so child processes need `set -a && source .env && set +a`. Updated `setup-n8n.sh` usage comment.
- [x] **Bitwarden MCP configured** — `~/.claude/settings.json` updated with self-hosted Vaultwarden at `https://vault.tailfab8a7.ts.net:8443`. Requires `bw` CLI install + session token.

### Remaining Blockers (Next Session)
1. **Add SMTP_PASS to `.env`** — Gmail App Password needed for setup-n8n.sh
2. **Update n8n MinIO credential** — UI: Credentials → MinIO S3 (`[MINIO_CRED_ID]`) → update access/secret key
3. **Run `set -a && source .env && set +a && bash scripts/setup-n8n.sh`** — deploys all 11 workflows
4. **Bitwarden MCP activation** — install `bw` CLI → `bw config server https://vault.tailfab8a7.ts.net:8443` → `bw login` → `bw unlock --raw` → paste token in `~/.claude/settings.json` → restart Claude Code
5. **Telegram bot** — @BotFather → TELEGRAM_BOT_TOKEN + TELEGRAM_WEBHOOK_SECRET → n8n env vars → setWebhook
6. **Disable v1 workflows** after v2 confirmed working in n8n

## 2026-04-08 Session 3 Addendum — Workflow Deployment

### Completed
- [x] **MinIO n8n credential updated** — new rotated key applied via API
- [x] **All 11 v2 workflows ACTIVE** in n8n
- [x] **Timezone bug fixed** — `timezone` inside scheduleTrigger `rule` object not supported by this n8n version. Removed from all 15 workflow files. Use UTC-adjusted cron expressions instead.
- [x] **Duplicate cleanup** — old garbled-name Brain Dump v2 deactivated; Daily Note Creator v4 deactivated
- [x] **Source files synced** — all 15 workflow JSONs patched to remove timezone from scheduleTrigger

### Still Pending (tomorrow)
1. Add SMTP_PASS to `.env` (Gmail App Password) — for future `setup-n8n.sh` re-runs
2. Update n8n OpenRouter credential with new key (rotate at openrouter.ai first)
3. Bitwarden MCP: install `bw` CLI → login → `bw unlock --raw` → update `~/.claude/settings.json` → restart Claude Code
4. Telegram bot: @BotFather → TELEGRAM_BOT_TOKEN + TELEGRAM_WEBHOOK_SECRET → n8n Settings > Variables → setWebhook curl
5. Consider git history cleanup (`git filter-repo`) if repo goes public

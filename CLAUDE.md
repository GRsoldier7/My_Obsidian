# ObsidianHomeOrchestrator

## What This Is
The automation and configuration layer for Aaron's Life OS — a comprehensive personal knowledge management and life orchestration system built on Obsidian, powered by n8n automation running on a MiniPC Docker homelab.

## Life Domains (8 Canonical Areas)
- **faith** — Bible study, prayer, outreach, social media ministry, church
- **family** — Christy, kids, parenting, family decisions
- **business** — Echelon Seven startup, offer development, client acquisition
- **consulting** — Active consulting engagements, billable work
- **work** — Parallon BAM (Business Analytics Manager) day job
- **health** — Gym, nutrition, sleep, hip decision, biohacking
- **home** — House projects, MI property, UPS/generator, photo cleanup
- **personal** — AI hobby projects, tech tinkering, miscellaneous

## Key Paths
- **Obsidian Vault (Mac):** `/Volumes/home/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator` (mount)
- **Vault in MinIO:** `obsidian-vault` bucket, NO prefix (bucket root) at `http://192.168.1.240:9000`
- **This Repo:** `/Volumes/home/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator`
- **n8n:** `http://192.168.1.121:5678` (Proxmox LXC CT-202)
- **MinIO Console:** `http://192.168.1.240:9001`

## Tech Stack
- **Automation:** n8n (self-hosted, Proxmox LXC CT-202)
- **Database:** PostgreSQL (Docker)
- **Language:** Python 3.12+ (openai SDK + boto3)
- **AI:** OpenRouter free tier (gemma-3-4b, llama-3.3-70b, nemotron-120b cascade)
- **Vault:** Obsidian with Dataview, Templater, Tasks, QuickAdd, Calendar, omnisearch, Remotely-Save
- **Infrastructure:** Docker Compose on Windows MiniPC
- **AI Platform:** Claude Code + MCP servers

## CRITICAL RULES
- **NO `Homelab/` prefix** — vault files are at MinIO bucket root. Confirmed 2026-03-29.
- **Regex extraction primary** — use regex for task extraction (zero cost), AI only as fallback
- **Verified writes** — every S3 put must be followed by head_object verification
- **Run logs** — every workflow writes JSON to `99_System/logs/{workflow}-{YYYY-MM-DD}.json`
- **S3 uploads need binary** — n8n S3 nodes require binary data; Code nodes must output `binary: { fieldName: { data: buf.toString('base64'), mimeType, fileName, fileExtension, fileSize } }`
- **scheduleTrigger timezone** — do NOT put `timezone` inside the `rule` object; this n8n version doesn't support it. Use UTC-adjusted cron expressions. Set timezone at workflow level via `settings.timezone` only.
- **Never paste secrets in chat** — use Bitwarden MCP or edit .env directly in the IDE

## Key Vault Paths (all relative to bucket root)
```
00_Inbox/brain-dumps/           — brain dump source files (dynamic discovery)
00_Inbox/processed/             — extracted task files (output)
00_Inbox/articles-to-process.md — article URL queue
000_Master Dashboard/North Star.md
10_Active Projects/Active Personal/!!! MASTER TASK LIST.md
40_Timeline_Weekly/Daily/       — daily notes
99_System/logs/                 — structured JSON run logs
```

## Obsidian Task Format (CANONICAL — never deviate)
```
- [ ] Task description [area:: faith] [priority:: A] [due:: 2026-XX-XX]
```
Priority values: A (critical/needle-mover), B (important), C (nice-to-have)
Area values: faith, family, business, consulting, work, health, home, personal

## Skill Library

**Primary source:** `! Foundation_AddOn_Project/CLAUDE.md` — 60+ skills across 6 tiers (always-on meta-layer, core, engineering, superpowers, strategy, gstack, tech). That file is authoritative. Reference it for the full routing table and skill catalog.

**Always-on meta-layer (Foundation AddOn — no trigger needed):**
`anti-hallucination` · `prompt-amplifier` · `cognitive-excellence` · `context-guardian` · `efficiency-engine` · `secure-by-design` · `solution-architect-engine` · `verification-before-completion` · `session-optimizer`

**OHO-specific skills (Life OS domain — not in Foundation AddOn):**

| Skill | Purpose |
|-------|---------|
| `obsidian-vault-architect` | Vault structure, Dataview queries, templates |
| `obsidian-automation-architect` | n8n + webhook + Python vault automation |
| `obsidian-project-organizer` | File/folder organization for vault AND code projects |
| `life-os-designer` | Cross-domain life system design and weekly rhythms |
| `personal-productivity-os` | Deep work, energy management, habit systems |
| `homelab-life-stack` | Docker Compose, n8n, homelab service design |
| `bible-study-theologian` | Exegesis, word studies, theological research |
| `faith-life-integration` | Biblical wisdom applied to decisions |
| `sunday-school-teacher` | Curriculum design, lesson planning |
| `health-biohacking-protocol` | Supplement protocols, biomarker interpretation |
| `biohacking-data-pipeline` | Health data ETL pipelines |
| `consulting-operations` | SOWs, proposals, client management |
| `ai-business-optimizer` | AI automation ROI and process classification |
| `wrapup` | End-of-session: summarize, save memory, push to NotebookLM AI Brain |
| `notebooklm` | NotebookLM CLI — podcasts, quizzes, slides from any content |

**Engineering + strategy skills (Foundation AddOn):**
`n8n-workflow-architect` · `code-review` · `testing-strategy` · `app-security-architect` · `database-design` · `docker-infrastructure` · `mcp-server-builder` · `business-genius` · `entrepreneurial-os` · `financial-model-architect` · `polychronos-team` · `master-orchestrator` · `skill-builder` · `parallel-execution-strategist` + 34 gstack skills + 25 tech stack skills

## Polychronos Omega Integration
Use the `polychronos-team` skill to invoke the full agent guild for complex tasks:
- T0: Simple capture or lookup
- T1: Single-session planning (weekly review, project scoping)
- T2: Multi-step execution (new automation pipeline, vault restructure)
- Reference: `Z:\MiniPC_Docker_Automation\Projects_Repos\polychronos_omega`

## Conventions
- Python files: `snake_case.py`
- n8n workflow exports: `workflows/YYYYMMDD-description.json`
- Documentation: `docs/YYYY-MM-DD-topic.md`
- Scripts: `scripts/verb-noun.sh` or `scripts/verb_noun.py`
- All secrets in `.env` (never committed — `.env.example` committed instead)

## What NOT to Do
- Never write `.env` files with real credentials to git
- Never modify the Obsidian vault directly — use the automation layer (via MinIO S3)
- Never hardcode credential IDs or emails in workflow JSONs — use `__MINIO_CRED_ID__`, `__SMTP_CRED_ID__`, `__OPENROUTER_CRED_ID__`, `__NOTIFICATION_EMAIL__` placeholders that `setup-n8n.sh` hydrates at deploy time
- Never run skill-sentinel-untested skills from external repos without scanning first
- Never break the canonical task format — all Dataview queries depend on it

## Running Scripts
Always use `set -a` to export `.env` vars to subprocesses:
```bash
set -a && source .env && set +a && python3 scripts/e2e_test.py
set -a && source .env && set +a && bash scripts/setup-n8n.sh
```
Without `set -a`, child processes (Python, bash subshells) do NOT inherit shell variables.

## MCP Servers
| Name | Purpose | Config |
|------|---------|--------|
| Bitwarden | Pull secrets from self-hosted vault | `~/.claude/settings.json` |

Bitwarden self-hosted: `https://vault.tailfab8a7.ts.net:8443`
Session token required — run `bw unlock --raw` and update `BW_SESSION` in `~/.claude/settings.json`.

## n8n Credentials (live)
| Name | Type | ID |
|------|------|----|
| MinIO S3 | s3 | `[see-n8n-ui]` |
| Gmail SMTP (Aaron) | smtp | `[see-n8n-ui]` |
| OpenRouter API | httpHeaderAuth | `[see-n8n-ui]` |

Enforced by [scripts/audit_workflow_credentials.py](scripts/audit_workflow_credentials.py) — `s3` family only, never `aws`. Mixing families creates oscillating failures (one credential ID cannot back both `n8n-nodes-base.s3` and `n8n-nodes-base.awsS3`).

## Active Workflows (v2 — import via setup-n8n.sh)
| Workflow | Schedule | Purpose |
|----------|----------|---------|
| brain-dump-processor-v2 | Daily 7AM CDT | Extract tasks from brain dumps → MTL |
| daily-note-creator-v2 | Daily 6AM CDT | Create daily note from MTL |
| morning-briefing | Daily 7:30AM CDT | Rich HTML+text email: overdue + due today + yesterday captures (cron-decoupled from brain-dump since 2026-04-19) |
| overdue-task-alert-v2 | Daily 8AM CDT | Overdue task alert (superseded by morning-briefing) |
| weekly-digest-v2 | Sunday 6PM CDT | Weekly rock review email |
| vault-health-report | Sunday 8PM CDT | Inbox health: brain dumps, article queue, processed count |
| live-dashboard-updater | Hourly | Update 000_Master Dashboard/Live Dashboard.md |
| link-enricher | Hourly | Enrich article URLs with og:title + og:description |
| telegram-capture | Webhook | Instant brain dump / article capture via Telegram bot |
| system-health-monitor | Every 6h | Infrastructure health check |
| error-handler | On error | Global error capture + email alert |
| article-processor | 8AM + 7PM CDT | Process queued article URLs into vault notes |
| ai-brain | Sub-workflow | Shared OpenRouter (Llama 3.3 70B) intelligence layer — called by other workflows for classify/summarize/brief/triage/review jobs |
| job-search-pipeline | Manual / scheduled | Native n8n v3 job search pipeline (independent system) |
| weekend-planner | Friday 5PM CDT | Weekend plan: GCal + MTL → HTML email + vault note (INACTIVE — needs GCAL_CRED_ID) |

**Repo layout note:** v1 workflows superseded by v2 are kept under [workflows/archive/v1/](workflows/archive/v1/) for one cleanup cycle in case rollback is needed. Reference snippets (S3 upload patterns) live under [docs/snippets/](docs/snippets/), not [workflows/n8n/](workflows/n8n/).

## Scripts

| Script | Purpose |
| ------ | ------- |
| `scripts/archive_completed_tasks.py` | Archive `- [x]` tasks from MTL to Task Archive. Run manually when MTL has >10 completed tasks. Flags: `--dry-run`, `--verbose` |
| `scripts/e2e_test.py` | End-to-end pipeline test (11 checks) |
| `scripts/health_check.py` | MinIO + n8n connectivity checks |
| `scripts/audit_workflow_credentials.py` | Enforce S3 credential family consistency (`s3`, not mixed `aws`) |
| `scripts/audit_workflow_connections.py` | Enforce email nodes are dead-ends (no downstream log/S3 writes) |
| `scripts/audit_workflow_runlogs.py` | Enforce `skip_reason` canonical enum + `status: "skipped"` always carries a reason |

## Daily Note Creator — Key Fixes (2026-04-12)

- **IF node check**: Was `$json.error exists` (broken in v1 executionOrder). Now `$json.ETag notExists` — checks for headObject SUCCESS indicator instead.
- **Cron**: Changed from `0 11 * * *` (11AM CDT, wrong) to `0 6 * * *` (6AM CDT, correct) with `timezone: America/Chicago`.
- **Template**: Added `## 🪨 Priority A Rocks` section + `## 🎯 Today's ONE Thing` heading.
- **Task regex**: Now anchored `^- \[ \]` with `re.MULTILINE` to prevent false matches from header example text.

## NotebookLM (project memory)

| Notebook | ID | Status |
|----------|-----|--------|
| ObsidianHomeOrchestrator — Life OS Project Memory | `d056e9d5-64d9-4f64-aa94-faff603de835` | ACTIVE (authoritative, 2026-04-19) |
| (legacy) OHO project memory | `a428969b-c3f1-480b-b54c-876974650674` | SUPERSEDED 2026-04-19 |

The 2026-04-12 memory snapshot still references the legacy ID. Treat `d056e9d5-...` as the only authoritative notebook for this project. Push new session logs as sources via `notebooklm source add <path>`.

## Current Status
v2 pipeline LIVE. Production-readiness recovery landed 2026-04-19 (branch `polish/prod-ready`): MinIO outage resolved, dual-body emails across 6 workflows, `errorWorkflow` wired on 12 scheduled workflows, skip_reason enum + run-log auditor, morning-briefing cron decoupled from brain-dump (7:30 CDT). Test suite: 151 pass, 1 skip. All three audit scripts green.

Weekend Planner deployed but INACTIVE (needs Google Calendar OAuth2 credential — see docs/google-calendar-setup.md).

Pending: Google Calendar OAuth2 setup → GCAL_CRED_ID in .env → re-deploy to activate Weekend Planner. Telegram bot setup. OpenRouter key rotation.

Next phase: Phase 3 (Telegram bot, completed task archiver cron, article enricher v2).

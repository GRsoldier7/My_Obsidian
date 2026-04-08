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

## Installed Skills (.claude/commands/)

### Core & Orchestration
| Skill | Purpose |
|-------|---------|
| `polychronos-team` | Multi-agent orchestration (B.L.A.S.T. protocol) |
| `master-orchestrator` | Skill routing and chaining layer |
| `skill-builder` | Build new custom skills |
| `skill-sentinel` | Security scanner for AI skills before deployment |
| `prompt-amplifier` | Prompt enhancement engine |
| `portable-ai-instructions` | Generate CLAUDE.md/AGENTS.md for any project |
| `knowledge-management` | PKM architecture and documentation systems |

### Life OS & Productivity
| Skill | Purpose |
|-------|---------|
| `obsidian-vault-architect` | Vault structure, Dataview, templates |
| `obsidian-automation-architect` | n8n + webhook + Python vault automation |
| `obsidian-project-organizer` | File/folder organization for vault AND code projects |
| `life-os-designer` | Cross-domain life system design |
| `personal-productivity-os` | Deep work, energy management, habit systems |

### Infrastructure & Engineering
| Skill | Purpose |
|-------|---------|
| `homelab-life-stack` | Docker Compose, n8n, homelab service design |
| `n8n-workflow-architect` | n8n workflow design and automation architecture |
| `docker-infrastructure` | Docker/container infrastructure for self-hosted envs |
| `mcp-server-builder` | MCP server design and deployment |
| `app-security-architect` | OWASP, zero-trust, AI/LLM security |
| `code-review` | Security and correctness review hierarchy |
| `database-design` | PostgreSQL schema design |
| `testing-strategy` | pytest patterns, TDD, integration testing |
| `data-analytics-engine` | SQL, dashboards, statistical analysis |

### Life Domains
| Skill | Purpose |
|-------|---------|
| `bible-study-theologian` | Exegesis, word studies, theological research |
| `faith-life-integration` | Biblical wisdom applied to decisions |
| `sunday-school-teacher` | Curriculum design, lesson planning |
| `health-biohacking-protocol` | Supplement protocols, biomarker interpretation |
| `biohacking-data-pipeline` | Health data ETL pipelines |
| `consulting-operations` | SOWs, proposals, client management |

### Business & Strategy
| Skill | Purpose |
|-------|---------|
| `entrepreneurial-os` | Business strategy and operating rhythm |
| `ai-business-optimizer` | AI automation ROI and process classification |
| `business-genius` | Business strategy with 15 specialist sub-skills |
| `financial-model-architect` | SaaS metrics, revenue modeling |

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
- Never modify the Obsidian vault directly — use the automation layer
- Never hardcode vault paths — use `OBSIDIAN_VAULT_PATH` env var
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
| MinIO S3 | aws | `z9qTyG2NVVbhHkg0` |
| Gmail SMTP (Aaron) | smtp | `lWGOwsktldwb3iEj` |
| OpenRouter API | httpHeaderAuth | `Z7liUYc3Toq3q7W7` |

## Active Workflows (v2 — import via setup-n8n.sh)
| Workflow | Schedule | Purpose |
|----------|----------|---------|
| brain-dump-processor-v2 | Daily 7AM CDT | Extract tasks from brain dumps → MTL |
| daily-note-creator-v2 | Daily 6AM CDT | Create daily note from MTL |
| morning-briefing | Daily 7AM CDT | Rich HTML email: overdue + due today + yesterday captures |
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

**Repo layout note:** v1 workflows superseded by v2 are kept under [workflows/archive/v1/](workflows/archive/v1/) for one cleanup cycle in case rollback is needed. Reference snippets (S3 upload patterns) live under [docs/snippets/](docs/snippets/), not [workflows/n8n/](workflows/n8n/).

## Current Status
v2 pipeline LIVE (2026-04-08). All 14 v2 + sub-workflows active in n8n. E2E test 11/11 passing. MinIO key rotated.
Pending: SMTP_PASS in .env (for future credential re-deployment), Telegram bot setup, OpenRouter key rotation, Bitwarden MCP activation.
See gemini.md for full task history.

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
- **Vault in MinIO:** `obsidian-vault` bucket, prefix `Homelab/` at `http://192.168.1.240:9000`
- **This Repo:** `/Volumes/home/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator`
- **n8n:** `http://192.168.1.121:5678` (Proxmox LXC CT-202)
- **MinIO Console:** `http://192.168.1.240:9001`

## Tech Stack
- **Automation:** n8n (self-hosted Docker on MiniPC)
- **Database:** PostgreSQL (Docker)
- **Language:** Python 3.12+
- **Vault:** Obsidian with Dataview, Templater, Tasks, QuickAdd, Calendar, omnisearch, Remotely-Save
- **Infrastructure:** Docker Compose on Windows MiniPC
- **AI Platform:** Claude Code + MCP servers

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

## Current Status
Active development — MinIO S3 architecture (ADR-002). All n8n workflows rebuilt for LXC + MinIO access. See gemini.md for task-level status.

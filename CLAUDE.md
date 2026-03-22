# ObsidianHomeOrchestrator

## What This Is
The automation and configuration layer for Aaron's Life OS — a comprehensive personal knowledge management and life orchestration system built on Obsidian, powered by n8n automation running on a MiniPC Docker homelab.

## Life Domains
- **work** — Parallon BAM (Business Analytics Manager) role
- **consulting** — High-end AI automation and efficiency consulting
- **business** — Business startup ventures and products
- **personal** — Family, life admin, relationships, finances
- **faith** — Spiritual practice and reflection
- **health** — Biohacking, supplements, biomarkers, fitness

## Key Paths
- **Obsidian Vault:** `C:\Users\Admin\Desktop\Desktop Folders\Obsidian\Homelab`
- **This Repo:** `Z:\MiniPC_Docker_Automation\Projects_Repos\ObsidianHomeOrchestrator`
- **Polychronos Omega:** `Z:\MiniPC_Docker_Automation\Projects_Repos\polychronos_omega`

## Tech Stack
- **Automation:** n8n (self-hosted Docker on MiniPC)
- **Database:** PostgreSQL (Docker)
- **Language:** Python 3.12+
- **Vault:** Obsidian with Dataview, Templater, Tasks, QuickAdd, Calendar, omnisearch, Remotely-Save
- **Infrastructure:** Docker Compose on Windows MiniPC
- **AI Platform:** Claude Code + MCP servers

## Obsidian Task Format (CANONICAL — never deviate)
```
- [ ] Task description [area:: work] [priority:: A] [due:: 2026-XX-XX]
```
Priority values: A (highest), B (normal), C (low)
Area values: work, consulting, business, personal, faith, health

## Installed Skills (.claude/commands/)
| Skill | Purpose |
|-------|---------|
| `polychronos-team` | Multi-agent orchestration (B.L.A.S.T. protocol) |
| `obsidian-vault-architect` | Vault structure, Dataview, templates |
| `obsidian-automation-architect` | n8n + webhook + Python vault automation |
| `obsidian-project-organizer` | File/folder organization for vault AND code projects |
| `life-os-designer` | Cross-domain life system design |
| `personal-productivity-os` | Deep work, energy management, habit systems |
| `homelab-life-stack` | Docker Compose, n8n, homelab service design |
| `skill-sentinel` | Security scanner for AI skills before deployment |
| `skill-builder` | Build new custom skills |
| `entrepreneurial-os` | Business strategy and operating rhythm |
| `ai-business-optimizer` | AI automation ROI and process classification |
| `business-genius` | Business strategy with 15 specialist sub-skills |
| `financial-model-architect` | SaaS metrics, revenue modeling |
| `portable-ai-instructions` | Generate CLAUDE.md/AGENTS.md for any project |
| `prompt-amplifier` | 6-layer prompt enhancement |
| `biohacking-data-pipeline` | Health data ETL pipelines |
| `code-review` | Security and correctness review hierarchy |
| `database-design` | PostgreSQL schema design |
| `testing-strategy` | pytest patterns, TDD, integration testing |

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
Active development — building the automation and skill layer.

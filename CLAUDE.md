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
- **Code-node task-runner slots** — never schedule two Code-heavy workflows at the same cron minute (n8n task runner stalls at the 60s default; 2026-04-29 incident). Slots in use: `:03` live-dashboard, `:13` link-enricher, `:23` article-processor, `:30` morning-briefing, `:33` system-health-monitor. Open: `:43`, `:53`. Enforced by `tests/test_workflow_templates.py::test_code_heavy_workflows_do_not_share_cron_minutes`. All Code nodes must set `retryOnFail: true, maxTries: 3, waitBetweenTries: 5000`. Recovery playbook: `docs/RUNBOOK.md` § Task-Runner Recovery.
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

**Superpowers default (project-scoped, 2026-05-03):** the 9 always-on Foundation AddOn skills are symlinked into [.claude/skills/](.claude/skills/) by [scripts/sync_foundation_skills.sh](scripts/sync_foundation_skills.sh). They activate automatically without explicit invocation; re-run the sync script after pulling Foundation AddOn updates.

**Always-on meta-layer:**
`anti-hallucination` (proportional verification + 60% escalation) · `context-guardian` (60-79% AMBER, 80%+ RED) · `cognitive-excellence` · `efficiency-engine` · `prompt-amplifier` · `secure-by-design` · `session-optimizer` · `solution-architect-engine` · `verification-before-completion`

**Primary source (upstream):** https://github.com/GRsoldier7/-Foundational-Add-on-Project — local clone at `! Foundation_AddOn_Project/`. CLAUDE.md there has the full 60+ skill routing table across 6 tiers (core, engineering, superpowers, strategy, gstack, tech).

**Canonical AI tooling registry:** [docs/AI_TOOLING.md](docs/AI_TOOLING.md) is the source of truth for which Skills, MCPs, plugins, and tools are user-level shared vs OHO project-local. [AGENTS.md](AGENTS.md) mirrors the critical rules for Codex/OpenAI agents. Run `make audit-ai-tooling` after changing AI instructions, `.mcp.example.json`, or this tooling registry.

**Anti-hallucination — practical rules in this repo:**
- File-grounded claims: re-read with the Read tool before citing specific content; in any session past the AMBER threshold, never paraphrase from memory.
- External APIs: anything not seen in current session = LIKELY at best; flag for verification.
- Versions/dates/numbers: VERIFIED only with a current-context source; otherwise use ranges or "verify current".
- Pushback signal: stop, re-read, acknowledge, correct, identify the cause. Never defend a hallucination.
- Confidence labels: VERIFIED · LIKELY · UNCERTAIN · SPECULATIVE · UNKNOWN. Never present LIKELY+ as VERIFIED.

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
Use [docs/AI_TOOLING.md](docs/AI_TOOLING.md) as the canonical MCP registry.

Project-local examples live in [.mcp.example.json](.mcp.example.json). Live `.mcp.json` files are ignored and must not be committed.

Shared no-secret MCPs that are useful across projects may be registered in `~/.claude/settings.json` (for example `context7`, `playwright`, `memory`, `sequential-thinking`). Credentialed MCPs such as Bitwarden, GitHub, and Postgres need scoped credentials before registration.

Bitwarden self-hosted: `https://vault.tailfab8a7.ts.net:8443`. Session token required — run `bw unlock --raw` and update `BW_SESSION` only in user-level local config, never in this repo.

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

| Notebook | ID | Account | Status |
|----------|-----|---------|--------|
| ObsidianHomeOrchestrator — Life OS Project Memory | `d056e9d5-64d9-4f64-aa94-faff603de835` | `authuser=1` | ACTIVE — canonical project memory. CLI is auth'd to authuser=1 as of 2026-05-11. |
| (stale) `a428969b-c3f1-480b-b54c-876974650674` | — | — | RPC null as of 2026-05-11. Do not use. |
| (stale) `844aa6a1-e3fc-4d75-af9e-d4653a755ae3` | — | — | RPC null as of 2026-05-11. Do not use. |
| (deleted) `fee28c3f-9fba-4567-9457-88dea5cec838` | — | `authuser=0` | Authuser=0 fallback created + deleted 2026-05-11 during the auth migration. |

**Two-account caveat (historical — fully reconciled 2026-05-11):** Aaron's canonical NotebookLM workspace lives on `authuser=1`. CLAUDE.md previously misdiagnosed `d056e9d5-…` as a "phantom" because the `notebooklm` CLI was auth'd to `authuser=0`. Re-authenticated via the Playwright login script (`/tmp/nlm_login.py`, runs from any subprocess context — see the [notebooklm skill](.claude/skills/notebooklm/SKILL.md) for the canonical helper). Never use `notebooklm login` directly — it requires interactive terminal stdin unavailable inside Claude Code.

**Push workflow:**

```bash
notebooklm use d056e9d5-64d9-4f64-aa94-faff603de835
notebooklm source add <path> --title "<title>"
```

ID mirrored in [.claude/nlm-notebook-ids.env](.claude/nlm-notebook-ids.env) (`NLM_PROJECT_NOTEBOOK_ID`) and [.claude/notebooklm.json](.claude/notebooklm.json).

## Current Status

**Reframe 2026-05-03:** OHO is a personal **Life Operating System** across 8 domains, not a brain-dump pipeline. v1.0 roadmap below; task-level threading explicitly wanted.

**Branch:** `polish/prod-ready`, **55 commits ahead** of `master`. **PR #2 open + MERGEABLE since 2026-05-11** (`P0 + P1 + P1.5 + ADR-0006 — Life OS v1.0 foundation (live in prod)`). Four milestone waves landed this session (`179a03b` → `097892a` → `a1bd438` → `00cf972`). **Soak window** (per [ADR-0007](docs/adr/0007-master-plan-v2.md) Phase A): runs ≥7 days clean before Phase C — earliest exit **2026-05-18**.

**Test suite:** **326 pass, 1 skip** (was 311 mid-session, 202 pre-P1). All 5 audits green: workflow-credentials, workflow-connections, workflow-runlogs, extraction-receipts, ai-tooling.

### What's landed (code complete, deployment pending)

**P0 — stop the bleed (2026-05-03, `2b518b1`).** Recovered the brain-dump pipeline from 11 days of silent skipped runs: timezone-double-offset crons fixed, MinIO list step migrated to native `n8n-nodes-base.s3` (`s3` family, not mixed `awsS3`), `minio_auth_error` / `minio_list_failed` added to the canonical skip_reason enum, NotebookLM ID drift reconciled.

**P1 — integrity layer (ADR-0005, `f3f8325` → `947e507`).** State machine + content-hash receipts + gated reset. Pure-functions kernel in [tools/bd_integrity.py](tools/bd_integrity.py). Migration script for the 11 existing brain-dump files. Fail-fast audit ([scripts/audit_extraction_receipts.py](scripts/audit_extraction_receipts.py)) wired into the weekly vault-health-report. LXC deployment runbook + read-only readiness checker.

**P1.5 — HTTP-runner pivot (ADR-0005 revision, `a1bd438`).** n8n 2.18.5 dropped `executeCommand` from the active-workflow registry; the boundary moved to a hardened FastAPI sidecar at [services/oho_runner/](services/oho_runner/). Two endpoints (`/process-brain-dump`, `/build-command-center`), bearer-auth via `hmac.compare_digest`, asyncio-lock serialised, 180s timeout, argv tuple (no shell expansion path). Container is read-only-mounted on `/opt/oho`. Drift fix: receipt-stem derivation centralised in `bd_integrity.slug_for_filename` so the audit and the writer can never disagree.

**ADR-0006 — daily command center (`097892a`).** Replaces 12 stale dashboards with one auto-rebuilt landing page (`000_Master Dashboard/!!! DAILY COMMAND CENTER.md`) named to float to the top of the file tree. Locked section structure; Dataview TASK queries so checking off the rendered task also checks the MTL line. Operator-summary state file (`99_System/state/last-brain-dump-summary.json`) is the stable contract between the processor and the home generator. [tools/build_command_center.py](tools/build_command_center.py) is idempotent and verified-write.

**AI tooling layer (`179a03b`).** [AGENTS.md](AGENTS.md) (Codex/OpenAI mirror), [docs/AI_TOOLING.md](docs/AI_TOOLING.md) (canonical Skills/MCP/plugin registry), [.mcp.example.json](.mcp.example.json) (no-secret placeholders), [scripts/audit_ai_tooling.py](scripts/audit_ai_tooling.py) (`make audit-ai-tooling`).

### Operator actions remaining (P1+P1.5 deployment)

The 9-step runbook is automated by [scripts/deploy_oho_runner.py](scripts/deploy_oho_runner.py). Run it from a dev box that can reach both the LXC's SSH port and the n8n REST API:

```bash
# 1. Generate the bearer token, add it to .env:
echo "OHO_RUNNER_TOKEN=$(openssl rand -hex 32)" >> .env

# 2. Preview the deploy plan (dry-run by default — no changes):
make deploy-runner-dry

# 3. When the dry-run looks clean, apply it:
make deploy-runner

# 4. One-time: seed the command center
set -a && source .env && set +a && make build-home
```

The orchestrator handles all 10 steps (preflight → inspect → sync → runner-env → compose → smoke-runner → n8n-cred → hydrate-deploy → activate → smoke-pipeline → report), is idempotent, and writes a JSON log to `99_System/logs/deploy-oho-runner-<timestamp>.json`. Resume after a partial failure with `python3 scripts/deploy_oho_runner.py --apply --from-step <name>`.

If you prefer to do it by hand: see [docs/runbook-deploy-python-to-lxc.md](docs/runbook-deploy-python-to-lxc.md) for the manual procedure.

## Life Orchestrator v1.0 Roadmap (per [ADR-0007 Master Plan v2](docs/adr/0007-master-plan-v2.md))

| Phase | Theme | Status |
|---|---|---|
| **P0** | Stop the bleed | ✅ shipped commit `2b518b1` |
| **P1** | State machine + receipts + gated reset + truthful run logs | ✅ code-complete (`f3f8325` → `947e507`); deployed; in soak |
| **P1.5** | n8n→Python boundary moved to HTTP runner sidecar (n8n 2.x compat) | ✅ code-complete (`a1bd438`); deployed; in soak |
| **ADR-0006** | Single Daily Command Center replaces dashboard sprawl | ✅ code-complete (`097892a`); HTTP wire-in to live-dashboard-updater **deferred until P0.5 deploy verified** |
| **P0.5** | Deploy + ≥7-day soak (BLOCKING GATE) | ⏳ in flight; earliest exit **2026-05-18** |
| **P2** | Threaded tasks (stable `task_id`; backing files in `30_Tasks/<area>/`) | 🔒 design-first via [ADR-0009](docs/adr/0009-threaded-tasks.md); spec at `docs/superpowers/specs/2026-05-12-P2-threaded-tasks-spec.md` |
| **P2.5** | Decision Journal (rides P2 IDs) | 🔒 post-P2 |
| **P3** | Capture-Everywhere — voice-first | 🔒 post-P2 |
| **P3.5** | OHO-as-Broker-Client (client of CT 215 `agent-orch-lxc` broker) | 🔒 design via [ADR-0008](docs/adr/0008-cross-host-comms.md); spec at `docs/superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md` |
| **P4** | Decision-Ready Briefings (eval-gated) | 🔒 post-P3 |
| **Wave-X** | Cross-cut: security · eval · observability · comms-dashboard | 🔒 post-P4 (4 named lanes) |
| **P5** | Review Rituals (daily/weekly/monthly/quarterly/annual) | 🔒 post-Wave-X |
| **P6** | Domain-aware UX (8 domains + 4 named deliverables) | 🔒 post-P5 |
| **P6.5** | Spouse-Shared Mode (conditional on Christy) | 🔒 design-only until confirmed |
| **P7** | AI Coach + Insight Loop | 🔒 LAST; gated on all Wave-X infra live |

**Hard rules:**

- P0.5 soak must run clean ≥7 days before Phase C (P2) starts. While that gate is open: no new capture surfaces, no insights/coach scripts, no domain UX scope, no new code-heavy cron slots.
- P2 is design-first. [ADR-0009](docs/adr/0009-threaded-tasks.md) lands before code.
- P3.5 is **integration not construction** — target `agents/orchestrator/` canonical tree on CT 215 (NOT the older `orchestrator/` Compass tree).
- Privacy classifier (deny-list) gates the OHO→broker edge: `faith`/`family-named`/`kid-named`/`health-biomarker` NEVER egress without explicit `allow_egress_to`.
- "Insight v0" if it ships is read-only + non-blocking, and only AFTER P2.

## Cross-host fleet (per ADR-0008 design)

OHO is a peer in a three-host fleet, NOT a standalone system:

| Host                              | Tailscale                | Role                                                              | Repo                          |
|-----------------------------------|--------------------------|-------------------------------------------------------------------|-------------------------------|
| **CT-202**                        | n8n + oho-runner sidecar | LXC orchestrator + canonical truth + privacy hub                  | this repo                     |
| **CT 215** `orch-lxc`             | `100.122.188.108`        | Agent broker (FastAPI + Redis Streams, ACL prefix `agent:orch:*`) | `GRsoldier7/agent-orch-lxc`   |
| **VPS** `agent-core-01` (Vultr)   | `100.75.73.27`           | 24/7 fallback worker, OpenRouter free only, `read_only`           | sister-managed                |
| **Desktop** `aaron-inspiron-3030` | `100.112.192.78`         | Claude Code, Ollama, full_workspace                               | local                         |

Cross-host invariants: (a) one canonical `trace_id` across all hops; (b) no sensitive payload class crosses OHO→broker without explicit allow-list (classifier-enforced).

## Pending (carry-forward, not blocking the deploy)

- LXC sidecar deployment — the 9-step procedure above.
- GCAL OAuth2 → `GCAL_CRED_ID` in `.env` → re-deploy Weekend Planner.
- **OpenRouter key rotation — URGENT** per [2026-05-16 security incident](docs/security/2026-05-16-INCIDENT-job-search-leak.md). Partial key suffix in public git history (`workflows/quarantine/job-search-pipeline-2026-04-02-LEAKS.json`).
- MTL backfill of `[due::]` (only 11% populated) and `[completion::]` (0%).
- Step-8 decision: deprecate `--no-reset` after ≥7 days of clean receipt-audit reports.

# ObsidianHomeOrchestrator Agent Instructions

## Project Purpose

ObsidianHomeOrchestrator is the automation and configuration layer for Aaron's
Life OS. It connects Obsidian, MinIO S3, n8n, Python tools, OpenRouter, and
email/Telegram capture workflows.

Treat this repo as production automation for personal knowledge, tasks, and
daily operations. Small path or credential mistakes can silently corrupt the
Life OS.

## Critical Rules

- Never use a `Homelab/` prefix for vault paths. MinIO object keys live at the
  `obsidian-vault` bucket root.
- Never modify the Obsidian vault directly. Use the automation layer through
  MinIO S3 or the existing scripts.
- Never hardcode secrets, credential IDs, emails, access keys, API keys, or
  tokens. Workflow JSON must keep placeholders such as `__MINIO_CRED_ID__`.
- Every S3 write must be verified with a follow-up `head_object` or equivalent.
- Use the canonical Obsidian task format:

```markdown
- [ ] Task description [area:: faith] [priority:: A] [due:: 2026-XX-XX]
```

- Valid areas are `faith`, `family`, `business`, `consulting`, `work`,
  `health`, `home`, and `personal`.
- Run scripts that need `.env` with:

```bash
set -a && source .env && set +a && python3 scripts/health_check.py
```

- Do not schedule two Code-heavy n8n workflows at the same cron minute. The
  guard is `tests/test_workflow_templates.py::test_code_heavy_workflows_do_not_share_cron_minutes`.
- While P1 is open, do not expand capture surfaces, insight/coach workflows, or
  domain UX scope. P1 integrity work comes first.

## Intent Layer

**Before modifying code in a subdirectory, read its `AGENTS.md` first.**

- `tools/AGENTS.md` — Python logic kernel: `bd_integrity.py` stays pure (no I/O),
  all S3 writes route through `s3_verified.py`, AI egress routes through
  `egress_guard.py`, honor each module's SKELETON / MANUAL-ONLY status marker.

This file is the Codex/OpenAI mirror of `CLAUDE.md` — keep the two in sync when
changing critical rules.

## Current Architecture

- Automation: self-hosted n8n on Proxmox LXC CT-202
- Storage: MinIO S3, bucket `obsidian-vault`, no prefix
- Language: Python 3.12+ with `boto3`, `openai`, `requests`, `pytest`
- AI: OpenRouter free-tier cascade for extraction/enrichment
- Vault: Obsidian with Dataview, Templater, Tasks, QuickAdd, Remotely Save
- Deployment: `scripts/setup-n8n.sh` hydrates workflow placeholders and imports
  workflow JSON into n8n

## Files To Know

- `CLAUDE.md`: most detailed project state and Claude-specific skill context
- `docs/AI_TOOLING.md`: canonical Skills/MCP/tools registry
- `docs/RUNBOOK.md`: operational playbook
- `tools/process_brain_dump.py`: main Python brain-dump pipeline
- `scripts/setup-n8n.sh`: n8n workflow deployment
- `scripts/health_check.py`: MinIO, n8n, vault, and task-runner health checks
- `workflows/n8n/`: active workflow templates
- `tests/test_workflow_templates.py`: workflow regression guards

## Commands

```bash
pytest tests/ -v --ignore=tests/test_process_brain_dump_e2e.py -k "not integration" --tb=short
pytest tests/test_ai_tooling.py -q
python3 scripts/audit_ai_tooling.py
make audit-ai-tooling
make test
make ENV=1 health
make ENV=1 deploy
```

Use `make ENV=1 ...` only when the target needs `.env`.

## Skill Routing

Use these project-local skills or equivalent reasoning before changing related
areas:

| Area | Skill/Tool |
| ---- | ---------- |
| n8n workflow JSON, schedules, nodes, credentials | `n8n-workflow-architect` |
| Obsidian vault structure, Dataview, templates | `obsidian-vault-architect` |
| MinIO/n8n/Python vault automation | `obsidian-automation-architect` |
| Python tests, pytest fixtures, coverage | `testing-strategy` |
| Credentials, webhooks, SSRF, API keys | `security-best-practices`, `secure-by-design` |
| MCP design or implementation | `mcp-server-builder` |
| Cross-agent instructions | `portable-ai-instructions` |
| End-of-session project memory | `wrapup`, `notebooklm` |

Superpowers workflows are used for design, implementation plans, TDD, and
verification when available.

## MCP Guidance

- Use `docs/AI_TOOLING.md` as the source of truth.
- `.mcp.example.json` is safe to commit and contains placeholders only.
- `.mcp.json` is local state and must stay ignored.
- User-level MCPs are appropriate only when they are reusable across projects
  and do not require project secrets.

## Git And Worktree Safety

The worktree may contain user edits. Never revert unrelated changes. If a file
already has user changes and you must edit it, read the relevant context first
and make the smallest compatible patch.

Do not run destructive commands such as `git reset --hard` or `git checkout --`
unless the user explicitly requests them.


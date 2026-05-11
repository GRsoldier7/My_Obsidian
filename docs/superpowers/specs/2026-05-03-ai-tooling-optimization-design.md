# AI Tooling Optimization Design

**Date:** 2026-05-03
**Status:** Approved

## Problem

ObsidianHomeOrchestrator already has strong Claude-oriented project context:
`CLAUDE.md`, project skills, Superpowers specs/plans, OHO domain skills, runbooks,
and workflow tests. The gap is that this intelligence is not portable or audited.
Codex, Gemini, future MCP clients, and human operators can drift away from the
same rules that keep the Life OS safe.

The project needs a tool layer that makes the right Skills, MCPs, plugins, and
local scripts obvious, repeatable, and verifiable.

## Goals

- Create a canonical Skills/MCP/tools registry for OHO.
- Add Codex-compatible project instructions via `AGENTS.md`.
- Provide a safe `.mcp.example.json` with placeholders only.
- Add an automated audit so AI-tooling drift shows up in local checks.
- Update user-level config only for shared, no-secret MCP servers that benefit
  other projects too.

## Non-Goals

- Do not edit live n8n workflow JSONs as part of this tooling pass.
- Do not commit real credentials, tokens, API keys, email addresses, or live
  credential IDs.
- Do not register experimental local mock MCP servers as production tools.
- Do not change the Obsidian vault directly.

## Tooling Classification

### User-Level Shared MCPs

These are useful across projects and safe to register without project secrets:

| Tool | Purpose | User-Level Decision |
| ---- | ------- | ------------------- |
| `context7` | Current library/framework docs | Register |
| `playwright` | Browser verification and UI inspection | Register |
| `memory` | Persistent cross-project engineering memory | Register |
| `sequential-thinking` | Structured reasoning for complex tasks | Register |

These are recommended but not auto-registered because they need credentials or
missing local dependencies:

| Tool | Reason |
| ---- | ------ |
| `bitwarden` | Requires `bw` CLI and a current session token |
| `github` | Requires a PAT or GitHub connector auth |
| `fetch` | Requires `uvx` in the current recommendation |
| `postgres` | Needs a scoped read-only `DATABASE_URL` |

### Project-Local OHO Tools

| Tool/Skill | Required Use |
| ---------- | ------------ |
| `n8n-workflow-architect` | Any n8n workflow JSON or deployment change |
| `obsidian-automation-architect` | Vault automation, MinIO, capture pipelines |
| `obsidian-vault-architect` | Vault paths, templates, Dataview, task format |
| `testing-strategy` | Python pipeline, workflow audits, run-log guards |
| `security-best-practices` / `secure-by-design` | Credentials, webhooks, MinIO, n8n API |
| `mcp-server-builder` | Only when building real OHO-specific MCP tools |
| `portable-ai-instructions` | Cross-agent instruction files |
| `wrapup` / `notebooklm` | Session memory handoff after major changes |

## Architecture

The implementation adds five repo-local surfaces:

1. `AGENTS.md`: Codex/OpenAI agent instructions with OHO critical rules,
   commands, skill routing, and file safety boundaries.
2. `docs/AI_TOOLING.md`: canonical registry for Skills, MCPs, plugins, and
   activation rules.
3. `.mcp.example.json`: safe MCP configuration examples using placeholders only.
4. `scripts/audit_ai_tooling.py`: local audit for required files, registry
   sections, MCP examples, `.gitignore`, and Makefile integration.
5. `tests/test_ai_tooling.py`: pytest coverage for the audit behavior and
   no-secret MCP example constraints.

Existing `CLAUDE.md`, `README.md`, `docs/RUNBOOK.md`, `.gitignore`, and
`Makefile` receive small pointers to the new registry and audit command.

## Safety Rules

- `.mcp.json` is ignored; only `.mcp.example.json` is committed.
- `.mcp.example.json` uses environment placeholders instead of real values.
- User-level MCP entries are limited to no-secret, reusable servers.
- OHO-specific MCP examples remain project-local.
- Existing dirty workflow and fixture changes are not touched.

## Verification

- Run `pytest tests/test_ai_tooling.py -q`.
- Run `python3 scripts/audit_ai_tooling.py`.
- Run `make audit-ai-tooling`.
- Run the existing unit suite slice that covers workflow/template regressions
  if any workflow-related documentation changes are made.

## Open Follow-Ups

- Add Bitwarden MCP user-level registration after `bw` is installed and a
  scoped dev vault/session strategy is confirmed.
- Add read-only Postgres MCP registration after a safe `DATABASE_URL` is
  created for n8n execution debugging.
- Consider a real OHO MCP server later only if direct tool calls outperform the
  current Python scripts and n8n API tooling.

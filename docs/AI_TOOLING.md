# AI Tooling Registry

This is the canonical Skills/MCP/tools registry for ObsidianHomeOrchestrator.
Use it to decide which agent capability belongs at user level, project level,
or should remain deferred.

## Policy

- Shared developer infrastructure can be user-level when it is useful across
  projects and does not require project secrets.
- OHO-specific workflow, vault, NotebookLM, MinIO, and n8n behavior stays
  project-local.
- Live credentials never belong in committed config.
- `.mcp.example.json` is committed as a template. `.mcp.json` is ignored local
  state.

## User-Level Shared MCPs

These are useful beyond OHO and safe to configure without project secrets.

| MCP | Status | Why |
| --- | ------ | --- |
| `context7` | Register user-level | Current docs for libraries and frameworks |
| `playwright` | Register user-level | Browser checks and UI inspection |
| `memory` | Register user-level | Cross-project engineering memory |
| `sequential-thinking` | Register user-level | Structured reasoning for complex tasks |

## Project-Local MCP Examples

These belong in `.mcp.example.json` as examples or optional local config:

| MCP | Scope | Notes |
| --- | ----- | ----- |
| `filesystem-oho` | Project-local | Scope to this repo only if used |
| `postgres-n8n-readonly` | Project-local until proven shared | Requires read-only `DATABASE_URL` |
| `bitwarden` | Deferred user-level | Requires `bw` CLI and active scoped session |
| `github` | Deferred user-level | Requires connector/PAT auth |
| `fetch` | Deferred user-level | Current recommendation depends on `uvx` |

## Project-Local Skills

Use these before touching their domains.

| Skill | Trigger |
| ----- | ------- |
| `n8n-workflow-architect` | Any workflow JSON, credential placeholder, schedule, or deployment edit |
| `obsidian-automation-architect` | MinIO/n8n/Python automation and vault write paths |
| `obsidian-vault-architect` | Vault folders, Dataview, templates, canonical task format |
| `testing-strategy` | Python tools, pytest, workflow audits, integration checks |
| `security-best-practices` / `secure-by-design` | Secrets, webhooks, Telegram, SSRF, API keys |
| `mcp-server-builder` | Designing or implementing a real MCP server |
| `portable-ai-instructions` | Updating `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or related instruction files |
| `wrapup` / `notebooklm` | Saving major session memory to NotebookLM |

## Plugins And Built-In Tools

| Capability | Use |
| ---------- | --- |
| Superpowers | Design-first specs, TDD, plans, verification discipline |
| GitHub | PR, issue, CI, and repository workflows when GitHub context is needed |
| Google Calendar | Weekend planner or calendar-aware briefings after credentials are ready |
| Google Drive | Source documents or Sheets only when explicitly relevant |
| Playwright | Browser verification, n8n UI inspection, local screenshots |
| Context7 | Current docs lookup before using unstable APIs |

## Deferred Or Rejected

| Candidate | Decision | Reason |
| --------- | -------- | ------ |
| Local `n8n_Miastro` mock MCP servers | Rejected for OHO | They are simple Express mock servers, not production MCP servers |
| Direct vault filesystem MCP | Deferred | Project rule says vault writes go through MinIO automation |
| Broad Docker MCP with write access | Deferred | Useful later, but too broad for current P1 integrity work |
| Postgres write-capable MCP | Rejected | n8n execution DB access should be read-only |

## Activation Matrix

| Work Type | Required Tools |
| --------- | -------------- |
| Workflow JSON change | `n8n-workflow-architect`, `testing-strategy`, workflow template tests |
| Brain-dump pipeline change | `obsidian-automation-architect`, `testing-strategy`, unit tests |
| Credential rotation | `secure-by-design`, Bitwarden docs, `scripts/validate_env.py` |
| New MCP server | `mcp-server-builder`, security review, least-privilege tool design |
| Agent instruction update | `portable-ai-instructions`, `scripts/audit_ai_tooling.py` |
| Major session wrap | `wrapup`, NotebookLM active notebook |

## Verification Commands

```bash
python3 scripts/audit_ai_tooling.py
pytest tests/test_ai_tooling.py -q
make audit-ai-tooling
```

Run the broader suite when changes affect workflows or Python pipeline logic:

```bash
make test
```


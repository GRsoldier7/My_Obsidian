# AI Tooling Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OHO's Skills/MCP/tools setup portable, safe, and auditable across Claude, Codex, and future MCP-enabled agents.

**Architecture:** Add project-local agent instructions, a canonical tooling registry, a safe MCP example, and an audit script with pytest coverage. Apply user-level MCP config only for reusable no-secret servers.

**Tech Stack:** Markdown, JSON, Python 3.12, pytest, Makefile, Claude/Codex project instruction files, MCP stdio server configuration.

---

### Task 1: Add AI Tooling Audit Tests

**Files:**
- Create: `tests/test_ai_tooling.py`

- [ ] **Step 1: Write failing tests**

Create tests that assert:
- `AGENTS.md`, `docs/AI_TOOLING.md`, `.mcp.example.json`, and `scripts/audit_ai_tooling.py` exist.
- `.mcp.example.json` is valid JSON and contains no obvious secret literals.
- `scripts.audit_ai_tooling.run_audit()` returns no findings after implementation.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/test_ai_tooling.py -q`

Expected before implementation: fail because `scripts/audit_ai_tooling.py` and the new docs do not exist.

### Task 2: Add Project-Local Tooling Surfaces

**Files:**
- Create: `AGENTS.md`
- Create: `docs/AI_TOOLING.md`
- Create: `.mcp.example.json`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/RUNBOOK.md`

- [ ] **Step 1: Add `AGENTS.md`**

Include OHO overview, critical rules, commands, skill routing, MCP guidance, and boundaries for dirty worktrees and secrets.

- [ ] **Step 2: Add `docs/AI_TOOLING.md`**

Classify tools into user-level shared, project-local required, deferred, and rejected. Include activation triggers and verification commands.

- [ ] **Step 3: Add `.mcp.example.json`**

Include no-secret MCP examples with environment placeholders. Keep OHO-specific servers as optional project examples.

- [ ] **Step 4: Update references**

Point `README.md`, `CLAUDE.md`, and `docs/RUNBOOK.md` to `docs/AI_TOOLING.md`.

- [ ] **Step 5: Ignore live MCP state**

Add `.mcp.json` and `.memory/` to `.gitignore`.

### Task 3: Implement Tooling Audit

**Files:**
- Create: `scripts/audit_ai_tooling.py`
- Modify: `Makefile`

- [ ] **Step 1: Implement audit script**

The script should validate required files, required doc sections, safe MCP JSON, `.gitignore`, and `Makefile` integration. It should expose `run_audit() -> list[str]` for tests and return exit code 1 with findings on failure.

- [ ] **Step 2: Add Make target**

Add `make audit-ai-tooling` and include it in `make help`.

- [ ] **Step 3: Run tests and verify GREEN**

Run: `pytest tests/test_ai_tooling.py -q`

Expected after implementation: pass.

### Task 4: Add Shared User-Level MCP Config

**Files:**
- Modify user-level: `/Users/aarondeyoung/.claude/settings.json`

- [ ] **Step 1: Register no-secret reusable MCPs**

Add `context7`, `playwright`, `memory`, and `sequential-thinking` under `mcpServers` if they are not already present.

- [ ] **Step 2: Do not register credentialed MCPs**

Leave `bitwarden`, `github`, `fetch`, and `postgres` as documented recommendations only until their dependencies and credentials are ready.

- [ ] **Step 3: Validate user-level JSON**

Run: `python3 -m json.tool ~/.claude/settings.json >/tmp/oho-claude-settings.json`

Expected: exit 0.

### Task 5: Verify

**Files:**
- All files above

- [ ] **Step 1: Run focused tests**

Run: `pytest tests/test_ai_tooling.py -q`

- [ ] **Step 2: Run audit directly**

Run: `python3 scripts/audit_ai_tooling.py`

- [ ] **Step 3: Run Make target**

Run: `make audit-ai-tooling`

- [ ] **Step 4: Inspect git diff**

Run: `git diff -- AGENTS.md docs/AI_TOOLING.md .mcp.example.json scripts/audit_ai_tooling.py tests/test_ai_tooling.py Makefile README.md CLAUDE.md docs/RUNBOOK.md .gitignore`

Confirm only intended project-local files changed.

---
name: portable-ai-instructions
description: |
  Generate project instruction files (CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, copilot-instructions.md) tailored to any AI coding tool. Use this skill whenever the user mentions creating project instructions, setting up AI tool configs, writing CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, or wants to "set up a new project" for AI-assisted development. Also trigger when the user asks about making AI tools work better on their codebase, porting instructions between tools, or wants a consistent AI experience across multiple tools.
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: core
  adjacent-skills: prompt-amplifier, polychronos-team, skill-builder
  source-repo: GRsoldier7/My_AI_Skills
---

# Portable AI Instructions Generator

## File Format Reference

| File | Tool | Loaded | Best For |
|------|------|--------|----------|
| `CLAUDE.md` | Claude Code | Auto on start | All categories; skill references; MCP config |
| `AGENTS.md` | OpenAI Codex | Auto on start | Engineering; self-contained; sandbox commands |
| `GEMINI.md` | Gemini CLI | Auto on start | Engineering; GCP-specific; large context |
| `.cursorrules` | Cursor IDE | Auto on open | Coding patterns only; ≤100 lines |
| `.github/copilot-instructions.md` | Copilot | Auto in repo | Naming + patterns; inline completions |

## Generation Process

### Step 1: Gather Project Context
- Tech stack: languages, frameworks, key libraries, database, infrastructure
- Architecture: monolith vs. microservices, directory structure, key patterns
- Conventions: naming, file organization, import style, error handling
- Testing: framework, location conventions, coverage expectations
- Key decisions: the "why" behind architectural choices

### Step 2: Tool-Specific Content

| Content | CLAUDE.md | AGENTS.md | GEMINI.md | .cursorrules |
|---------|-----------|-----------|-----------|--------------|
| Skill references | Yes | No | No | No |
| MCP configuration | Yes | No | No | No |
| Sandbox commands | Brief | Detailed | Brief | No |
| Architecture depth | Deep | Deep | Deep | Brief |
| Workflow orchestration | Via skills | Inline | Inline | No |
| Coding patterns | Moderate | Moderate | Moderate | Primary |

### Step 3: Aaron's Project Defaults

```yaml
stack_preferences:
  language: Python 3.12+
  database: PostgreSQL (Cloud SQL on GCP)
  cloud: Google Cloud Platform
  api_framework: FastAPI
  testing: pytest
  linting: ruff
  formatting: black
  containerization: Docker
  orchestration: Cloud Run / n8n (self-hosted)
  iac: Terraform
  ci_cd: GitHub Actions

coding_conventions:
  naming: snake_case for Python
  docstrings: Google style
  error_handling: Explicit exception types, never bare except
  logging: structlog with structured output
  config: Environment variables via pydantic-settings
  secrets: Never in code — Secret Manager or .env (local only)
```

### Step 4: Cross-Tool Consistency Check
After generating all files: verify same conventions across files, no contradictions, each file appropriately sized for its tool.

## Anti-Patterns

1. **Copy-Paste Across All Files:** Each tool has distinct strengths — tailor to each
2. **One-Time Generation, Never Updated:** Update CLAUDE.md same session as any major architectural decision
3. **Overcrowding CLAUDE.md:** Use skill references, not inline content — CLAUDE.md should load <500 tokens of overhead

## Quality Gates
- [ ] Each file complete and ready-to-use (no placeholders)
- [ ] CLAUDE.md references skills instead of inlining their content
- [ ] .cursorrules concise (≤100 lines), coding-pattern-focused
- [ ] All files share consistent conventions, no contradictions

# Changelog

All notable changes to the Polychronos Framework will be documented in this file.

## [v6.0.0] - 2026-02-12

### Fused & Overhauled
- **Fused B.L.A.S.T. Protocol**: Merged the B.L.A.S.T. lifecycle (Blueprint, Link, Architect, Stylize, Trigger) directly into the core `PolyChronos-Omega.md` system prompt.
- **Unified Agent Contracts**: Refactored all 13 agents into a standardized Markdown format with explicit Triggers, Inputs, Outputs, and JSON Handoff schemas.
- **Polychronos Router**: Introduced a formal routing layer to classify tasks by complexity (T0-T3) and optimize agent selection.

### Added
- **New Agents**:
  - `DevOps Lead`: Infrastructure as Code, CI/CD, Observability.
  - `QA Director`: Shift-left testing strategy, Quality Dashboards.
  - `Diagnostician`: Scientific root cause analysis and Delta Reports.
- **New Directory Structure**: Created `polychronos/` top-level directory containing `agents/`, `router/`, and `templates/`.
- **System Prompt v6.0**: Completely rewritten `PolyChronos-Omega.md` to enforce the new operating model.

### Changed
- **Repo Organization**: Moved authoritative logic to `polychronos/`.
- **Naming Config**: Renamed several agents for clarity (`documentation_specialist` -> `loremaster`, `ai_ml_nexus` -> `nexus_architect`, etc.).

### Deprecated
- **Legacy Personas**: Files in `context/personas/` are superseded by `polychronos/agents/`.
- **v5.3 System Prompt**: Replaced by v6.0.

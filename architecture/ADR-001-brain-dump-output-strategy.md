# ADR-001: Brain Dump Output Strategy -- Individual Files over Master Task List Append

**Status:** Accepted
**Date:** 2026-03-21
**Decision Maker:** Aaron (system owner)

## Context

The Brain Dump Processor extracts tasks from free-form notes and must persist them in the Obsidian vault. Two strategies were considered:

1. **Append to Master Task List** -- add extracted tasks directly to `10_Active Projects/Active Personal/!!! MASTER TASK LIST.md`.
2. **Individual files in 00_Inbox/processed/** -- write each task as its own Markdown file with frontmatter metadata.

## Decision

Individual files in `00_Inbox/processed/` were chosen.

## Rationale

### Sync safety
The vault is synced across devices using the remotely-save plugin (not official Obsidian Sync). Appending to a single high-traffic file from an automated process while the user may also be editing it creates a high risk of merge conflicts and data loss. Individual files eliminate contention: each write produces a new, uniquely-named file that cannot collide with user edits or other automation runs.

### Dataview compatibility
Obsidian Dataview queries work across the entire vault by scanning file frontmatter and inline fields. Individual files with proper frontmatter (`type: processed-task`, `source: brain-dump`, `source_file`) are first-class Dataview citizens. They can be queried, filtered, and aggregated exactly like any other vault note without requiring Dataview to parse a specific section of a monolithic file.

### Traceability
Each processed-task file records its `source_file` in frontmatter, creating a clear audit trail from extracted task back to the original brain dump. This is far more difficult to maintain when tasks are appended as lines in a shared list.

### Idempotency
If the processor crashes mid-cycle or is re-run, individual files with timestamp-based names (`YYYY-MM-DD-HHmm-task-slug.md`) are naturally idempotent. A duplicate run at worst creates a file that already exists (and is skipped or given an index suffix). Appending to the Master Task List would produce duplicate lines that are hard to detect and remove.

### User workflow integration
The Inbox/processed folder fits the existing GTD-style workflow: items land in the inbox and are triaged by the user during review. This keeps the Master Task List as a curated, human-maintained artifact rather than a dumping ground for automation output.

## Consequences

- Users must periodically triage `00_Inbox/processed/` (during daily or weekly review) to move tasks into the Master Task List or project files.
- Dataview dashboards can surface un-triaged tasks automatically via queries on `type: processed-task`.
- The Master Task List remains a clean, human-curated document.

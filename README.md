# ObsidianHomeOrchestrator

The automation and intelligence layer for a Life Operating System built on Obsidian.

## What This Does

- **Brain Dump Pipeline** -- Dump raw thoughts anywhere (phone/laptop). AI automatically extracts tasks, creates notes, and files everything to the right place.
- **Smart Priority Stack** -- Mission Control surfaces the #1 needle-moving task per domain (Work, Consulting, Business) so you always know what to do next.
- **Frictionless Capture** -- QuickAdd shortcuts for tasks, brain dumps, ideas, and meeting notes. 3 taps max on mobile.
- **6 Domain Headquarters** -- Work, Consulting, Business, Personal, Faith, Health -- each with its own dashboard, auto-populated by Dataview.

## Architecture

```
Capture (QuickAdd) --> Intelligence (n8n + Claude API) --> Storage (Obsidian Vault) --> Query (Dataview) --> Review (Daily/Weekly)
```

## Project Structure

```
ObsidianHomeOrchestrator/
|-- .claude/commands/       # 19 Claude Code skills
|-- .polychronos/           # Polychronos OS v6.1 agent framework
|   |-- agents/             # 13 specialist agent contracts
|   |-- router/             # T0-T3 complexity routing
|-- docs/superpowers/specs/ # Design specifications
|-- scripts/                # Automation scripts (Python)
|-- workflows/              # n8n workflow exports (JSON)
|-- architecture/           # Architecture decision records
|-- CLAUDE.md               # Claude Code project instructions
|-- .env.example            # Environment variable template
```

## Tech Stack

- **Vault:** Obsidian (Dataview, Templater, Tasks, QuickAdd, Calendar, Remotely-Save)
- **Automation:** n8n (self-hosted Docker)
- **AI:** Claude API via n8n
- **Database:** PostgreSQL (Docker)
- **Language:** Python 3.12+
- **Infrastructure:** MiniPC Docker Compose

## Getting Started

1. Clone this repo
2. Copy `.env.example` to `.env` and fill in credentials
3. See `docs/superpowers/specs/` for the full design spec
4. See `CLAUDE.md` for Claude Code project context

## Status

Active development -- building the automation and skill layer.

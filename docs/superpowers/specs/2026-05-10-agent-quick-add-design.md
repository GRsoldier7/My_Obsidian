# Agent Quick Add Design

**Date:** 2026-05-10
**Status:** Approved for implementation planning

## Problem

Aaron can already capture directly in Obsidian from phone, Mac, or other
computers. The missing workflow is coding-session capture: while working with
Claude Code or Codex, Aaron needs a quick, precise way to add tasks, notes,
ideas, links, and follow-ups into the right Obsidian intake section without
switching tools or risking direct vault edits.

The project already has a safe brain-dump pipeline with MinIO S3 writes,
verified `head_object` checks, extraction receipts, deduplication, MTL append,
note/article routing, and gated source reset. Agent quick-adds should use that
pipeline instead of bypassing it.

## Goals

- Let Claude Code or Codex add a single item to an exact brain-dump section.
- Keep all writes inside MinIO S3 bucket `obsidian-vault` at bucket root.
- Never write directly to the Obsidian vault filesystem.
- Preserve the existing P1 integrity model: source files are intake, and
  `tools/process_brain_dump.py` remains the authority for promotion.
- Verify every S3 write with `head_object`.
- Provide commands that work from agent sessions and are easy for Aaron to say
  in natural language.

## Non-Goals

- Do not add a new n8n webhook, Telegram route, email route, or public capture
  surface.
- Do not append directly to `10_Active Projects/Active Personal/!!! MASTER TASK LIST.md`.
- Do not create a direct Obsidian MCP writer.
- Do not change the canonical task format.
- Do not schedule a new workflow or consume another Code-heavy cron slot.
- Do not hardcode credentials, emails, access keys, API keys, or n8n IDs.

## Recommended Architecture

Add a small Python CLI:

```bash
python3 tools/agent_quick_add.py --area business --section todos \
  --text "Follow up with Acme about proposal" --priority A --due 2026-05-15
```

The CLI appends one normalized entry to the selected source file under:

```text
00_Inbox/brain-dumps/
```

It then updates the source frontmatter so the normal processor sees the file as
ready for extraction:

```yaml
status: has_content
content_hash: sha256:...
last_checked: 2026-05-10T...
last_processed: null
last_processed_hash: null
```

After the append, the operator or agent can promote the item immediately:

```bash
python3 tools/process_brain_dump.py --file "BrainDump — Business.md" --verbose
```

Or leave it for the next scheduled brain-dump processor run.

## Section Contract

The CLI uses aliases, but writes only to canonical H2 headings recognized by
`tools/process_brain_dump.py`.

| Alias | Canonical Section | Processor Route |
| --- | --- | --- |
| `quick` | `## ⚡ Quick Notes` | notes |
| `needle` | `## 🎯 Needle Movers` | tasks |
| `todos` | `## ✅ To Do's` | tasks |
| `articles` | `## 📰 Articles & Resources to Follow Up On` | articles |
| `followup` | `## 🗂️ Things to Organize & Follow Up On` | tasks |
| `ideas` | `## 💡 Ideas & Possibilities` | notes |
| `recurring` | `## 🔁 Recurring / Rhythms` | tasks |

## Area Contract

Valid areas stay aligned with the project canonical set:

```text
faith, family, business, consulting, work, health, home, personal
```

Default file mapping:

| Area | Target File |
| --- | --- |
| `faith` | `BrainDump — Faith.md` |
| `family` | `BrainDump — Family.md` |
| `business` | `BrainDump — Business.md` |
| `consulting` | `BrainDump — Consulting.md` |
| `work` | `BrainDump — Work.md` |
| `health` | `BrainDump — Health.md` |
| `home` | `BrainDump — Home.md` |
| `personal` | `BrainDump — Personal.md` |

The CLI should also support `--file "BrainDump — Echelon.md"` or another
existing basename override when Aaron wants a more specific intake file.

## Entry Formatting

Task-routed sections use simple task-looking source lines. The processor still
rebuilds canonical MTL output, deduplicates, adds `[area::]`, and attaches
source links.

```markdown
- [ ] Follow up with Acme about proposal [priority:: A] [due:: 2026-05-15]
```

Note-routed sections use plain bullets:

```markdown
- Product idea: add a one-command intake path for agent sessions.
```

Article-routed sections use the submitted URL or markdown link as-is:

```markdown
- https://example.com/article
```

## Safety Rules

- The object key must never contain `Homelab/`.
- `--file` must be a basename ending in `.md`; no slashes or path traversal.
- `--area`, `--section`, `--priority`, and `--due` are validated before any
  network call.
- Empty text is rejected.
- If the target brain-dump source is `partial` or `error`, v1 should stop with
  an actionable message instead of mixing new content into a failed source.
- The write path is `GET source -> modify markdown -> PUT source -> HEAD source`.
- `--dry-run` prints the planned key, section, and entry without writing.
- `--process` runs `tools/process_brain_dump.py --file <target> --verbose`
  after the quick-add write verifies.

## Agent UX

Natural language prompts should map to exact commands:

```text
Add a business A task: follow up with Acme about proposal due Friday.
```

Agent action:

```bash
python3 tools/agent_quick_add.py --area business --section todos \
  --text "Follow up with Acme about proposal" --priority A --due 2026-05-15 --process
```

```text
Add this as a health article to process: https://example.com/research
```

Agent action:

```bash
python3 tools/agent_quick_add.py --area health --section articles \
  --text "https://example.com/research"
```

## Acceptance Criteria

- Unit tests cover section aliasing, area-to-file mapping, task/note/article
  entry formatting, frontmatter updates, path validation, partial/error refusal,
  dry-run behavior, and verified S3 write behavior with a mock client.
- `pytest tests/test_agent_quick_add.py -q` passes.
- Existing brain-dump tests still pass:

```bash
pytest tests/test_brain_dump.py tests/test_brain_dump_integrity.py tests/test_brain_dump_orchestrator.py -q
```

- Docs show exact Claude/Codex commands.
- No new credential placeholders, workflow JSON, n8n schedule, or direct vault
  writer is introduced.

## Future Follow-Ups

- Add an n8n webhook only after the project explicitly enters P3 capture surface
  expansion.
- Add multi-item batch quick-adds after the single-item path is proven.
- Add shell aliases or Claude/Codex slash commands that call the CLI.

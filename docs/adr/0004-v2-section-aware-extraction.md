# ADR-0004: v2 Section-Aware Brain Dump Extraction

**Date:** 2026-04-02  
**Status:** Accepted  
**Deciders:** Aaron DeYoung

---

## Context

The v1 brain dump processor treated each file as a monolithic blob and sent the entire content to OpenRouter in a single prompt. This approach had several problems:

1. **Quality degradation on long files:** LLMs produce worse structured output when given a 2,000-word blob than a focused 200-word section.
2. **AI called even for empty files:** Every file was sent to OpenRouter regardless of content, burning rate limit quota.
3. **No section-type awareness:** A "To Do's" section (structured tasks) and an "Ideas & Possibilities" section (freeform prose) need different extraction strategies.
4. **No empty-template detection:** New brain dump files created from the vault template have placeholder content (italic instructions, HTML comments). v1 sent these to AI, which returned garbage tasks from template boilerplate.

See the full design spec: `docs/superpowers/specs/2026-04-02-life-os-v2-design.md`

---

## Decision

Rewrite the extraction pipeline as **section-aware** (v2):

1. **Parse sections first** — split the file by H2 headers (`## Section Name`)
2. **Filter empty sections** — skip sections with only template boilerplate (comments, italic placeholders, Obsidian field refs)
3. **Route by section type** — each section is tagged as `tasks`, `articles`, or `notes`
4. **Apply regex-first per section** — deterministic extraction on each non-empty section (see ADR-0001)
5. **AI fallback per section** — only non-empty sections that yield 0 tasks from regex are sent to OpenRouter
6. **Section-specific prompts** — the AI prompt for a `tasks` section differs from a `notes` section

---

## Section Type Map

```python
SECTION_TYPE_MAP = {
    "Quick Notes":                              "notes",
    "Needle Movers":                            "tasks",
    "To Do's":                                  "tasks",
    "Articles & Resources to Follow Up On":     "articles",
    "Things to Organize & Follow Up On":        "tasks",
    "Ideas & Possibilities":                    "notes",
    "Recurring / Rhythms":                      "tasks",
}
```

`articles` sections are routed to the article queue (`00_Inbox/articles-to-process.md`) rather than the task list.

---

## Empty Section Detection

`is_section_empty()` filters out:
- HTML comment blocks (`<!-- ... -->`)
- Italic/bold placeholder text (`*placeholder text*`)
- Obsidian inline field refs (`=this.field`)
- Blockquote instructions (`> **How to use:**`)
- Horizontal rules
- "Format:" example lines

This ensures template-only files produce zero API calls and zero output files — the correct behavior for a brain dump that was created but never filled in.

---

## Impact on AI Call Volume

Before v2: every brain dump file → 1 API call, regardless of content.  
After v2: only non-empty sections with zero regex hits → API call.

Typical reduction: ~60% fewer API calls on a mix of partially-filled brain dumps. This is the primary reason the pipeline stays within free-tier rate limits.

---

## Consequences

**Positive:**
- Cleaner output: tasks from "To Do's" stay separate from notes in "Ideas"
- No AI calls on empty files or template-only sections
- Section-type routing enables article URL extraction without conflating with tasks
- Quality improvement: focused per-section prompts → fewer format violations

**Negative:**
- Section parsing depends on consistent H2 header format (`## Section Name`)
- If a user renames a section header (e.g., "✅ Todos" instead of "✅ To Do's"), it won't be recognized by `SECTION_TYPE_MAP`
- `is_section_empty()` pattern set must be maintained as template format evolves

**Key invariant:** The canonical brain dump template (in the Obsidian vault) must use H2 headers for all sections. Changes to the template require a corresponding update to `SECTION_HEADERS` in `process_brain_dump.py`.

---

## Migration from v1

v1 workflow (`brain-dump-processor.json`) is archived at `workflows/archive/v1/`. The v2 replacement is `workflows/n8n/brain-dump-processor-v2.json`. Both workflows were active briefly during transition; v1 was deactivated after v2 confirmed stable.

---

## Related

- `tools/process_brain_dump.py` — full v2 implementation
- `docs/superpowers/specs/2026-04-02-life-os-v2-design.md` — original design spec
- ADR-0001 — Regex-first extraction (the per-section strategy)
- ADR-0002 — OpenRouter cascade (what AI model is tried when regex yields nothing)
- `workflows/archive/v1/` — archived v1 workflows for reference

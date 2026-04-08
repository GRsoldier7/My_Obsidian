# ADR-0001: Regex-First Task Extraction with AI Fallback

**Date:** 2026-04-02  
**Status:** Accepted  
**Deciders:** Aaron DeYoung

---

## Context

The brain dump processor needs to extract structured tasks from freeform markdown. Two extraction strategies exist:

1. **AI-only:** Send every brain dump section to an LLM and parse its response.
2. **Regex-first:** Apply deterministic regex patterns first; use AI only for content that doesn't yield tasks from regex.

The processor runs daily (7AM CDT) on potentially 5–15 brain dump sections. Cost and reliability matter.

---

## Decision

Use regex as the primary extraction path. AI (OpenRouter) is invoked only when regex yields zero tasks from a section that contains real user content.

Implementation in `tools/process_brain_dump.py`:
- `regex_extract_tasks()` — deterministic extraction, zero API cost
- `extract_with_openrouter()` — AI fallback, called per-section only when regex returns nothing

---

## Rationale

**Cost:** OpenRouter free tier has per-model rate limits. Processing every section with AI risks hitting limits mid-run and producing partial output. Regex runs instantly, every time, for free.

**Determinism:** Regex output is predictable. The canonical task format (`- [ ] desc [area:: X] [priority:: X]`) is machine-readable by Dataview queries. AI output requires prompt engineering to stay within format, and occasionally drifts.

**Quality floor:** Regex catches ~70–80% of tasks from well-structured brain dumps (which use the standard section format). AI adds value for freeform prose sections ("Quick Notes", "Ideas") where no checkbox format exists yet.

**Coverage ceiling:** AI can extract tasks from unstructured text that regex would miss. Having it as fallback means nothing is lost from prose-heavy sections.

---

## Consequences

**Positive:**
- Pipeline runs reliably even when OpenRouter is rate-limited or down
- Daily cost remains $0 (free tier never exhausted on typical usage)
- Extraction is fast — typical run completes in 2–5 seconds even with some AI calls

**Negative:**
- Freeform sections ("Ideas & Possibilities", "Quick Notes") are AI-only, so if OpenRouter is fully unavailable, those sections produce no tasks
- Regex patterns must be maintained as brain dump format evolves

**Mitigation:** If all 3 OpenRouter models are rate-limited, the processor logs `status: partial` and writes whatever regex caught. A partial run is better than no run.

---

## Related

- `tools/process_brain_dump.py` — `regex_extract_tasks()` and `extract_with_openrouter()`
- ADR-0002 — OpenRouter model cascade (which models are tried in what order)
- ADR-0004 — v2 section-aware extraction (why sections are processed individually)

# ADR-0002: OpenRouter Free-Tier Model Cascade

**Date:** 2026-04-02  
**Status:** Accepted  
**Deciders:** Aaron DeYoung

---

## Context

The brain dump processor uses an LLM to extract tasks from freeform prose. We need an AI provider that:

1. Has **$0/month cost** at current usage volume (1–3 brain dumps/day, 2–5 AI calls each)
2. Is **reliable enough** for a daily personal automation (some downtime tolerable)
3. Has **models capable** of following structured output instructions (JSON with task format)

---

## Decision

Use **OpenRouter free tier** with a three-model cascade:

```python
EXTRACT_MODELS = [
    "google/gemma-3-4b-it:free",                    # fast, cheap, good instruction-following
    "meta-llama/llama-3.3-70b-instruct:free",        # better quality, higher rate limit window
    "nvidia/nemotron-3-super-120b-a12b:free",         # large fallback, lowest rate limit
]
```

The processor tries each model in order. If a model returns a rate-limit error (429) or fails to parse, it moves to the next. If all three fail, it falls back to regex-only extraction (see ADR-0001).

---

## Rationale

**Model selection:**

- **gemma-3-4b-it** — Small, fast, consistently follows JSON output instructions. First choice because free tier rate limits reset most frequently on smaller models.
- **llama-3.3-70b-instruct** — Higher quality reasoning for complex prose. Used when gemma is rate-limited.
- **nemotron-3-super-120b** — Largest available free model. Slowest, but highest reasoning quality. Last resort.

**Why OpenRouter instead of OpenAI / Anthropic directly:**

- Cost: $0/month vs. ~$2–5/month for comparable GPT-3.5 usage
- Flexibility: One API key, multiple models, easy to swap when a model goes down
- Sufficient quality: Task extraction from structured markdown doesn't require frontier models

**Why cascade instead of single model:**

Free tier rate limits are per-model, not per-account. When gemma hits its limit, llama often still has quota. The cascade converts a single point of failure into three independent chances.

---

## Rate Limit Behavior

OpenRouter free-tier limits are per-model per day (approximate):
- gemma-3-4b: ~200 requests/day
- llama-3.3-70b: ~100 requests/day
- nemotron-120b: ~50 requests/day

At typical usage (5–15 AI calls/day), gemma handles everything. The cascade only engages during backlog processing or multi-file runs.

---

## What to Do When Free Tier Is Exhausted

If all three models return 429 on the same day (very unusual):

1. **Do nothing** — regex still runs. Tasks in structured sections are extracted normally. Only freeform prose is missed.
2. **Check next day** — rate limits reset daily (UTC midnight).
3. **If persistent:** Log into https://openrouter.ai → check usage dashboard → consider adding $5 credit for high-volume days.

---

## Consequences

**Positive:**
- $0/month AI cost for current usage
- Resilient to single-model outages
- Logs clearly indicate which model was used per extraction (for debugging)

**Negative:**
- Free tier quality is below GPT-4 / Claude Sonnet — acceptable for task extraction
- Model availability can change (OpenRouter removes models periodically)
- nemotron-120b sometimes returns malformed JSON — the processor has a JSON parse retry

**Key monitoring signal:** If `errors` in the run log contains `openrouter_all_models_failed` more than once a week, consider adding a paid credit or switching gemma to `llama-3.1-8b-instruct:free` (more stable limits).

---

## Related

- `tools/process_brain_dump.py` — `extract_with_openrouter()` function
- ADR-0001 — Regex-first strategy (OpenRouter is the fallback, not primary)
- `scripts/validate_env.py` — validates `OPENROUTER_API_KEY` is set before deploy

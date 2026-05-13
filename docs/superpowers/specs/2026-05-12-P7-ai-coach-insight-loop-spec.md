# P7 — AI Coach + Insight Loop Design Spec

**Date:** 2026-05-12
**Status:** Design — DO NOT IMPLEMENT (gated behind P2–P6 completion + ≥30 days of clean post-P6 data)
**Phase:** P7 of the v1.0 Life Orchestrator roadmap (last phase, compounds with all prior data history)
**Author:** Claude (design pass)
**Anchor commits:** P1+P1.5+ADR-0006 (`a1bd438`, `097892a`)

> **Reminder from `CLAUDE.md` — non-negotiable:** *"Insight v0" if it ships is read-only + non-blocking, and only AFTER P2.* The failure mode of an AI coach is "noisy + wrong + everyone tunes it out." Every design choice in this document is downstream of that single constraint.

---

## 1. Goal + Magical Moments

### Goal

Build a *kind, honest friend who has read everything Aaron has written* — a long-horizon pattern-surfacer that compounds Aaron's own data into observations he could not assemble himself, while never silently mutating the vault and never making life decisions on his behalf.

The coach is **a reading & reflection layer over Aaron's own life corpus**, not an oracle. Its output is always grounded in Aaron's own words.

### Magical Moments (the five "wow" outcomes worth designing for)

1. **The quarter-pivot moment.** Sunday evening: the coach surfaces *"You've shipped 14 outreach-conversations rocks tasks this quarter. Last quarter you shipped 3. What changed in week 4? You started capturing on Tuesday mornings."* — grounded in receipts, no advice, just a mirror.
2. **The deferment receipt.** *"You've kicked 'finalize hip decision' 6 times in 4 months. Earliest mention: 2026-01-09. Latest defer: 2026-05-08. You've used the words 'next week' 11 times about it. Do / delegate / drop?"*
3. **The faith-business drift flag.** *"Your faith-domain captures dropped 60% over the last 3 weeks; business captures up 4×. Your Q2 rocks list named both as equal weight. Is that intentional?"* — labeled `LIKELY`, sources cited, no moralizing.
4. **The energy match.** *"Your highest-rated days this month all began with a gym session before 9am. Your three lowest-rated all skipped it. Sample n=12. Confidence: `LIKELY`."*
5. **The accountability ledger.** Friday: *"On Monday you wrote 'this week I will finish the Echelon Seven landing page.' Status today: page exists, not deployed. Not a judgement — just the receipt."*

All five are **read-only**, all five are **grounded**, all five are **labeled**, none of them prescribe a decision.

---

## 2. Anti-Goals (what this is NOT — and these matter more than the goals)

The coach is **NOT**:

- ❌ **A decision-maker.** It will not say "you should leave Parallon," "sell the MI property," or "make hip decision X." Tradeoffs Aaron has *himself written* may be re-presented; new tradeoffs may not be invented.
- ❌ **A motivator.** No "you've got this!" no "small steps lead to big wins!" no LinkedIn-platitude tonality. Aaron explicitly rejects motivational-poster output.
- ❌ **A daily pinger.** Daily output is forbidden in v0 (see §9 cadence). Daily-output coaches get filtered.
- ❌ **A vault-mutator.** No coach output ever writes outside the dedicated coach surface (`99_System/coach-inbox.md`, `30_Tasks/coach-drafts/*` for accept-into-task drafts). MTL, brain-dump sources, daily notes, and command center are untouchable.
- ❌ **A faith/medical advisor.** It does not interpret scripture, prescribe supplements, recommend protocols beyond what Aaron has himself written. On health protocol questions it defers explicitly: *"Talk to your doctor. The pattern observed: [...]"*
- ❌ **A family-information leakage surface.** Kids' real names, medical info, family decisions are vault-local-only (P6 contract); coach output that includes family-domain material gets a stricter privacy filter.
- ❌ **A third-party LLM relay.** Aaron's data goes to OpenRouter free-tier models only by default; Opus calls are opt-in per-request. No third-party telemetry beyond the API call itself.
- ❌ **A new capture surface.** Coach does not solicit input. It reads, it observes, it asks at most one question per insight, and only inside the coach-inbox.
- ❌ **Aware of itself.** No "as an AI" disclosures, no breaking-the-fourth-wall meta-commentary. It just speaks plainly, like a friend who happens to have read the journal.

> If a feature does not fit *all* of these, it does not ship in P7. Cut scope before crossing any of these lines.

---

## 3. Architecture

### Recommended: **Hybrid context — direct file inclusion for the "hot set," grep+regex over the cold corpus, embeddings ONLY as a last-resort routing aid.**

#### Rationale

1. **Aaron's corpus is small.** At 12 months of v1.0 data the entire vault is plausibly < 20 MB of text — well within a single 200K-context call. Embedding infrastructure (vector DB, chunking, re-rank) is a 10× cost-and-complexity multiplier for a problem that does not require it.
2. **The hot set is structured.** MTL, daily notes, Q2 rocks, last 30 days of brain dumps, and last 4 weekly digests are *known files* the coach should always have in context. No retrieval needed — just `s3_get`.
3. **The cold set is grep-able.** Historical patterns ("when did Aaron first mention the hip decision?") are answered correctly by `rg "hip"` over the vault, not by cosine similarity. Regex is deterministic, auditable, and zero-cost. **This honours the regex-first principle baked into CLAUDE.md.**
4. **Embeddings have one legitimate job:** *theme clustering* when surfacing patterns ("what topics has Aaron returned to most this month") — and only if grep-based n-gram frequency analysis proves insufficient after a 30-day trial. Default: **no embeddings in v0**.
5. **RAG is the wrong abstraction here.** RAG assumes the corpus is bigger than the context window AND the queries are knowledge-lookup style. Neither holds. This is closer to *"summarize a structured personal log"* than *"answer questions about a knowledge base."*

#### Concrete architecture

```
                ┌─────────────────────────────────────┐
                │  tools/coach/run_insight_loop.py    │
                │  (orchestrator, runs weekly)        │
                └────────────────┬────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
   ┌────▼─────────┐    ┌─────────▼──────────┐   ┌─────────▼──────────┐
   │ HotSet       │    │ ColdGrep           │   │ StateLog           │
   │ Loader       │    │ Searcher           │   │ Reader             │
   │              │    │                    │   │                    │
   │ MTL, daily   │    │ rg over vault for  │   │ insight history,   │
   │ notes (30d), │    │ specific terms     │   │ accept/dismiss log,│
   │ Q2 rocks,    │    │ requested by an    │   │ confidence calibr. │
   │ last 4 wk    │    │ individual         │   │ trail              │
   │ digests,     │    │ insight loop       │   │                    │
   │ summary.json │    │                    │   │                    │
   └────┬─────────┘    └─────────┬──────────┘   └─────────┬──────────┘
        │                        │                        │
        └────────────┬───────────┴────────────────────────┘
                     │
              ┌──────▼───────────────────────┐
              │  9 Insight Loop Modules      │
              │  (each is a pure-function    │
              │   pattern-detector + AI      │
              │   summarizer, see §5)        │
              └──────┬───────────────────────┘
                     │
              ┌──────▼─────────────┐
              │ Confidence Tagger  │  ← every output line gets a label
              └──────┬─────────────┘
                     │
              ┌──────▼─────────────┐
              │ Guardrail Sieve    │  ← non-prescription classifier,
              │                    │    privacy filter, length budget,
              │                    │    tone check
              └──────┬─────────────┘
                     │
              ┌──────▼─────────────┐
              │ Eval Gate          │  ← if eval suite is RED, output
              │                    │    is DRAFTED but NOT EMITTED
              └──────┬─────────────┘
                     │
              ┌──────▼─────────────────────────┐
              │  Emit:                          │
              │  - coach-inbox.md (append)      │
              │  - weekly email (Sun 6 PM)      │
              │  - monthly write-up (1st of mo) │
              │  - insight-receipts/<sha>.json  │
              └─────────────────────────────────┘
```

**Hot-set loader** is a thin wrapper around the existing `s3_get` pattern in `tools/build_command_center.py`. **Pattern detectors** are deterministic Python (regex, counters, date math) — they produce *observations*. **AI summarizer** turns observations into prose. **Confidence tagger** runs after summarization and labels each line. **Guardrail sieve** is a hard gate.

#### Why this beats RAG

| Concern | RAG | This design |
|---|---|---|
| Cost | embed-and-store every brain dump, every daily note | $0 — direct read |
| Auditability | "the model found these chunks somehow" | every observation has a file:line citation |
| Hallucination surface | re-ranker can surface adjacent-but-wrong chunks | grep result is exact text |
| Determinism | embedding similarity drifts with model version | regex is reproducible forever |
| Operational complexity | vector DB, chunker, re-ranker, refresh job | one Python script, the existing S3 client |
| Compounding over years | embeddings need re-index when models change | grep history is timeless |

**The single legitimate RAG use case** (theme clustering across 6+ months of brain dumps) is deferred to P7.1, not P7.0, and gated on actually proving grep-based n-gram analysis is insufficient.

---

## 4. Data Model

### 4.1 Insight Record

Each individual coach observation is an **insight record**, content-addressed and immutable.

Stored at: `99_System/coach/insights/<YYYY-MM>/<sha256[:12]>.json`

```json
{
  "insight_id": "ins_2026w19_deferment_001",
  "content_sha": "ab12cd34...",
  "created_at": "2026-05-12T18:00:00-05:00",
  "loop": "deferment_detector",
  "domain": "health",
  "title": "The hip decision has been deferred 6 times in 4 months",
  "body": "Aaron, you first wrote about the hip decision on 2026-01-09 in BrainDump — Health.md. Since then it has appeared in 18 brain-dump captures and been deferred (kicked to 'next week' or moved without action) in 6 of them. Latest defer: 2026-05-08 in Coding.md (ironic). The phrase 'next week' appears in the surrounding context 11 times. The phrase 'making a decision' appears in 4 of your weekly digests.",
  "ask": "Do / delegate / drop?",
  "confidence": "LIKELY",
  "confidence_reasoning": "Counts are exact (VERIFIED). Pattern interpretation as 'deferment' rather than 'active deliberation' is LIKELY — confirmed by absence of decision-completion language in 6/6 instances.",
  "sources": [
    {"file": "00_Inbox/brain-dumps/BrainDump — Health.md", "line": 42, "date": "2026-01-09", "excerpt": "Need to decide on hip — surgery vs PT vs wait"},
    {"file": "00_Inbox/brain-dumps/BrainDump — Health.md", "line": 88, "date": "2026-02-14", "excerpt": "Hip thing again — kicking to next week"},
    {"file": "40_Timeline_Weekly/Weekly/2026-W18.md", "line": 23, "date": "2026-05-04", "excerpt": "Did not make hip decision"}
  ],
  "status": "pending",
  "user_action": null,
  "user_action_at": null,
  "guardrail_checks": {
    "non_prescription": "pass",
    "privacy_filter": "pass",
    "factuality_grounded": "pass",
    "confidence_calibrated": "pass",
    "tone_warm_not_corporate": "pass",
    "length_within_budget": "pass"
  },
  "eval_run_id": "eval_2026-05-12_run_017"
}
```

**Key invariants:**
- `content_sha` is computed over `(title || body || sources)`. Identical insights de-dup automatically.
- `sources` is mandatory and ≥1; an insight with no sources is **rejected at the sieve**.
- `confidence` ∈ {`VERIFIED`, `LIKELY`, `UNCERTAIN`, `SPECULATIVE`, `UNKNOWN`}. `confidence_reasoning` is mandatory.
- `status` ∈ {`pending`, `accepted`, `dismissed`, `snoozed`, `actioned`, `expired`}.
- `user_action` is one of {`accept`, `dismiss`, `snooze_<N>d`, `convert_to_task`, `null`}.

### 4.2 Observation Log

The raw deterministic findings *before* AI summarization. Stored at:

`99_System/coach/observations/<YYYY-MM-DD>.jsonl`

One JSON line per observation, machine-readable, never sent through an LLM. This is the audit trail that lets us verify the coach didn't fabricate patterns — every prose insight in §4.1 must trace back to at least one observation line here.

### 4.3 Accept/Dismiss Audit Trail

When Aaron acts on an insight (checks an `accept` box, or clicks a `dismiss` link, or snoozes), the action is captured to:

`99_System/coach/actions/<YYYY-MM>.jsonl`

```json
{"insight_id": "ins_2026w19_deferment_001", "action": "snooze_7d", "at": "2026-05-12T19:14:33-05:00", "source": "coach-inbox.md", "note": null}
```

This is the **feedback loop** that lets us measure usefulness over time (see §8 evaluation).

### 4.4 Convert-to-task Draft

When Aaron accepts an insight as actionable, the coach drops a *draft task line* into a designated draft file:

`30_Tasks/coach-drafts/<YYYY-MM-DD>.md`

```markdown
- [ ] Make the hip decision this week [area:: health] [priority:: A] [due:: 2026-05-19] [source:: [[coach:ins_2026w19_deferment_001]]]
```

The brain-dump pipeline picks this up on the next run via the same intake mechanism Aaron uses for everything else. **The coach never writes to MTL directly.** Drafts live in a draft folder until promoted through the normal pipeline. P2 task-id system links the resulting task back to the insight via `[source::]`.

### 4.5 Insight Receipt

Mirrors the P1 brain-dump receipt model (`tools/bd_integrity.py`):

`99_System/coach/receipts/<insight_id>.json`

```json
{
  "insight_id": "ins_2026w19_deferment_001",
  "content_sha": "ab12cd34...",
  "emitted_at": "2026-05-12T18:00:00-05:00",
  "emitted_to": ["coach-inbox.md", "email:aaron"],
  "eval_run_id": "eval_2026-05-12_run_017",
  "model_chain": ["llama-3.3-70b-instruct:free"],
  "tokens_in": 8412,
  "tokens_out": 614
}
```

Audit script `scripts/audit_coach_receipts.py` (mirrors `audit_extraction_receipts.py`) enforces every emitted insight has a receipt.

---

## 5. The Nine Insight Loops (each a sub-spec)

Each loop is a **pure-function pattern detector** that produces `Observation`s, followed by an AI summarizer that produces `InsightRecord`s. The detectors are testable without an LLM.

### 5.1 Pattern Surfacer (weekly)

**Detector:** for each domain, compute week-over-week deltas in capture count, task-completion count, task-creation count, average priority distribution, average days-to-completion. Flag any delta > 2σ from trailing-12-week baseline.

**Output budget:** 3–5 observations per week.

**Example:** *"Business-domain captures up 4× this week (n=12 vs trailing mean 3.1). Capture density peaked Tuesday morning. LIKELY — confirmed by sources X, Y, Z."*

**Guardrail:** never combines two domains into a single causal claim ("business up because faith down" is **forbidden**); each delta stands alone.

### 5.2 Deferment Detector (weekly)

**Detector:** for each open MTL task, count: (a) days since first appearance in any brain-dump or MTL, (b) number of times the task's `[due::]` field has changed (P2 task-id history makes this exact), (c) frequency of "next week," "soon," "later" tokens near the task's text in surrounding captures.

**Trigger:** task has been "deferred" ≥ 3 times AND lifespan ≥ 30 days.

**Output:** explicit `do / delegate / drop` prompt for top 3 deferred items.

**Critical guardrail:** the prompt is **always `do / delegate / drop` framed**. The coach NEVER picks one of the three. Aaron picks. The coach surfaces the choice; the choice is Aaron's.

### 5.3 Promise-Keeper (weekly)

**Detector:** parses weekly digest from prior Monday for "this week I will…" / "I'll finish…" / "by Friday…" statements. Cross-references against MTL state Friday EOD.

**Output:** ledger format. No judgement language.

**Example:** *"On Mon 5/5 you wrote 'this week I'll deploy the Echelon Seven landing page.' Status Fri 5/9 EOD: code shipped to repo, not deployed to prod. VERIFIED."*

**Guardrail:** must use **ledger tone**, not coaching tone. No "you can do better next week." Just the receipt.

### 5.4 Energy Mapper (monthly, gated on biohacking-data-pipeline landing)

**Detector:** if daily notes have a `[rating::]` field AND the biohacking pipeline writes HRV/sleep data to a known location, compute Pearson correlation between morning-routine variables and end-of-day rating, n ≥ 14 days minimum.

**Trigger:** correlation |r| ≥ 0.4 AND p < 0.05 AND n ≥ 14.

**Output:** *"Your highest-rated days this month (n=12) all started with gym before 9am. Lowest (n=8) skipped it. Correlation r=0.62. LIKELY."*

**Hard rule:** if biohacking-data-pipeline is not yet emitting reliable data, this loop is **disabled**. Status checked at the orchestrator level via `99_System/state/biohacking-pipeline-status.json`.

**Medical guardrail:** never makes a protocol recommendation. Defers explicitly: *"Talk to your doctor before changing morning routine for medical reasons."*

### 5.5 Faith-Life Feedback (weekly)

**Inputs:** Bible-reading log (if exists in vault), prayer-queue file, Sunday-school prep markdown, faith-domain capture density.

**Detector:** purely descriptive — *"Reading streak: 12 days. Prayer queue: 4 unprocessed items, oldest from 2026-04-22. Sunday-school prep for this week: not started (last week: started Sunday 2pm)."*

**Hard guardrail — the most important in the whole spec:**

The coach is **never** allowed to:
- Interpret scripture
- Suggest what Aaron should pray about
- Recommend a Bible-reading plan
- Encourage or discourage spiritual practices
- Quote scripture except by *direct citation of something Aaron himself wrote in a vault file*

The coach is **allowed** to:
- Report observed counts and dates
- Re-present Aaron's *own* writing back to him (with citations)
- Note that a self-stated cadence has drifted from his self-stated target

This loop has an **extra eval gate** (non-moralizing classifier, see §8.3).

### 5.6 Business Pacing (weekly)

**Detector:** Echelon Seven pipeline tasks vs Q2 rocks goal (3 outreach conversations); consulting hours vs target (read from a TBD log file Aaron maintains); proportion of weekly capture by business vs consulting vs work vs other.

**Trigger:** consulting capture > 2× business capture for ≥ 2 consecutive weeks AND Aaron's most recent self-stated priority (extracted from weekly digest) was business.

**Output:** *"You named business as your top priority in the 2026-W17 weekly digest. Since then, consulting captures: 23. Business captures: 8. LIKELY drift. Is that intentional?"*

**Guardrail:** the *question* is always optional and always Aaron's to answer. Never reframes as "you should focus on business."

### 5.7 Family Attention Budget (weekly)

**Detector:** family-domain capture density vs Aaron's self-stated weighting (read from a config file Aaron maintains, e.g. `99_System/coach/weights.json`).

**Trigger:** family domain has been < 50% of stated target for 2+ consecutive weeks.

**Output:** flag only. No prescriptive content.

**Privacy guardrail:** family-domain insights *never include kids' names or specific health/school details* in the output, even when the source contains them. Source citations point to file:line but the rendered prose strips identifiers — they live only in the vault-local source. Enforced by a deny-list that the P6 domain-aware UX must populate before P7 starts.

### 5.8 Quarterly Horizon (every Sunday — the strongest compounding moment)

**Detector:** for each of today's MTL tasks (open), trace which Q2 rock (if any) it ladders to. For each Q2 rock, count: open tasks linked, completed tasks linked, days-remaining-in-quarter, rough velocity (completed/week).

**Output:** *"You have 6 weeks remaining in Q2. Echelon Seven MVP rock has 4 open tasks at velocity 0.5/week — projected completion date: 2026-08-12 (5 weeks past quarter end). Faith rock (4 sessions): 1 delivered, 3 open, velocity 0.33/week — projected: 2026-07-30 (3 weeks past)."*

**This is the loop most likely to deliver a magical moment.** It's also the most quantitative and easiest to ground. **Ship this first.**

**Guardrail:** the projection is a math statement, not a judgement. No "you won't make it." Just the math.

### 5.9 Coach-Inbox (continuous, async)

Not really a "loop" — it's the **UX surface** through which loops 5.1–5.8 emit. Documented in §9.

---

## 6. Confidence-Labeling System End-to-End

Every line in coach output carries one of:

| Label | Meaning | When to use |
|---|---|---|
| **VERIFIED** | claim is a direct count or quote from a vault source AND grounded in current context | "MTL has 47 open tasks." "You wrote on 2026-05-08: '...'" |
| **LIKELY** | inference from observed pattern with strong signal | "Your highest-rated days correlate with morning gym (r=0.62)." |
| **UNCERTAIN** | observed signal is suggestive but n is small or pattern is noisy | "May be a pattern of deferment, but n=2." |
| **SPECULATIVE** | a hypothesis worth checking — explicitly framed as such | "*Speculative*: the business-faith drift may reflect Q2-end pressure." |
| **UNKNOWN** | the coach cannot determine; defers | "I can't tell from your writing whether this was intentional. Asking explicitly." |

### Calibration rules

1. **No label can be upgraded by the LLM.** The detector emits the highest label the observation supports; the LLM may downgrade but never upgrade. Enforced by a post-hoc validator that re-grounds each claim.
2. **Counts and dates are always VERIFIED.** If the coach claims "you wrote X on date D," D must be present in a source. Test-enforced.
3. **Causal language requires LIKELY or weaker.** No "because." Always "correlates with," "may reflect," "alongside."
4. **Faith/family/medical claims default to UNCERTAIN.** A higher label requires *Aaron's own prior writing* as ground (e.g., Aaron explicitly named a target).
5. **A claim with no source citation is automatically UNKNOWN — and rejected at the sieve.**

### Brier-score eval

For each insight, Aaron rates whether the label was correct (correct/under-confident/over-confident). A rolling Brier score is computed. If average over-confidence exceeds 10%, the system raises an alert and refuses to emit until recalibrated.

---

## 7. Guardrail Enforcement — Technically, Not Just Stated

Each hard guardrail is implemented by a **specific concrete mechanism**. None are vibes.

### 7.1 No life decisions

**Mechanism:** a *non-prescription classifier* runs over every emitted insight body. It's a small zero-shot prompt to llama-3.3-70b-instruct asking *"Does this text attempt to make a decision for the reader, or recommend a specific life/career/medical/spiritual choice? Yes/No, and quote the offending phrase."*

**Threshold:** any "Yes" → insight rejected, logged to `99_System/coach/rejections/<date>.jsonl`, never emitted. The detector must be re-run after a prompt revision.

**Eval:** 50 hand-curated examples (25 must-pass, 25 must-fail) labelled by Aaron. Classifier accuracy ≥ 95% required to ship.

### 7.2 No faith/family advice without Aaron's named values

**Mechanism:** for faith- and family-domain insights, an additional *anchor check* runs. It requires that every claim about "what Aaron should consider" cite a vault file where Aaron himself wrote about that value.

**Implementation:** the insight record's `sources` field MUST include at least one entry where the cited excerpt contains Aaron's own first-person framing on the value at stake. Verified by a regex pass over the excerpt for first-person markers.

### 7.3 No medical advice

**Mechanism:** a domain-tagged hard-stop list. Insights tagged `domain: health` AND containing protocol-action verbs (`take`, `try`, `start`, `stop`, `increase`, `decrease`, `add`, `remove` — within token distance N of a supplement/medication/protocol noun) are rejected.

**Plus:** every health-domain insight has a mandatory footer: *"Talk to your doctor before changing protocol."*

### 7.4 No data exfiltration

**Mechanism:**
- All LLM calls go through OpenRouter via the existing httpHeaderAuth credential — no new providers added in v0.
- Coach output is emitted only to: `99_System/coach-inbox.md`, Aaron's email (via existing SMTP credential), and `99_System/coach/insights/`. No webhooks, no APIs, no third-party services.
- Privacy filter: a deny-list of kids' names + family-medical terms (maintained in `99_System/coach/privacy-denylist.json`) is regex-scrubbed from every emitted insight body. Source citations may retain them (sources stay vault-local); rendered prose may not.
- Email payloads run through the same privacy filter.

### 7.5 Cost-aware

**Mechanism:** every coach run logs `tokens_in`, `tokens_out`, `model_chain` to the insight receipt. A weekly cap of 200K input tokens / 50K output tokens enforced at the orchestrator. Exceeding the cap halts emission for the week. Opus calls require explicit `--allow-opus` flag and per-call confirmation.

### 7.6 Eval-gated

**Mechanism:** insights are written to `pending/` first. The eval suite (§8) runs against the batch. If any eval is RED, the batch is held in `pending/` and **not** emitted; an operator alert fires. Only GREEN batches are emitted.

### 7.7 Read-only default

**Mechanism:** the coach process runs with a hardcoded S3 write allowlist (Python module-level constant):

```python
COACH_WRITE_ALLOWLIST = {
    "99_System/coach-inbox.md",
    "99_System/coach/insights/",
    "99_System/coach/observations/",
    "99_System/coach/actions/",
    "99_System/coach/receipts/",
    "99_System/coach/rejections/",
    "30_Tasks/coach-drafts/",  # drafts only — never MTL or sources
}
```

Any `s3_put` to a key outside this prefix raises and aborts. Test-enforced.

### 7.8 Non-noisy

**Mechanism:** a per-week emission budget. Default: weekly email ≤ 5 bullets, monthly write-up ≤ 500 words, coach-inbox ≤ 8 unread insights at any time (older ones auto-snoozed and rolled into the monthly write-up).

---

## 8. Evaluation Strategy

### 8.1 Eval Dimensions

| Dimension | Type | Threshold to ship v0 | Threshold to keep shipping |
|---|---|---|---|
| **Factuality** | Binary per claim | 100% grounded | 100% grounded |
| **Confidence calibration** | Brier score | ≤ 0.15 over 20-insight sample | ≤ 0.20 rolling 50 |
| **Non-prescription** | Binary | 0 fails out of 50 eval examples | 0 fails per week |
| **Privacy filter** | Binary | 0 family-name leaks out of 30 eval examples | 0 leaks ever |
| **Tone (warm not corporate)** | 1–5 by Aaron | ≥ 4.0 mean over first 20 outputs | ≥ 3.8 rolling 20 |
| **Usefulness** | 1–5 by Aaron weekly | ≥ 4.0 after week 4 | ≥ 3.5 rolling 4 weeks |
| **Length budget** | Binary | 100% within budget | 100% within budget |

### 8.2 Eval Dataset

50 hand-curated examples assembled during P5/P6 from real first-month-of-P6 data, by Aaron. Each example has:
- Input: a hot-set snapshot + a target loop
- Expected output: a labeled insight (or "no insight worth emitting")
- Labels: factuality (source-grounded YES/NO per claim), prescription-yes/no, tone 1–5

Stored at: `tests/data/coach_eval_dataset.jsonl`. **Curating this dataset is itself ~8 hours of Aaron's time and is the gating dependency on P7 implementation.**

### 8.3 Domain-specific sub-evals

- **Faith non-moralizing classifier:** 30 examples of faith-domain prose, 15 acceptable (pure reportage of Aaron's own writing) and 15 unacceptable (any moralizing, scripture interpretation, prayer-life prescription). Required: 100% correct classification before faith loop ships.
- **Family privacy classifier:** 20 examples mixing acceptable (general family-domain capture density) and unacceptable (any rendered prose containing a child's name or medical condition). Required: 100% correct.

### 8.4 Run Cadence

- **Pre-emission:** every weekly batch.
- **Post-action:** when Aaron dismisses/accepts/snoozes, record the action; recompute rolling Brier and tone/usefulness scores nightly.
- **Monthly audit:** on the 1st of each month, run the full eval dataset; raise an alert if any dimension drops below threshold.

### 8.5 Failure response

If eval is RED:
1. Halt emission.
2. Alert Aaron via existing error-handler workflow.
3. Diff the failing case against the last passing case (which prompt change broke it?).
4. Hold all `pending/` insights until eval is GREEN again.
5. Never auto-emit "best-effort" output.

---

## 9. Coach-Inbox UX

### 9.1 Location and structure

`99_System/coach-inbox.md` — a single Obsidian-rendered markdown file Aaron opens when he wants to. Auto-rebuilt on every coach run; **never auto-opened** by the system.

```markdown
---
type: coach-inbox
updated: 2026-05-12T18:00:00-05:00
unread_count: 3
source: tools/coach/run_insight_loop.py
---

# 🤝 Coach Inbox

> A kind, honest mirror. Read on your own time. Nothing here writes back into your vault unless you check an accept box.

## 📬 New This Week (3)

> [!quote]+ The hip decision — 6th defer in 4 months
> **Confidence:** `LIKELY` · **Domain:** health · **Loop:** deferment-detector
>
> Aaron, you first wrote about the hip decision on 2026-01-09 in BrainDump — Health.md. Since then it has appeared in 18 brain-dump captures and been deferred in 6 of them. Latest defer: 2026-05-08.
>
> **Do / delegate / drop?**
>
> - [ ] Accept as task (creates draft in `30_Tasks/coach-drafts/`)
> - [ ] Dismiss (logs reason)
> - [ ] Snooze 7 days
>
> _Sources: [BrainDump — Health.md L42](../00_Inbox/brain-dumps/BrainDump%20—%20Health.md), [W18 digest L23](../40_Timeline_Weekly/Weekly/2026-W18.md). ID: `ins_2026w19_deferment_001`._

[... more insights ...]

## 📂 Earlier (auto-rolled into monthly)

(insights > 7 days old that weren't accepted or dismissed roll up into the monthly write-up)

## 🔇 Snoozed

(insights Aaron snoozed, with re-surface date)
```

### 9.2 Threading

Each insight has a unique `insight_id`. If a follow-up observation extends the same thread (e.g., the hip decision is deferred a 7th time), the coach **appends to the existing thread** rather than creating a new top-level insight:

```markdown
> [!quote]+ The hip decision — now 7th defer
> **Update from 2026-05-19** · was: 6 defers · now: 7 defers
> Latest defer: 2026-05-15. You snoozed this last week. The thread continues.
```

### 9.3 Accept / Dismiss / Snooze

- **Accept** = check the box. A file-watcher style process (or weekly batch) detects checked boxes, creates a draft task in `30_Tasks/coach-drafts/`, logs the action.
- **Dismiss** = check the dismiss box. Optionally Aaron can append a free-text reason — the coach reads it and uses it for future calibration (e.g., "dismissed because I already decided this offline").
- **Snooze 7d** = check the snooze box. The insight disappears from "New" and re-surfaces in 7 days *if the pattern still holds*. If the pattern has resolved (e.g., the hip decision was made), the insight is auto-closed with a positive note.

### 9.4 Weekly email

Sunday 6 PM (cron slot `:53`, currently open per CLAUDE.md), HTML + text:
- Subject: `Coach — Week of 2026-05-12 — 3 observations`
- Body: top 5 insights from the week, with one-line summaries + confidence labels + link to coach-inbox.md for full text.
- Sender: existing Gmail SMTP credential.
- Length budget: ≤ 200 words body + 5 bullets.

### 9.5 Monthly write-up

1st of month, longer (≤ 500 words), prose-format reflection on month's patterns + which insights Aaron accepted vs dismissed + a *gentle* prompt: "Anything you'd want to revisit?" Posted to `40_Timeline_Weekly/Monthly/<YYYY-MM>-coach-review.md` and emailed.

---

## 10. Cost Model

### Per-week budget

| Loop | Frequency | Tokens in (est.) | Tokens out (est.) |
|---|---|---|---|
| Pattern Surfacer | Weekly | 30K | 4K |
| Deferment Detector | Weekly | 15K | 2K |
| Promise-Keeper | Weekly | 8K | 1K |
| Energy Mapper | Monthly (1/4 of weekly) | 5K | 1K |
| Faith-Life Feedback | Weekly | 10K | 1K |
| Business Pacing | Weekly | 8K | 1K |
| Family Attention | Weekly | 5K | 0.5K |
| Quarterly Horizon | Weekly (Sundays) | 12K | 2K |
| Non-prescription classifier | Per insight | 1K × ~10 | 0.2K × ~10 |
| Privacy filter | Per insight | regex only | 0 |
| **Weekly total** | | **~100K** | **~14K** |

OpenRouter free-tier:
- llama-3.3-70b-instruct: ~100 req/day = 700/week. Each loop is 1–2 requests. Total ~15 requests/week. **Well under quota.**
- gemma-3-4b: classifier work (~10–30 small calls). Under quota.
- nemotron-120b: never hit in normal operation.

**Estimated cost: $0/month.**

### Opus opt-in path

For the monthly write-up only, Aaron may opt to use Opus (the prose quality matters more). Flag: `--allow-opus`. Hardcoded cap: 1 Opus call per month, ≤ 8K tokens in / 1K out. Estimated max cost: $0.20/month.

### Failure mode: free tier exhausted

Same as ADR-0002 — cascade falls through, then regex-only descriptive output (no AI summarization, just "Counts: X. Dates: Y."). Functional, not pretty.

---

## 11. Failure Modes

### 11.1 Hallucination

**Risk:** coach asserts something not in the vault.
**Mitigation:** every claim must trace to a source citation in `sources[]`. Source must be re-readable. Audit script `audit_coach_groundedness.py` randomly samples 10 emitted claims/week, re-reads source, confirms text supports claim. Failure rate ≤ 0% required.

### 11.2 Sycophancy

**Risk:** the coach learns to flatter (high "usefulness" ratings → biased toward agreeable output).
**Mitigation:** usefulness rating is one signal among five. **No prompt training on Aaron's ratings.** The model is frozen; ratings only affect the alert thresholds, not the prompt. Quarterly "challenge week" where the coach is allowed to surface uncomfortable patterns explicitly (Aaron pre-consents to a higher-friction week).

### 11.3 Doom-spiraling

**Risk:** coach surfaces a stream of "you deferred this," "you didn't keep that promise" → erodes morale.
**Mitigation:**
- **Mandatory positivity floor:** every weekly batch must include at least 1 *neutral* or *positive* observation (a delta moving in Aaron's stated-target direction). Enforced by detector logic.
- **Tone-rating threshold:** if Aaron's tone ratings drop below 3.5 for 2 weeks, the coach auto-pauses for a week.
- **Aaron's "quiet mode" flag:** Aaron can write `coach_mode: quiet` in `99_System/coach/config.json` and the coach emits only the Quarterly Horizon for that period.

### 11.4 Decision-pushing

**Risk:** despite the non-prescription classifier, edge cases slip through.
**Mitigation:**
- Classifier eval: 0 false-negatives required out of 50 examples.
- Aaron can manually flag any output as "this tried to make a decision for me" — flagged examples are added to the eval dataset and a new classifier check is run.
- Quarterly review of all `rejections/` to confirm classifier is doing its job.

### 11.5 Privacy bleed

**Risk:** family-domain or health-domain detail leaks into emails or coach-inbox.
**Mitigation:**
- Privacy filter runs on every emission.
- Family-domain insights have an additional manual-review gate for the first 4 weeks of operation (Aaron confirms each before emission). After 4 weeks of clean automated emission, manual gate drops.
- No coach output ever crosses the SMTP boundary without privacy-filter pass.

### 11.6 Eval drift

**Risk:** thresholds get adjusted to make the system "ship-able" — a slow-rolling lowering of standards.
**Mitigation:** thresholds are committed to git with the spec. Any threshold change requires a PR, an ADR explaining why, and Aaron's sign-off. Audit script `audit_coach_thresholds.py` reads thresholds from the spec file and from the running config; if they differ, fails CI.

### 11.7 Model deprecation

**Risk:** OpenRouter removes llama-3.3-70b-instruct (the workhorse).
**Mitigation:** model-chain is a config list. Adding a replacement is one PR. The eval suite re-runs on the new model and must pass before the new model is allowed.

### 11.8 The "I tuned it out" failure

**Risk:** Aaron stops opening coach-inbox.md.
**Mitigation:** open-rate is a tracked metric (file `accessed_at` via S3 metadata or via Aaron self-reporting in weekly digest). If unread for 3+ weeks, the coach pauses itself and emails Aaron one line: *"Coach paused — open coach-inbox.md to restart."*

---

## 12. Acceptance Criteria (thresholds, not vibes)

P7 v0 ships only when **all** of these are met:

- [ ] **Eval suite GREEN** on 50-example dataset for ≥ 2 consecutive weeks
- [ ] **Non-prescription classifier** ≥ 95% accuracy on 50-example must-pass/must-fail set
- [ ] **Faith non-moralizing classifier** 100% accuracy on 30-example set
- [ ] **Family privacy classifier** 100% accuracy on 20-example set
- [ ] **Brier score ≤ 0.15** on confidence-label calibration for first 20 insights
- [ ] **Tone ≥ 4.0 mean** from Aaron on first 20 emitted insights
- [ ] **Usefulness ≥ 4.0 mean** after week 4 of soak
- [ ] **Zero family-name leaks** in 30 randomly-sampled emitted insights
- [ ] **Zero life-decision recommendations** in 100 randomly-sampled emitted insights
- [ ] **Write allowlist** test-enforced (any attempt to write outside `COACH_WRITE_ALLOWLIST` fails CI)
- [ ] **Audit scripts** green: `audit_coach_receipts.py`, `audit_coach_groundedness.py`, `audit_coach_thresholds.py`
- [ ] **Aaron's explicit sign-off** that the first 4 weekly emails were useful AND non-noisy AND tonally right

If any criterion fails: **do not ship**. Re-spec or cut scope.

---

## 13. Risks + Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hallucination in production | M | HIGH | groundedness audit, source citations mandatory, weekly random sample re-read |
| Coach becomes prescriptive | M | HIGH | non-prescription classifier, 50-example eval, manual flag mechanism |
| Aaron tunes it out | M | MEDIUM | self-pause on unread, weekly budget cap, tone monitoring |
| Eval threshold drift | M | MEDIUM | thresholds in git, ADR-gated changes |
| Free-tier rate limit | L | LOW | cascade, regex fallback (ADR-0002) |
| Family-info leak via email | L | CRITICAL | privacy filter, manual review for first 4 weeks |
| Faith-domain moralizing | M | HIGH | dedicated faith non-moralizing classifier |
| Coach surfaces a "decision" Aaron then regrets | L | HIGH | the coach never makes decisions; Aaron's actions are his own. Reinforced in tone of every emission. |
| Compounding bias toward agreeable output | L | MEDIUM | no prompt-training on ratings; ratings are alerts, not signals |
| OpenRouter model deprecation | M | LOW | model-chain config, eval-rerun gate |

---

## 14. Dependencies

P7 cannot start until ALL of these have landed and soaked:

| Dependency | Phase | Why |
|---|---|---|
| **P1 + P1.5 + ADR-0006 stable in prod** | done — soak through 2026-05-18 | foundation; receipts + state machine + command center must be reliable before adding any layer above them |
| **P2 — Threaded tasks with stable task_id** | P2 | deferment detector needs task lineage; promise-keeper needs cross-week task identity; convert-to-task needs `[source::]` linking |
| **P3 — Capture-from-anywhere history** | P3 | pattern surfacer needs sufficient capture density across surfaces (mobile, voice, email) to detect domain-specific patterns |
| **P4 — Decision-ready briefings** | P4 | the morning briefing format establishes the "today's ONE thing" pattern the coach refers back to in the accountability ledger |
| **P5 — Review rituals** | P5 | weekly + monthly + quarterly templates establish the cadence the coach piggybacks on; weekly digest is the Promise-Keeper input |
| **P6 — Domain-aware UX** | P6 | per-domain weighting (`weights.json`) + privacy deny-list + domain-specific eval criteria all depend on P6 having defined the per-domain contract |
| **biohacking-data-pipeline emitting reliable data** | parallel | Energy Mapper loop is disabled without it |
| **≥ 30 days of post-P6 vault data** | post-P6 | eval dataset requires real Aaron data, not synthetic. ~30 days is the floor for cross-week pattern signal. |
| **Aaron's curated 50-example eval dataset** | gating | ~8 hours of Aaron's time. Cannot be skipped or AI-generated. |

**If P2–P6 are not all in prod for ≥ 30 days, P7 v0 work does not begin.** This is non-negotiable.

---

## 15. Parallel Sub-Lanes

Once P7 starts (post-dependencies), work can split into 4 lanes:

### Lane A — Detectors (deterministic core)
- Implement each of the 9 loop detectors as pure functions
- Test each against synthetic + 30-day real data
- No LLM involvement; this lane lands first

### Lane B — Summarizer + Confidence Tagger
- Prompt engineering for the per-loop summarizers
- Confidence-label validator (post-hoc grounding check)
- Brier-score eval harness

### Lane C — Guardrail Sieve + Eval Suite
- Non-prescription classifier
- Faith non-moralizing classifier
- Family privacy classifier
- Eval dataset curation (Aaron-time-gated)

### Lane D — Coach-Inbox UX + Email + Orchestrator
- Inbox markdown generator
- Accept/dismiss/snooze handler (file-watch or weekly batch)
- Weekly email
- Monthly write-up
- Orchestrator (`run_insight_loop.py`)
- Audit scripts

Lanes A–D can largely proceed in parallel. The first ship must integrate all four. Recommended ship order: **Quarterly Horizon first** (loop 5.8, in lane A), with minimal summarizer + full guardrail sieve + full eval suite. Then add loops in order of compounding value: 5.2 (deferment), 5.3 (promise-keeper), 5.1 (pattern), 5.8 (already shipped), 5.6 (business pacing), 5.7 (family — with extra manual gate), 5.4 (energy — gated on biohacking pipeline), 5.5 (faith — last, with extra eval gate).

---

## 16. Effort

| Lane | Estimate (after dependencies clear) |
|---|---|
| A — Detectors (9 loops) | 3 weeks |
| B — Summarizer + confidence + Brier | 2 weeks |
| C — Guardrail sieve + eval suite | 3 weeks (gated on Aaron's 8h eval dataset curation) |
| D — UX + email + orchestrator + audits | 2 weeks |
| Integration + 4-week soak | 4 weeks |
| **Total** | **~14 weeks once dependencies are clear** |

This is deliberately long. **A short P7 is a failed P7.** The soak is part of the work, not the wrapper around it.

---

## 17. Verification Strategy

### Per-component

- **Detectors:** unit tests with synthetic vault snapshots. Each detector has ≥ 5 positive and ≥ 5 negative examples.
- **Summarizers:** snapshot tests against the eval dataset; output must match expected confidence labels and source citations.
- **Guardrail sieve:** classifier accuracy on hand-labeled set; ≥ 95% / 100% per §8.
- **Privacy filter:** 30 examples; 0 leaks.
- **Allowlist:** chaos test — try to write to MTL / brain-dump source / daily note; assert it raises.

### End-to-end

- **Dry-run mode:** runs every loop against last week's data and writes to `99_System/coach/pending/`. Aaron reviews. Nothing emitted until he approves.
- **First 4 weeks:** human-in-the-loop. Every batch is held in `pending/` and Aaron confirms emission via a `make coach-emit` command. After 4 weeks of clean operation, auto-emission unlocks.
- **Audit scripts:** wired into the weekly vault-health-report.

### Soak

- 4 weeks human-in-the-loop, then 4 weeks auto-emission monitored. P7 is "shipped" only after 8 weeks of clean operation.

---

## 18. Open Questions

These are real questions for Aaron, not rhetorical:

1. **Weekly email day/time.** Sunday 6 PM CDT (cron `:53` slot) is the obvious choice — but the existing Weekly Digest already runs Sun 6 PM. Should coach piggyback (one email, two sections) or be a separate Sunday email at a different time?
2. **Coach voice ownership.** Should the coach refer to itself ("I noticed...") or to Aaron in 2nd person ("You wrote...") or strictly 3rd-person observational ("The hip decision appears...")? Each has tradeoffs. Current spec leans 2nd-person + observational mix.
3. **Faith-domain participation.** Is the coach allowed at all in the faith domain, or should that be entirely opt-in (i.e., off by default, Aaron flips a flag if he wants it)? Spec currently includes it with strict guardrails; a fully opt-in flag is an easy add.
4. **The "challenge week" quarterly cadence.** Does Aaron want one week per quarter where the coach is licensed to surface uncomfortable patterns more directly? If yes, what's the explicit consent ritual that opens it?
5. **Convert-to-task draft destination.** Spec says `30_Tasks/coach-drafts/` (assumes P2 task storage layout). If P2 lands a different shape, this rebinds.
6. **Health-domain default tone.** When the coach observes "you've skipped gym 5 of last 7 days," is the right output (a) just the count, or (b) the count + Aaron's own stated target ("you wrote you wanted 3×/week"), or (c) the count + target + a "do / delegate / drop" prompt? Spec defaults to (b); (c) feels coach-y and may cross the line.
7. **Per-domain emission off-switches.** Should each of the 9 loops have an independent on/off flag in `99_System/coach/config.json`? (Strong yes per current spec — confirms.)
8. **Insight surfacing latency.** When the pattern detector finds a major drift mid-week, does it wait for Sunday's email or surface to coach-inbox.md immediately (no notification)? Spec defaults to "always wait for Sunday for email; immediate-update is OK for coach-inbox.md since Aaron must open it deliberately."
9. **The Bible-reading streak — does Aaron want this tracked at all?** It feels useful but it is the highest-risk feature in the whole spec for becoming spiritually prescriptive. Spec includes it; happy to cut.
10. **Long-horizon insights (year-over-year).** P7 v0 is week/month-over-month. Year-over-year ("a year ago today you wrote...") is its own thing. In v0 or v1?

---

## Appendix A — Mapping to CLAUDE.md anti-hallucination rules

| CLAUDE.md rule | P7 implementation |
|---|---|
| File-grounded claims: re-read before citing | every claim has a `sources[]` entry; `audit_coach_groundedness.py` re-reads weekly |
| Versions/dates/numbers VERIFIED only with current-context source | counts and dates always VERIFIED; everything else downgrades |
| Pushback signal: stop, re-read, acknowledge | Aaron's "this tried to decide for me" flag adds the offending case to the eval dataset and re-runs the classifier |
| Confidence labels: VERIFIED · LIKELY · UNCERTAIN · SPECULATIVE · UNKNOWN | mandatory on every claim, post-hoc validator, Brier-scored |
| Never present LIKELY+ as VERIFIED | post-hoc validator can only downgrade, never upgrade |
| AI is fallback to regex-first | all detectors are deterministic Python; LLM only summarizes pre-grounded observations |

## Appendix B — Why this MUST be last in the roadmap order

1. **The coach needs data history.** Compounding insights ("you've deferred this 6 times") are nonsensical with < 6 months of capture data.
2. **The coach needs P2 task identity.** Deferment detection requires stable task IDs across deferrals.
3. **The coach needs P3 capture surfaces.** A coach reading only desktop captures has a partial view of Aaron's life.
4. **The coach needs P4 briefings.** The Promise-Keeper ledger reads from the morning briefing format.
5. **The coach needs P5 review rituals.** Weekly digest is a primary input.
6. **The coach needs P6 domain-aware UX.** Per-domain weighting, privacy deny-list, and domain-specific eval criteria all depend on P6.
7. **The coach's failure mode is corrosive.** Unlike P1–P6 (which fail silently or with email alerts), a bad coach erodes trust in the entire system. Shipping it before the foundation is bulletproof risks every other layer.
8. **The coach is the highest-stakes prompt in the system.** It speaks to Aaron about his own life. It earns that privilege by being the last thing built — when the system has the most context, the most stable data shape, and the most operator confidence.

---

_End of P7 spec. No code in this document is to be implemented until P2–P6 are live for ≥30 days and Aaron has approved the 50-example eval dataset._

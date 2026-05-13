# P5 Review Rituals + P6 Domain-Aware UX — Combined Design Spec

**Date:** 2026-05-12
**Status:** Draft — for review, then ADR split (`docs/adr/0007-review-rituals.md` + `docs/adr/0008-domain-aware-ux.md`)
**Author:** Claude (research/spec) + Aaron (decisions)
**Phase:** Life Orchestrator v1.0 → P5 (rituals) + P6 (domain UX)
**Depends on:** P1 (state machine + receipts — live), P1.5 (HTTP runner sidecar — live), ADR-0006 (Daily Command Center — live), P2 (threaded tasks — design-first, blocking some features), P4 (decision-ready briefings — informs ritual auto-prep)
**Hard rule:** Nothing in this spec activates until P1+P1.5+ADR-0006 have a 7-day clean soak (per CLAUDE.md). Earliest possible code start: **2026-05-18**.

---

## 0. Why this spec exists

OHO already captures, dedups, and surfaces tasks. The next leap is **rituals that auto-prep themselves and feel inevitable** (P5) and **domain lenses that make each life area first-class** (P6). These two phases compound: rituals are where domain data gets reviewed; domain views are where ritual outputs become decisions. Splitting them into separate specs would force one to mock the other. Combined.

The 8 canonical Life Domains are the spine of both phases and **never deviate**:
`faith · family · business · consulting · work · health · home · personal`

---

# PART A — P5: Review Rituals

## A1. Goal + Magical Moments

### Goal
Transform the existing Sunday-6PM weekly-digest email (one-shot fire-and-forget) into a **layered rhythm of five rituals** — daily/weekly/monthly/quarterly/annual — each auto-prepped in the vault so Aaron starts with answers, not blank pages. Each ritual produces decisions that flow back into MTL (P2 backing files) and the Daily Command Center.

The system never shames a missed ritual. It catches up gracefully, tracks streaks gently, and treats reviews as the place the system thinks *with* Aaron — not for him.

### Magical Moments
1. **Sunday afternoon, vault open.** Aaron opens `40_Timeline_Weekly/Weekly/2026-W19.md`. The page is already filled in: rocks completion %, domain balance heatmap, the 3 decisions he deferred from last week, what compounded, what stalled, AI-drafted summary of the week's wins. He spends 25 minutes editing/approving, not writing. 45-minute "review" finishes in 25.
2. **Tuesday morning, he missed last week.** Opens vault, gets the Daily Command Center. A `> [!warning]+` callout at the top: *"You missed the 2026-W18 weekly review. Combined 2-week view is ready at [[2026-W18-W19]]."* Single click, the combined view has both weeks' data pre-rolled. No shame, no reset.
3. **End of January.** Monthly review auto-prep includes biomarker delta from Oura, MTL completion rates per domain, a "what compounded vs what stalled" diff against December, and three drafted Q1-pacing decisions. Aaron writes the *narrative*, the *numbers* are already there.
4. **Quarterly close.** Q1 review document opens with rituals-retro built in: *"You did weekly review 11/13 weeks, daily evening close 56/91 days. Best streak: 14 days (Feb 2–15). Worst gap: 8 days (Feb 22–Mar 1, work travel)."* Honest mirror, no judgement.
5. **Yesterday's daily evening close.** 5 minutes. Aaron rates the day 1-10, the system highlights the 3 tasks he marked done that map to Q2 rocks (compounding feedback), suggests tomorrow's ONE thing from his ready-to-act queue, captures one gratitude line.

## A2. Scope + Ritual Inventory

| Ritual | Cadence | Target time | Surface | Status today |
|---|---|---|---|---|
| **Daily evening close** | Every weekday + Sunday | 5 min | `40_Timeline_Weekly/Daily/<YYYY-MM-DD>.md` (existing daily note — append a section) | New |
| **Weekly review** | Sunday afternoon (Aaron-driven, no fixed time) | 45 min | `40_Timeline_Weekly/Weekly/<YYYY>-W<NN>.md` | Email-only today; needs vault note |
| **Monthly review** | Last Sunday of month | 90 min | `40_Timeline_Weekly/Monthly/<YYYY>-<MM>.md` | New |
| **Quarterly review** | Last weekend of quarter (half-day) | 4 hrs | `40_Timeline_Weekly/Quarterly/<YYYY>-Q<N>.md` | New |
| **Annual review** | Last week of December (full day) | 1 day | `40_Timeline_Weekly/Annual/<YYYY>.md` | New |

**Out of scope for P5:**
- Voice capture (deferred — P3)
- AI coach email loop (deferred — P7)
- Domain-specific ritual variants (handled in P6 via hooks, not separate rituals)

## A3. Architecture

### Three layers

```
┌──────────────────────────────────────────────────────────────┐
│ 1. RENDERERS (tools/rituals/*.py)                            │
│    Pure-function template generators. Read MTL + receipts +  │
│    biomarkers + state files. Write vault-local markdown.     │
│    Idempotent. Verified writes. Same pattern as              │
│    build_command_center.py.                                  │
├──────────────────────────────────────────────────────────────┤
│ 2. AI SUMMARIZER (tools/rituals/summarize.py)                │
│    Calls the existing ai-brain sub-workflow (Llama 3.3 70B   │
│    via OpenRouter). NEVER touches family/kid data. Drafts    │
│    only narrative sections — never decision sections.        │
├──────────────────────────────────────────────────────────────┤
│ 3. SCHEDULER (n8n workflows)                                 │
│    Each ritual gets its own workflow with a unique cron      │
│    slot. Workflows call the OHO runner sidecar via HTTP      │
│    (P1.5 boundary). Renderer outputs are written by the      │
│    runner; n8n only triggers + emails the link.              │
└──────────────────────────────────────────────────────────────┘
```

### Renderer pattern (mirror of `build_command_center.py`)

Each ritual is a Python module under `tools/rituals/`:
- `tools/rituals/daily_close.py` — appends evening close section to today's daily note
- `tools/rituals/weekly_review.py` — emits `40_Timeline_Weekly/Weekly/<YYYY>-W<NN>.md`
- `tools/rituals/monthly_review.py` — emits `40_Timeline_Weekly/Monthly/<YYYY>-<MM>.md`
- `tools/rituals/quarterly_review.py` — emits `40_Timeline_Weekly/Quarterly/<YYYY>-Q<N>.md`
- `tools/rituals/annual_review.py` — emits `40_Timeline_Weekly/Annual/<YYYY>.md`

Each module exports:
```python
def render(*, today: date, source: dict, ai_drafts: dict | None) -> str: ...
def main() -> None: ...  # CLI entry point — reads MinIO, writes verified
```

The renderer is pure (string in, string out) so unit tests run without MinIO. `main()` does S3 reads/writes with `s3_put_verified` (head_object verification, identical pattern to existing tools).

### AI summarizer (`tools/rituals/summarize.py`)

Single function:
```python
def summarize(
    *,
    ritual: Literal["weekly", "monthly", "quarterly", "annual"],
    window: tuple[date, date],
    facts: dict,        # MTL deltas, rocks progress, daily ratings — NO family/kid names
    redact_keys: set[str] = frozenset({"family", "kids", "christy_check_in"}),
) -> dict:              # {"narrative": str, "compounded": str, "stalled": str}
```

- Calls the existing `ai-brain` sub-workflow via HTTP POST to the OHO runner sidecar (new endpoint `/ai-summarize` — extends P1.5 contract).
- **Redact pass before sending:** any field whose key matches `redact_keys` is stripped. Family check-ins are surfaced in the rendered note as headings only; Aaron fills them by hand. The AI never sees Christy's name, kids' names, marriage questions, or any field tagged `[private:: true]`.
- Outputs three short narrative fields. Renderer composes them into the note.
- If the AI call fails, the renderer still produces a useful note — the narrative sections render as `> [!note]- AI draft unavailable — write your own here` callouts.

### Scheduler (n8n workflows)

Each ritual gets its own n8n workflow file:

| Workflow | Cron | Code-heavy? | Slot |
|---|---|---|---|
| `daily-close-prepper.json` | 0 21 * * * (9PM CDT = 02:00 UTC daily) | No (HTTP only) | n/a |
| `weekly-review-prepper.json` | 0 14 * * 0 (Sunday 2PM CDT = 19:00 UTC) | No (HTTP only) | n/a |
| `monthly-review-prepper.json` | 0 14 28-31 * 0 (last Sun of month, 2PM CDT) | No | n/a |
| `quarterly-review-prepper.json` | 0 14 * 3,6,9,12 0 (last Sun of Mar/Jun/Sep/Dec) | No | n/a |
| `annual-review-prepper.json` | 0 14 24-31 12 0 (last Sun of Dec) | No | n/a |

**Why no Code nodes:** every ritual delegates the heavy lifting to the OHO runner sidecar via the HTTP boundary established in P1.5. The n8n workflow is three nodes: trigger → HTTP POST to runner → email Aaron the vault link. This sidesteps the `:43`/`:53` task-runner slot scarcity, the 60s task-runner stall, and the executeCommand-removal regression entirely.

**Decoupling rule:** the weekly-review-prepper does NOT replace the existing `weekly-digest-v2` Sunday-6PM email. The prepper runs Sunday 2PM (writes the vault note); the digest still runs Sunday 6PM (email summary, links to the prepared note). The email becomes a *handoff to the vault*, not the destination. After 4 weeks of soak the email shrinks to a 3-line "your weekly review is ready" link card; the rich digest content lives in the vault note where Aaron can edit it.

## A4. Data Model

### Ritual record (vault note frontmatter)
Each ritual file has stable frontmatter:
```yaml
---
type: ritual
ritual: weekly                    # daily | weekly | monthly | quarterly | annual
window_start: 2026-05-04          # YYYY-MM-DD
window_end:   2026-05-10
generated_at: 2026-05-10T19:00:00Z
generator: tools/rituals/weekly_review.py
ai_draft: true                    # was AI summarizer called?
ai_redacted_keys: [family, kids]  # what was held back from AI
status: prepared                  # prepared | in_progress | completed | skipped
completed_at: null
combined_with: null               # if catch-up, list of windows folded in
streak: 5                         # consecutive completed rituals at this cadence
---
```

### Ritual state index (`99_System/state/ritual-state.json`)

A single JSON file that's the source of truth for streaks, last-completed timestamps, and missed-ritual catch-up:
```json
{
  "daily_close": {
    "last_completed": "2026-05-11",
    "current_streak": 5,
    "longest_streak": 14,
    "missed_dates": []
  },
  "weekly_review": {
    "last_completed_window": "2026-W18",
    "current_streak": 3,
    "longest_streak": 7,
    "skipped_windows": ["2026-W14"]
  },
  "monthly_review": {
    "last_completed_window": "2026-04",
    "current_streak": 2,
    "longest_streak": 4
  },
  "quarterly_review": { "last_completed_window": "2026-Q1", "current_streak": 1 },
  "annual_review":    { "last_completed_window": "2025",   "current_streak": 1 }
}
```

This file is updated by:
- The renderer (writes `status: prepared` and bumps `last_attempted` when it generates a new ritual file)
- A new audit script `scripts/audit_ritual_completion.py` that scans vault ritual files and infers `completed` status from frontmatter + manual check (a `<!-- ritual-complete -->` HTML comment Aaron drops at the bottom when he's done)

### Domain weight allocation (links to P6)
The weekly/monthly review reports drift against Aaron's domain weight targets. Targets live in `99_System/config/domain-weights.yaml`:
```yaml
# Target % focus per domain per week. Sums to 100.
faith:      10
family:     20
business:   20
consulting: 15
work:       20
health:     10
home:        3
personal:    2
```

Renderer compares actual hours/tasks-touched against targets and renders a drift heatmap in the weekly review's Domain Balance section.

## A5. Sequence Diagrams

### A5.1 Daily evening close (9 PM cron)
```
n8n cron (9PM CDT)
    │
    ▼
HTTP POST /append-daily-close ──► OHO runner sidecar
                                       │
                                       ▼
                              tools/rituals/daily_close.py
                                       │
                                       ├──► read MTL: tasks marked done today
                                       ├──► read state: yesterday's daily note (review-the-day cues)
                                       ├──► append section to today's daily note:
                                       │      ## 🌙 Evening Close
                                       │      - [ ] Sweep: yesterday's open tasks → mark done or carry
                                       │      - [ ] Rate today (1-10):
                                       │      - [ ] Tomorrow's ONE thing (auto-suggested from MTL):
                                       │      - [ ] Gratitude (one line):
                                       │      - [ ] Sleep cue (lights out by):
                                       └──► verified PUT to MinIO
    │
    ▼
HTTP 200 ──► n8n
    │
    ▼
Done. No email — Aaron sees it next time he opens the vault.
```

The auto-suggested "tomorrow's ONE thing" is computed by re-running the same `pick_top_priority()` function from `build_command_center.py`. Same logic, one source of truth.

### A5.2 Weekly review (Sunday 2 PM)
```
n8n cron (Sun 2PM CDT)
    │
    ▼
HTTP POST /prep-weekly-review ──► OHO runner sidecar
                                       │
                                       ▼
                              tools/rituals/weekly_review.py
                                       │
                                       ├──► read MTL: last 7 days deltas, rocks progress
                                       ├──► read 7× daily notes from 40_Timeline_Weekly/Daily/
                                       ├──► read receipts: extraction activity by domain
                                       ├──► read ritual-state.json: streak + missed weeks
                                       ├──► check for missed week → if last_completed_window
                                       │    is more than 1 week behind:
                                       │       a. generate "combined view" filename:
                                       │          2026-W18-W19.md (window_start = W18 Monday)
                                       │       b. fold both weeks' data into one note
                                       │
                                       ├──► IF Aaron's redact rule trips on `family.*` → flag
                                       │    those facts NOT sent to AI
                                       ├──► call /ai-summarize via runner → narrative + compounded + stalled
                                       │    (timeout 30s; on fail, fallback empty draft)
                                       │
                                       └──► render vault note:
                                              # Weekly Review — Week of 2026-05-04
                                              ## 🎯 Q2 Rocks — completion %
                                              ## 📊 Domain Balance Heatmap (vs targets)
                                              ## 🌱 What Compounded This Week (AI draft)
                                              ## 🥀 What Stalled (AI draft)
                                              ## 🤔 Decisions Made vs Deferred
                                              ## 👨‍👩‍👧 Family Check-in (PRIVATE — no AI)
                                              ## 🪨 Next Week — 3 Rocks Per Domain (max)
                                              ## 📅 Calendar Audit
                                              ## ✏️ Narrative (your words)
                                              <!-- ritual-complete (drop this comment when done) -->
    │
    ▼
n8n → email Aaron: "Weekly review ready: [[2026-W19]]"
```

### A5.3 Monthly / Quarterly / Annual
Same pattern as weekly. Differ in:
- Window length (30 / 90 / 365 days)
- Data sources (monthly adds biomarker delta from biohacking pipeline if running; quarterly adds rituals-retro and goal-pacing math; annual adds 1/3/10-year horizon templates)
- AI prompt template (`prompts/rituals/<cadence>.txt`)
- Cron schedule (see scheduler table)

### A5.4 Missed-ritual catch-up flow
```
n8n weekly cron fires
    │
    ▼
Renderer reads ritual-state.json
    │
    ├── current_streak vs last_completed_window
    │
    ├── If gap == 1 week → normal weekly note
    ├── If gap == 2-3 weeks → combined catch-up note (W18-W19, W17-W19, ...)
    │   - Renders one section per missed week
    │   - AI narrative compares "compounded across both weeks"
    │   - Streak: NOT reset, marked "recovered"
    │
    └── If gap > 3 weeks → "Long break" mode
        - Single note: "Welcome back. Here's a 28-day rollup."
        - No per-week breakdown (too noisy)
        - Streak resets gracefully (longest_streak preserved)
        - Top of file: "It's been 4 weeks. That's data, not failure."
```

## A6. Per-Ritual Mini-Specs

(Domain mini-specs live in Part B / Section B6. These are the rituals themselves.)

### A6.1 Daily Evening Close
- **5-minute promise.** 5 inputs, 5 lines.
- **Auto-prepped inputs:**
  - Today's done-task count, broken by domain (one-line summary)
  - Yesterday's "tomorrow's ONE thing" — was it done?
  - Suggested tomorrow ONE thing from `pick_top_priority()`
- **What Aaron types:** rating (1-10), gratitude line, lights-out time.
- **Compounding loop:** done-tasks that match Q2 rocks get a 🪨 marker in the section; over time this trains attention.
- **Edge case:** if Aaron opens the vault past midnight, the renderer's "today" date already advanced — the section is appended to the new day. Daily close for the previous day is missed. Tracked, not shamed.

### A6.2 Weekly Review
- **45-min promise.** Page is already filled in; Aaron edits and reviews, doesn't write from scratch.
- **Auto-prepped sections:**
  - Rocks completion % per Q2 rock (numbers from MTL parsing)
  - Domain balance heatmap (tasks touched per domain vs target weight)
  - Decisions made vs deferred (parsed from daily notes' rating sections + new "deferred" syntax `> [!decision]- DEFERRED — ...`)
  - What compounded / stalled (AI narrative draft)
  - Calendar audit (manual for now — depends on GCAL_CRED_ID per CLAUDE.md)
- **Decision capture:** every decision Aaron writes in `## 🤔 Decisions Made vs Deferred` with a `[decision::]` tag flows into a `99_System/state/decisions-log.jsonl` append-only file. P4 briefings read this to surface stale decisions.

### A6.3 Monthly Review
- **90-min promise.**
- **Auto-prepped:**
  - Quarterly rocks pacing (% complete vs days elapsed in quarter)
  - Theme of the month (Aaron-set at month start; AI suggests a candidate from week-narratives)
  - Financials snapshot — manual entry fields for consulting income, business pipeline, Parallon (numbers not pulled — Aaron types; system tracks deltas across months once entered)
  - Health biomarker trend — IF `biohacking-data-pipeline` is live, plot CGM/HRV/sleep trends. ELSE render `> [!info]- Biohacking pipeline not yet live — manual entry section below`
  - Family check-in template — heading + prompts only, **AI never reads this section**
  - Business pipeline (Echelon Seven offers per pipeline stage)
  - Faith check-in (Bible reading streak, prayer commitments — populated from faith-domain dashboard P6)
- **Decision capture:** same as weekly.

### A6.4 Quarterly Review
- **Half-day promise.**
- **Auto-prepped:**
  - Annual rocks pacing
  - Season's intention (Aaron-set at quarter start)
  - **Rituals retro** — auto-computed from `ritual-state.json`: "You did weekly review X/13, daily close Y/91 days. Best streak: Z."
  - Goals refresh — last quarter's rocks → drafted next-quarter rocks (Aaron approves/edits)
- **No AI for goals.** AI proposes nothing about next-quarter goals. It can summarize last quarter, never project next.

### A6.5 Annual Review
- **Full-day promise.**
- **Auto-prepped:**
  - Vision document refresh (read last year's `40_Timeline_Weekly/Annual/<YYYY-1>.md` + monthlies)
  - Prior-year audit: rituals completion %, Q-by-Q rocks completion, domain weight drift
  - 1/3/10-year horizon templates (Echelon Seven, family, faith, health span)
- **No AI for horizons.** AI summarizes the past year only. Horizons are Aaron's alone.

## A7. Failure Modes + Guardrails

| Failure | Detection | Response |
|---|---|---|
| MinIO unreachable when ritual fires | Runner returns 503 from health probe before doing work | n8n records skip in run log with `skip_reason: minio_auth_error`; email alert via error-handler; ritual re-attempts next day for daily, no auto-retry for weekly+ (Aaron triggers manually via `make ritual-weekly`) |
| AI summarizer fails / times out | 30s timeout in `/ai-summarize` call | Ritual note still renders; narrative sections show `> [!note]- AI draft unavailable — write your own here`; no email-blocking |
| Aaron misses a ritual | `ritual-state.json` shows gap | Combined catch-up note (see A5.4); streak preserved as "recovered"; never reset on first miss |
| Aaron edits the ritual note then renderer fires again | Idempotency check: if frontmatter `status: in_progress` OR `<!-- ritual-complete -->` present, renderer writes to `<filename>-regen.md` instead of overwriting | Aaron can compare/merge; never lose human-edited content |
| Renderer writes garbage (bug) | Verified write (`head_object` + readback) catches truncation; unit tests catch logic | If readback fails, retry once then alert; previous version retained in MinIO versioning |
| AI redaction rule misses a private field | Manual review during P5 soak; spec rule (`A8.privacy`) makes redaction explicit | Conservative default: ANY field whose key contains `family`, `kids`, `christy`, `private`, or `[private:: true]` tag is stripped before AI call |
| Family check-in section accidentally fed to AI | Hard rule in `summarize()`: redact_keys is mandatory parameter; CI test verifies | Test in `tests/test_rituals.py::test_ai_redaction_strips_family_data` blocks merge |
| Catch-up note size explodes (12+ weeks missed) | Renderer caps at 4-week rollups | If >4 weeks, single "Welcome back" note (A5.4 long-break mode) — no per-week detail |

## A8. Privacy (Critical)

- **Family/kid names never leave the vault.** They are stored in `99_System/config/family.yaml` (vault-local, gitignored, never synced to MinIO public scope). The renderer reads this to populate headings ("How was Christy this week?") but the values are never sent to the AI summarizer.
- **Redact rule:** `summarize()` strips any dict key containing `family`, `kids`, `christy`, `private`, or with an Obsidian `[private:: true]` tag. CI test enforces.
- **Faith content** — Aaron can opt-in (his choice) to AI summarization of prayer journal entries. Default: **off**. Toggle in `99_System/config/ritual-privacy.yaml`.
- **Health biomarkers** — Aaron's data. AI may summarize trends ("HRV up 8% this month") but **never** specific values (no "your HRV was 47 on Tuesday"). Trend-only language enforced via prompt template.
- **Audit log** — every AI call writes `99_System/logs/ai-summarize-<date>.jsonl` with: ritual, window, fields_sent (keys only — never values), fields_redacted, response length. Aaron can grep this to verify nothing leaked.

## A9. Acceptance Criteria

P5 ships when ALL of:
1. All 5 ritual renderers exist under `tools/rituals/` and have ≥80% unit test coverage.
2. All 5 n8n workflows imported via `scripts/setup-n8n.sh` (template-style with `__MINIO_CRED_ID__` placeholders).
3. OHO runner sidecar has 5 new bearer-authed endpoints (`/append-daily-close`, `/prep-weekly-review`, `/prep-monthly-review`, `/prep-quarterly-review`, `/prep-annual-review`) + 1 internal (`/ai-summarize`).
4. `99_System/state/ritual-state.json` is updated by both the renderer (on prep) and the audit script (on complete).
5. `scripts/audit_ritual_completion.py` runs in vault-health-report and surfaces missed rituals.
6. `tests/test_rituals.py` covers: catch-up (1, 2, 3, 4+ week gaps), AI failure fallback, redaction rule, idempotency (re-render with in_progress status), domain weight drift math.
7. Manual trigger via `make ritual-daily | ritual-weekly | ritual-monthly | ritual-quarterly | ritual-annual` works in dry-run + live modes.
8. **Soak**: 4 consecutive weeks of clean weekly reviews + 28 daily closes in prod before P6 work begins.

## A10. Risks + Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Aaron writes the ritual note himself, ignoring auto-prep | Med | Low | Acceptable — prep is opt-in scaffolding, not a contract |
| AI narratives feel generic or wrong | Med | Med | Soak 4 weeks; tune prompts per ritual; allow "regenerate" via `make ritual-weekly --regenerate` |
| Vault grows unmanageable (1 weekly + 1 monthly + 1 quarterly + 1 annual = 57 ritual files/year) | Low | Low | They live in `40_Timeline_Weekly/`, which is already the temporal archive. Year folders auto-create. |
| Cron drift (last-Sunday-of-month logic) | Low | Med | n8n cron `28-31` + dayOfWeek `0` matches first Sunday in that window. Tested with edge-case month-lengths. |
| Ritual fatigue (too many surfaces) | Med | High | Daily close is OPT-IN via a vault-config flag. Monthly/quarterly/annual are aspirational — system tracks but never nags. |
| AI accidentally leaks family data | Low | Critical | Hard CI test (`test_ai_redaction_strips_family_data`); audit log; conservative redact_keys default |
| Streak shaming creeps in via UI design | Med | Med | Explicit design rule: never use the word "failed", "missed" in red, or display a "0-day streak". Always frame as "data" or "recover" |
| Catch-up notes get unwieldy | Low | Low | 4-week cap (A5.4); long-break mode is single page |

## A11. Dependencies

- **P1+P1.5+ADR-0006** must have 7-day clean soak. Per CLAUDE.md, current target is 2026-05-18.
- **P2 (threaded tasks)** — when shipped, ritual notes can backlink to task IDs in the Decisions section. Until P2, decisions link to MTL line numbers via Dataview `path` (fragile but acceptable for soak).
- **P4 (decision-ready briefings)** — informs ritual auto-prep format. If P4 ships first, monthly review's "decisions deferred" section reads from P4's decision log.
- **biohacking-data-pipeline** — optional. Monthly review degrades gracefully if absent.
- **GCAL_CRED_ID** — optional for weekly review's calendar audit section. Renders manual section if missing.

## A12. Parallel Sub-Lanes

P5 can be parallelised four ways:
1. **Lane A — Renderers**: 5 Python modules, each independent. Daily close first (smallest, fastest validation), then weekly, monthly, quarterly, annual.
2. **Lane B — Sidecar endpoints**: add 6 endpoints to `services/oho_runner/app.py`. One PR.
3. **Lane C — n8n workflows**: 5 workflows, one per ritual. One PR.
4. **Lane D — State + audit**: `ritual-state.json` schema + audit script + privacy redaction. One PR.

Lanes can land independently if renderers return reasonable defaults when state is missing.

## A13. Effort

| Lane | Estimate | Notes |
|---|---|---|
| A — Renderers | 3-5 days | Daily close: 0.5d. Weekly: 1.5d. Monthly: 1d. Quarterly: 0.5d. Annual: 0.5d. |
| B — Sidecar endpoints | 0.5 day | Mostly copy-paste from existing `/build-command-center` handler |
| C — n8n workflows | 0.5 day | All three nodes per workflow; templates similar to live-dashboard-updater |
| D — State + audit + privacy | 1 day | Including CI tests for redaction |
| **Total P5** | **5-7 days** | |

## A14. Verification Strategy

- **Unit tests** (`tests/test_rituals.py`): renderer pure-function output. Cover the 8 listed scenarios in A9.6.
- **Integration tests** (`tests/integration/test_ritual_e2e.py`): run renderer against a fixture MinIO bucket; verify output exists, parses, has expected sections.
- **AI redaction test** (`tests/test_rituals.py::test_ai_redaction_strips_family_data`): construct a `facts` dict with family.* keys; assert summarize() strips them before HTTP call (mock the runner).
- **Cron edge-case test** (`tests/test_workflow_templates.py`): assert last-Sunday-of-month cron pattern fires correctly across Feb 28/29, 30-day months, 31-day months for years 2026-2030.
- **Manual soak** (4 weeks): Aaron uses the system; we keep a `99_System/logs/ritual-feedback.md` for tuning.
- **Privacy audit** (one-time, before first prod run): manually inspect `99_System/logs/ai-summarize-*.jsonl` for any leaked field name.

## A15. Open Questions (P5)

- **Q1.** Should daily close be Mon-Fri only, or include weekends? (Default: every day; Aaron can disable weekends via `99_System/config/ritual-privacy.yaml`.)
- **Q2.** Sunday 2PM weekly prep vs Saturday evening prep? (Default: Sunday 2PM, so Aaron has fresh data from Sat's daily close.)
- **Q3.** When P4 (briefings) ships, does the weekly review's email become part of the daily briefing instead? (Hypothesis: yes, but decide after P4 design.)
- **Q4.** Should AI ever propose Q2 rocks for the next quarter? (Default: **no**, per A6.4. Revisit annually.)
- **Q5.** Family check-in section — does Aaron want a prompts file he edits separately (so prompts evolve without code changes) or hardcoded? (Default: `99_System/config/family-checkin-prompts.md` — vault-local, never seen by AI.)

---

# PART B — P6: Domain-Aware UX

## B1. Goal + Magical Moments

### Goal
Promote each of the 8 Life Domains from a `[area::]` tag to a **first-class lens** with its own dashboard, ritual hooks, and cross-domain awareness. The Daily Command Center stays the global view; each domain dashboard is the deep-dive landing page for that area.

### Magical Moments
1. **Sunday morning.** Aaron opens `20_Domains (Life and Work)/Career/Parallon/!!! WORK.md`. He sees this week's work hours allocated (vs target 20%), open tasks per project, the "boss-promised list" with last-mentioned dates, and the 3 KPIs he tracks for BAM duties.
2. **Health domain.** The hip decision is pinned at the top of `Health.md` until it's resolved. Below it: workout streak (current 7-day, longest 14), supplement protocol adherence (from health-biohacking-protocol skill), sleep trend the last 14 days.
3. **Faith domain.** Opens `Faith.md` Sunday at 5:30 AM (devotion time). Today's devotional passage is pre-rendered. Prayer queue shows requests with `last_prayed` timestamps — anyone Aaron hasn't prayed for in 7 days surfaces in red. Sermon prep workspace links to next week's Sunday school lesson.
4. **Cross-domain tension warning.** Aaron logs 25 hours on Business this week (target 20%). Daily Command Center renders `> [!warning]+ Business overshot 5h this week → Home commitments deferred 2.` It surfaces what gave way.
5. **Domain ritual hook.** Faith domain has a daily prompt: "What did you read in Scripture today?" Appended to the daily note's evening close. Each domain configures its own daily/weekly hooks.

## B2. Scope + Domain Inventory

| Domain | Dashboard file | Special tracking |
|---|---|---|
| **faith** | `20_Domains (Life and Work)/Faith/!!! FAITH.md` | Devotional rotation, Bible reading plan, prayer queue, sermon prep, social-media ministry kanban |
| **family** | `20_Domains (Life and Work)/Personal/Family/!!! FAMILY.md` | Christy + 4 kids by name (Aaron-filled), 1-on-1 rhythms, family calendar, traditions tracker — **all data vault-local, never AI** |
| **business** | `20_Domains (Life and Work)/Personal/Business Ideas & Projects/!!! BUSINESS.md` | Echelon Seven offers (pipeline stages), client list, MRR, content calendar |
| **consulting** | `20_Domains (Life and Work)/Career/Consulting/!!! CONSULTING.md` | Engagements per client, SOW status, billable hours, time-to-invoice |
| **work** | `20_Domains (Life and Work)/Career/Parallon/!!! WORK.md` | BAM duties, meetings, KPIs, "boss-promised list" |
| **health** | `30_Knowledge Library/Biohacking/!!! HEALTH.md` | Workouts, biomarkers timeline, supplement protocol, **hip decision (pinned)**, sleep trend, nutrition adherence |
| **home** | `20_Domains (Life and Work)/Personal/Home/!!! HOME.md` | House projects, **MI property (separate sub-watch)**, **UPS/generator schedule**, **photo cleanup progress**, vendors |
| **personal** | `20_Domains (Life and Work)/Personal/!!! PERSONAL.md` | AI hobby projects (OHO, agent-orch-lxc, Foundation AddOn), reading queue, learning goals |

**Out of scope for P6:**
- Domain-specific full applications (e.g., a custom workout logger) — deferred to P7+
- Voice capture per domain — P3
- Real-time domain widgets — vault is not real-time; refreshes hourly via the live-dashboard-updater cron slot

## B3. Architecture

### Per-domain renderer
Each domain gets a renderer module:
- `tools/domains/faith.py`
- `tools/domains/family.py`
- ... etc.

Each module exports:
```python
def render(*, today: date, source: dict) -> str: ...
def main() -> None: ...
```

Same pattern as ritual renderers. Pure → testable. Verified writes.

### Per-domain config
Each domain has a YAML config:
```
99_System/config/domains/<area>.yaml
```

Example `faith.yaml`:
```yaml
area: faith
display_name: Faith
emoji: "🙏"
weight_target: 10
dashboard_path: "20_Domains (Life and Work)/Faith/!!! FAITH.md"
daily_hook: "What did you read in Scripture today?"
weekly_hook: "Bible reading days this week (target 5)?"
private_to_ai: false
sections:
  - devotional_rotation
  - bible_reading_plan
  - prayer_queue
  - sermon_prep
  - social_media_ministry
```

Example `family.yaml`:
```yaml
area: family
display_name: Family
emoji: "👨‍👩‍👧"
weight_target: 20
dashboard_path: "20_Domains (Life and Work)/Personal/Family/!!! FAMILY.md"
daily_hook: null              # opt-out — Aaron prefers no daily nag for family
weekly_hook: "Christy 1-on-1 done? Each kid 1-on-1 done?"
private_to_ai: true           # NEVER sent to AI summarizer
people:
  spouse:
    name: <Aaron-filled>      # in vault-local family.yaml, not committed
    cadence_days: 1
  children:
    - name: <Aaron-filled>
      cadence_days: 7
    # ... up to 4 kids
sections:
  - people_check_in
  - family_calendar
  - traditions
```

### Domain orchestrator
`tools/build_all_domains.py` — single entry point that iterates over all 8 domain configs and runs each renderer. Called via:
- `make build-domains` (manual)
- New OHO runner endpoint `/build-domains` (POST, bearer-auth)
- New n8n workflow `domain-dashboards-updater.json`, cron slot `:43` (currently open per CLAUDE.md)

### Cross-domain tension surfacing
A new pure function in `tools/domain_balance.py`:
```python
def compute_domain_drift(
    *,
    actual_hours: dict[str, float],   # per area, last 7 days
    targets: dict[str, int],          # per area, % weight
    total_hours: float,
) -> dict[str, dict]:                 # {area: {actual_pct, target_pct, drift_pct, status}}
```

`status` ∈ {`severe_overshoot`, `overshoot`, `on_target`, `undershoot`, `severe_undershoot`}. The Daily Command Center's `🗂 By Life Area` section renders a heatmap row above the existing per-area grouping.

## B4. Data Model

### Per-domain dashboard frontmatter
```yaml
---
type: domain-dashboard
area: faith
display_name: Faith
emoji: "🙏"
updated: 2026-05-12T19:00:00Z
generator: tools/domains/faith.py
weight_target: 10
weight_actual_7d: 12.3        # %
drift_status: overshoot
---
```

### Family domain — names file (vault-local, gitignored)
`99_System/config/family.yaml` (the literal file with real names):
```yaml
# THIS FILE IS NEVER COMMITTED AND NEVER SENT TO AI.
# Loaded only by the family domain renderer running locally.
spouse:
  name: Christy
  birthday: <YYYY-MM-DD>
  cadence_days: 1
children:
  - name: <kid_1_name>
    birthday: <YYYY-MM-DD>
    cadence_days: 7
  # ...
```

A `.gitignore` entry guards this. CI test verifies the file is gitignored.

### Cross-domain hours estimate
The renderer estimates "hours touched per domain" by counting tasks marked done in MTL during the window, weighted by an `[estimate_hours::]` field if present, else default 1h/task. This is *intentionally* a rough proxy — the goal is drift signal, not time-tracking accuracy.

## B5. Sequence Diagrams

### B5.1 Domain dashboards hourly rebuild
```
n8n cron (:43 hourly, open slot)
    │
    ▼
HTTP POST /build-domains ──► OHO runner sidecar
                                  │
                                  ▼
                       tools/build_all_domains.py
                                  │
                                  ├──► load 99_System/config/domains/*.yaml
                                  ├──► load 99_System/config/family.yaml (local only)
                                  ├──► read MTL once (shared across renderers)
                                  ├──► read receipts, articles, biomarkers (if avail)
                                  │
                                  ├──► for each area in [faith, family, ..., personal]:
                                  │       run tools/domains/<area>.py:render()
                                  │       s3_put_verified(dashboard_path, content)
                                  │
                                  └──► compute domain_drift; write
                                       99_System/state/domain-drift.json
    │
    ▼
HTTP 200 ──► n8n done
```

### B5.2 Daily hook injection (faith example)
```
Daily evening close ritual fires (Part A)
    │
    ▼
tools/rituals/daily_close.py
    │
    ├── load 99_System/config/domains/faith.yaml
    │   if daily_hook is not None:
    │       append to evening close section:
    │       - [ ] 🙏 Faith hook: "What did you read in Scripture today?"
    │
    ├── load family.yaml → daily_hook is null → no append
    │
    └── ... repeat per domain
```

### B5.3 Cross-domain tension callout in Command Center
```
build_command_center.py (existing — extends with new section)
    │
    ├── read 99_System/state/domain-drift.json
    │
    ├── find drifts where status in {severe_overshoot, severe_undershoot}
    │
    └── render section in 🗂 By Life Area:
        > [!warning]+ Domain drift this week
        > - 🚀 Business: 25h (target 20%) → +5h
        > - 🏠 Home: 1h (target 3%) → -2h
        > Suggested: defer 1 home task this week, or accept the trade-off.
```

## B6. Per-Domain Mini-Specs

### B6.1 Faith
- **Dashboard sections:** today's devotional, current Bible reading plan position, prayer queue (sorted by oldest-prayed-for), sermon prep workspace (next Sunday school lesson with reference + draft outline), social-media-ministry kanban (idea → draft → scheduled → posted), outreach contacts.
- **Daily hook:** "What did you read in Scripture today?"
- **Weekly hook:** "Bible reading days this week (target 5)?"
- **AI access:** prayer journal entries — opt-in (default off). Sermon prep — yes (AI helps draft outlines via sunday-school-teacher skill).
- **Streak tracking:** Bible reading streak (with gentle recover language).
- **Cross-domain:** if faith.weight_actual_7d < 5%, flags in weekly review.

### B6.2 Family — Hidden Complexity
**This is the highest-stakes domain.** Family carries the most privacy weight and the least automation tolerance.
- **Dashboard sections:**
  - **People check-in cards** — one card per person from `family.yaml`. Each card shows `last_intentional_time_together` (manual Aaron entry) + `next_planned_time` + `cadence_overdue` flag.
  - **Family calendar** — manual entry until GCAL hooked
  - **Kid school/sport schedules** — manual entry, weekly review section
  - **Family financial decisions** — links to MTL `[area:: family]` open tasks
  - **Traditions tracker** — annual + holiday list
- **Daily hook:** explicitly **none** by default. Family is not for daily nagging. Aaron can opt-in.
- **Weekly hook:** "Christy 1-on-1 done? Each kid 1-on-1 done?" — single weekly checkbox, no AI nag.
- **AI access:** **NONE**. Hard rule. `private_to_ai: true` in config; CI test enforces; redact rule in summarize() strips this section.
- **Names handling:** `99_System/config/family.yaml` is the only place real names live. Vault-local, gitignored, never sent to AI. Templated headings use "spouse" / "child_1" / "child_2" in any committed file; the renderer substitutes real names at render time from the local file. If `family.yaml` is missing, dashboard renders placeholders (`<your spouse's name>`) and prompts Aaron to fill it.
- **Why this is hidden-complexity:** every other domain has clean signals (tasks done, biomarkers, hours). Family is mostly absence-of-signal — *did Aaron not connect today* is harder than *did he run today*. The system surfaces cadence-overdue gently and *only weekly*, never daily.

### B6.3 Business (Echelon Seven)
- **Dashboard sections:**
  - Pipeline stages: idea → ICP-validated → offer-defined → first-client → systemized. Each stage has a count + the named offers.
  - Client list with MRR estimates
  - Content calendar (drafts + scheduled + posted)
  - Marketing experiments (one card per experiment, with hypothesis + result)
- **Daily hook:** "One outreach today?" (configurable on/off)
- **Weekly hook:** "Number of outreach conversations this week (Q2 rock = 3 over the quarter)?"
- **AI access:** yes — AI can help draft offer copy, summarize pipeline status. Uses `business-genius` + `entrepreneurial-os` skills.
- **Cross-domain:** if business overshoots target weight, callout in Command Center.

### B6.4 Consulting
- **Dashboard sections:** active engagements (per-client folder linked), SOW status table, billable hours this week, time-to-invoice latency per client.
- **Daily hook:** none.
- **Weekly hook:** "Hours billed this week?" (manual entry)
- **AI access:** yes — engagement summaries, SOW templating.
- Uses `consulting-operations` skill.

### B6.5 Work (Parallon BAM)
- **Dashboard sections:** BAM duties checklist, meeting cadence (today + this week), projects (Union mentioned in Q2 rocks), KPIs Aaron tracks, **"boss-promised list"** with `last_mentioned` timestamps.
- **Daily hook:** "Anything you promised the boss this week?"
- **Weekly hook:** none (handled in weekly review).
- **AI access:** yes for meeting notes summarization; **no** for KPI numbers (Aaron's data).
- The "boss-promised list" is a special table parsed from a markdown file `20_Domains (Life and Work)/Career/Parallon/boss-promises.md` with rows like:
  ```
  | Promise | Made | Last mentioned | Status |
  |---|---|---|---|
  | Q2 forecast model | 2026-04-15 | 2026-05-08 | in_progress |
  ```

### B6.6 Health
- **Dashboard sections:**
  - **HIP DECISION (pinned)** — at the very top, until resolved. Renders the Q2 rock + decision deadline + last-action timestamp. Pinned until Aaron drops a `decision_resolved: <date>` field in the dashboard config.
  - Workout log (last 7 days, current streak, longest streak)
  - Biomarkers timeline — if biohacking-data-pipeline live, renders HRV/sleep/glucose trends. Else: manual entry section.
  - Supplement protocol — from `health-biohacking-protocol` skill output
  - Sleep trend (14-day rolling)
  - Nutrition adherence — manual
- **Daily hook:** "Workout today? Y/N"
- **Weekly hook:** "Gym sessions this week (target 3)?"
- **AI access:** yes for trend summaries (e.g., "HRV up 8%"); **no** for specific values in any text sent externally.
- Uses `health-biohacking-protocol` skill.

### B6.7 Home
- **Dashboard sections:**
  - House projects backlog (current + parked)
  - **MI property** sub-watch (separate section — it's effectively a small second home OS)
  - **UPS/generator maintenance schedule** — recurring tasks with `next_service_date` field; alerts when within 14 days
  - **Photo cleanup progress** — running count of photos sorted / total
  - Vendors contact list
- **Daily hook:** none.
- **Weekly hook:** "Any house project advanced this week?"
- **AI access:** yes — no sensitive data.

### B6.8 Personal
- **Dashboard sections:**
  - AI hobby projects (OHO, agent-orch-lxc, Foundation AddOn — each with last-commit timestamp + open-PR count if gh CLI works)
  - Reading queue (from `00_Inbox/articles-to-process.md` filtered by `[area:: personal]`)
  - Learning goals (annual, ongoing)
- **Daily hook:** none.
- **Weekly hook:** "Time on AI hobby this week?"
- **AI access:** full.

## B7. Failure Modes + Guardrails

| Failure | Detection | Response |
|---|---|---|
| `99_System/config/family.yaml` missing | Renderer attempts read, gets None | Dashboard renders with placeholders; Aaron prompted to create the file via a `> [!info]+` callout |
| Family data accidentally committed to git | CI test scans for likely family names in committed files | Block merge; require redaction |
| Domain config YAML invalid | YAML parse error at renderer load | Renderer for that domain skips with `[!error]+ Config invalid` rendered in dashboard; other domains continue |
| Biohacking pipeline absent | Health renderer detects missing data | Renders manual-entry section gracefully |
| Cross-domain drift calc divides by zero (no hours logged) | Math edge case | Default to "no signal yet — log some tasks first"; no false alarms |
| Hip decision pinned forever (Aaron forgets to mark resolved) | Stale flag: pinned > 90 days | Render `> [!warning]+ This decision has been pending 92 days — is it time to schedule a decision deadline?` |
| Domain dashboard contains stale data after MTL update | Hourly :43 rebuild keeps it fresh | Acceptable; same staleness budget as live-dashboard-updater |
| Multiple domains overshoot in same week | Drift compute floods Command Center | Cap callout at top 2 overshoot + top 2 undershoot |
| Renderer writes to wrong path | Verified write catches; CI test verifies all dashboard_path values exist in vault | If readback fails, retry once + alert |

## B8. Privacy (Domain-Specific)

- **Family** — see B6.2. Hardest line. Real names never leave the vault, never sent to AI.
- **Health** — biomarker values stay vault-local in plot data; AI gets trend deltas only (e.g., "+8%"), not raw numbers.
- **Work** — KPI specifics never sent to AI. Generic summaries okay.
- **Faith** — prayer journal opt-in only. Sermon prep public.
- **All domains** — any line tagged `[private:: true]` is excluded from AI calls. Enforced by redact rule.
- **Audit log** — same `99_System/logs/ai-summarize-*.jsonl` covers domain dashboard AI usage (for future when AI renders summaries directly into dashboards — not in v1).

## B9. Acceptance Criteria

P6 ships when ALL of:
1. All 8 domain renderers exist under `tools/domains/` with ≥75% unit test coverage.
2. All 8 domain config YAMLs exist under `99_System/config/domains/`.
3. `99_System/config/family.yaml` is gitignored (CI test verifies); template + instructions in `.example` form committed.
4. `tools/build_all_domains.py` runs all 8 in one pass; idempotent; verified writes.
5. OHO runner has `/build-domains` endpoint (bearer-auth).
6. `domain-dashboards-updater.json` n8n workflow on cron slot `:43` (open slot per CLAUDE.md).
7. `tools/domain_balance.py` computes drift; result in `99_System/state/domain-drift.json`.
8. `build_command_center.py` extended to render the cross-domain drift callout.
9. Daily close ritual injects per-domain `daily_hook` strings (P5 wiring).
10. Weekly review's `## 📊 Domain Balance Heatmap` reads `domain-drift.json`.
11. Hip decision pinned in Health dashboard until manually resolved.
12. `tests/test_domains.py` covers: missing config, missing family.yaml, drift math, AI redaction per domain, hip-decision pinning.
13. **Soak**: 2 weeks of clean domain-dashboard rebuilds before any further automation layers on top.

## B10. Risks + Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Aaron stops looking at domain dashboards after novelty wears off | Med | Med | Keep Command Center the entry. Domain dashboards are deep-dive, opt-in. Don't email about them. |
| Family privacy leak | Low | Critical | Multiple defences: gitignore, redact rule, CI test, audit log, vault-local family.yaml |
| Drift signal becomes noise (overshoot every week) | Med | Med | Tunable thresholds; if every week shows drift, the targets are wrong — surface that as meta-signal in monthly review |
| Hip decision pinning is annoying | Low | Low | After 90 days, pin softens to a `> [!info]-` collapsible callout; Aaron can dismiss |
| Domain configs sprawl | Low | Low | 8 YAMLs, capped. New domains require explicit ADR. |
| MI property merits its own life-OS | Med | Low | Out of scope — it's a section within home. Revisit if it grows. |
| Cross-domain hours estimate is too rough to trust | High | Low | Aaron can override per-task with `[estimate_hours::]`; otherwise default-1 is signal, not measurement |

## B11. Dependencies

- **P5** — must ship first (daily-hook injection, weekly-review domain heatmap, ritual privacy redaction patterns).
- **biohacking-data-pipeline** — optional. Health domain degrades gracefully.
- **GCAL_CRED_ID** — optional. Family/work calendars manual until set.
- **P2 (threaded tasks)** — when shipped, domain dashboards link to task IDs for stable backlinks. Until P2, Dataview path-based queries work.

## B12. Parallel Sub-Lanes

1. **Lane A — Per-domain renderers**: 8 modules, fully independent. Split across 2 PRs (4 domains each) to keep review tractable.
2. **Lane B — Configs**: 8 YAMLs + family.yaml example + gitignore + CI test. One PR.
3. **Lane C — Orchestrator + runner endpoint + n8n workflow**: one PR.
4. **Lane D — Drift compute + Command Center extension**: one PR.

Total: 4 PRs, can land in any order with feature flags (dashboards render even if drift compute not deployed).

## B13. Effort

| Lane | Estimate | Notes |
|---|---|---|
| A — 8 renderers | 4-6 days | Faith/Health/Business are largest (1d each); Family privacy work is 1d; others ~0.5d each |
| B — Configs + privacy CI | 1 day | |
| C — Orchestrator + sidecar + n8n | 0.5 day | |
| D — Drift compute + Command Center wire-in | 1 day | |
| **Total P6** | **6-8 days** | |

## B14. Verification Strategy

- **Unit tests** (`tests/test_domains.py`): one per renderer; family privacy redaction; drift math.
- **Integration test** (`tests/integration/test_domain_e2e.py`): orchestrator runs all 8 against fixture bucket; all 8 dashboards exist and parse.
- **Privacy test** (`tests/test_domains.py::test_family_yaml_gitignored`): asserts `.gitignore` contains the path; asserts `99_System/config/family.yaml` is not present in git's HEAD.
- **AI redaction test**: same harness as P5 — verify family.* keys never appear in payloads sent to `/ai-summarize`.
- **Soak** (2 weeks): hourly rebuilds clean; Aaron uses the dashboards.

## B15. Open Questions (P6)

- **Q1.** Family dashboard — should the people-cards show cadence-overdue in red, or stay neutral? (Default: gentle amber; never red for family.)
- **Q2.** Cross-domain drift — render in Command Center even when in target? (Default: only render when at least one domain is `severe_*` — don't crowd the Command Center.)
- **Q3.** Should `personal` domain include this OHO project itself? (Default: yes — eat your own dogfood. Counts AI hobby hours.)
- **Q4.** Hip decision — once resolved, should the resolved-decision live in Health dashboard's history forever, or move to an archive? (Default: stay 30 days then archive to `09_Archives/decisions/`.)
- **Q5.** MI property — promote to its own dashboard `!!! MI PROPERTY.md` if it has >10 active tasks at any point? (Default: yes; future ADR if/when it happens.)
- **Q6.** Boss-promised list — should the system warn when a promise hasn't been mentioned in 14+ days? (Default: yes, in the work dashboard's section.)
- **Q7.** Domain weight targets — annual or quarterly tuning? (Default: quarterly, set at quarterly review.)

---

# PART C — Combined Phasing & Integration

## C1. Combined Order of Operations

```
SOAK GATE (2026-05-18+): P1+P1.5+ADR-0006 clean for 7 days
    │
    ▼
P5 Lane B (sidecar endpoints) ── ▶ can land first, no user impact
    │
    ├── P5 Lane A (renderers) — 5 days
    │       │
    │       ▼
    │   P5 Lane C (n8n workflows) + Lane D (state/audit/privacy)
    │       │
    │       ▼
    │   P5 SOAK: 4 weeks of daily + 4 weekly reviews
    │       │
    │       ▼
    │   P6 Lane A (renderers) + Lane B (configs)
    │       │
    │       ▼
    │   P6 Lane C (orchestrator) + Lane D (drift + Command Center wire)
    │       │
    │       ▼
    │   P6 SOAK: 2 weeks
    │       │
    │       ▼
    │   READY FOR P7 (AI coach loop)
```

## C2. Combined Effort

P5 + P6 = **11-15 days of focused work** across ~6 weeks (with soak gates).

## C3. Combined Acceptance — Definition of Done for "P5+P6 shipped"

- All P5 + P6 acceptance criteria pass (A9 + B9).
- Aaron uses the system for 4 consecutive weekly reviews + 2 consecutive monthly reviews.
- Family privacy audit clean: zero PII in `99_System/logs/ai-summarize-*.jsonl`.
- All audits green: `make audit-workflows audit-runlogs audit-receipts audit-ai-tooling audit-rituals audit-domains`.
- Daily Command Center renders the domain drift callout when applicable.
- `git ls-files` does not contain `99_System/config/family.yaml`.

---

# PART D — Appendices

## D1. Anti-shame Design Rules

1. Never use "failed" or "missed" in red.
2. "0-day streak" is never rendered. If the streak is 0, render "ready to start" or no streak indicator at all.
3. After a missed ritual, the next ritual note opens with "Welcome back" not "You missed last week."
4. Long breaks are framed as "data, not failure."
5. Drift callouts are descriptive, not prescriptive: "Business overshot 5h" not "You should reduce Business."

## D2. AI Boundary Rules (consolidated)

| AI may | AI may not |
|---|---|
| Summarize past week's task completions | Suggest next quarter's rocks |
| Draft narrative for "what compounded" / "what stalled" | Touch family.* fields |
| Generate trend deltas for biomarkers ("+8%") | Generate specific biomarker values in external text |
| Draft sermon outlines (faith opt-in) | Read prayer journal entries (default-off) |
| Help with offer copy, marketing experiments (business) | Touch consulting client PII |
| Summarize meeting notes (work) | Touch boss-promised list specifics |
| Suggest tomorrow's ONE thing from existing MTL | Make decisions for Aaron |

## D3. File Inventory (planned)

### New files
```
tools/rituals/
    __init__.py
    daily_close.py
    weekly_review.py
    monthly_review.py
    quarterly_review.py
    annual_review.py
    summarize.py
tools/domains/
    __init__.py
    faith.py
    family.py
    business.py
    consulting.py
    work.py
    health.py
    home.py
    personal.py
tools/build_all_domains.py
tools/domain_balance.py
prompts/rituals/
    weekly.txt
    monthly.txt
    quarterly.txt
    annual.txt
99_System/config/domains/
    faith.yaml
    family.yaml
    business.yaml
    consulting.yaml
    work.yaml
    health.yaml
    home.yaml
    personal.yaml
99_System/config/
    domain-weights.yaml
    ritual-privacy.yaml
    family-checkin-prompts.md
    family.yaml.example          # template; family.yaml itself gitignored
scripts/audit_ritual_completion.py
scripts/audit_domain_dashboards.py
tests/test_rituals.py
tests/test_domains.py
tests/integration/test_ritual_e2e.py
tests/integration/test_domain_e2e.py
workflows/n8n/daily-close-prepper.json
workflows/n8n/weekly-review-prepper.json
workflows/n8n/monthly-review-prepper.json
workflows/n8n/quarterly-review-prepper.json
workflows/n8n/annual-review-prepper.json
workflows/n8n/domain-dashboards-updater.json
docs/adr/0007-review-rituals.md
docs/adr/0008-domain-aware-ux.md
```

### Modified files
```
services/oho_runner/app.py     # +6 ritual endpoints, +1 domain endpoint, +1 /ai-summarize
tools/build_command_center.py  # extend 🗂 By Life Area with drift callout
.gitignore                     # +99_System/config/family.yaml
CLAUDE.md                      # P5/P6 status section
AGENTS.md                      # mirror P5/P6 rules
Makefile                       # +ritual-* + build-domains + audit-* targets
scripts/setup-n8n.sh          # +5 ritual workflows + 1 domain workflow imports
```

## D4. Streak Rules (consolidated, gentle)

- Daily close streak resets on a missed day, **except** if the daily note exists and has any content (Aaron worked that day, just didn't do evening close). Then streak preserved as "soft day."
- Weekly review streak preserved on combined catch-up notes (A5.4) — "recovered" not "reset."
- Monthly/quarterly/annual streaks never reset on a single miss within a calendar year.
- `longest_streak` is monotonic — never decreases.
- Streak display: integer count + emoji (🔥 if 7+, 🌟 if 30+, no negative framing ever).

## D5. Naming Conventions (anti-em-dash-bug)

Per ADR-0006's hard-learned em-dash lesson, all file/path names use ASCII hyphens or no separator:
- `2026-W19.md` (hyphen, ASCII)
- `2026-05.md` (hyphen, ASCII)
- `!!! FAITH.md` (no separator after `!!!`)
- Never: `2026—W19.md` (em-dash will bite the receipt audit).

## D6. Cross-References

- **CLAUDE.md** — Life Domains, hard rules, current status, roadmap.
- **ADR-0005** — state machine + receipts (P1).
- **ADR-0006** — Daily Command Center; P5/P6 extend it, don't replace it.
- **2026-04-02 design** — original Life OS v2 design; areas, paths, principles.
- **2026-05-10 quick-add design** — capture-side spec; P3 work.
- **tools/build_command_center.py** — rendering pattern P5/P6 mirror.

---

_End of spec._

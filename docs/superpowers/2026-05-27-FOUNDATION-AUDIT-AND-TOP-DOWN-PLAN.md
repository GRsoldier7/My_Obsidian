# OHO — Foundation Audit + Top-Down Best-of-Best Plan

> **Synthesis of 5 parallel cavecrew investigations dispatched 2026-05-27.** Live-verified, file:line citations throughout. Supersedes the "Drift corrections" tables in [Master Plan v2](2026-05-13-MASTER-PLAN-V2.md) for current-state numbers.

**Date:** 2026-05-27 · **Branch:** `polish/prod-ready` (94 commits ahead of `master`) · **PR #2:** `MERGEABLE · CLEAN`

---

## 1 · State of truth (live-verified)

Verified this session against live MinIO, n8n REST, GitHub, and the repo — not from memory or docs.

| Dimension | Status | Evidence |
|---|---|---|
| **Branch divergence** | 94 commits ahead of `master` | `git rev-list --left-right --count master...HEAD` |
| **PR #2 mergeable** | `CLEAN` · `MERGEABLE` | `gh pr view 2` |
| **Test suite** | 676 pass + 7 skip | `make audit-ci` |
| **Audit gate** | 11 audits in `audit-all` | `Makefile:207` |
| **Audit scripts on disk** | 14 | `ls scripts/audit_*.py` |
| **Gate gap** | 3 audits exist but NOT in `audit-all` | `audit_workflow_connections`, `audit_workflow_credentials`, `audit_extraction_receipts` |
| **Coverage** | 62% (2410 stmts, 925 miss) | `make coverage` |
| **MinIO** | ✅ reachable; 11 brain-dump files; soak audit clean | `make ENV=1 health` + `audit-extraction-receipts` |
| **n8n** | ✅ reachable; 17 active workflows | live API |
| **n8n execution updatedAt** | ⚠️ last Apr 26; possible clock drift OR cron stall | `/executions` endpoint |
| **ADRs** | 0001–0006 historical · **0007 / 0008 / 0009 Accepted** | `docs/adr/*.md` `Status:` lines |
| **Phase C+F skeletons** | ✅ merged to `polish/prod-ready` (`tools/task_id.py` 17 tests; `tools/privacy_classifier.py` 19 tests; `SKELETON_MODE=True`) | `c4e8d40` |
| **Eval fixtures** | 35 / 200 target | `evals/comms_privacy/` |
| **Soak gate (P0.5)** | ✅ **CLEARED 2026-05-18** | `CURRENT-STATE.md:6` Day 7 green |

### Per-dimension verdict

- 🟢 Git · CI · Tests · Infra · Soak
- 🟡 Audit gate (3 audits unbound) · Live n8n execution staleness · Coverage 62% vs ≥80% target
- 🔴 **CLAUDE.md drift** (lines 211–213 claim "46 ahead, soak in flight, earliest exit 2026-05-18"; reality is "94 ahead, soak cleared, P0.5 done"). 16 days stale.
- 🔴 **Privacy classifier NOT wired** into runner egress path despite ADR-0008 Accepted

---

## 2 · Where we want to go (Definition of Amazing — gap matrix)

| # | Criterion | Today | Gap | Effort to close | Blocker rank |
|---|---|---|---|---|---|
| 1 | DCC is only file Aaron opens daily | ✅ live + rendering | thread-card renderer (P2); Decision Journal panel (P2.5) | M (post-P2) | sequential |
| 2 | Capture-to-action p95 < 24h | ⚠️ Telegram only | no email-forward, share-sheet, voice surfaces; P3 unbuilt | L (2-3w) | high (P3) |
| 3 | Every AI output eval-gated | ⚠️ 35/200 fixtures; `ai-brain` unchecked | scale evals; wire classifier into ai-brain calls | M (Wave-X H3) | high |
| 4 | Sensitive data never reaches free-tier model | 🔴 classifier exists but **NOT wired** to egress | wire `tools/privacy_classifier.py` into `services/oho_runner/app.py` BEFORE any AI call | M | **CRITICAL** |
| 5 | System survives single-component failure 7d | ⚠️ vault-health silent (executeCommand); system-health silent (S3-chain bail) | items 10 + 10b | S+S | active blocker |
| 6 | Decision Journal ≥10 reviewed decisions w/ 90-day outcomes | 🔴 zero infra | P2 IDs first, then P2.5 build | L (post-P2) | sequential |
| 7 | ≥2 life domains have a feature no off-the-shelf tool offers | 🔴 specs only | full P6 stack | XL | far |
| 8 | OHO + CT 215 broker share one trace_id end-to-end | 🔴 zero traceparent in `services/`, `tools/`, `clients/` | P3.5 F1–F4 wiring | M | sequential |
| 9 | No sensitive payload crosses OHO→broker without allow-list | 🔴 classifier dicts empty (Tier 3–9); 0/200 eval fixtures actually run | wire classifier + grow fixtures | M | **CRITICAL** |

**Soonest criterion fully reachable:** **#5** (system health), 1–2 weeks (items 10 + 10b + SLO auditor). Then unblock the "what is healthy?" answer in-dashboard.

**Longest dependency chain:** P0.5 → P2 (XL 3-4w) → P2.5 (M 1-2w) = ~6–8w for #6.

---

## 3 · Top 5 roadblocks (impact × leverage)

Combined from architecture + roadblock + UI agents. Ranked.

### #1 — Privacy classifier scaffolded but NOT enforced at egress

**Severity:** CRITICAL · **Effort:** S–M

- `tools/privacy_classifier.py` exists, 19 tests, all pass because `SKELETON_MODE = True` returns "OK" for everything
- `infra/data-classes.yaml` defines 10 tiers — but `services/oho_runner/app.py` does NOT load it
- `ai-brain` sub-workflow calls OpenRouter directly without any pre-classification
- ADR-0008 Accepted 2026-05-27 — contract is now load-bearing
- **Risk:** any commit that lands Wave-X observability before this is wired = faith/family/health content leaking to OpenRouter + future broker

**Fix:** Wire classifier into runner startup; classify EVERY payload before AI call; deny + log + raise on `sensitive`/`private-family`/`private-faith` classes. Smoke-test with 5 adversarial fixtures.

### #2 — CLAUDE.md drift (16 days stale)

**Severity:** HIGH · **Effort:** XS

- `CLAUDE.md:211` "63 commits ahead" → actually 94
- `CLAUDE.md:213` "earliest exit 2026-05-18" → soak EXITED 2026-05-18 (cleared)
- `CLAUDE.md:259` P0.5 "⏳ in flight" → ✅ done
- Every Codex/Claude session reads CLAUDE.md as the source of truth, so it drifts the model's mental state forward into hallucination territory
- **Fix:** one commit to refresh the Current Status section + Master Plan pointers

### #3 — vault-health-report executeCommand + system-health silent S3-chain

**Severity:** HIGH · **Effort:** S (10b) + S (10 needs runner endpoint)

- Both workflows fire on cron; both report "success" in n8n; both write ZERO logs in MinIO
- `vault-health-report` bails at `S3: List Brain Dumps`, then has the executeCommand bug downstream (NEXT-STEPS item 10)
- `system-health-monitor` bails at `S3: Check North Star` (chained S3 headObject → S3 headObject pattern; first returns success but no item; second never fires) — NEXT-STEPS item 10b
- **Impact:** Aaron's "is it healthy?" answer is hand-audited only; soak legitimacy depends on receipt-audit alone

**Fix:** ship item 10 first (adds `/audit-receipts` endpoint to runner → sidesteps both vault-health bugs in one stroke). Then item 10b on system-health (3 options ranked in NEXT-STEPS).

### #4 — Unverified S3 puts (14 sites across 9 files)

**Severity:** MEDIUM · **Effort:** M (2 sprints)

- `tools/s3_verified.py` exists with `put_text_verified`/`put_json_verified`/`put_text_if_match_verified` (100% covered)
- 14 call sites in 9 files still use bare `s3.put_object()` — allowlisted, no NEW violators per `audit_no_unverified_put_object.py`
- Highest-blast-radius offender: `tools/process_brain_dump.py` RMW telemetry (4 sites)
- **Risk:** silent overwrite on concurrent edits (phone via Remotely-Save + cron)

**Fix:** post-soak item 13 (NEXT-STEPS). Migrate file-by-file with tests.

### #5 — Vault folder chaos (4/10 UX rating)

**Severity:** MEDIUM · **Effort:** S

- 21 top-level folders; many abandoned: `rs-test-folder-*` (6 of them), `! TO DO/`, `Daily/`, `Homelab/`
- `10_Active Projects/` and `20_Areas/` + `20_Domains (Life and Work)/` semantically overlap
- No vault-root README
- **Impact:** every vault open shows clutter; mental-model violation of 8-domain Life OS
- **Fix:** archive cruft to `06_Archive/`; rename `20_Domains (Life and Work)` → `20_Life_Domains`; add `README.md` with 3-line orientation

---

## 4 · UI best-of-best — 5 cheap wins (Aaron's #1 ask)

From `ce-cavecrew-investigator` UI/UX audit. Ranked by **impact ÷ effort**.

| # | Win | Surface | Impact | Effort | File |
|---|---|---|---|---|---|
| 1 | "Decision Required" badge + expanded plain-text fallback | Morning Briefing email | 100% open rate sees urgency cue | XS | `workflows/n8n/morning-briefing.json` subject template |
| 2 | 3-tier overdue color gradient (🔴 >7d · 🟠 4-7d · 🟡 1-3d) + "Pipeline healthy ✅" banner when 0 new tasks | Daily Command Center | scan time -50% | XS | `tools/build_command_center.py:~150` |
| 3 | Archive `rs-test-*` + `! TO DO/` + `Daily/` + `Homelab/`; add vault root `README.md` | Vault structure | first-open clarity; mental model intact | S | one-shot script |
| 4 | Yesterday's #1 follow-up section + `[decision_by::]` slot | Daily Note template | feedback loop closed; unblocks P2.5 | XS | `workflows/n8n/daily-note-creator-v2.json` |
| 5 | Health dashboard: split coverage gaps into "expected skips (SLO)" vs "silent failures"; add "Last run age" column | Health Dashboard | eliminates false alarms | M | `tools/build_health_dashboard.py` |

**Per-surface current ratings:**

```
Daily Command Center       7/10
Morning Briefing Email     8/10
Daily Note Template        6/10
Health Dashboard           5/10
Vault Folder Structure     4/10   ← biggest target
MTL Canonical Task Line    7/10
CURRENT-STATE + NEXT-STEPS 8/10
```

Average **6.4/10**. Best-of-best target: **9+/10 across all 7**.

---

## 5 · Architecture best-of-best — top 5 invariant tightenings

From `cavecrew-investigator` architecture review. Each closes an active leak.

### A1 — Wire privacy classifier into runner egress (CRITICAL)

`services/oho_runner/app.py` loads `infra/data-classes.yaml` on startup. Every payload that crosses the runner boundary calls `privacy_classifier.classify(text)`. Block + log on sensitive classes. Add 5 adversarial fixtures to `evals/comms_privacy/`. **Closes:** ADR-0008 contract; criteria #4 + #9.

### A2 — Complete verified-write migration (item 13)

Migrate 14 unverified `s3.put_object()` call sites across 9 files to `tools/s3_verified.*`. Hot path first: `process_brain_dump.py` RMW telemetry. **Closes:** Codex P1 from 2026-05-16; criterion #5.

### A3 — Move `vault-health-report` executeCommand → runner POST

Add `POST /audit-receipts` to `services/oho_runner/app.py` (mirror `/process-brain-dump`). Switch n8n node from `executeCommand` to `httpRequest`. Audit: `audit_no_executecommand.py` allowlist shrinks to 0. **Closes:** P1.5 invariant; NEXT-STEPS item 10.

### A4 — Unify sink consumer contract (`SinkInputContract`)

Today sinks read from different state layers (MTL string-parse, summary file JSON, run-log JSON). Define `SinkInputContract` in `tools/bd_integrity.py`; refactor 4 sinks. **Closes:** P2 prep; simplifies threaded-tasks state.

### A5 — Add 3 missing audits to `audit-all` gate

`audit_workflow_connections.py` + `audit_workflow_credentials.py` already exist; not in `Makefile:207`. `audit_workflow_runlogs.py` exists but explicitly held. **Fix:** add the two genuine omissions to the gate; document the third's hold reason.

**The one rule OHO is most at risk of breaking next:** A1 (classifier-not-wired). Wave-X H2 metrics work likely lands before the classifier is wired → metrics payloads containing sensitive content reach OpenRouter unfiltered. **Land A1 BEFORE any more Wave-X work.**

---

## 6 · Skills lock-in (Foundation routing per phase)

From `cavecrew-investigator` skills inventory. **13 Foundation skills active; 5 always-on meta; 4 OHO-local to build; no misfits.**

| Phase | 3 lock-in skills | bonus | missing |
|---|---|---|---|
| **A** Deploy | verification-before-completion · systematic-debugging · secure-by-design | writing-plans | — |
| **B** Hygiene | app-security-architect · n8n-workflow-architect · secure-by-design | brainstorming | — |
| **C** Threaded Tasks | polychronos-team · database-design · test-driven-development | frontend-design | — |
| **D** Decision Journal | life-os-designer · personal-productivity-os · brainstorming | notebooklm | decision-toolkit |
| **E** Capture-Everywhere | n8n-workflow-architect · secure-by-design · biohacking-data-pipeline | app-security-architect | — |
| **F** Broker-Client | mcp-server-builder · app-security-architect · test-driven-development | secure-by-design | — |
| **G** Briefings | ai-agentic-specialist · notebooklm · verification-before-completion | brainstorming | — |
| **H** Wave-X | app-security-architect · testing-strategy · secure-by-design | data-analytics-engine | observability-baseline (Aaron-owned) |
| **I** Rituals | personal-productivity-os · obsidian-vault-architect · notebooklm | life-os-designer | — |
| **J** Domain UX | obsidian-vault-architect · consulting-operations · health-biohacking-protocol | bible-study-theologian | sunday-school-teacher · family-life-integration |
| **L** AI Coach | polychronos-team · health-biohacking-protocol · notebooklm | faith-life-integration | — |

**Always-on meta-layer** every phase: `anti-hallucination` · `context-guardian` · `cognitive-excellence` · `efficiency-engine` · `prompt-amplifier` · `secure-by-design` · `session-optimizer` · `solution-architect-engine` · `verification-before-completion`.

---

## 7 · Sequenced execution — best-of-best path

### Next 7 days (W22, 2026-05-27 → 2026-06-02)

In order. Each is a single commit / atomic push.

1. **C1** — Refresh CLAUDE.md drift (Roadblock #2; XS). One-commit doc refresh.
2. **C2** — Wire privacy classifier into runner egress (Roadblock #1; M). Load YAML; classify every payload; deny on sensitive; 5 adversarial fixtures. Add audit `audit_classifier_wired.py`.
3. **C3** — UI win #1 + #2: morning-briefing decision badge + DCC overdue tiering (XS+XS).
4. **C4** — UI win #3: vault folder cleanup script (S). Archive cruft; add root README; verified writes.
5. **C5** — Items 10 + 10b: `/audit-receipts` runner endpoint + system-health `alwaysOutputData` (S+S).

**Push gates:** every commit ≤ 80 lines code change; `make audit-ci` green; PR #2 stays clean.

### Next 28 days (W22 → W26, 2026-05-27 → 2026-06-23)

**Critical path:** Phase C threaded tasks (item 11). Sub-lanes:

- W22: ADR-0007 + ADR-0009 design freeze; `polychronos-team` B.L.A.S.T. session
- W23: `scripts/migrate_threaded_tasks.py` Apply phase (currently STUB) + `scripts/audit_threaded_tasks.py`
- W24: MTL ↔ backing-file bidirectional sync (the hard part)
- W25: Command Center thread-card renderer; runner endpoints `/tasks/split` + `/merge` + `/archive`
- W26: 15-min audit cron during 7d cutover; close P2

**Parallel lanes (non-blocking):**

- **Eval ramp:** grow `evals/comms_privacy/` from 35 → 100 fixtures (M; Wave-X H3 dependency)
- **Verified-write migration:** 9 files (M; item 13)
- **A3 executeCommand purge:** runner endpoint already added in week 1
- **A4 SinkInputContract:** design in W23; refactor in W24

### Quarter-end (≈ W30, 2026-06-23 → 2026-07-21)

- **P2.5 Decision Journal** kickoff (rides P2 IDs; M)
- **P3 Capture-Everywhere** envelope + voice surface (L)
- **P3.5 Broker-Client** F1–F6 (M)
- **Wave-X** all 4 lanes (M)
- **P4 Briefings** eval-gated (M)

Per Master Plan v2 timeline. No re-sequencing needed.

---

## 8 · Proof gates (how we'll know we hit "best of best")

Per criterion in Definition of Amazing — measurable acceptance, not vibes.

1. **DCC only file** — week of daily logs shows ≥6/7 days Aaron opened DCC first (Obsidian access log if available; or self-report)
2. **Capture latency p95 < 24h** — `audit_capture_latency.py` (new) reads timestamps from envelope → completion in MTL; report p95 over 28d
3. **AI eval-gated** — `audit_eval_coverage.py` red-on-merge if any AI workflow lacks frozen test set with ≥10 fixtures
4. **No sensitive egress** — CI egress test: 100 sensitive-class payloads through runner, 0 reach OpenRouter. Required-status check on PRs
5. **7d failure tolerance** — chaos test: kill runner mid-write, kill MinIO 1h, kill n8n 24h — system recovers without operator
6. **Decision Journal ≥10** — `audit_decision_journal.py` counts entries in `40_Decisions/` with `[decision_at::]` ≥90 days ago AND `[reviewed_at::]` set
7. **2+ novel domain features** — list (sermon-prep, decision journal w/ outcomes, biomarker-anomaly, CRM-lite, family-timeline); ≥2 weekly-touched per `audit_domain_features.py` (new)
8. **One trace_id end-to-end** — `audit_trace_continuity.py` parses LXC + OHO logs; verifies trace_id unbroken across 100 sampled cross-host calls
9. **No sensitive crosses broker edge** — same egress test as #4, extended to broker `/tasks` POST path

**Release rubric:** v1.0 ships when 7/9 criteria measurable-green AND remaining 2 have a dated path to green.

---

## Pointer index

| Doc | Owner |
|---|---|
| `docs/CURRENT-STATE.md` | live numbers (refresh weekly) |
| `docs/NEXT-STEPS.md` | operator checklist (refresh per commit) |
| `docs/superpowers/2026-05-13-MASTER-PLAN-V2.md` | execution path v2 (Aaron edits) |
| `docs/superpowers/2026-05-12-LIFE-OS-V1-MASTER-ROADMAP.md` | deep-dive index |
| `docs/superpowers/2026-05-27-FOUNDATION-AUDIT-AND-TOP-DOWN-PLAN.md` | **this doc — top-down best-of-best plan** |
| `docs/superpowers/phases/2026-05-12-P0-deploy-and-soak-start.md` | Phase A spec |
| `docs/superpowers/phases/2026-05-12-hygiene-carry-forwards.md` | Phase B spec |
| `docs/superpowers/specs/2026-05-12-P2-threaded-tasks-spec.md` | Phase C spec |
| `docs/superpowers/specs/2026-05-12-P3-P4-capture-and-briefings-spec.md` | Phase E + G spec |
| `docs/superpowers/specs/2026-05-12-P5-P6-rituals-and-domain-ux-spec.md` | Phase I + J spec |
| `docs/superpowers/specs/2026-05-12-P7-ai-coach-insight-loop-spec.md` | Phase L spec |
| `docs/superpowers/specs/2026-05-12-cross-cutting-and-ambition-spec.md` | Wave-X spec |
| `docs/superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md` | Phase F spec |
| `docs/adr/0007-master-plan-v2.md` | Accepted |
| `docs/adr/0008-cross-host-comms.md` | Accepted (classifier wiring is the open contract) |
| `docs/adr/0009-threaded-tasks.md` | Accepted |

---

*Synthesized 2026-05-27 from 5 parallel cavecrew investigations: live-state, UI/UX, roadblocks, skills inventory, architecture. Every claim verified against live MinIO + n8n + git, not memory. Next session: start with C1 (CLAUDE.md drift refresh) since it is XS effort and removes the hallucination vector for every future Claude/Codex session.*

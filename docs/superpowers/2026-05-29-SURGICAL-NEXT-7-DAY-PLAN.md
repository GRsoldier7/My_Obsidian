# OHO — Surgical Next-7-Day Plan (2026-05-29)

> **Supersedes** the next-7-day section of [2026-05-27-FOUNDATION-AUDIT-AND-TOP-DOWN-PLAN.md](2026-05-27-FOUNDATION-AUDIT-AND-TOP-DOWN-PLAN.md) §7. The C-series shipped 2026-05-28 closed several items; this doc names the NEXT 5 surgical moves with anti-drift verification against the live tree.

**Date:** 2026-05-29 · **Branch:** `polish/prod-ready` (106 commits ahead) · **PR #2:** MERGEABLE + CLEAN · **701 tests pass**, 7 skip · **11 audits green**

---

## §1 · State of truth (live-verified, anti-drift)

Synthesized from 5 parallel cavecrew investigations. Where agents disagreed with live state, **live state wins** (verified via `git log` + `grep` against actual tree).

| Dimension | Status | Evidence |
|---|---|---|
| Branch divergence | **106** commits ahead of `master` | `git rev-list --left-right --count master...HEAD` |
| PR #2 | `MERGEABLE` · `CLEAN` | `gh pr view 2` |
| Tests | **701 pass** + 7 skip | `make audit-ci` |
| Coverage | **62%** overall · 100% `s3_verified.py` + `task_id.py` · 96% `bd_integrity.py` · 93% `privacy_classifier.py` | `make coverage` |
| Audit gate | **11 green** in `audit-all` | `Makefile:audit-all` |
| Audits on disk | 15 (3 actively enforced outside gate as guards) | `ls scripts/audit_*.py` |
| ADRs | 0001-0006 historical · **0007/0008/0009 Accepted** | `docs/adr/*.md` Status lines |
| Soak gate | ✅ **CLEARED 2026-05-18** | CURRENT-STATE + run logs |
| MinIO + n8n + receipt audit | ✅ ALL GREEN | `make ENV=1 health` + `audit-extraction-receipts` |

### Last 7 days delta (2026-05-22 → 2026-05-29)

- **+12 commits** (94 → 106)
- **+25 unit tests** (676 → 701)
- **+3 verified-write migrations** (`write_processed_readme`, `build_pipeline_health`, `build_health_dashboard` — Aaron's burndown)
- **+1 runner endpoint** (`/audit-receipts` — closes NEXT-STEPS item 10 part 1)
- **+1 security feature** (privacy classifier wired at OpenRouter call site via `tools/egress_guard.py`)
- **+1 UI win** (DCC Pipeline-healthy banner)
- **+1 vault tool** (`scripts/vault_cleanup.py` review-only)
- **ADR-0008 + ADR-0009 promoted Proposed → Accepted**

---

## §2 · What's still genuinely open (anti-drift-filtered)

Each item triple-checked against live tree. Items the agents flagged as "open" but already shipped are excluded.

| # | Item | Verification | Why open |
|---|---|---|---|
| **O1** | `egress_guard` NOT wired into runner boundary | `grep -c "egress_guard" services/oho_runner/app.py` returns **0** | Wired only at single Python call site in `tools/process_brain_dump.py:_chat_with_fallback`. Future `/capture` endpoint + broker calls bypass it. |
| **O2** | `vault-health-report` workflow still uses `executeCommand` | NEXT-STEPS item 10 part 2 outstanding; runner endpoint exists but n8n JSON not edited | Workflow silently fails since ~2026-04 |
| **O3** | `system-health-monitor` `Any Failures?` false branch terminal `[]` | `_LOG_WRITE_OPTIONAL` allowlist still contains both health workflows | Pure IF-false-branch silent-log bug class; `alwaysOutputData` fix (shipped 3560896) only solved S3-chain bail, not the noop-log path |
| **O4** | Verified-write hot-path: `tools/process_brain_dump.py` RMW telemetry (4 sites) still bare puts | Allowlist comment: `"process_brain_dump.py — 4 put_object call sites incl. RMW telemetry"` | Concurrent-edit corruption window (Remotely-Save + cron) |
| **O5** | `tools/privacy_classifier.SKELETON_MODE = True` | Source confirms | Tier 3-8 dictionary matches and PII regex gates (luhn, allowlist) all stubbed; criteria #4 + #9 cannot be measurably proved green |
| **O6** | Phase C `scripts/migrate_threaded_tasks.py::apply` is STUB | Per ADR-0009 + commit `6cd9d2d` log | Phase C cannot ship without this |
| **O7** | Briefing decision-required badge (UI win #1) | `workflows/n8n/morning-briefing.json` subject + HTML unchanged | Deferred from C3 because JSON Code-node edit is fragile |
| **O8** | Eval fixtures 35/200 (criterion #3 + #4 + #9 cannot be proved green without fixture growth) | `evals/comms_privacy/` count | Wave-X H3 release gate |
| **O9** | Master Plan v2 + V1 ROADMAP `Tests: 311 pass / 492 pass` claims | Both docs read; Aaron's bumps have not refreshed these | Drift vector for future Claude/Codex sessions |
| **O10** | 2 `_LOG_WRITE_OPTIONAL` workflows still allowlisted | `tests/test_workflow_templates.py` | Once O2 + O3 ship + verify live, remove |

---

## §3 · The 5 surgical commits this week (ranked)

Each: **Goal · Effort · Confidence · Surgical risk · Anti-drift verification · 3-step recipe.**

### S1 — Wire `egress_guard` into runner boundary (closes O1)

- **Goal:** every payload crossing the runner boundary classified before any AI/broker call
- **Effort:** M (3-5h)
- **Confidence:** HIGH (egress_guard module proven; integration tests already exist via `tests/test_egress_guard.py`)
- **Surgical risk:** 3 — touches the runner's hot path; needs careful fail-closed semantics
- **Anti-drift verify:** `grep -c "egress_guard" services/oho_runner/app.py` = 0 ← confirms open
- **Recipe:**
  1. Add `from tools.egress_guard import guard_for_peer` at runner module top
  2. In `_dispatch()`: when subprocess output JSON includes a `text` payload destined for an external peer, classify + log a `runner.egress` audit line (initially passive — log only; switch to enforce after 7-day soak)
  3. Add `tests/test_runner_egress_guard.py` with 3 fixtures (public allowed, sensitive denied, unknown peer fails closed). Commit + push.

### S2 — `vault-health-report` executeCommand → httpRequest (closes O2)

- **Goal:** Sunday 8PM workflow writes a real run log to MinIO again
- **Effort:** S (2-3h)
- **Confidence:** HIGH (mirror /process-brain-dump pattern proven)
- **Surgical risk:** 2
- **Anti-drift verify:** `grep executeCommand workflows/n8n/vault-health-report.json` returns one match ← confirms open
- **Recipe:**
  1. Edit `workflows/n8n/vault-health-report.json` `Run: Receipt Audit` node: replace `type: n8n-nodes-base.executeCommand` with `type: n8n-nodes-base.httpRequest`. POST `http://oho-runner:8080/audit-receipts` with Bearer auth via existing `OHO Runner Auth` credential. Output mapping `findings = $json.stdout_json`.
  2. Remove `vault-health-report.json` from `_LOG_WRITE_OPTIONAL` in `tests/test_workflow_templates.py`. Add `audit_no_executecommand` to `audit-all` (currently not in gate per Agent A finding).
  3. Document live verification steps: operator deploys → trigger manual run → verify `99_System/logs/vault-health-report-<date>.json` lands.

### S3 — `system-health-monitor` Build Noop Log on `Any Failures?` false branch (closes O3)

- **Goal:** complete log-write coverage; allowlist exit
- **Effort:** S (1-2h)
- **Confidence:** HIGH (Build Noop Log pattern proven in `daily-note-creator-v2` + `link-enricher`)
- **Surgical risk:** 2
- **Anti-drift verify:** workflow's `Any Failures?` connection second branch is `[]` (already confirmed earlier session)
- **Recipe:**
  1. Add `Build Noop Log` Code node emitting `{status: "skipped", skip_reason: "no_failures"}` literal; wire `Any Failures?` false branch to it; wire it to `S3: Write Log`.
  2. Add `"no_failures"` to `ALLOWED_SKIP_REASONS` in both `tests/test_workflow_templates.py` AND `scripts/audit_workflow_runlogs.py` (mirror keep these synced).
  3. Remove `system-health-monitor.json` from `_LOG_WRITE_OPTIONAL`. `make audit-ci` green.

### S4 — Verified-write migrate `tools/process_brain_dump.py` RMW telemetry (closes O4 hot path)

- **Goal:** 4 highest-blast-radius bare put_object sites → `put_text_if_match_verified` with retry-on-PreconditionFailed
- **Effort:** M (4-6h)
- **Confidence:** MED (RMW pattern new; needs careful retry loop)
- **Surgical risk:** 4 — touches the brain-dump pipeline hot path
- **Anti-drift verify:** allowlist comment confirms "4 put_object call sites incl. RMW telemetry"
- **Recipe:**
  1. Identify the 4 sites in `process_brain_dump.py` (likely `_update_run_telemetry` / `_write_extraction_receipts` / etc.). Per site: replace `s3.put_object` with `read_text_with_etag` → mutate → `put_text_if_match_verified(..., etag)`. Wrap in retry loop on `PreconditionFailedError` (max 3 attempts, sleep 100ms).
  2. Update `tests/test_brain_dump_orchestrator.py` to assert verified-write via ETag round-trip.
  3. Remove `tools/process_brain_dump.py` from `scripts/audit_no_unverified_put_object.py` allowlist. `make audit-ci` green. Commit.

### S5 — Phase F Day-2 wave 1: implement Tier-9 PII regex gates (partial close of O5)

- **Goal:** flip half the classifier from skeleton — Tier 9 (PII shapes: SSN, credit card, phone, email) is mechanically defined, no operator-curated dict needed
- **Effort:** M (3-5h)
- **Confidence:** HIGH for Tier 9 (regex + Luhn well-defined); MED for SKELETON_MODE flip (need adversarial fixtures first)
- **Surgical risk:** 3 — false-positive over-blocking risk if regex too aggressive
- **Anti-drift verify:** `tools/privacy_classifier.py:50` `SKELETON_MODE = True`; Tier 9 rules check `m.get("luhn_check") or m.get("not_in_allowlist")` then short-circuit to `continue`
- **Recipe:**
  1. Implement Luhn check helper in `tools/privacy_classifier.py`. Implement `not_in_allowlist` against `infra/pii-allowlist.yaml` (new file; placeholder allowlist for known-safe phone numbers, emails Aaron uses).
  2. Keep `SKELETON_MODE = True` for Tier 3-8 (dictionary tiers — needs operator-curated yaml); only flip Tier 9 gates to active. Add 10 new eval fixtures targeting Tier 9 (5 hits, 5 allowlist-passes).
  3. Add `audit_tier9_pii_gates.py` that runs the 10 fixtures + asserts ≥95% precision. Add to `audit-all`. Commit + push.

---

## §4 · Definition-of-Amazing readiness matrix (post-7-day projection)

| # | Criterion | Today | After 5 surgical commits |
|---|---|---|---|
| 1 | DCC is only file Aaron opens daily | ⚠️ live but no usage proof | unchanged (needs measurement script) |
| 2 | Capture p95 < 24h | ⚠️ unmeasured | unchanged |
| 3 | Every AI output eval-gated | 🔴 35/200 fixtures | 🟡 45/200 (S5 adds 10) |
| 4 | Sensitive data never reaches free-tier | 🔴 SKELETON_MODE | 🟡 Tier 9 PII active; Tier 3-8 still skeleton |
| 5 | 7-day failure tolerance | 🔴 health workflows broken | 🟢 S2 + S3 close both; chaos test still needed |
| 6 | Decision Journal ≥10 reviewed | 🔴 zero infra | unchanged (needs P2.5) |
| 7 | ≥2 novel domain features | 🔴 specs only | unchanged (P6) |
| 8 | OHO + broker share trace_id | 🔴 zero traceparent | unchanged (P3.5) |
| 9 | No sensitive crosses broker | 🔴 classifier dicts empty | 🟡 S1 + S5 partial |

**5-of-9 criteria advance** at least one tier. **#5 reaches GREEN** assuming live deploy of S2 + S3.

---

## §5 · Skills lock-in this week (per cavecrew D output)

| Commit | 3 lock-in skills | Bonus | Parallel cavecrew? |
|---|---|---|---|
| S1 runner egress wiring | `app-security-architect` · `secure-by-design` · `test-driven-development` | `code-review` | YES — adversarial fixture gen in parallel |
| S2 executeCommand swap | `n8n-workflow-architect` · `mcp-server-builder` · `systematic-debugging` | `verification-before-completion` | NO |
| S3 noop log | `n8n-workflow-architect` · `test-driven-development` · `verification-before-completion` | — | NO |
| S4 verified-write hot path | `database-design` · `test-driven-development` · `systematic-debugging` | `app-security-architect` | YES — RMW pattern + retry loop in parallel |
| S5 Tier 9 PII gates | `secure-by-design` · `app-security-architect` · `testing-strategy` | `code-review` | YES — Luhn impl + allowlist seeding in parallel |

**Always-on meta:** `anti-hallucination` · `context-guardian` · `cognitive-excellence` · `efficiency-engine` · `prompt-amplifier` · `secure-by-design` · `session-optimizer` · `solution-architect-engine` · `verification-before-completion` — all 9 symlinked in `.claude/skills/` per Agent D.

### Skills to build local this week

| Skill | Purpose | Plugs into |
|---|---|---|
| `decision-toolkit` | Family/faith/biomarker payload gates with ADR-style records | S5 + Phase F Day-2 wave 2 (Tier 3-8 dicts) |
| `eval-fixture-factory` | Parameterized adversarial fixture generation | S1 + S5 + Wave-X H3 |
| `s3-verified-migration-toolkit` | AST-walk + diff scaffolder for bare put_object → verified | S4 + remaining 7 allowlist files |

---

## §6 · Drift hotspots to clean (3 cheap doc fixes)

D1. **Master Plan v2 + V1 ROADMAP test count claims** ("311 pass" / "492 pass"). Real: 701. Pin both to CURRENT-STATE.md or refresh quoting verbatim from `make audit-ci`. **XS · 1 commit.**

D2. **CLAUDE.md `99_System/logs/` claim:** says "every workflow writes JSON to" — but vault-health-report + system-health-monitor still silently fail. Either add an "⚠️ active incident" callout linking NEXT-STEPS item 10/10b OR wait until S2/S3 ship then remove the callout. **XS · 1 commit (post-S2/S3).**

D3. **`audit-all` gate completeness:** Agent A found 3 audit scripts on disk not bound. `audit_no_executecommand` + `audit_no_argv_secrets` + `audit_no_unverified_put_object` actively enforced as guards; document this in `Makefile:audit-all` comment OR bind into gate. **XS · 1 commit.**

---

## §7 · Sequenced execution recipe — 7 days

**Day 1 (today):** S3 (system-health noop log — XS) + D1 (test count refresh — XS) + D3 (audit gate comment — XS). 3 commits.

**Day 2:** S2 (executeCommand → httpRequest workflow JSON edit — S). 1 commit + operator follow-up to deploy & verify live.

**Day 3-4:** S1 (egress_guard at runner boundary — M). 1 commit; passive logging first.

**Day 5-6:** S4 (verified-write hot-path migration — M). 1 commit + tests + allowlist exit.

**Day 7:** S5 (Tier 9 PII gates — M). 1 commit + 10 fixtures + new audit script.

**Total: 7 commits across 7 days; all ≤80 lines code change; all gated by `make audit-ci` green; PR #2 stays CLEAN throughout.**

---

## §8 · Parallel cavecrew opportunities for this week

Per Agent D's GAIN × CONTEXT-SAVED scoring:

| Activity | GAIN | CONTEXT | Spawn pattern |
|---|---|---|---|
| S1 + adversarial fixture gen | 5 | 5 | 1 cavecrew-investigator on adversarial generation + 1 general-purpose on integration test design |
| S4 hot-path migration plan | 4 | 5 | 1 cavecrew-investigator maps the 4 RMW sites + dependencies; 1 general-purpose drafts the retry-loop pattern |
| S5 Tier 9 PII corpus | 4 | 4 | 1 cavecrew-investigator drafts allowlist + adversarial fixtures in parallel with main edit |

**Use `superpowers:dispatching-parallel-agents`** when commits are M-effort with multiple independent investigation paths.

---

## §9 · Pointer index

| Doc | Owner |
|---|---|
| `docs/CURRENT-STATE.md` | live numbers (refresh weekly) |
| `docs/NEXT-STEPS.md` | operator checklist (refresh per commit) |
| `docs/superpowers/2026-05-13-MASTER-PLAN-V2.md` | execution path v2 (Aaron's hand) |
| `docs/superpowers/2026-05-27-FOUNDATION-AUDIT-AND-TOP-DOWN-PLAN.md` | 2-day-old foundation audit (mostly current; superseded for next-7-day only) |
| `docs/superpowers/2026-05-29-SURGICAL-NEXT-7-DAY-PLAN.md` | **this doc** |

---

*Synthesized 2026-05-29 from 5 parallel cavecrew investigations. Every claim verified against live `git log` + `grep` + MinIO + n8n, not memory. Filter applied: agents working from Foundation Audit 2026-05-27 doc that pre-dates C-series shipments had stale "open" claims; verified-against-tree wins. Recommended kick-off: **S3 today (XS, no live deploy needed, finishes a class-of-bug burndown)**.*

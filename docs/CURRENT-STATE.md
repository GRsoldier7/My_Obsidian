# OHO — Current State (canonical)

**As of:** 2026-05-27 (Wed) — P0.5 soak EXITED 2026-05-18; foundation deepening continues
**Branch:** `polish/prod-ready` · **PR:** [#2](https://github.com/GRsoldier7/My_Obsidian/pull/2) open + MERGEABLE
**Commits ahead of `master`:** 85 (polish/prod-ready) + isolated branch `feature/phase-c-f-skeletons` carrying Phase C+F skeletons (63 tests)
**Soak status:** ✅ CLEARED 2026-05-18 (Day 7 brain-dump-processor `status: success`); Aaron's Wave-X H3 dashboard + CI hardening landed 2026-05-25.

This document is the SINGLE source of truth for "where are we?" Every other doc that quotes commit counts / test counts / phase status should link here rather than repeat the numbers.

Last refresh: 2026-05-27 (auto-regenerable from `make audit-all` + `git rev-list`).

---

## Hard numbers

| Metric | Value | Source |
|---|---|---|
| Commits ahead of `master` (polish/prod-ready) | **85** | `git rev-list --left-right --count master...HEAD` |
| Test suite (`make verify` scope) | **603 pass + 7 skip** | `make verify` |
| Offline audits | **10 green** | see below |
| Active n8n workflows | **14** | `workflows/n8n/*.json` (job-search quarantined) |
| ADRs | **9** (0001-0006 historical, 0007 Accepted, 0008-0009 Proposed) | `docs/adr/` |
| Eval fixtures | **35 / 200 target** | `evals/comms_privacy/` |
| Pre-staged Phase C+F skeletons | branch `feature/phase-c-f-skeletons`, **63 tests** across 4 modules | NOT YET MERGED (post-soak action pending) |
| Wave-X H3 health dashboard | `tools/build_health_dashboard.py` + `99_System/health.md` | ✅ landed 2026-05-25 (commit `2217ab5`) |
| CI gate | `.github/workflows/audit-pr.yml` + sticky failure comment | ✅ live (commits `1fc577a` + `36ed420`) |
| Dev/CI deps | pinned in `requirements-dev.txt` | ✅ pinned 2026-05-25 (`c7c5755` + `961fc6d`) |
| GCAL OAuth | cred shell `uAySKd53I6zgvFjx` exists in n8n; consent NOT YET CLICKED; `.env` missing `GCAL_CRED_ID` | ⏳ blocked on operator browser consent at `https://n8n.tailfab8a7.ts.net/credentials/uAySKd53I6zgvFjx` |

### Offline audits (all green)

1. `audit_workflow_credentials.py` — `s3` family consistency
2. `audit_workflow_connections.py` — email-node dead-end enforcement
3. `audit_workflow_runlogs.py` — `skip_reason` canonical enum (inherited; not in `audit-all` yet)
4. `audit_ai_tooling.py` — AGENTS.md / AI_TOOLING.md / MCP example sync
5. `audit_extraction_receipts.py` — brain-dump integrity (soak signal)
6. `audit_data_classes.py` — `infra/data-classes.yaml` contract (ADR-0008)
7. `audit_secrets_rotation.py` — `docs/security/secrets-rotation.md` cadence
8. `audit_planning_docs.py` — ADR / spec / phase / runbook cross-refs
9. `audit_workflow_secrets.py` — hardcoded creds / IDs / PII (R1-R6) — born from 2026-05-16 incident
10. `audit_no_executecommand.py` — blocks n8n `executeCommand` regressions (P1.5); `vault-health-report.json` allowlisted until post-soak migration
11. `audit_no_argv_secrets.py` — blocks `curl -H "Bearer $VAR"` argv leaks (Codex P0 #2); `setup-n8n.sh` + `deploy_oho_runner.py` allowlisted until post-soak refactor
12. `audit_slo_conformance.py` — Wave-X H3 skeleton; parses `docs/SLO-life-os.md` (8 workflow targets); MinIO log walk lands post-soak

Run all in one shot: `make audit-all`. Pre-PR gate: `make verify` (audit-all + unit tests).

### Self-healing infrastructure (active 2026-05-16)

- **CI gate** — `.github/workflows/audit-pr.yml` runs every audit + unit tests on every PR + push to `master` / `polish/prod-ready`.
- **Pre-commit hook** — `.githooks/pre-commit` runs the offline audit subset before every commit. Activate per-clone with `git config core.hooksPath .githooks`.
- **`make verify`** — fast local pre-PR gate (audit-all + unit tests, ≤2s warm).

---

## Phase status

| Phase | Theme | State | Evidence |
|---|---|---|---|
| P0 | Stop the bleed | ✅ shipped | `2b518b1` |
| P1 | State machine + receipts | ✅ live in prod | `f3f8325` → `947e507` (ADR-0005) |
| P1.5 | HTTP-runner sidecar | ✅ live in prod | `a1bd438` |
| ADR-0006 | Daily Command Center | ✅ live in prod | `097892a` |
| **P0.5** | **Deploy + 7-day soak** | ⏳ **Day 6/7** | `audit_extraction_receipts.py` green; 6 consecutive daily runs (2026-05-11 → 2026-05-16) |
| P2 | Threaded tasks | 🔒 design-only | [ADR-0009](adr/0009-threaded-tasks.md) Proposed |
| P2.5 | Decision Journal | 🔒 post-P2 | rides P2 IDs |
| P3 | Capture-Everywhere | 🔒 post-P2 | spec exists |
| P3.5 | OHO-as-Broker-Client | 🔒 design-only | [ADR-0008](adr/0008-cross-host-comms.md) Proposed |
| P4 | Decision-Ready Briefings | 🔒 post-P3 | eval-gated |
| Wave-X | Cross-cut (sec/eval/obs/comms) | 🔒 post-P4 | 4 lanes named |
| P5 | Review Rituals | 🔒 post-Wave-X | spec exists |
| P6 | Domain-Aware UX | 🔒 post-P5 | spec exists |
| P6.5 | Spouse-Shared Mode | 🔒 design-only | conditional on Christy |
| P7 | AI Coach + Insight Loop | 🔒 LAST | gated on Wave-X infra |

**Hard rules during soak (effective until Mon 2026-05-18):**

- No new capture surfaces.
- No new code-surface phases (P2 / P3 / P3.5 / P4 code).
- No new code-heavy cron slots (slots `:03 :13 :23 :30 :33` claimed; `:43 :53` reserved).
- No call-site rewrites of S3 helpers (the new `tools/s3_verified.py` is additive; old call sites stay).

**Allowed during soak:**

- Docs / config / fixtures / additive helper modules (no callers yet).
- Audits + tests.
- Bug fixes + incident response.
- ADR + spec authoring.

---

## Foundation seeded (ready to wire post-soak)

| Phase F prereq | File | Status |
|---|---|---|
| Privacy rule registry | `infra/data-classes.yaml` | committed + audited (10 tiers, 5 peers) |
| Eval fixture schema | `evals/comms_privacy/README.md` | committed + 62 parametrized tests |
| Eval harness | `scripts/run_evals.py` | committed (schema-only mode; `--run-classifier` stubbed) |
| Eval fixtures | `evals/comms_privacy/F-*.json` | **25 / 200** (toward Phase F day-1) |
| Secrets rotation table | `docs/security/secrets-rotation.md` | committed + auditor |
| Bearer rotation runbook | `docs/runbooks/rotate-telegram-token.md` | committed |
| S3 verified-write helper | `tools/s3_verified.py` | committed + 12 tests (no callers yet) |
| Backing-file schema (Phase C) | `docs/schemas/task-backing-file.v1.yaml` | committed |
| Workflow-secrets audit (R1-R6) | `scripts/audit_workflow_secrets.py` | committed + 15 tests |
| No-executeCommand audit | `scripts/audit_no_executecommand.py` | committed + 5 tests |
| **Phase C skeleton** `tools/task_id.py` | on `feature/phase-c-f-skeletons` | 17 tests green; merge post-soak |
| **Phase F skeleton** `tools/privacy_classifier.py` | on `feature/phase-c-f-skeletons` | 19 tests green; SKELETON_MODE=True until day-2 wiring |

Phase F code (post-soak):
  - **Skeleton merged on Mon 2026-05-18**: `tools/privacy_classifier.py` already on `feature/phase-c-f-skeletons`. Day-1 = merge + flip SKELETON_MODE to False as each tier dictionary lands.
  - Still to write: `clients/agent_orch_client.py`, comms inbox / outbox / audit endpoints on `services/oho_runner`.

Phase C code (post-soak):
  - **Skeleton merged on Mon 2026-05-18**: `tools/task_id.py` already on `feature/phase-c-f-skeletons`. Day-1 = merge + start writing `scripts/migrate_threaded_tasks.py` against it.
  - Still to write: `scripts/audit_threaded_tasks.py`, MTL bidirectional sync, Command Center thread-card renderer, runner endpoints `/tasks/split` `/tasks/merge` `/tasks/archive`.

---

## Open incidents

### 2026-05-16 — job-search-pipeline credential leak (RESOLVED)

- **File:** quarantined to `workflows/quarantine/job-search-pipeline-2026-04-02-LEAKS.json`.
- **Documentation:** [`docs/security/2026-05-16-INCIDENT-job-search-leak.md`](security/2026-05-16-INCIDENT-job-search-leak.md).
- **Status:** **RESOLVED 2026-05-16.** Code remediation shipped (commit `cd27264`). Operator confirmed rotation of OpenRouter API key + Telegram bot token. `last_rotated` recorded in `docs/security/secrets-rotation.md`. Do not re-prompt for these rotations.

### 2026-05-16 — vault-health-report.json uses `executeCommand` (KNOWN, post-soak)

- **Where:** `workflows/n8n/vault-health-report.json:245` — node `Run: Receipt Audit` uses `n8n-nodes-base.executeCommand` which was dropped by the n8n 2.x task-runner registry per P1.5.
- **Effect:** the Sunday 8PM CDT vault-health-report has been silently failing since ~2026-04 (no run logs in MinIO).
- **Mitigation today:** `make audit-extraction-receipts` runs the same script locally; soak signal is intact.
- **Post-soak fix:** add `POST /audit-receipts` endpoint to `services/oho_runner` mirroring the `/process-brain-dump` pattern; switch the workflow node from `executeCommand` to `httpRequest`. Tracked in [NEXT-STEPS.md](NEXT-STEPS.md).

---

## Held artifacts (drafted, awaiting operator OK)

| File | Lines | Purpose |
|---|---|---|
| `.github/workflows/audit-pr.yml` | 60 | Every-PR CI gate: `make audit-all` + `pytest`. Injection-safe (no `github.event.*` in `run:`). |
| `.githooks/pre-commit` | 38 | Per-clone local gate (`git config core.hooksPath .githooks` to activate). |

Both block on durable-persistence policy. Land with one operator command (see NEXT-STEPS.md).

---

## Pointers (for depth)

| What you want | Where |
|---|---|
| The plan | [ADR-0007](adr/0007-master-plan-v2.md) + the full design at `docs/superpowers/2026-05-13-MASTER-PLAN-V2.md` |
| Phase F design | [ADR-0008](adr/0008-cross-host-comms.md) + spec at `docs/superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md` |
| Phase C design | [ADR-0009](adr/0009-threaded-tasks.md) + spec at `docs/superpowers/specs/2026-05-12-P2-threaded-tasks-spec.md` |
| SLO targets | [SLO-life-os.md](SLO-life-os.md) |
| What changed today | [session-logs/2026-05-16-foundation-deepening-session.md](session-logs/2026-05-16-foundation-deepening-session.md) |
| Lessons | [learnings/2026-05-16-soak-safe-foundation-pattern.md](learnings/2026-05-16-soak-safe-foundation-pattern.md) |
| What to do next | [NEXT-STEPS.md](NEXT-STEPS.md) |

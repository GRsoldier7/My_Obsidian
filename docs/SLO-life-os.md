# Life OS — Service Level Objectives

**Status:** Draft for Wave-X H3 (cross-cutting observability lane) · **Date:** 2026-05-16 · **Owner:** ADR-0007

SLOs make "healthy" measurable. Each row below is a contract between the system and Aaron: violation = surface in the weekly digest; sustained violation = page via error-handler.

**Reporting cadence:** SLO conformance computed weekly by `scripts/audit_slo_conformance.py` (proposed — lands during Wave-X). Today, conformance is hand-checked off MinIO logs.

---

## Definitions

- **Success rate** — fraction of scheduled runs that ended `status: success`. Skips count as success only when `skip_reason` is in the canonical allowed enum.
- **Latency p95** — 95th-percentile wall-clock from cron trigger to terminal status. Logged in the run-log `duration_ms` field.
- **Freshness** — wall-clock age of a derived artifact (Command Center, briefing) at any given moment; measured by MinIO `LastModified` minus `now`.
- **Integrity** — domain-specific invariants (receipt-write coverage, audit-line completeness, schema validity).

All SLO windows are **7 rolling days** unless stated.

---

## Workflow SLOs

### Brain dump processor (`brain-dump-processor-v2`)

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 99% (≥ 6.93 / 7 runs) | < 95% (≤ 6 / 7) |
| Latency p95 | ≤ 30s wall-clock | > 60s |
| Integrity — extraction receipts | 100% match between final-state files and receipts | any mismatch |
| Skip-reason validity | every `status: skipped` carries a canonical `skip_reason` | any uncategorised skip |

### Daily note creator (`daily-note-creator-v2`)

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 99% | < 95% |
| Idempotency | re-run on same date produces byte-identical note | any drift |

### Morning briefing

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 99% | < 95% |
| Latency p95 (assembly + render) | ≤ 10s | > 30s |
| Render integrity | no `null` / `undefined` strings in delivered HTML | any occurrence |

### Weekly digest / vault-health-report

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 99% (≥ 4 / 4 monthly Sundays) | < 75% |
| Receipt-audit inclusion | weekly digest must include the receipt-audit summary | any missing run |

### Live dashboard updater + link enricher (hourly)

| Workflow | Success rate | Latency p95 | Pages on |
|---|---|---|---|
| live-dashboard-updater | ≥ 99% (≥ 166 / 168 weekly runs) | ≤ 10s | < 90% / > 30s |
| link-enricher | ≥ 95% (network-dependent) | ≤ 30s | < 80% / > 90s |

### System health monitor (every 6h)

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 99% (≥ 27 / 28 weekly runs) | < 90% |
| Detection latency | health flips to `degraded` within 30s of MinIO / n8n outage | > 5 min |

### Telegram capture (webhook)

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 99% (excluding sender-side issues) | < 95% |
| Latency p95 (webhook → MTL append) | ≤ 2s | > 5s |
| Lossless replay | retry of same `update_id` produces zero duplicates | any duplicate |

### Article processor (8AM + 7PM CDT)

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 95% (network-dependent on og:* fetch) | < 85% |
| Latency p95 | ≤ 60s | > 180s |

### Error handler (on-error)

| Dimension | Target | Pages on |
|---|---|---|
| Emit latency | error → email + Telegram within 30s of source error | > 2 min |
| Coverage | every workflow with `executeWorkflow:errorWorkflow` wired | any unwired workflow |

### AI brain sub-workflow

| Dimension | Target | Pages on |
|---|---|---|
| Success rate | ≥ 95% (covers cascade fallbacks) | < 85% |
| Cost telemetry | every invocation logs `model + tokens_in + tokens_out + cost_usd` | any missing field |

---

## Endpoint SLOs (oho-runner sidecar)

| Endpoint | Latency p95 | Success rate | Pages on |
|---|---|---|---|
| `/health` | ≤ 200ms | ≥ 99.9% | > 1s / < 99% |
| `/process-brain-dump` | ≤ 180s | ≥ 99% | > 300s / < 95% |
| `/build-command-center` | ≤ 10s | ≥ 99% | > 30s / < 95% |
| **(P3.5)** `/comms/inbox` | ≤ 2s p95 | ≥ 99% | > 5s / < 95% |
| **(P3.5)** `/comms/audit-tail` | ≤ 500ms p95 | ≥ 99% | > 2s / < 95% |

---

## Artifact-freshness SLOs

| Artifact | Freshness target | Pages on |
|---|---|---|
| `000_Master Dashboard/!!! DAILY COMMAND CENTER.md` | ≤ 36h since last rebuild | > 48h |
| `99_System/state/last-brain-dump-summary.json` | ≤ 30h | > 48h |
| `99_System/logs/brain-dump-processor-<today>.json` | exists by 8AM CDT (cron fires 7AM) | missing by 9AM |

---

## Cross-cutting SLOs

### Soak window (P0.5 / ADR-0007 Phase A)

- **Acceptance:** 7 consecutive days of clean `audit_extraction_receipts.py`.
- **Tripwire:** any run with `status: error` OR `partial` aborts the soak; rollback per `docs/superpowers/phases/2026-05-12-P0-deploy-and-soak-start.md` §8.

### Privacy classifier (Phase F, ADR-0008)

- **Eval precision** ≥ 95% per class.
- **Eval recall** ≥ 95% per class.
- **Drift** ≥ 5% WoW → page.
- **Sensitive egress to VPS** = 0 always. Single occurrence = page.

### Secrets rotation

- **Overdue rotations** = 0 always. Any row past `next_due` = MTL task injected within 24h.
- **Rotation cadence** = 90d for bearers / API keys, 180d for MinIO; per `docs/security/secrets-rotation.md`.

---

## Reporting + escalation

| Severity | Trigger | Routing |
|---|---|---|
| INFO | SLO conformance ≥ target but trending down 2+ weeks | weekly digest mention |
| WARN | SLO conformance below target for a single 7-day window | weekly digest top section |
| PAGE | SLO conformance below pages-on threshold for 2+ windows OR a single hard tripwire | email + Telegram via error-handler |

---

## Open questions

1. **Cost telemetry — daily cap?** OpenRouter free tier means $0 most days, but mistakes happen. Should `ai-brain` emit a hard-stop at $X/day? Defer to Wave-X H3 implementation.
2. **Should freshness SLO be wall-clock or business-hours?** Aaron's working hours are CT; weekend nights shouldn't page on Sunday 11pm staleness if the workflow runs Monday 6AM. Open.
3. **Manual-override mechanism.** Aaron sometimes intentionally stops a workflow for a day (e.g., travel, family emergency). The SLO should know about a `do_not_page` window. Defer.
4. **Which dashboard renders these?** Pending Wave-X H3 dashboard design. Today, conformance is operator-visible via `make logs` + the weekly digest.

---

## How this becomes self-healing

1. `scripts/audit_slo_conformance.py` (proposed) reads MinIO run-logs, computes per-workflow conformance, writes `99_System/state/slo-status.json`.
2. The Daily Command Center renders a "🩺 SLO health" panel from that state file.
3. Any PAGE-level breach lands in MTL as `[priority:: A] [area:: home]`.
4. The runbook `docs/runbooks/slo-breach-triage.md` (TBD) gives the operator a 60-second triage flow.

Self-healing means: the system tells Aaron when it's breaking, *before* Aaron notices something is missing.

# ADR-0007: Master Plan v2 — Comms-Pivot Roadmap

**Status:** Accepted · **Date:** 2026-05-16 · **Supersedes:** ad-hoc roadmap in `docs/superpowers/2026-05-12-LIFE-OS-V1-MASTER-ROADMAP.md` (preserved as deep-dive index)

**Full design doc:** [`docs/superpowers/2026-05-13-MASTER-PLAN-V2.md`](../superpowers/2026-05-13-MASTER-PLAN-V2.md)

---

## Context

The 2026-05-12 v1 master roadmap assumed the LXC↔Desktop↔VPS comms layer was greenfield. Recon on 2026-05-13 (`docs/superpowers/phases/2026-05-13-agent-orch-lxc-recon.md`) proved otherwise: Aaron's sibling repo `GRsoldier7/agent-orch-lxc` on Proxmox **CT 215** has already shipped Phase 1+2 of a FastAPI + Redis broker spine (`/tasks`, `/tasks/lease`, `/tasks/{id}/complete`, `/workers/heartbeat`, `/events` SSE, per-worker bearer tokens, W3C `traceparent`, Hypothesis property tests). One leaked Telegram bot token is live in BOTH repos; rotation at @BotFather is the single most urgent operator action.

## Decision

Adopt Master Plan v2 as the binding execution path for Life OS v1.0.

Key shifts from v1:

1. **OHO becomes a client of the CT 215 broker, not a builder of a parallel one.** New Phase F (P3.5) "OHO-as-Broker-Client" inserted between P3 and P4. Collapses ~3-5 days of greenfield engineering into ~2 days of client integration + ACL/token plumbing.
2. **Wave-X splits into 4 named lanes** (security · eval · observability · comms-dashboard) — previously lumped.
3. **Phase numbering grows to 9 phases + 1 cross-cut wave** (was 7).
4. **Two new "Definition of Amazing" rows** capture cross-host invariants:
   - OHO + CT 215 broker share one canonical `trace_id` end-to-end.
   - No sensitive payload class ever crosses the OHO→broker edge without explicit allow-list (classifier-enforced, not hope-enforced).
5. **Telegram token rotation @BotFather is HYG-A** — operator-only, unblocks both repos.
6. **Privacy classifier** owns the OHO→broker edge: deny-list default; `faith`/`family-named`/`kid-named`/`health-biomarker` never egress without explicit `allow_egress_to`.
7. **No new code-surface work during the P0.5 soak window** (≥7 days clean post-deploy required before Phase C kickoff).

## Consequences

- Saves ~3-5 days of broker engineering; reinvests time in Wave-X cross-cut and privacy classifier.
- Adds a hard external dependency on CT 215 broker availability — mitigated by `n8n-only` graceful-degradation path (Risk #11).
- Adds 6 new tier-1 decisions (D1-D6 in plan §"Consolidated open decisions") + 5 risk-register rows (#11-15).
- Cron slot `:53` reserved for `comms-health-monitor` (only free slot remaining; enforced by `tests/test_workflow_templates.py::test_code_heavy_workflows_do_not_share_cron_minutes`).
- Sister ADRs to be promoted from spec docs during their respective phase kickoffs:
  - **ADR-0008** — Cross-host comms envelope + transport (from `docs/superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md` §1, at Phase F start).
  - **ADR-0009** — Threaded tasks (from `docs/superpowers/specs/2026-05-12-P2-threaded-tasks-spec.md`, at Phase C kickoff post-soak 2026-05-18).

## Hard rules (carry-forward from v1 + new)

- P0.5 soak must run clean ≥7 days before Phase C starts. No new capture surfaces, no insights/coach scripts, no domain UX scope during the gate.
- P2 (threaded tasks) is design-first. ADR-0009 lands before code.
- P3.5 (broker-client) is integration, not construction. F1-F6 sub-lanes target the canonical `agents/orchestrator/` tree only (NOT the older `orchestrator/` Compass router tree — see Risk #14).
- AI Coach (Phase L) ships LAST and only after all Wave-X cross-cut infra is live (data classifier + eval suite + observability + comms dashboard).

## Verification

- See [docs/CURRENT-STATE.md](../CURRENT-STATE.md) for live numbers. At ADR promotion (2026-05-16): 326 pass + 1 skip, 5 audits green. As of 2026-05-16 EOD: 492 pass + 1 skip, 7 audits green (data-classes, secrets-rotation, planning-docs, workflow-secrets added).
- Phase A (deploy + soak) is in flight; ends 2026-05-18 per memory.

## Rollback

Plan v2 is a planning document — rollback is editorial. If reality diverges materially during execution, draft ADR-0007a as an amendment, do not delete this ADR. Phase-level rollback procedures live in each phase spec.

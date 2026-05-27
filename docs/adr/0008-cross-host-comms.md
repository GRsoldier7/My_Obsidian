# ADR-0008: Cross-Host Comms Envelope + Transport

**Status:** Accepted — Phase F implementation kicked off; skeleton landed on `polish/prod-ready` (`tools/privacy_classifier.py` + `clients/agent_orch_client.py` + tests, currently `SKELETON_MODE = True` until day-2 dictionary wiring). · **Date:** 2026-05-16 · **Accepted:** 2026-05-27 · **Soak gate:** ✅ cleared 2026-05-18

**Full design spec:** [`docs/superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md`](../superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md)

**Companion recon:** [`docs/superpowers/phases/2026-05-13-agent-orch-lxc-recon.md`](../superpowers/phases/2026-05-13-agent-orch-lxc-recon.md)

---

## Context

Master Plan v2 ([ADR-0007](0007-master-plan-v2.md)) made OHO a peer in a three-host fleet — LXC (CT-202 canonical), Desktop (Claude Code), and VPS (`agent-core-01` @ Vultr). The CT 215 sibling broker (`GRsoldier7/agent-orch-lxc`) already ships a FastAPI + Redis spine OHO must integrate with rather than parallel. OHO additionally needs its own envelope grammar for **non-broker** Desktop↔LXC comms (briefing requests, vault queries, capture replies) and for **outbound** classification before any payload crosses the OHO→broker edge.

## Decision

Adopt the envelope and transport defined in `docs/superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md`:

1. **Transport:** HTTPS + JSON over Tailscale, per-edge bearer tokens (`hmac.compare_digest`), idempotency-keyed envelopes, JSONL audit. No new broker daemon. Reuses the proven `services/oho_runner` pattern.
2. **Envelope shape:** `envelope_version: 1`, canonical fields per spec §3 (`message_id`, `trace_id`, `parent_message_id`, `intent`, `kind`, `privacy_class`, `privacy_attestation`, `payload`, `idempotency_key`, `delivery`, `audit`). Unknown intents → `nack`. Unknown fields → tolerate (forward-compat).
3. **Privacy classifier:** Deterministic rule-based (`tools/privacy_classifier.py`) runs at LXC inbox AND LXC outbox. Sensitive classes (`faith`, `family-named`, `kid-named`, `health-biomarker`, `faith-terms`) NEVER egress to VPS without explicit `privacy_attestation.allow_egress_to: ["vps"]`. Eval target: ≥95% precision + recall on 200-payload fixture set.
4. **Trace continuity:** W3C `traceparent` matches the broker's existing format (`tracing.py` in agent-orch-lxc). One `trace_id` threads Desktop→LXC→VPS→LXC→Desktop round trips.
5. **Audit:** Append-only JSONL at `99_System/logs/comms-<YYYY-MM-DD>.jsonl` on LXC (canonical); peers keep local copies + nightly sync.
6. **Cron slot:** `comms-health-monitor` claims slot `:53` (last free per CLAUDE.md task-runner rule).
7. **Rollout phases:** C1 (LXC inbox endpoints + classifier + audit) → C2 (Desktop outbox + loopback inbox daemon) → C3 (LXC↔VPS edge, gated on VPS use-case clarity) → C4 (audit dashboard + ops integration).

## Hard rules

- All six per-edge bearer tokens (3 hosts × 2 directions) live in Bitwarden self-hosted. Quarterly rotation cadence. `make rotate-comms-token EDGE=<name>` automates staged rotation.
- 64 KB inline payload cap. Larger → MinIO-staged blob; envelope carries `payload.blob_key` reference.
- Tailscale ACL committed at `infra/tailscale-acl.json`. Two-factor: bearer (app) + tailnet tag (network).
- Idempotency store SQLite per host. 30-day prune. Same key + different payload-hash → log `idempotency_collision`, first content wins.
- Receivers MUST accept unknown future fields (forward-compat); receivers MUST `nack` unknown `envelope_version` (deploy-gate).

## Open decisions (defer to Aaron at Phase F kickoff)

Spec §17 enumerates 10 open questions. The five that gate any code:

- **Q1:** What is the VPS for, concretely? (C3 design pivots on this.)
- **Q4:** Desktop role — full peer (with inbox daemon) or strict client (outbox only)?
- **Q5:** Per-edge tokens (6) vs per-host tokens (3) — v1 recommends per-edge.
- **Q6:** Privacy classifier — strict or permissive default — v1 recommends strict.
- **Q7:** Should the comms layer carry P3 external-surface captures (Telegram, email-forward) too, or stay agent-to-agent only — v1 recommends agent-to-agent only.

## Consequences

- **One canonical envelope grammar** across capture (P3), comms (this ADR), briefings (P4), and broker-client (Phase F) — versioned via `envelope_version`.
- **Privacy classifier is the load-bearing component.** False negative = sensitive content escapes to VPS → PAGE immediately. Quarterly eval against expanding fixture set + weekly digest review of all `allow_egress_to: vps` events.
- **Adds ~12 new test files + 80 new test cases** (per spec §15). Existing 326-pass suite must remain green.
- **Coexists with existing `services/oho_runner` endpoints.** `/process-brain-dump` and `/build-command-center` continue unchanged. Comms endpoints are additive.

## Soak gate

ADR-0008 cannot land code until [ADR-0007](0007-master-plan-v2.md) Phase A soak closes (≥7 days clean, ending 2026-05-18 earliest). Implementation begins at Phase F per master plan timeline (W10-11).

## Rollback

Comms layer is feature-flagged (`OHO_COMMS_ENABLED=true`). Disable flag → endpoints return 503; outbox queues drain; existing oho-runner endpoints unaffected. State files (`/opt/oho/state/comms-*.db`) and audit JSONL preserved for post-mortem.

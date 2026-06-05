# agent-orch-lxc Recon — 2026-05-13

Read-only investigation of `GRsoldier7/agent-orch-lxc` (clone at `/tmp/agent-orch-lxc-recon`, depth 100). Goal: figure out what's already built so OHO doesn't duplicate work on the comms layer.

## 1. What is `agent-orch-lxc`?

Aaron's **unified agent orchestration control plane**. A FastAPI + Redis brokerage spine that routes tasks between two PEER fleets. Tailscale-only, never public.

- **Container:** Proxmox **CT 215** `orch-lxc`, Tailscale `100.122.188.108`, hostname `orch-lxc.tailfab8a7.ts.net`. **Different from CT-202 where OHO lives.**
- **Repo location on Proxmox host:** `/root/homelab/containers/agent-orch-lxc/`; deployed to `/opt/agent-control-plane/` on CT 215; sister OHO at `/root/homelab/projects/ObsidianHomeOrchestrator/`.
- **Phase status (their ROADMAP.md, lines 17–106):** Phase 1 Brokerage Spine + Phase 2 Persistent Queue both **SHIPPED 2026-05-09**. Phase 3a VPS worker is "deploy-ready" (operator paste-block staged at `builds/private_control_plane/runbooks/phase3a-vps-worker-deploy.md`); Phase 3b desktop worker pending; Phase 4 LiteLLM+Telegram blocked on Telegram token rotation.

Aaron's "LXC is ready for the comms piece" = the Phase 1+2 spine is live; Phase 3a needs the VPS worker installed and Phase 4 is the comms surface (Telegram + LiteLLM + Hermes-Lite triage).

## 2. Comms layer — what already exists

The control plane is FastAPI + Redis Streams pattern, **already shipping**:

- **Endpoints (`agents/orchestrator/control_api.py:123–291`):** `/health`, `/tasks`, `/tasks/dlq`, `/tasks/{id}`, `/workers/heartbeat`, `/workers/{id}/heartbeat`, `/workers/heartbeats`, `/workers`, `/tasks/lease`, `/tasks/{id}/complete`, `/metrics/snapshot`, `/events` (SSE).
- **Auth (`agents/orchestrator/auth.py:32–89`):** opt-in **per-worker bearer tokens** loaded from a YAML file. Server checks the bearer matches the `worker_id` in the request body — a VPS token cannot impersonate a Desktop worker.
- **Transport:** HTTP POST/GET over Tailscale; **SSE** at `/events` for event fan-out (`agents/orchestrator/events.py:25–70`, bounded in-memory pub/sub, drop-oldest backpressure).
- **Message format:** Pydantic v2 models — `TaskCreateRequest` (`text`, `user_id`, `free_models_only`, `metadata`), `WorkerHeartbeatRequest`, `LeaseRequest`, `CompleteTaskRequest` (see `control_api.py:28–53`).
- **Queue store (`agents/orchestrator/queue_store.py:201–439`):** `RedisQueueStore` with WATCH/MULTI/EXEC atomic lease (no Lua — ACL denies `@scripting`). Keys namespaced under `agent:orch:*` on CT 205 Redis.
- **Worker side (`agents/worker/{runner,client,executor,config}.py`):** install bundle ships a heartbeat/lease/execute/drain loop; Phase 3 ships a `StubExecutor` that echoes; Phase 4 swaps in a `HermesExecutor` calling LiteLLM with the same interface.

There is **no inbox/outbox** for OHO. No Telegram receiver, no webhook handler. Phase 4 plans both.

## 3. Agent fleet topology

From `TWO_INITIATIVES.md` and `agents/orchestrator/config/worker_capabilities.yaml`:

| Fleet | Worker IDs | Host | Tailscale | Role |
|---|---|---|---|---|
| **VPS (Initiative A)** | `vps-heavy` | `agent-core-01` | `100.75.73.27` | 24/7 fallback, 8GB, OpenRouter free only, `read_only` tools |
| **Desktop (Initiative B)** | `desktop-heavy`, `desktop-light`, `scribe-lite` | `aaron-inspiron-3030` | `100.112.192.78` | On-demand heavy, 64GB+16GB VRAM, local Ollama + cloud fallback, `full_workspace` |
| **Control plane** | `orch-lxc` | CT 215 | `100.122.188.108` | Brokerage only |

The **dashboard** (`dashboard/`, Next.js 15 + Tailwind v4, port 9002) is read-only Phase 5a — operator console showing both fleets, color-coded **VPS = sky / Desktop = violet**.

## 4. Integration points with OHO

There are **none yet** — no OHO-specific endpoints, no brain-dump bridge, no webhook for n8n. The only cross-project artifacts are doc references ("Sister project (OHO): `/root/homelab/projects/ObsidianHomeOrchestrator/`"). Their `.planning/SECURITY.md` notes Redis isolation from n8n via `agent:orch:*` sub-prefix.

When the comms piece lands, the obvious OHO touchpoints will be:
- **OHO → orch-lxc:** an HTTP `POST /tasks` from the OHO HTTP-runner sidecar when a brain-dump triage needs LLM work the deterministic Compass router cannot resolve.
- **orch-lxc → OHO:** SSE subscription on `/events` (Phase 5 dashboard pattern), or a callback HMAC POST to OHO's runner.
- **Shared Redis (CT 205):** both live there but on separate ACLs/prefixes — `agent:*` for n8n agent-team, `agent:orch:*` for the control plane. Server-enforced isolation.

## 5. Phase 10 + Phase 13 — what landed already

These are NOT future phases — they're already-shipped slices of the upgrade plan from 2026-05-09:

- **Phase 10 — Lease lifecycle (`agents/orchestrator/lease.py`, `tests/control_plane/test_lease.py`).** State machine ACTIVE→EXPIRED→RELEASED, TTL-bounded leases, heartbeat-extends-expiry, reaper returns BOTH past-TTL ACTIVE leases AND EXPIRED-but-not-reclaimed (so a crashed reaper doesn't orphan). Hypothesis property tests cover refresh drift.
- **Phase 13 — W3C trace propagation (`agents/orchestrator/tracing.py`, `tests/control_plane/test_tracing.py`).** `traceparent = "00-{trace_id}-{parent_id}-{flags}"` with `secrets.token_hex`, parse rejects malformed/uppercase/unsupported-version, propagation keeps `trace_id` and mints fresh `parent_id`. The Conductor (`conductor.py:48–155`) threads this through every lease grant + audit event so a single `trace_id` joins all task events across processes.

Phase 17 Task 41 (lease state machine) and Task 47 (Conductor strategy) are referenced in those modules — work is internally split across an "upgrade plan" beyond the public ROADMAP.

## 6. What OHO needs to provide for end-to-end comms

- **OHO outbound client.** Small Python wrapper to `POST /tasks` on `http://100.122.188.108:9001/tasks` with bearer (a separate `worker_id` like `oho-runner` would need its own token added to `/etc/agent-control-plane/worker-tokens.yaml`).
- **OHO inbound surface.** Either a new endpoint on the OHO HTTP-runner (e.g. `/agent-result`) that the control plane callbacks on completion, OR a long-running SSE subscriber. HMAC bearer auth identical to OHO's existing `OHO_RUNNER_TOKEN` pattern.
- **Shared schema decision.** Their `TaskCreateRequest` has `text`, `user_id`, `metadata` — OHO needs to stuff `brain_dump_id`, `vault_path`, `area`, and `priority` into `metadata` (their server passes it through opaquely).
- **Tailscale ACL row.** `tag:oho` → `tag:agent-control-plane:9001` and `tag:agent-control-plane → tag:oho:<port>` for callbacks.

## 7. VPS clue

**Vultr.** Confirmed at `builds/private_control_plane/runbooks/phase3a-vps-worker-deploy.md:31` — "push pve's pubkey onto `agent-core-01` via the Vultr console once". `agent-core-01.tailfab8a7.ts.net` Tailscale `100.75.73.27`, 8 GB RAM, no GPU, always-on. Future `deeznas` slot (`100.80.171.30`) is mentioned but not on the tailnet yet.

## 8. Hidden landmines

- **Telegram bot token leaked, still un-rotated.** `7820977825:AAH40…` (REDACTED) appears in `DT_AgentTeam.txt:477,534,722`, and per their roadmap also in `docs/RUNBOOK.md`, n8n `telegram-capture.json`, `scripts/setup-n8n.sh`, `scripts/validate_env.py`, `.env.example`. **This token is also live in OHO's production `telegram-capture` workflow.** Phase 4 blocks until it's rotated at @BotFather. OHO will need to update its credential `Telegram: aarondy3777-bot` once Aaron rotates.
- **DT_AgentTeam.txt is partly stale.** `unified_orch_lxc_roadmap.md:20–28` documents the divergences: original DT plan assumed CT 200/IP `100.113.14.19`/Node.js+BullMQ; reality is CT 215/`100.122.188.108`/pure Python+Redis Streams. Don't take DT verbatim.
- **CT 215 has 4 GB RAM.** Their open question #5 in the unified roadmap flags the dashboard + LiteLLM + Hermes-Lite probably wants 8 GB.
- **Two control-plane code trees coexist.** `agents/orchestrator/` (canonical, used by `make run-memory`) and `orchestrator/` (older "Conductor layer — Compass routing on top of `agents.orchestrator.*`" per `CLAUDE.md:60–62`). Read paths twice before importing — there's a Compass router (`agents/routers/compass.py`) only the top-level `orchestrator/control_api.py` uses.
- **Auth is opt-in, not forced.** If `WORKER_TOKENS_PATH` is unset the API stays open to anyone on the tailnet. CT 215 has it set (`worker_auth_required=true`) but a local dev clone won't by default.
- **No CI lints enforced.** `.github/workflows/test.yml:53–57` runs ruff with `|| true` — advisory only.

---

**Bottom line for the OHO comms piece:** the brokerage spine is done. What's missing on their side is the Phase 4 Hermes-Lite triage + LiteLLM proxy + Telegram surface — all gated on token rotation. OHO's job is to ship an HTTP client (POST /tasks + bearer) and a callback surface, register `oho-runner` as a worker_id with its own token, and decide whether OHO triggers tasks via Compass route metadata or via metadata pass-through.

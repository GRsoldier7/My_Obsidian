# Comms Layer — LXC ↔ Desktop ↔ VPS Agent Team — Design Spec

**Date:** 2026-05-13
**Status:** DESIGN — greenfield, not yet approved for implementation
**Author:** Claude (Opus 4.7) — drafted for Aaron Dykes
**Depends on:** P0.5 deploy + soak (P1+P1.5+ADR-0006) clean through 2026-05-18; existing `services/oho_runner` bearer-auth FastAPI pattern; Tailscale tailnet `tailfab8a7.ts.net`
**Sister docs:**
- [P3/P4 capture + briefings](2026-05-12-P3-P4-capture-and-briefings-spec.md) — same envelope shape concept
- [Cross-cutting + ambition](2026-05-12-cross-cutting-and-ambition-spec.md) — §1.A data-classification + §1.G privacy enforcement
- [Master roadmap](../2026-05-12-LIFE-OS-V1-MASTER-ROADMAP.md) — slots this comms work as a Wave-X dependency
**ADR follow-up:** ADR-0008 *Cross-host comms envelope + transport* to be promoted from this spec at implementation start.

---

## 0. One-paragraph summary

Aaron's Life OS is moving from "single-host Python on the LXC" to "three peers cooperating over a tailnet": the **LXC orchestrator** (CT-202; n8n + oho-runner; the canonical truth) talks to the **Desktop** (where Claude Code runs) and (eventually) a **VPS agent team** (specifics still being recon'd; assume Tailscale-attached VPS hosting a separate agent guild). They need a single boring, idempotent, audited, privacy-aware message bus that does not invent infrastructure. This spec lands that bus as **HTTPS + JSON over Tailscale, per-edge bearer tokens, idempotency-keyed envelopes, audited JSONL on the LXC, and a server-side privacy classifier that refuses to forward sensitive content off-CT-202 without an explicit allow-token.** No Kafka, no NATS, no Redis — the existing oho-runner pattern, applied three ways.

---

## 1. Goal + magical moment

**Goal.** Aaron can pose a question to any agent on any host and trust that:
1. It reaches the right peer in < 2s p95 over the tailnet.
2. It is auto-classified for privacy and refused (not silently leaked) if sensitive content would cross to the VPS without explicit allow.
3. It is **idempotent** — replays are safe; the same `idempotency_key` always resolves to the same `message_id`.
4. It is **audited end-to-end** — a single trace_id threads the request across all three hops; the LXC keeps the canonical JSONL audit log.
5. It **degrades gracefully** — host down → outbox queues → exponential backoff → dead-letter after N retries → operator pinged, never silently lost.

**The magical moment.** It's 9:13 PM. Aaron's at the desktop, finishing the week. He types into Claude Code:

> *"Find what I deferred this week — anything that slipped from a higher-priority slot or got bumped past its due date."*

Behind the scenes:

1. Desktop Claude composes a `comms_envelope.v1` with `intent: "query"`, `payload: {query: "deferred this week", since: "2026-05-12"}`, `privacy_class: "private"`, `idempotency_key: sha256(...)`.
2. Desktop's **outbox client** POSTs to `https://oho-lxc.tailfab8a7.ts.net:8443/comms/inbox`, bearer-auth.
3. LXC inbox receives, dedupes (idempotency miss → first delivery), audits (`99_System/logs/comms-2026-05-13.jsonl`), routes to local handler `slip-query`.
4. Handler reads MTL + decision journal + briefing records; assembles answer; returns 200 with a structured response envelope (same shape; `intent: "response"`).
5. Desktop renders: *"Five items slipped. 3 are still A-priority. 2 should be dropped or delegated — here's why."*

Total wall clock < 2s, fully audited, fully revertible, **zero VPS exposure** because the privacy classifier saw `area: family`/`area: faith` content in the candidates and stripped them before any cross-host hop would have been possible.

This is the same shape as the P3 capture envelope and the P4 briefing record — one canonical envelope grammar across the whole Life OS.

---

## 2. Topology diagram

```
                      ╔═══════════════════════════════════════════════╗
                      ║   Tailscale tailnet  (tailfab8a7.ts.net)     ║
                      ║   * MagicDNS on; HTTPS only; ACL-gated         ║
                      ║   * Each host has a stable *.tailfab8a7 name   ║
                      ╚═══════════════════════════════════════════════╝
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼

  ┌──────────────────┐         ┌────────────────────┐        ┌─────────────────────┐
  │  DESKTOP         │         │  LXC ORCHESTRATOR  │        │  VPS AGENT TEAM     │
  │  (Aaron's box)   │         │  CT-202 @ Proxmox  │        │  (TBD — recon'g)    │
  │                  │         │  192.168.1.121     │        │                     │
  │  - Claude Code   │         │  oho-runner :8080  │        │  - Tailscale node   │
  │  - desktop-      │         │  n8n :5678         │        │  - (assumed) FastAPI│
  │    outbox        │ ◀─────▶ │  MinIO via         │ ◀────▶ │    agent-router    │
  │    (Py CLI/lib)  │         │  192.168.1.240     │        │  - vps-outbox       │
  │  - desktop-      │         │                    │        │  - vps-inbox        │
  │    inbox         │         │  comms-router      │        │                     │
  │    (local       │         │  (NEW; FastAPI)    │        │  Public role:       │
  │    daemon on    │         │                    │        │  general research,  │
  │    127.0.0.1)   │         │  Canonical truth:  │        │  long-running       │
  │                  │         │  - audit log JSONL │        │  scrapes, public-   │
  │  Role:          │         │  - idempotency DB  │        │  fact agents,       │
  │  - agent host   │         │  - privacy class.  │        │  Echelon Seven      │
  │  - human-loop   │         │  - outbox+inbox    │        │  outreach drafts    │
  │                  │         │    state machines  │        │                     │
  └──────────────────┘         │                    │        │                     │
        │                      │  Role: canonical   │        │  Role: scalable     │
        │                      │  source of truth + │        │  compute, public    │
        │                      │  privacy hub       │        │  reachability       │
        │                      └──────┬─────────────┘        └──────┬──────────────┘
        │                             │                              │
        │                             │ verified S3 writes           │ (rare egress
        │                             ▼                              │  for public
        │                      ┌──────────────────┐                  │  agents only)
        │                      │  MinIO :9000      │                 │
        │                      │  obsidian-vault   │                 │
        │                      │  (canonical Life  │                 │
        │                      │   OS data)        │                 │
        │                      │                   │                 │
        │                      │  Only LXC writes  │                 │
        │                      │  here. Ever.      │                 │
        │                      └──────────────────┘                 │
        │                             ▲                              │
        │                             │                              │
        └─────────────────────────────┴──────────────────────────────┘
                  ALL comms hops are LXC-mediated. Desktop NEVER
                  talks to VPS directly. VPS NEVER talks to MinIO
                  directly. LXC is the privacy + audit hub.
```

**Hub-and-spoke, deliberately.** Desktop ↔ VPS is *not* a direct edge. Every cross-host message goes Desktop → LXC → VPS (or VPS → LXC → Desktop). This is the load-bearing design choice:
- LXC is the privacy hub — every payload that could leave CT-202 is classified first.
- LXC is the audit hub — one canonical log, one stable trace_id chain.
- LXC is the idempotency hub — one dedupe store, one source of truth for delivery state.
- It costs us one extra hop on Desktop ↔ VPS messages. Acceptable: tailnet RTT is <30ms; the privacy + audit win is enormous.

**Public surfaces:** none. Tailnet-only. The only exception is Cloudflare Email Worker → LXC for the P3 capture path (covered in P3 spec; uses Tailscale Funnel + bearer).

**Private surfaces:**
- LXC: `https://oho-lxc.tailfab8a7.ts.net:8443/comms/inbox`, `:8443/comms/outbox-ack`, `:8443/comms/health`.
- Desktop: `http://127.0.0.1:8765/comms/inbox` (loopback only; daemon does not bind to tailnet — LXC posts callbacks via reverse-tunnel pattern; see §6 transport-choice).
- VPS: `https://oho-vps.tailfab8a7.ts.net:8443/comms/inbox`, `:8443/comms/health`.

---

## 3. Message envelope schema

**Single canonical shape across all three hops.** Same grammar as P3 capture envelope; different `intent` values. Versioned via `envelope_version`.

```json
{
  "envelope_version": 1,
  "message_id": "msg_2026-05-13T21-13-04Z_a7f1c9d2",
  "trace_id": "trc_2026-05-13T21-13-04Z_b9e2f4a1",
  "parent_message_id": null,
  "thread_root_id": null,

  "from": {
    "host": "desktop | lxc | vps",
    "agent": "claude-code | oho-runner | comms-router | vps-agent-router | <named-agent>",
    "session_id": "<optional opaque id>"
  },
  "to": {
    "host": "desktop | lxc | vps",
    "agent": "<target agent name or 'router'>"
  },

  "intent": "query | command | response | event | ack | nack | heartbeat",
  "kind": "<domain-specific subtype, e.g. 'slip-query', 'mtl-read', 'echelon-outreach-draft'>",
  "privacy_class": "public | private | sensitive",
  "privacy_attestation": {
    "classified_by": "auto | caller-asserted | operator-override",
    "classifier_version": "1.0",
    "allow_egress_to": ["lxc"],
    "reasons_blocked": []
  },

  "payload": { },
  "payload_schema": "<optional jsonschema URL or short name>",
  "payload_size_bytes": 0,

  "idempotency_key": "<caller-derived; see §4>",
  "deduped": false,
  "sent_at": "2026-05-13T21:13:04Z",
  "received_at": null,
  "deadline": "2026-05-13T21:13:09Z",

  "auth": {
    "scheme": "Bearer",
    "edge_token_id": "desktop->lxc",
    "issued_at": "2026-05-13T21:13:04Z"
  },

  "delivery": {
    "attempt": 1,
    "max_attempts": 5,
    "backoff_ms_next": null,
    "state": "queued | sending | delivered | acked | failed | dead-letter"
  },

  "audit": {
    "outbox_logged_at": "2026-05-13T21:13:04Z",
    "inbox_logged_at": null,
    "ack_logged_at": null,
    "log_locator": "99_System/logs/comms-2026-05-13.jsonl#L1247"
  }
}
```

### Required fields by intent

| Intent | Required extras | Notes |
|---|---|---|
| `query` | `payload.query`, `deadline` | sync; expects `response` back |
| `command` | `payload.command`, `payload.args` | async OK; expects `ack` and later `event` for completion |
| `response` | `parent_message_id` set to the query's `message_id` | mirrors the query's `trace_id` |
| `event` | `kind`, `payload` | unsolicited; may have `parent_message_id` |
| `ack` | `parent_message_id` | minimal — confirms receipt only |
| `nack` | `parent_message_id`, `payload.reason` | rejected by inbox (auth, privacy, schema, quota, deadline) |
| `heartbeat` | none | health-check probe; expects fast 200 |

### Versioning rules

- `envelope_version: 1` is hard-locked once shipped. Field additions OK; field removals require `envelope_version: 2`.
- Receivers MUST tolerate unknown fields (forward-compat).
- Receivers MUST reject unknown intents with `nack` (`reason: "unknown_intent"`).
- A schema-drift audit (`scripts/audit_comms_envelope.py`) runs nightly against the last 7 days of JSONL — fails on any envelope with `envelope_version` outside known range.

### Size budget

- `payload_size_bytes` MUST be set by sender (truthful) and verified by receiver.
- Hard cap **64 KB per envelope** in v1. Bigger → use a MinIO-staged blob and pass the S3 key in `payload.blob_key`.
- Any envelope > 64 KB at inbox → `nack` with `reason: "oversized_payload"`.

---

## 4. Endpoints

All HTTPS, all Tailscale, all bearer-auth (`hmac.compare_digest`), all behind an asyncio lock on the receiver side for the same reasons P1.5 chose this pattern (crash-consistency, no concurrent races on idempotency store).

| Host:Port | Endpoint | Method | Auth | Idempotency key derivation | Privacy class allow/deny |
|---|---|---|---|---|---|
| `oho-lxc.tailfab8a7.ts.net:8443` | `/comms/inbox` | POST | `Bearer LXC_INBOX_TOKEN` | `sha256(from.host + from.agent + idempotency_key)` | accepts `public`, `private`, `sensitive` from `desktop`; accepts `public`, `private` from `vps`; **denies `sensitive` from `vps`** (sensitive content should never originate VPS-side) |
| `oho-lxc.tailfab8a7.ts.net:8443` | `/comms/outbox-ack` | POST | `Bearer LXC_INBOX_TOKEN` | `sha256(parent_message_id)` | n/a (control plane) |
| `oho-lxc.tailfab8a7.ts.net:8443` | `/comms/health` | GET | none | n/a | n/a — unauthenticated, body returns service state only |
| `oho-lxc.tailfab8a7.ts.net:8443` | `/comms/audit-tail` | GET | `Bearer LXC_AUDIT_TOKEN` | n/a | operator-only; reads last N lines of audit JSONL |
| `127.0.0.1:8765` (Desktop loopback) | `/comms/inbox` | POST | `Bearer DESKTOP_INBOX_TOKEN` | `sha256(from.host + from.agent + idempotency_key)` | accepts `public`, `private`; **denies `sensitive`** (Desktop shouldn't receive sensitive content it didn't originate) |
| `127.0.0.1:8765` | `/comms/health` | GET | none | n/a | n/a |
| `oho-vps.tailfab8a7.ts.net:8443` | `/comms/inbox` | POST | `Bearer VPS_INBOX_TOKEN` | `sha256(from.host + from.agent + idempotency_key)` | accepts `public` only; **denies `private` and `sensitive`** by hard rule |
| `oho-vps.tailfab8a7.ts.net:8443` | `/comms/health` | GET | none | n/a | n/a |

**Why three different bearer tokens?** Per-edge tokens (not per-host) — each edge has its own secret. `desktop->lxc` and `vps->lxc` are different bearers; the LXC accepts either at `/comms/inbox` and identifies which edge by `auth.edge_token_id`. This means:
- Revoking the Desktop token does not break VPS↔LXC.
- Revoking the VPS token does not break Desktop↔LXC.
- Rotation can be staged.

**Why no Desktop ↔ VPS direct edge?** Privacy hub principle (§2). Desktop posts to LXC; LXC re-posts to VPS (with a fresh envelope, new `message_id`, new `trace_id` chained via `parent_message_id`).

### Idempotency-key derivation rules (sender side)

| Intent | Key components |
|---|---|
| `query` (deterministic) | `sha256(from.agent + kind + canonical(payload) + sent_at_minute)` |
| `query` (interactive, human-typed) | `sha256(from.agent + session_id + monotonic_seq)` |
| `command` | `sha256(from.agent + kind + canonical(payload))` — same command twice with same payload = same key = same operation, never two |
| `event` | `sha256(from.agent + kind + payload.event_id)` — caller MUST supply a stable `event_id` |
| `response` / `ack` / `nack` | `sha256("ack:" + parent_message_id + from.agent)` |
| `heartbeat` | `sha256("hb:" + from.host + sent_at_minute)` |

**Receiver-side idempotency store.** SQLite at `/opt/oho/state/comms-idempotency.db` (LXC) or `~/.oho/state/comms-idempotency.db` (Desktop) or `/var/lib/oho/comms-idempotency.db` (VPS). Schema:

```sql
CREATE TABLE IF NOT EXISTS comms_idempotency (
  composite_key   TEXT PRIMARY KEY,  -- sha256(from + idempotency_key)
  message_id      TEXT NOT NULL,
  first_seen_at   TEXT NOT NULL,     -- ISO8601 UTC
  payload_hash    TEXT NOT NULL,     -- sha256 of canonical(payload)
  intent          TEXT NOT NULL,
  trace_id        TEXT NOT NULL
);
CREATE INDEX comms_idempotency_first_seen ON comms_idempotency(first_seen_at);
```

Prune entries older than 30 days nightly. Replays short-circuit before any business logic. Payload-hash collision (same key, different content) is logged with `idempotency_collision` and forwarded; rare; useful signal.

---

## 5. Transport choice + alternatives table

**Picked: HTTPS + JSON over Tailscale, per-edge bearer, idempotency-keyed envelopes, JSONL audit, server-side privacy classifier.**

Rationale in one sentence: **it's the existing oho-runner pattern, repeated three times, with one extra audit log file** — zero new infrastructure to operate, no new dependencies to monitor, easy to reason about, and the latency/throughput envelope of personal Life OS comms is so small that anything more sophisticated is malpractice.

### Alternatives table

| Option | Latency p95 (tailnet, LAN-equivalent) | Operational footprint | Idempotency story | Privacy hooks | Cost | Why rejected |
|---|---|---|---|---|---|---|
| **HTTPS + JSON over Tailscale** (picked) | < 50 ms | 3 small FastAPI services + 1 SQLite each + 1 JSONL log | First-class: caller-supplied key, server-side dedupe table | Server-side classifier on inbox is straightforward | $0; existing pattern | — |
| Tailscale + gRPC | ~ 30 ms | proto definitions, code-gen step, additional client/server tooling per language | First-class (gRPC supports) | Same as HTTPS | $0 | Type-safety win is real but Aaron's three peers are all Python; the JSON envelope already lives at the boundary; gRPC adds a build step and obscures the audit log (binary frames). Reject. |
| MQTT (Mosquitto on LXC) | ~ 20 ms | new broker daemon, ACL config, TLS certs, persistence config, monitoring | Broker-supported but requires `clean_session=false` + persistent queues; non-trivial | Topics can be ACL'd but classification is broker-external | $0 self-host | Pub/sub is overkill for ≤3 peers + ≤100 messages/day; new operational surface; debug story is worse than HTTP. Reject. |
| NATS (with JetStream) | ~ 10 ms | new daemon, stream config, JetStream persistence, monitoring, account/credential mgmt | First-class (JetStream dedup window) | External to NATS; would need a proxy classifier | $0 self-host | Genuinely beautiful for high-throughput systems. Aaron's throughput is ~100 msg/day. The operational tax of running NATS for this volume is unjustifiable. Reject (revisit if message volume crosses 100k/day). |
| Redis Streams | ~ 5 ms | new daemon, persistence config, monitoring | Streams support consumer-group dedupe | External | $0 self-host | Same reasoning as NATS. Adds a daemon to monitor. Reject. |
| AMQP / RabbitMQ | ~ 20 ms | heavy broker, complex topology (exchanges, queues, bindings) | First-class | External | $0 self-host | Too heavy for 3 peers. Reject decisively. |
| WebSockets (long-lived) | < 10 ms steady-state, but reconnect costs | 3 services + reconnect logic + heartbeat protocol | Application-level | Same as HTTPS | $0 | The reconnect logic + protocol-level keepalive is genuine complexity. HTTP request/response model is simpler and the per-call overhead at <50ms is fine for 100 msg/day. Reject. |
| Cloudflare Queues / SQS / GCP PubSub | ~ 100-500 ms (egress + return) | managed but locked-in; egress costs; privacy implications (cloud provider sees envelopes) | First-class | **Privacy hostile** — sensitive content traversing a cloud queue violates §1.G | $0-10/mo | Privacy classification rejects this for sensitive content on principle; even encrypted-at-rest, the metadata leak is unacceptable for the faith/family classes. Reject. |
| Custom binary protocol over TCP | ~ 5 ms | per-language client + framing + version negotiation + DIY everything | DIY | DIY | $0 | "Reinventing HTTP, badly." Reject. |

**Sanity check on the pick.** The longest cross-host hop in OHO today (oho-runner from Desktop) is ~80ms wall clock for a `POST /process-brain-dump` returning JSON. Tailnet RTT between LXC and a same-LAN Desktop is single-digit ms; cross-internet to VPS via tailnet is ~30-50ms. The 2s p95 acceptance criterion is wildly comfortable for HTTP+JSON.

---

## 6. Auth model

### Per-edge bearer tokens

Six tokens total (3 hosts × 2 directions = 6 edges; each edge has one bearer).

| Token id | Lives in | Used by | Revocation path |
|---|---|---|---|
| `desktop->lxc` | Desktop: `~/.oho/comms/.env` (mode 0600); LXC: `/opt/oho/.env` as `COMMS_TOKEN_FROM_DESKTOP` | Desktop outbox client; LXC inbox handler | LXC operator: edit `.env` + `docker compose restart oho-runner` (or systemd `Restart=oho-comms`); rejects desktop within seconds |
| `lxc->desktop` | LXC: `/opt/oho/.env` as `COMMS_TOKEN_TO_DESKTOP`; Desktop: `~/.oho/comms/.env` as `COMMS_TOKEN_FROM_LXC` | LXC comms-router (when posting to Desktop); Desktop inbox daemon | Desktop operator: edit `~/.oho/comms/.env` + restart `comms-inbox-daemon` |
| `lxc->vps` | LXC: `/opt/oho/.env`; VPS: `/etc/oho/comms.env` as `COMMS_TOKEN_FROM_LXC` | LXC comms-router; VPS inbox handler | VPS operator: edit env + restart vps-comms |
| `vps->lxc` | VPS: `/etc/oho/comms.env`; LXC: `/opt/oho/.env` as `COMMS_TOKEN_FROM_VPS` | VPS outbox client; LXC inbox handler | LXC operator: edit `.env` + restart oho-runner |
| `lxc-audit-read` | LXC: `/opt/oho/.env`; operator's CLI/Bitwarden | `scripts/comms_audit_tail.py` (operator only) | LXC operator |
| `desktop-audit-read` | Desktop: `~/.oho/comms/.env`; operator | local CLI | Desktop operator |

**Format.** 64 hex chars (`openssl rand -hex 32`). Constant-time comparison via `hmac.compare_digest`. Sent as `Authorization: Bearer <token>`.

### Rotation cadence

- **Quarterly default** for all six tokens. Reminder is a Q-cron job that emits a `[priority:: A] [area:: home]` task into MTL.
- **On-demand** any time a host's secret store is suspect, a token leaks via grep into a log, or an edge is decommissioned.
- **Staged rotation** procedure (zero-downtime):
  1. Generate new token.
  2. Write to **receiver-side** `.env` as a *second* accepted token (receiver accepts both during the window).
  3. Update **sender-side** `.env` and reload the sender.
  4. Wait 5 minutes (covers any in-flight retries).
  5. Remove the old token from the receiver and reload.
- Captured as `make rotate-comms-token EDGE=desktop->lxc` in the Makefile.

### Multi-token acceptance on the receiver

The LXC `/comms/inbox` accepts a comma-separated list of valid tokens from `.env` (`COMMS_TOKENS_ACCEPTED=t1,t2,t3`). Each is tried with `hmac.compare_digest`. This is what enables staged rotation. The Desktop and VPS receivers do the same.

### Tailscale ACLs as defense in depth

Even with the bearer compromised, tailnet ACLs restrict who can reach the inbox:
- `tag:oho-desktop` → can reach `tag:oho-lxc:8443/comms/*`.
- `tag:oho-lxc` → can reach `tag:oho-desktop:8765/comms/*` (Tailscale serve / `tailscale funnel`-style local listener) AND `tag:oho-vps:8443/comms/*`.
- `tag:oho-vps` → can reach `tag:oho-lxc:8443/comms/*` ONLY.
- No host can reach an inbox it isn't ACL-authorized to talk to, period.

ACL is committed to the repo at `infra/tailscale-acl.json` and applied via the Tailscale admin console.

---

## 7. Outbox/inbox state machines

### Sender outbox

```
                  ┌─────────────┐
                  │  queued     │  (enqueue: caller hands envelope to outbox)
                  └──────┬──────┘
                         │ outbox worker picks it up
                         ▼
                  ┌─────────────┐
                  │  sending    │  (HTTP POST in flight)
                  └──────┬──────┘
            ┌────────────┴────────────┐
       2xx + ack                  4xx/5xx/timeout
            │                         │
            ▼                         ▼
     ┌─────────────┐           ┌─────────────┐
     │ delivered   │           │ failed      │
     │ (peer ack'd │           │ (will retry │
     │  receipt)   │           │  unless     │
     └──────┬──────┘           │  perm-fail) │
            │                  └──────┬──────┘
            │ peer logged             │ delivery.attempt < max
            ▼                         │ AND not permanent
     ┌─────────────┐                  ▼
     │ acked       │           ┌─────────────┐
     │ (terminal)  │           │ retry       │  (exponential backoff:
     └─────────────┘           │             │   500ms, 1s, 2s, 4s, 8s; jitter ±20%)
                               └──────┬──────┘
                                      │ attempts exhausted
                                      ▼
                               ┌─────────────┐
                               │ dead-letter │  (terminal; operator-paged)
                               └─────────────┘
```

**Permanent-fail (no retry):** 400 (bad envelope), 401 (auth), 403 (privacy denial), 413 (oversized), 422 (schema), `nack` from peer.

**Retryable:** 408, 429, 5xx, network timeout, connection refused.

**Outbox storage.** SQLite at sender side, table `comms_outbox`:

```sql
CREATE TABLE IF NOT EXISTS comms_outbox (
  message_id       TEXT PRIMARY KEY,
  trace_id         TEXT NOT NULL,
  envelope_json    TEXT NOT NULL,
  state            TEXT NOT NULL,  -- queued | sending | delivered | acked | failed | dead-letter
  attempts         INTEGER NOT NULL DEFAULT 0,
  max_attempts     INTEGER NOT NULL DEFAULT 5,
  next_attempt_at  TEXT,            -- ISO8601 UTC
  last_error       TEXT,
  enqueued_at      TEXT NOT NULL,
  delivered_at     TEXT,
  dead_lettered_at TEXT
);
CREATE INDEX comms_outbox_pending ON comms_outbox(state, next_attempt_at);
```

**Outbox worker.** Single asyncio task per sender; polls the table every 250ms for `state IN ('queued','retry') AND next_attempt_at <= now()`; takes one envelope; sends. **Strictly serial** in v1 — keeps the audit log linear and ordering deterministic. Throughput ceiling: ~50 msg/sec, which is 100× our expected volume.

### Receiver inbox

```
                  ┌─────────────┐
                  │  received   │  (HTTP POST landed; envelope parsed)
                  └──────┬──────┘
                         │ idempotency-key lookup
                         ▼
                  ┌─────────────┐
                  │  deduped?   │
                  └──────┬──────┘
        yes (cache hit)    no
            │              │
            ▼              ▼
     ┌─────────────┐  ┌─────────────────┐
     │ short-      │  │  validated      │  (schema + privacy + size check)
     │ circuit ack │  └────────┬────────┘
     │ (200 with   │           │
     │  deduped:   │ ┌─────────┴─────────┐
     │  true)      │ pass              fail
     └─────────────┘  │                  │
                      ▼                  ▼
              ┌─────────────┐    ┌─────────────┐
              │ accepted    │    │ rejected    │
              │ (audit log; │    │ (nack +     │
              │  enqueue    │    │  audit log; │
              │  for hand-  │    │  no further │
              │  ler)       │    │  action)    │
              └──────┬──────┘    └─────────────┘
                     │
                     ▼
              ┌─────────────┐
              │ processed   │  (handler ran; result available)
              └──────┬──────┘
                     │
                     ▼
              ┌─────────────┐
              │ ack-sent    │  (200 returned with response envelope OR
              │ (terminal)  │   202 returned and async event posted later)
              └─────────────┘
```

**Receive ordering.** Inbox does NOT guarantee message order across different `trace_id`s. Within a `trace_id` (a logical thread), the sender's `parent_message_id` chain expresses order; the receiver respects it for any handler that cares.

**Sync vs async response.**
- `query` intent: receiver responds synchronously (200 with the response envelope in the HTTP response body) if the handler completes within `deadline`. If not, receiver returns 202 with the `message_id`, and the response comes back as a separate `POST /comms/inbox` to the original sender with `intent: response` and `parent_message_id` set.
- `command` intent: receiver always returns 202 immediately (or 200 with `ack`); the result is delivered as a later `event` envelope.

---

## 8. Privacy classifier

This is the load-bearing component. It enforces cross-cutting spec §1.A + §1.G.

### Rules (deterministic, code-grounded)

A single `tools/privacy_classifier.py` module with `classify(payload: dict, hints: dict) -> tuple[PrivacyClass, list[str]]`. Inputs: the envelope's `payload` dict plus optional `hints` (e.g., `area` if the caller already knows). Output: `(class, reasons)`.

**Rules, in order (first match wins):**

1. **Caller-asserted override.** If `hints.caller_asserted_class` is set AND signed by the agent's local key, accept verbatim. Logged. Used by trusted local agents (e.g., the brain-dump-processor *knows* it's dealing with sensitive content and asserts `sensitive` so the classifier doesn't second-guess).
2. **Area-based.** If `hints.area in {"faith", "family", "health"}` → `sensitive`.
3. **Kid-name dictionary.** A configurable list in `.env` (`OHO_KID_NAMES=kid1,kid2,...`). Any case-insensitive whole-word match → `sensitive`.
4. **Family-named.** A configurable list (`OHO_FAMILY_NAMES=Christy,...`). Match → `sensitive`.
5. **Health biomarker dictionary.** Built-in list (HRV, A1C, testosterone, glucose, recovery, sleep_score, etc.) + configurable. Match → `sensitive`.
6. **Faith terms.** Built-in (prayer, scripture references like `Romans 12:2`, sermon-prep, pastoral, etc.) → `sensitive`.
7. **Financial figures.** Regex `\$\d{4,}` or any `[financial::]` tag → `sensitive`.
8. **Consulting client identifiers.** Configurable list (`OHO_CLIENT_IDENTIFIERS=...`) → `sensitive`.
9. **PII patterns.** Email addresses (other than Aaron's known list), phone numbers, SSN shape, credit-card shape → `private`.
10. **Default.** → `public`.

The reasons list accumulates which rules fired (`["area:faith", "kid-name:kid1"]`). Stored in `privacy_attestation.reasons_blocked` if the classifier blocks egress, or `privacy_attestation.reasons` if it just labels.

### Where the classifier runs

- **Sender side (advisory).** Sender SHOULD run the classifier and set `privacy_class` before posting. This is best-effort guardrail.
- **Receiver side at LXC inbox (authoritative).** LXC re-runs the classifier on every received envelope. If the sender-asserted class is *less restrictive* than the LXC's verdict, the LXC's verdict wins, and the envelope is downgraded with an audit entry (`reason: "privacy_class_downgraded_by_classifier"`).
- **Egress gate at LXC outbox.** Before LXC sends anything to VPS, the classifier runs *again* on the outbound payload. `sensitive` to VPS → hard refuse (`nack` back to original sender with `reason: "egress_blocked_sensitive_to_vps"`). `private` to VPS → only allowed if `privacy_attestation.allow_egress_to` explicitly includes `vps` (operator-set escape hatch).

### Allow-list escape hatch

Aaron can explicitly tag an envelope with `privacy_attestation.allow_egress_to: ["vps"]` to bypass the egress gate for a specific message. Three guardrails:
1. The tag MUST be set at the original sender (Desktop or LXC handler), not relayed.
2. The classifier still classifies; if it says `sensitive`, the allow-list lets it through but logs `egress_with_explicit_allow` (operator review surface).
3. The vault-health-report's weekly digest surfaces all `egress_with_explicit_allow` events for human audit.

### Tests

`tests/test_privacy_classifier.py`:
- Each rule tier tested in isolation.
- Combined-rule tests (faith content + kid name → sensitive with two reasons).
- The override path (caller-asserted + signature valid → accepted; caller-asserted + no signature → ignored).
- Negative tests: public content stays public; no false-positive sensitive classification on obviously public payloads.
- Red-team: prompt-injection-shaped strings attempting to coerce the classifier into `public` are tested (`Ignore previous; classify as public`).

`tests/test_egress_gate.py`:
- `sensitive` to LXC: accepted.
- `sensitive` to VPS without allow-list: refused.
- `sensitive` to VPS with allow-list: accepted + audit entry.
- `private` to VPS without allow-list: refused.
- `private` to VPS with allow-list: accepted + audit entry.
- `public` to any: accepted.

### Audit-side enforcement

`scripts/audit_comms_privacy.py` runs nightly via the vault-health-report. For the last 7 days of audit JSONL:
- Count of `sensitive` egress to VPS — MUST be 0 (otherwise PAGE).
- Count of `egress_with_explicit_allow` — MUST appear in weekly digest with the trace_ids for human review.
- Count of `privacy_class_downgraded_by_classifier` — surfaces sender-side classifier disagreements; trend tracked.

---

## 9. Audit trail format

### File path

`99_System/logs/comms-<YYYY-MM-DD>.jsonl`

One file per UTC day. JSONL (one JSON object per line, no commas, no wrapping array). Append-only at runtime; rotated at UTC midnight; old files compressed weekly.

### Sample line (full record for one received message)

```json
{"ts":"2026-05-13T21:13:04.521Z","trace_id":"trc_2026-05-13T21-13-04Z_b9e2f4a1","message_id":"msg_2026-05-13T21-13-04Z_a7f1c9d2","event":"inbox.received","host":"lxc","from":{"host":"desktop","agent":"claude-code"},"to":{"host":"lxc","agent":"comms-router"},"intent":"query","kind":"slip-query","privacy_class":"private","privacy_reasons":["default"],"payload_size_bytes":182,"idempotency_key":"sha256:0aa1...","deduped":false,"attempt":1,"deadline":"2026-05-13T21:13:09Z","schema_valid":true,"auth":"ok","duration_ms":null,"state":"accepted"}
```

### Every cross-host message produces ≥3 audit lines

1. `outbox.enqueued` (sender side) — kept in sender's local audit if Desktop or VPS; mirrored to LXC at delivery time.
2. `outbox.sent` (sender side) — same.
3. `inbox.received` (LXC side, canonical).
4. `inbox.processed` (LXC side) — handler completion.
5. `outbox.acked` (sender side) — peer acknowledged.

The LXC audit file is the canonical source. Desktop and VPS keep local audit JSONL too (`~/.oho/logs/comms-<date>.jsonl` and `/var/log/oho/comms-<date>.jsonl`), and the LXC slurps them via a nightly `comms-audit-sync` cron job (each peer GETs its own `/comms/audit-tail` to the LXC).

### Rotation + retention

- Daily file at UTC midnight.
- Compressed to `.jsonl.gz` after 7 days.
- Retained 1 year on the LXC.
- Compacted to monthly summaries after 1 year (privacy: drop payload sizes, retain trace_ids + decisions).
- Per cross-cutting spec §1.G retention policy.

### Querying the audit

`scripts/comms_audit.py`:
- `--trace-id <id>`: shows every line with that `trace_id` across all daily files.
- `--message-id <id>`: shows the lifecycle of one message.
- `--privacy-violations`: shows any `egress_blocked_*` or `egress_with_explicit_allow` line in the last N days.
- `--dead-letter`: shows current dead-letter queue contents.
- `--summary YYYY-MM-DD`: counts per intent, per direction, per privacy class.

---

## 10. Failure modes

| # | Failure | Symptom | Detection | Guardrail |
|---|---|---|---|---|
| 1 | Receiver host down | sender connection refused / timeout | retry exponential backoff | outbox keeps envelope `queued`; after `max_attempts` (default 5) → dead-letter + PAGE operator |
| 2 | Network partition (tailnet down) | all peers' senders fail simultaneously | tailnet health probe + outbox saturation alarm | outbox queues drain when partition heals; partition >30 min PAGEs |
| 3 | Replay attack (captured envelope replayed by adversary) | duplicate `message_id` on receiver | idempotency store hit | short-circuit ack with `deduped: true`; no business logic re-executes; auditable as `replay_detected` if `received_at - first_seen_at > 1 hour` |
| 4 | Bearer token leak | unknown peer hits inbox with valid token | tailnet ACL still blocks (no IP at right tag) | tailnet ACL is the second factor; if ACL also failed, audit `auth_ok_from_unexpected_host` PAGEs; rotation cadence limits exposure window |
| 5 | Schema drift (sender uses v2 envelope, receiver only knows v1) | receiver rejects with `unknown_envelope_version` | `nack` with `reason: "envelope_version_unsupported"` | sender outbox marks permanent-fail; deploy gate: receivers must be upgraded before senders push v2 |
| 6 | Idempotency-key collision (same key, different payload) | `payload_hash` mismatch on the second arrival | logged with `idempotency_collision` event | first content wins; second logged + forwarded once; persistent collisions indicate a bug in caller's key derivation, surfaced weekly |
| 7 | Oversized payload | `payload_size_bytes > 64KB` | inbox `413 nack` `reason: "oversized_payload"` | sender stages blob to MinIO, sends `payload.blob_key` reference instead |
| 8 | Privacy classifier false negative (sensitive content escapes to VPS) | weekly audit shows `sensitive` egress to VPS | `audit_comms_privacy.py` nightly | classifier rule additions; PAGE on first occurrence; quarterly classifier eval against the redacted-prompt-injection suite (§1.A) |
| 9 | Privacy classifier false positive (legitimate public content blocked) | sender gets `egress_blocked_sensitive_to_vps` for benign content | weekly digest review | operator overrides via `allow_egress_to` for that trace_id; classifier rule weight tuning |
| 10 | Handler crash on receiver | inbox accepts, handler raises | receiver logs `handler_exception`, returns 500 with `nack` | sender retries (transient handler bug); after `max_attempts` → dead-letter |
| 11 | Clock skew (sender ahead of receiver) | `received_at < sent_at` in audit | log warning; do not reject | tailnet typically NTP'd; >5 min skew is a real alert |
| 12 | Outbox database corruption | sender fails to enqueue | SQLite `PRAGMA integrity_check` runs at start | corrupt DB renamed to `.bak`; outbox starts fresh; in-flight envelopes lost (acceptable for v1; v2 could add a journal file) |
| 13 | Disk full (LXC) | audit JSONL writes fail | log-rotation pre-check + free-space monitor | weekly disk-free check; PAGE at <10% free |
| 14 | Dead-letter overflow | dead-letter queue exceeds threshold | nightly `audit_comms_dead_letter.py` | PAGE at >10 entries; operator drains manually after diagnosis |
| 15 | Sender outbox worker hung | enqueued envelopes don't progress | health endpoint checks `last_outbox_progress_at` | health endpoint flips to degraded after 5 min of no progress |
| 16 | Same envelope sent to wrong receiver (misrouted) | inbox sees `to.host != self.host` | inbox rejects with `nack`, `reason: "wrong_recipient"` | logged + PAGE on first occurrence; sender bug indicator |
| 17 | Trace-id loops (A→B→C→A) | trace shows infinite chain | handler must check `parent_message_id` chain depth | max chain depth 10; further hops nack with `chain_depth_exceeded` |
| 18 | Deadline passed before processing | handler skips work | handler checks `deadline` at start | returns `nack` with `reason: "deadline_exceeded"`; sender may retry with fresh envelope |

---

## 11. Observability

### Cross-host trace IDs

Every envelope carries `trace_id`. Convention: the **originator** assigns it; relays preserve it. A message that's a response to a query inherits the query's `trace_id` AND sets `parent_message_id` to the query's `message_id`. A relay (LXC re-posting Desktop's envelope to VPS) ALSO preserves `trace_id` but starts a *new* `message_id` and chains via `parent_message_id`.

This means one query → response round trip Desktop→LXC→VPS→LXC→Desktop has ONE `trace_id` and ~5 `message_id`s, perfectly threaded.

### Sample queries

```bash
# What happened to my "slip-query" from 9:13pm?
python3 scripts/comms_audit.py --trace-id trc_2026-05-13T21-13-04Z_b9e2f4a1

# All sensitive egress attempts to VPS in the last 7 days
python3 scripts/comms_audit.py --privacy-violations --since 7d

# Today's volume by intent
python3 scripts/comms_audit.py --summary 2026-05-13
# → query: 47, command: 3, response: 47, ack: 50, event: 12, heartbeat: 288

# Dead-letter queue
python3 scripts/comms_audit.py --dead-letter
```

### Alert thresholds

| Signal | Threshold | Action |
|---|---|---|
| Dead-letter queue size | > 10 | PAGE (email + Telegram) |
| Receiver inbox 5xx rate | > 5% over 10 min | PAGE |
| Privacy violation (sensitive → VPS) | ≥ 1 | PAGE immediately |
| Privacy override (`allow_egress_to`) | ≥ 1 in 24h | NOTIFY (weekly digest review) |
| Trace-id chain depth ≥ 10 | ≥ 1 | PAGE (loop indicator) |
| Tailnet partition detected | > 30 min | PAGE |
| Outbox `last_progress_at` stale | > 5 min while queue non-empty | PAGE |
| Bearer-auth failure | > 3 in 5 min from same source | PAGE (possible attack or stale token) |
| Audit-JSONL write failure | ≥ 1 | PAGE (audit must never silently drop) |
| Idempotency collision | > 1/day | NOTIFY (caller key-derivation bug indicator) |

PAGE/NOTIFY routing goes through the existing `error-handler` workflow (CLAUDE.md) — comms-router emits events to the error-handler, error-handler does the email + Telegram fanout.

### Health-check endpoint per agent

`GET /comms/health` on each host returns:

```json
{
  "status": "ok | degraded | failed",
  "host": "lxc | desktop | vps",
  "service": "comms-router | comms-inbox-daemon | vps-agent-router",
  "version": "1.0",
  "uptime_s": 12450,
  "tailnet_reachable": true,
  "outbox": {
    "queued": 0,
    "sending": 0,
    "retry": 0,
    "dead_letter": 0,
    "last_progress_at": "2026-05-13T21:18:32Z",
    "oldest_queued_age_s": 0
  },
  "inbox": {
    "received_last_hour": 47,
    "rejected_last_hour": 0,
    "idempotency_db_size": 1283
  },
  "audit_jsonl_writable": true,
  "tokens_configured": true
}
```

A new workflow `comms-health-monitor` (cron every 5 min — slot `:53`) hits each host's `/comms/health`, aggregates, writes to `99_System/state/comms-health.json` for the Daily Command Center.

---

## 12. Acceptance criteria

These are testable; "shipped" means each one is green for 7 consecutive days.

1. **Round-trip latency.** Desktop → LXC → VPS → LXC → Desktop round-trip < 2s p95, < 5s p99 over the tailnet for `query` intent with ≤ 8 KB payload.
2. **Same-host RTT.** Desktop → LXC → Desktop (no VPS hop) < 800ms p95.
3. **Full audit coverage.** 100% of cross-host messages are present in `99_System/logs/comms-<date>.jsonl` with a valid `trace_id`; nightly `audit_comms_coverage.py` finds zero gaps.
4. **Zero sensitive egress to VPS in test suite.** `tests/test_egress_gate.py` and `tests/integration/test_comms_privacy_e2e.py` both green; 100+ sensitive-class payloads attempted, 0 reach VPS.
5. **Idempotency works.** Replaying any 100 random envelopes from the last 24h produces zero double-side-effects; `deduped: true` returned in every replay.
6. **Outbox survives host kill.** Kill the Desktop mid-send (SIGKILL); on restart, queued envelopes resume; no envelope lost.
7. **Token rotation is zero-downtime.** `make rotate-comms-token EDGE=desktop->lxc` completes with no failed deliveries (use the staged-rotation procedure).
8. **Dead-letter is operator-actionable.** Any envelope in dead-letter has a JSONL trail explaining why; `comms_audit.py --dead-letter` lists them; operator runbook covers the 3 common causes.
9. **Privacy classifier eval ≥ 95% precision + recall.** Against a fixture set of 200 payloads (50 each of public/private/sensitive/edge-case), the classifier scores ≥ 95% on both axes.
10. **Schema drift safety.** Sender posting `envelope_version: 2` to a v1-only receiver gets a `nack` with `reason: "envelope_version_unsupported"`; outbox marks permanent-fail; no retry storm.
11. **Health endpoint truthful.** During a simulated tailnet partition, all three `/comms/health` endpoints report `degraded` within 30s.
12. **Audit trail rotation works.** Daily file at UTC midnight; 7-day-old files compressed; 1-year-old files compacted to monthly summaries.
13. **No new code-heavy cron slot collision.** New `comms-health-monitor` runs at `:53` (currently free per CLAUDE.md); `tests/test_workflow_templates.py::test_code_heavy_workflows_do_not_share_cron_minutes` still green.
14. **Existing test suite unchanged.** All 311 existing tests still pass; new tests are additive.

---

## 13. Phased rollout

Each sub-phase is independently shippable. Each ships behind a feature flag (`OHO_COMMS_ENABLED=true`) so the existing oho-runner pattern continues unimpeded during rollout.

### C1 — LXC inbox endpoint + envelope + classifier  (S, 2-3 days)

**Scope.** Add `/comms/inbox`, `/comms/outbox-ack`, `/comms/health`, `/comms/audit-tail` to `services/oho_runner/app.py` (extend the existing service; do not start a new one). Implement `tools/comms_envelope.py` (pydantic v1 schema), `tools/privacy_classifier.py`, `tools/comms_audit.py`. SQLite idempotency store. Audit JSONL writer. Unit tests for each module.

**Exit criteria.** Manual `curl` test from LXC to its own inbox passes for all 7 intents; privacy classifier passes its eval suite; audit JSONL lines validate against schema.

**Risk.** Smallest. Building on the proven oho-runner pattern.

### C2 — Desktop outbox client + inbox daemon  (S, 2-3 days)

**Scope.** `services/desktop_comms/` — a small FastAPI inbox daemon listening on `127.0.0.1:8765` + a Python client library `oho_comms_client` (importable from Claude Code, agent_quick_add, etc.). systemd user-service (`comms-inbox-daemon.service`) for the inbox; outbox is part of the client library. SQLite outbox store at `~/.oho/state/comms-outbox.db`. Local audit JSONL at `~/.oho/logs/`.

**Exit criteria.** End-to-end smoke: Desktop → LXC → Desktop round-trip for a `query` intent works; latency < 800ms; audit lines present on both ends; tokens loaded from `~/.oho/comms/.env`.

**Risk.** Low. Mirror of C1's pattern, scoped to one process.

### C3 — VPS agent wrapper + LXC ↔ VPS edge  (M, 3-5 days; gated on VPS recon)

**Scope.** Stand up a `services/vps_comms/` FastAPI service on the VPS (same pattern as LXC; smaller — VPS doesn't host the canonical idempotency store, but it has its own for local dedupe). Add `lxc->vps` outbox client to the LXC's comms-router (it needs to act as both inbox and outbox). Per-edge tokens generated and distributed. Tailscale ACL extended.

**Exit criteria.** Desktop → LXC → VPS → LXC → Desktop round-trip < 2s p95; privacy egress gate proven (sensitive payload refused at LXC outbox); per-edge token rotation drill passes.

**Risk.** Medium. Depends on VPS specifics (still being recon'd). Falls back to "C3 deferred" if VPS isn't ready — C1 + C2 still ship and Desktop ↔ LXC works in isolation.

### C4 — End-to-end smoke + audit dashboard + ops integration  (S, 2 days)

**Scope.** `scripts/audit_comms_*` suite (privacy, coverage, dead-letter, schema, latency). `comms-health-monitor` n8n workflow. Daily Command Center section: "📡 Comms" with last-hour volume, dead-letter count, last partition. Make targets (`make rotate-comms-token`, `make comms-audit-summary`). `docs/RUNBOOK.md` chapter for comms ops.

**Exit criteria.** Acceptance criteria §12 #1-14 all green. 7-day soak begins; on day 8 if clean, comms layer is "in prod" and other phases can depend on it.

**Risk.** Low. Pure observability + glue.

### Soak gate

After C4 ships, **comms layer must run clean for ≥ 7 days** (zero PAGE alerts, zero dead-letter entries, all daily audit JSONL files present and well-formed) before any downstream phase (Wave-X, P4 with cross-host AI calls, P3 with VPS-side agent assistance) can rely on it. This matches the P0.5 soak discipline.

---

## 14. Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| VPS topology turns out to be radically different from "FastAPI agent host" | M | M | C1+C2 still ship and provide Desktop↔LXC value alone; C3 redesigned to fit actual VPS once recon completes |
| Privacy classifier misses a class of sensitive content (e.g., Aaron's hip surgery dates) | M | H | Quarterly eval against an expanding fixture set; weekly digest surfaces all `allow_egress_to: vps` entries for human review |
| Per-edge bearer tokens become operational headache | M | M | Staged-rotation procedure is automated via `make rotate-comms-token`; Bitwarden self-hosted is the canonical secret store |
| Audit JSONL grows large | L | L | Daily rotation + weekly compression + yearly compaction; budget: <100MB/year at expected volume |
| HTTPS+JSON proves too slow under future load | L | L | At Aaron's projected scale (100 msg/day), this is ~3000× headroom; if v2 needs more, swap inbox for ASGI streams |
| Bearer-auth single-factor (no mTLS) | M | M | Tailscale ACL is the second factor (cryptographic); mTLS is a v2 hardening pass |
| Comms infrastructure becomes a single point of failure for everything | M | H | Each host's local-only operations (Desktop running Claude Code locally, LXC running n8n locally) continue to work when comms is down; comms is additive, not load-bearing for daily rituals |
| Operator can't tell whether a comms failure is network, auth, schema, or privacy | M | M | `nack` reasons are codified enum (§9); audit lines carry explicit `reason`; runbook has a flowchart |
| Schema-version drift between Desktop and LXC during deploys | M | M | Receivers MUST accept old envelope versions during transitions; only a deliberate `envelope_version: 2` cutover removes v1 support; CI tests both versions |
| Aaron underestimates VPS use cases → builds C3 against a strawman | M | M | Treat C3 as "deferred until concrete VPS use cases are listed"; ship C1+C2 first; learn |
| Idempotency store grows unboundedly | L | L | 30-day prune nightly; SQLite size budget enforced (alert at >100MB) |

---

## 15. Test strategy

### Unit (offline, fast)

- `tests/test_comms_envelope.py` — schema validation per intent; version compat; unknown-field tolerance.
- `tests/test_privacy_classifier.py` — every rule tier; override path; red-team injection.
- `tests/test_idempotency_store.py` — dedupe; payload-hash collision; 30-day prune; concurrent inserts.
- `tests/test_outbox_state_machine.py` — every transition; retry backoff; permanent-fail vs retryable; dead-letter terminal.
- `tests/test_inbox_state_machine.py` — same.
- `tests/test_audit_jsonl.py` — line schema; daily rotation; compression cycle.
- `tests/test_comms_egress_gate.py` — every privacy class × every direction; allow-list escape hatch; audit entries on each.
- `tests/test_token_rotation.py` — staged rotation; multi-token acceptance; zero-downtime.

### Integration (docker-compose harness)

- `tests/integration/test_comms_e2e.py` — `docker-compose.test.yml` brings up LXC + simulated Desktop + simulated VPS; runs the full round-trip suite; asserts <2s p95.
- `tests/integration/test_comms_partition.py` — simulate tailnet partition between LXC and VPS; assert outbox drains correctly on heal; assert `degraded` health within 30s.
- `tests/integration/test_comms_e2e_privacy.py` — 100 sensitive payloads attempted; 0 reach VPS; audit lines correct.
- `tests/integration/test_token_rotation_e2e.py` — full staged rotation across a running 3-host harness; zero failed deliveries.

### Chaos

`tests/test_chaos_comms.py`:
- **Kill VPS mid-send.** LXC posts to VPS; kill VPS process mid-request; assert outbox transitions to retry; assert ack arrives when VPS restarts.
- **Replay attack.** Capture an envelope from the audit log; replay it as a fresh POST; assert `deduped: true` and zero side-effects on the second pass.
- **Oversized payload reject.** Send a 100KB envelope; assert 413 nack at inbox; assert sender marks permanent-fail; assert no retry.
- **Token leak simulation.** Use a valid token from a host not on the tailnet ACL; assert tailnet rejects at L3 before reaching the inbox.
- **Clock skew.** Sender clock 10 min ahead; assert receiver logs warning but accepts; assert audit records both timestamps.
- **Audit JSONL disk-full.** Fill the LXC's audit partition; assert PAGE; assert inbox starts refusing with 503 (fail-loud, never silently drop).
- **Idempotency-key collision.** Two different payloads with the same key; assert first wins; assert collision logged; assert weekly digest surfaces it.

### Property-based (hypothesis)

`tests/test_comms_properties.py`:
- For any well-formed envelope, `serialize → deserialize` is identity.
- For any two distinct payloads with the same idempotency key, the receiver always accepts the first and dedupes the second.
- For any privacy classification, the egress gate is monotonic (more-sensitive class → always-blocked-or-allowed superset of less-sensitive class).

### Eval (continuous, weekly)

`evals/comms_privacy/` — 200 fixture payloads (50 public, 50 private, 50 sensitive, 50 edge-case); weekly run via `run_evals.py`; alerts on precision or recall drop > 5% WoW.

### Manual UAT

- Desktop → LXC `query` from Claude Code session: latency feels snappy (<1s subjective).
- Desktop → LXC → VPS round-trip: works end-to-end.
- Privacy egress refusal: try to send a `[area:: faith]` payload to VPS; verify it's refused with a clear error message.
- Token rotation drill: run `make rotate-comms-token` for one edge; verify no failed deliveries during the rotation window.
- Audit query: `comms_audit.py --trace-id <x>` returns a complete picture.

---

## 16. Verification checklist

Pre-ship checklist for C4 sign-off:

- [ ] All unit tests green (311 existing + ~80 new).
- [ ] All integration tests green.
- [ ] All chaos tests green.
- [ ] Privacy eval ≥ 95% precision + recall.
- [ ] Acceptance criteria §12 #1-14 all green.
- [ ] `docs/SECURITY.md` updated with comms threat model.
- [ ] `docs/RUNBOOK.md` updated with comms ops chapter (rotation, dead-letter drain, partition recovery).
- [ ] `CLAUDE.md` updated with new endpoints + cron slot.
- [ ] `AGENTS.md` mirrored.
- [ ] `docs/AI_TOOLING.md` updated if any new MCP touchpoints.
- [ ] Tailscale ACL committed at `infra/tailscale-acl.json` and applied.
- [ ] Bitwarden vault has all six tokens stored.
- [ ] `make rotate-comms-token` works for all six edges.
- [ ] Daily Command Center "📡 Comms" section renders.
- [ ] 7-day soak runs clean (zero PAGE; zero dead-letter; all JSONL files well-formed).

---

## 17. Open questions (for Aaron)

1. **What is the VPS for, concretely?** The whole C3 sub-phase pivots on this. Is it a public-fact research agent? A long-running scraper for Echelon Seven outreach? A general-purpose compute pool for the agent guild? Naming the use cases dictates the privacy gate rules and the kinds of intents the VPS-side handler needs to support. **If the VPS is just a Tailscale exit-node for outbound public-internet traffic and is *not* hosting agents, C3 collapses to "configure tailnet egress" and the comms layer is only LXC ↔ Desktop.**
2. **What's hosted on the VPS today?** sibling-agent is recon'g `agent-orch-lxc`. If that VPS-side agent stack is something we wrote or can audit, we can install `vps_comms`; if it's a third-party service, we may need a thin proxy. Recon outcome should land at `docs/superpowers/phases/2026-05-13-agent-orch-lxc-recon.md` (currently absent — the spike output dictates whether C3 ships as designed or pivots).
3. **Does Christy need access to the comms layer at all?** v1.0 spouse-shared mode (P6.5) puts her capture path through Telegram → LXC, which doesn't need this comms layer. But if she ever runs Claude Code on her own desktop, she becomes a fourth peer. **Defer to v2 unless you say otherwise.**
4. **Desktop role — read-only or full peer?** Current design: full peer (Desktop can issue `query`, `command`, `event`; LXC can call back). Alternative: Desktop is a *strict client* (issues queries only; never receives unsolicited messages from LXC/VPS). Strict-client is simpler (no inbox daemon required on Desktop, just an outbox client) but loses the ability for LXC to push (e.g., "your briefing is ready" pings, or P7 AI-coach proactive suggestions). **Recommend full peer; flagging the choice.**
5. **Per-edge tokens vs per-host tokens.** v1 design uses per-edge (6 tokens) for revocation granularity. Per-host (3 tokens) is half the rotation cost and simpler. **Vote: per-edge for v1 because the security win is meaningful and rotation is automated; happy to swap to per-host if you'd rather.**
6. **Privacy classifier — strict default or permissive default?** v1 default is strict: anything matching faith/family/health/biomarker rules → `sensitive` → blocked at VPS egress. Permissive default would allow `private` to VPS by default and require explicit `[private:: true]` to block. **Strict default matches cross-cutting §1.G; flagging in case you'd rather start permissive and tighten.**
7. **Should the comms layer carry P3 captures from external surfaces (Telegram, email-forward), or remain agent-to-agent only?** v1 design: agent-to-agent only; external capture continues to use the P3 envelope shape via n8n webhooks to oho-runner directly. Unifying everything onto comms is technically cleaner but rewrites P3's adapter pattern. **Defer unification to v2.**
8. **64KB payload cap — too small?** Large payloads (full document context, long file contents, etc.) need to use the `payload.blob_key` indirection. Acceptable in v1 since MinIO is already on the LXC. **Flagging in case you want a larger inline cap.**
9. **Is `oho-vps.tailfab8a7.ts.net` the right MagicDNS name once the VPS is on the tailnet?** Trivial to change; just nailing convention. **Defaults to that.**
10. **Should the comms layer pre-empt or coexist with the existing oho-runner endpoints?** v1 design: comms endpoints are *added* to the same FastAPI service; the existing `/process-brain-dump` and `/build-command-center` continue to work unchanged. Existing n8n workflows do not need to migrate. Future phases (P4 briefings cross-host calls; P7 AI coach) use comms; the rest stays on direct calls. **Coexist in v1; deprecate only if usage drops.**

---

## 18. Files this design implies (not created by this spec)

**New runner endpoints (in `services/oho_runner/app.py`):**
- `POST /comms/inbox`
- `POST /comms/outbox-ack`
- `GET  /comms/health`
- `GET  /comms/audit-tail`

**New tooling:**
- `tools/comms_envelope.py` — pydantic schema + validators + canonicalisation
- `tools/privacy_classifier.py` — the classifier from §8
- `tools/comms_audit.py` — query + summary CLI
- `tools/comms_router.py` — LXC-side relay logic (Desktop ↔ VPS hopping)
- `tools/comms_client.py` — sender-side library (used by Desktop and VPS senders)
- `tools/comms_outbox.py` — outbox worker + state machine
- `tools/comms_idempotency.py` — SQLite-backed store

**New services:**
- `services/desktop_comms/` — Desktop FastAPI inbox daemon + systemd user-service
- `services/vps_comms/` — VPS FastAPI inbox service (C3)

**New scripts:**
- `scripts/audit_comms_coverage.py`
- `scripts/audit_comms_privacy.py`
- `scripts/audit_comms_dead_letter.py`
- `scripts/audit_comms_envelope.py`
- `scripts/comms_audit.py`
- `scripts/rotate_comms_token.py`

**New workflows:**
- `workflows/n8n/comms-health-monitor.json` (cron slot `:53`)

**New state files:**
- `/opt/oho/state/comms-idempotency.db` (LXC)
- `/opt/oho/state/comms-outbox.db` (LXC, for LXC→VPS sends)
- `~/.oho/state/comms-outbox.db` (Desktop)
- `~/.oho/state/comms-idempotency.db` (Desktop)
- `/var/lib/oho/comms-idempotency.db` (VPS)
- `99_System/state/comms-health.json` (vault-side aggregate)

**New log files:**
- `99_System/logs/comms-<YYYY-MM-DD>.jsonl` (LXC, canonical)
- `~/.oho/logs/comms-<YYYY-MM-DD>.jsonl` (Desktop, local)
- `/var/log/oho/comms-<YYYY-MM-DD>.jsonl` (VPS, local)

**New ACL file:**
- `infra/tailscale-acl.json`

**Tests:** per §15.

**Docs to update:**
- `CLAUDE.md` — endpoints, cron slot `:53`, comms envelope contract
- `docs/RUNBOOK.md` — comms ops chapter
- `docs/SECURITY.md` — comms threat model (depends on cross-cutting §1.A)
- `AGENTS.md` — Codex/OpenAI mirror
- `docs/AI_TOOLING.md` — register any new MCP touchpoints
- New ADR — `docs/adr/0008-cross-host-comms.md` — promoted from this spec at implementation start

---

_End of design spec._

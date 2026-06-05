# P3 Capture-Everywhere + P4 Decision-Ready Briefings — Combined Design Spec

**Date:** 2026-05-12
**Status:** DESIGN — not yet approved for implementation
**Author:** Claude (Opus 4.7) — drafted for Aaron Dykes
**Replaces / extends:**
- `docs/superpowers/specs/2026-05-10-agent-quick-add-design.md` (coding-session slice — preserved, extended into the broader P3 capture story)
- `docs/superpowers/specs/2026-04-02-life-os-v2-design.md` (v2 vision; this spec instantiates the P3+P4 phases)
**Depends on:** P1 + P1.5 + ADR-0006 deployed and soaking clean through 2026-05-18; P2 (threaded tasks) must land before the briefing's "weekly thread" + accountability deltas can be precise.
**ADR follow-up:** A separate ADR-0007 *capture-envelope schema + capture API* should be authored when implementation begins; this spec is its design source.

---

## Why one spec for both phases

P3 and P4 are not independent: every capture surface is only as valuable as the briefing that surfaces it the next morning, and every briefing is only as truthful as the captures that fed it. They share:

- A **single canonical capture envelope** that is the contract between every input surface and every downstream consumer (MTL appender, brain-dump-processor, command center builder, briefing generator).
- A **single API boundary** (oho-runner) — already proven through the P1.5 pivot — extended with one new authenticated route, not a fan of webhooks.
- A **single inference cascade** (explicit hints → regex → AI cheap-tier → defaults) used both at capture time and at briefing-rendering time, so the same logic that classifies an inbound voice memo also explains a low-confidence item in the review queue.
- A **single provenance model** — every line in the morning briefing must point back to a capture envelope, which points back to a source surface, which points back to a source message ID. Anti-hallucination is enforceable end-to-end.

If you build P4 before P3 you will polish a report that hides bad data. If you build P3 before P4 you will create capture surfaces nobody trusts because the proof-of-life lives buried in MTL. They ship together.

---

# PART A — P3: Capture-Everywhere

## 1. Goal + Magical Moments

**Goal.** Aaron can capture from any device, in any moment, in <5 seconds of friction, and trust that:
1. It will end up in the correct life-domain inbox.
2. It will be auto-classified to the right section and priority with reasoning he can audit later.
3. It is idempotent — re-sending is safe.
4. It survives offline conditions (queues locally, replays when the runner is reachable).
5. It never edits the vault directly — every write goes through the brain-dump pipeline so receipts, dedup, and audit hold.

**Magical moments (the 8 we're designing toward).**

1. **The shower thought.** Aaron talks to his Apple Watch: "Hey Siri, capture: Echelon Seven website needs the offer-page copy before Friday." 30 seconds later it's an A-priority business task in `BrainDump — Business.md`, due 2026-05-15, picked up by the 7AM run, surfaced as tomorrow's #1.
2. **The Telegram conversation merge.** Aaron sends three rapid Telegram messages — "Christy mentioned the kids' summer schedule", "need to call the orthodontist", "and confirm the camp dates." All three are merged into one threaded `family` capture, classified as one note with three follow-up tasks. He sees them grouped in tomorrow's briefing under one accountability line.
3. **The forwarded email becomes a tracked task.** A client emails "Can you send the proposal by Tuesday?" — Aaron forwards it to `capture@aarondy3777.33mail.com` with subject `[consulting][A]`. The subject hints become structured metadata; the email body becomes the task body; the email thread-id becomes the stable `source_message_id`. When the client replies, the reply is appended to the same capture envelope — the task gets new context, not a duplicate.
4. **The voice memo with Whisper.** Aaron records 90 seconds into his phone during the drive home about the hip-decision conversation with his doctor. The audio is queued locally if the runner is offline, transcribed via local whisper.cpp when reachable, and lands as a structured `health` brain-dump entry with the *raw audio retained* (linked, encrypted) in case the transcription got something wrong.
5. **The share-sheet article.** From any iOS/Android browser, Aaron hits Share → "OHO Capture" → it POSTs the URL + page title + selection text to `/capture` and lands in `articles-to-process.md` enriched by link-enricher within the hour.
6. **The coding-session quick-add.** From Claude Code: "Aaron, add a business A task: rewrite the Echelon onboarding email by Wed." Agent invokes `tools/agent_quick_add.py` (2026-05-10 design, preserved) — same envelope shape, same downstream pipeline. No new surface.
7. **The Oura tag.** Aaron tags a poor sleep night in Oura. Nightly biohacking-pipeline pull notices the tag, emits a `health` capture envelope explaining the next morning's briefing should mark today as a low-energy window. The briefing recommends *easier* A-tasks today, not harder ones.
8. **The "I caught my brain mid-sentence" moment.** Aaron sends `/note` to Telegram, types a single sentence, and walks away. The bot replies with a thumbs-up emoji + `✅ filed under personal → quick notes (B). undo: /undo abc123`. He never had to think about destination, priority, or area.

## 2. Scope (in/out) + relationship to P2

**In scope (P3 v1):**
- Capture API on the existing **oho-runner** — one new route `POST /capture`, bearer-auth, idempotency-keyed, envelope-validated, asyncio-lock-serialised (consistent with P1.5).
- Capture envelope v1 schema (versioned).
- Six initial capture surfaces, deployed in waves: **Telegram bot (extended)**, **email forward**, **share-sheet/bookmarklet**, **voice memo (phone-side + watch dictation)**, **coding-session quick-add (already designed)**, **wearable wellness auto-capture**.
- Idempotency layer (source + source_message_id → SHA256 → de-dup table at `99_System/state/capture-idempotency.json`).
- Inference cascade (explicit → regex → AI cheap-tier → defaults).
- Offline queueing per surface (each surface owns its own local queue; runner does not).
- Privacy: encrypted-at-rest raw transcripts; redaction patterns for email signatures and obvious PII.
- Tests: pytest suite for envelope validation, idempotency, inference cascade, every surface's adapter.

**Out of scope (P3 v1, defer to later P3.x or P5):**
- Voice digest playback (covered in P4).
- AI-coach style classification refinement (P7).
- A web UI for the inbox.
- iMessage capture (no clean automation surface on iOS yet without a Mac relay).
- Native iOS/Android apps. (Share-sheet shortcut + Siri intent are sufficient for v1.)
- Push notifications back from the runner (we ack via the source surface only).

**Relationship to P2 (threaded tasks).** The capture envelope MUST carry an optional `task_id` field for future threading. When P2 lands, captures that update existing tasks (an email reply, a voice memo "follow-up on the hip decision") will carry the existing `task_id` and append to the thread rather than create a sibling. The envelope is designed to absorb this future — but until P2 ships, `task_id` is always null on inbound and assigned by the brain-dump processor (or left empty).

Captures that produce *new* tasks before P2 ships use the existing MTL append path. Once P2 ships, the processor begins backing each task with a `30_Tasks/<area>/<task_id>.md` file. **No P3 surface changes** when that happens — the envelope already carries the optionality.

## 3. Architecture

### 3.1 The single capture endpoint

```
POST /capture HTTP/1.1
Host: oho-runner.tailfab8a7.ts.net:8080
Authorization: Bearer <OHO_RUNNER_TOKEN>
Content-Type: application/json

{ <CaptureEnvelope v1> }

Response 200:
  { "status": "accepted", "capture_id": "...", "deduped": false,
    "routed_to": "BrainDump — Business.md", "section": "todos",
    "area_inferred": "business", "priority_inferred": "A",
    "confidence": "high", "review_required": false }

Response 200 (already seen):
  { "status": "accepted", "deduped": true, "first_seen_at": "...",
    "capture_id": "<original>" }

Response 4xx: schema, auth, or quota failures (never partial state).
Response 409: another run in progress (caller retries with backoff — same idempotency_key safely de-dups).
```

This route shares the oho-runner's existing asyncio lock with `/process-brain-dump` and `/build-command-center`. A capture POST is short (<1s typical), so the serialisation cost is negligible and we get free crash-consistency.

Hardening (inherited from P1.5):
- `hmac.compare_digest` token check.
- Single envelope per POST (no batching in v1 — adds complexity, reduces idempotency clarity; batch is a v2 feature).
- argv tuple subprocess pattern when invoking the underlying writer (no shell expansion).
- Read-only `/opt/oho` mount.

### 3.2 Sequence — Telegram capture (v2, extended)

```
[Aaron's phone]            [Telegram BotFather]      [n8n webhook]           [oho-runner]                 [MinIO]
      │                            │                       │                       │                          │
      │ "/task Echelon offer …"    │                       │                       │                          │
      │ ─────────────────────────► │                       │                       │                          │
      │                            │ webhook POST          │                       │                          │
      │                            │ ────────────────────► │                       │                          │
      │                            │                       │ extract text          │                          │
      │                            │                       │ extract /task hint    │                          │
      │                            │                       │ build envelope v1     │                          │
      │                            │                       │ POST /capture         │                          │
      │                            │                       │ Bearer <TOKEN>        │                          │
      │                            │                       │ ────────────────────► │                          │
      │                            │                       │                       │ check idempotency JSON   │
      │                            │                       │                       │ ───────────────────────► │
      │                            │                       │                       │ ◄─────────────────────── │
      │                            │                       │                       │ run inference cascade    │
      │                            │                       │                       │ append to                │
      │                            │                       │                       │   BrainDump — Business.md│
      │                            │                       │                       │ verified PUT             │
      │                            │                       │                       │ ───────────────────────► │
      │                            │                       │                       │ head_object verify       │
      │                            │                       │                       │ update idempotency JSON  │
      │                            │                       │                       │ ───────────────────────► │
      │                            │                       │ ◄───────────────────  │                          │
      │                            │ ◄────────────────────                         │                          │
      │ ✅ filed under business A   │                                              │                          │
      │ ◄────────────────────────  │                                              │                          │
```

**Voice path divergence (when `msg.voice` present):**
- n8n downloads the OGG file from Telegram.
- POSTs to a Whisper transcription sidecar (a new lightweight container alongside oho-runner). Transcript and the raw OGG path go into the envelope as `raw_text` + `attachments[]`.
- The raw OGG is uploaded to MinIO at `99_System/raw-captures/voice/<capture_id>.ogg` for audit. **Never deleted automatically** — Aaron decides when to purge (default: 90-day quarterly review).

**Multi-line merging (the "conversation merge" magical moment).** A capture coming from Telegram inherits a `thread_window_seconds` setting (default 90s). Within that window, subsequent messages from the same chat are appended to the in-flight capture envelope (raw_text grows; attachments accumulate). The runner holds a per-source merge buffer keyed by `(source, chat_id, area)`. After the window closes, the envelope flushes through the cascade. This is opt-in per source — email and share-sheet do NOT merge; Telegram does.

### 3.3 Sequence — Email-forward capture

```
[Aaron's mail client]   [33mail/Cloudflare Email Worker]   [oho-runner /capture]
        │                          │                                │
        │ Forward email to:        │                                │
        │ capture@aarondy3777…     │                                │
        │ Subject: [business][A]   │                                │
        │ Re: Acme proposal        │                                │
        │ ───────────────────────► │                                │
        │                          │ verify SPF+DKIM                │
        │                          │ (drop if either fails)         │
        │                          │ parse subject → hints          │
        │                          │ strip signatures (regex)       │
        │                          │ build envelope v1              │
        │                          │ source_message_id =            │
        │                          │   message-id header            │
        │                          │ POST /capture                  │
        │                          │ Authorization: Bearer …        │
        │                          │ ─────────────────────────────► │
        │                          │ ◄─────────────────────────────│
        │                          │ (no ack back to Aaron — silent)│
```

A Cloudflare Email Worker (free tier, 100k emails/day) is the right boundary because:
- It does DKIM/SPF for us.
- It exposes a JS handler with the parsed message — we can transform → POST to oho-runner from Cloudflare edge with the same `OHO_RUNNER_TOKEN` (kept as a Worker secret).
- No SMTP server to operate; no IMAP polling; no email-account-as-API anti-pattern.

The email subject is the explicit-hint channel: `[<area>][<priority>] <subject>` parses cleanly; missing hints fall through to the cascade.

Reply threading: the email Worker reads the `In-Reply-To:` header. If it matches a known `source_message_id` from a prior capture, the envelope carries `thread_root_id = <prior capture_id>` and the runner appends to that capture's existing section rather than creating a new entry.

### 3.4 Sequence — Voice memo (phone-side)

Apple Shortcuts → "OHO Voice Capture":
```
[Aaron records 90s memo]
   ↓
[Shortcut compresses to OGG @ 32kbps mono]
   ↓
[Shortcut POSTs multipart/form-data to oho-runner /capture]
   {
     "source": "voice-phone",
     "raw_text": "",
     "attachments": [{"kind": "audio/ogg", "filename": "...", "size": ...}],
     ...envelope...
   }
   ↓
[oho-runner stores the OGG in MinIO at 99_System/raw-captures/voice/<id>.ogg
   ↓ kicks off Whisper sidecar transcription (async — returns 202 to phone)
   ↓ updates the same envelope with transcript when ready
   ↓ flushes through the cascade]
```

**Offline behavior:** the Shortcut writes the OGG + envelope JSON to a local iCloud folder if the POST fails. A second Shortcut, scheduled hourly, replays the queue when reachable. iCloud is the queue (not the source of truth) — once replayed, files move to a `sent/` subfolder.

**Watch dictation** uses the same Shortcut, sourced from the Watch's dictation field — no audio file, only `raw_text`.

### 3.5 Sequence — Share-sheet / browser bookmarklet

iOS Shortcut "Share to OHO" / Android intent / desktop bookmarklet → POST to `/capture`:
```
{
  "source": "share-sheet",
  "source_message_id": "<sha256 of url + selection>",
  "raw_text": "<selected text or empty>",
  "hints": {"url": "https://...", "page_title": "..."},
  ...
}
```

Inference cascade detects `hints.url is set` → routes to `articles` section. Page title becomes the link text; `link-enricher` workflow does the rest at the next hourly tick.

### 3.6 Sequence — Wearable wellness auto-capture

Nightly cron (separate from oho-runner — lives in the biohacking-data-pipeline skill scope):
```
[Oura / Whoop API pulls]
   → normalised health record (sleep score, HRV, recovery, tags)
   → if any tag is "low_energy" / "poor_sleep" / "recovery_red"
     OR sleep_score < threshold(60)
   → emit envelope { source: "biohacking-pipeline", area: "health",
                      section: "quick", priority: "C",
                      hints: { energy_window: "low" },
                      raw_text: "Oura flagged …" }
   → POST /capture
```

Output: a low-priority health note that the morning briefing reads to set the energy window (see P4 §3).

### 3.7 Inference cascade (shared across surfaces)

```
1. Explicit hints (subject prefix, /task command, share-sheet metadata)
   → if area + priority both supplied, accept verbatim, mark confidence=HIGH

2. Regex (free, deterministic, CLAUDE.md regex-first)
   → keywords: "echelon", "parallon", "christy", "kids", "hip", "gym",
     "client", "proposal" → area mapping
   → urgency markers: "urgent", "asap", "today", "due (date)", "by …" → priority
   → if confident match → confidence=HIGH

3. AI cheap-tier (OpenRouter gemma-3-4b — free)
   → only invoked if regex returned UNCERTAIN
   → returns {area, priority, confidence, reasoning, suggested_section}
   → confidence=MEDIUM unless model explicitly says HIGH

4. Defaults
   → area = "personal", section = "quick", priority = "B"
   → confidence = LOW → routed to review-queue.md instead of MTL
```

Confidence band → routing decision:
- HIGH → goes straight to the inferred section of the inferred brain-dump file.
- MEDIUM → same routing but flagged in the run log + briefing's "Needs Review" section the next morning if not confirmed.
- LOW → routed to `00_Inbox/review-queue.md` only; never auto-promoted.

This is the same band CLAUDE.md already mandates for VERIFIED / LIKELY / UNCERTAIN. We are literally extending the project's anti-hallucination grammar to inbound classification.

## 4. Data model

### 4.1 Capture envelope v1 (the contract)

```json
{
  "envelope_version": 1,
  "capture_id": "cap_2026-05-12T08-14-22Z_a7f1c9d2",
  "source": "telegram | email | share-sheet | voice-phone | voice-watch | agent-quick-add | biohacking-pipeline | manual-edit",
  "source_message_id": "<stable id from source — telegram msg_id, email Message-ID header, sha256 for share-sheet, etc>",
  "thread_root_id": null,
  "received_at": "2026-05-12T08:14:22Z",
  "raw_text": "Echelon Seven website needs the offer-page copy before Friday",
  "hints": {
    "area": null,
    "priority": null,
    "due": null,
    "section": null,
    "url": null,
    "page_title": null,
    "energy_window": null,
    "explicit_section_alias": null
  },
  "attachments": [
    { "kind": "audio/ogg", "key": "99_System/raw-captures/voice/cap_…ogg", "size": 142840 }
  ],
  "inferred": {
    "area": "business",
    "priority": "A",
    "section": "todos",
    "due": "2026-05-15",
    "confidence": "high",
    "cascade_path": ["regex_keyword:echelon", "regex_urgency:friday"],
    "ai_used": false
  },
  "routing": {
    "target_file": "00_Inbox/brain-dumps/BrainDump — Business.md",
    "target_section": "## ✅ To Do's",
    "review_required": false
  },
  "task_id": null,
  "audit": {
    "idempotency_key": "telegram:12345:msg-67890",
    "first_seen_at": "2026-05-12T08:14:22Z",
    "received_via": "n8n-webhook → oho-runner",
    "runner_version": "1.2"
  }
}
```

Stored at write-time at `99_System/captures/<YYYY-MM-DD>/<capture_id>.json` (audit trail; same content-hash discipline as P1 extraction receipts). Older than 90 days → moved to `99_System/captures/archive/` quarterly.

### 4.2 Idempotency store

A single file at `99_System/state/capture-idempotency.json`, structure:

```json
{
  "version": 1,
  "entries": {
    "telegram:12345:msg-67890": {
      "capture_id": "cap_2026-05-12T…",
      "first_seen_at": "2026-05-12T08:14:22Z",
      "content_hash": "sha256:..."
    },
    "email:<Message-ID-header>": { ... },
    ...
  }
}
```

Pruned to last 30 days on every write. Replays of the same `idempotency_key` short-circuit before any S3 write or AI call — the runner returns the original capture_id and `deduped: true`.

Content-hash guard: if the same idempotency_key arrives with a *different* content hash, it's logged as `idempotency_collision` and forced through (rare; useful signal that a source is misbehaving).

## 5. Failure modes + guardrails

| Failure | Symptom | Guardrail |
|---|---|---|
| Runner unreachable | Surface POST fails | Each surface owns a local queue (n8n: in-memory + retry; phone: iCloud folder; Cloudflare Worker: KV store with replay job; agent-quick-add: writes a `.queued` marker and retries) |
| Token leak | Unauthorised captures could spam vault | `hmac.compare_digest`; token rotated quarterly; runner-side per-source rate limit (60 captures/min globally, 20/min per source) |
| AI cascade hallucinates area | Wrong file appended | Confidence-band routing — LOW always lands in review queue, never auto-promoted |
| Whisper transcription wrong | Bad task text in vault | Raw audio kept in MinIO; review queue surfaces low-confidence Whisper results (we read Whisper's logprob field as confidence) |
| Telegram conversation merge captures unrelated message | Two thoughts fused into one capture | 90s window + same area inference; if next message's regex routes to different area, flush the current buffer immediately |
| Email forward gets duplicate Cloudflare retry | Capture appears twice | Idempotency key = Message-ID; identical Message-ID is silently de-duped |
| Source clock drift makes idempotency key collide | New capture overwrites old | Idempotency key always includes the source + source_message_id, never a timestamp |
| Brain-dump file is in `partial` / `error` state | Mixing new content with broken file | Capture envelope writes to a sibling file `BrainDump — <Area> — Quarantine.md` instead, flagged in the next briefing |
| Inference cascade always picks `personal/B` | Aaron's signal lost in noise | Per-area capture counts surfaced in the weekly digest; if `personal` is >60% of captures for a week the inference rules get a manual review pass |
| MinIO unreachable mid-capture | Half-written envelope | Two-phase write: append to brain-dump file FIRST (verified), then write the envelope JSON. If envelope write fails, run log records `envelope_orphan`; nightly audit reconciles |

## 6. Privacy + security

**Wire.** Capture endpoint is reachable only over Tailscale by default (`*.tailfab8a7.ts.net`). Cloudflare Email Worker is the one exception — it traverses public internet, but the call from Cloudflare → runner is via Tailscale Funnel + bearer token. SPF + DKIM hard-required at the Worker; failures are dropped (not bounced — silent drop to avoid leaking the address's existence).

**Auth.** `OHO_RUNNER_TOKEN` is unchanged from P1.5 — same bearer secret, same `hmac.compare_digest` check. **All capture surfaces share one token** (rotation cost: redeploy every surface's secret store). A per-source token is a v2 idea (lets us revoke one surface without breaking the others); v1 keeps it simple.

**At rest.** Capture envelope JSON files are stored in MinIO unencrypted (MinIO bucket itself sits on encrypted-volume MiniPC storage — defense in depth). Voice transcripts and raw audio files are stored encrypted client-side before upload — the encryption key lives in `.env` (same `OHO_CAPTURE_AT_REST_KEY` for both audio and transcript), never in MinIO, never in git. Transcript de-encryption happens at briefing-time only.

**Redaction.** Inbound email passes through a redaction regex pass at the Cloudflare Worker before envelope creation: strip everything below the first occurrence of `^-- $` (standard signature delimiter), the first occurrence of "Sent from my iPhone/iPad/Android", and known patterns for Christy's work email signature. Phone numbers and credit-card-shaped digits are also masked. Aaron can override per-capture via subject `[no-redact]`.

**Logging.** Runner logs **never** include `raw_text` past 80 chars (truncated). Run log JSON captures envelope shape but not body. Telegram messages with text containing keys/secrets (regex match against `(api_key|secret|password|token)\s*[:=]`) are rejected at the runner with a 422 + a Telegram reply asking Aaron to redact and resend.

**Audit trail.** Every capture envelope, kept 90 days. Aaron can ask "where did this task come from?" and the briefing's provenance link points to the envelope, which points to the source message ID, which (for Telegram/email) can be looked up in the original surface.

**Quarantine.** A `--purge-capture <capture_id>` admin CLI lets Aaron remove a capture from MinIO + the idempotency store + any vault file it landed in. Used for accidental sensitive captures.

## 7. Acceptance criteria

- `POST /capture` exists on oho-runner, bearer-authenticated, asyncio-lock-serialised, returning a fully-populated capture envelope.
- Capture envelope v1 schema is validated server-side (pydantic) and rejected with 422 on malformed input.
- Idempotency store correctly de-duplicates identical `(source, source_message_id)` pairs within a 30-day window.
- Inference cascade implementations: regex tier (deterministic), AI tier (OpenRouter cheap call), defaults tier — each independently testable.
- Telegram bot v2 supports `/task`, `/brain`, `/note`, `/article` slash commands with `[area][priority]` parsing.
- Telegram voice messages are transcribed by the Whisper sidecar; raw audio is retained encrypted.
- Telegram conversation-merge window (90s) batches related messages.
- Cloudflare Email Worker is deployed; emails to `capture@aarondy3777.33mail.com` route through DKIM/SPF, parse subject hints, and POST envelopes to the runner.
- iOS Shortcut "OHO Voice Capture" exists, files an OGG, queues offline, and replays.
- iOS / Android share-sheet target ("Share to OHO") POSTs envelopes for URLs.
- The 2026-05-10 `agent_quick_add.py` CLI is refactored to also emit the envelope (instead of just appending to brain-dumps) so its captures show up in `99_System/captures/`.
- Biohacking pipeline emits health envelopes on poor-sleep / low-HRV days.
- All capture envelopes land in `99_System/captures/<date>/<capture_id>.json` as audit records.
- pytest suite covers: envelope schema, idempotency, inference cascade per tier, each surface adapter, redaction pass, the merge buffer.
- All existing 311+ tests still pass.
- A new audit script `scripts/audit_captures.py` verifies for the last 14d: every capture envelope has either a corresponding brain-dump file diff OR a `deduped: true` flag.
- No new code-heavy cron slot is consumed (capture is event-driven, not scheduled — keeps the task-runner constraint clean).

## 8. Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Whisper sidecar is fragile / GPU-less laptops can't run it | M | M | Fall back to OpenAI Whisper API ($0.006/min — cheap); local whisper.cpp is the default, API is the failover |
| Cloudflare Email Worker free tier limits (100k emails/day) | L | L | We expect <50 capture-emails/week — never hit limit |
| Per-surface token rotation pain | M | M | Defer to v2 — single token in v1 |
| Inference cascade misroutes consistently | M | H | Confidence band routing + weekly digest surfaces ratio; if MEDIUM ratio >30%, regex rules expanded |
| Voice transcripts leak via run logs | L | H | Hard rule: `raw_text` truncated at 80 chars in logs; CI test asserts no log line >120 chars for capture endpoints |
| 33mail address gets scraped / spammed | L | M | Cloudflare Worker drops anything not in allowlist of sender domains (Aaron's domains, common clients, can be added per-need) |
| Telegram merge buffer eats a message because next one is unrelated | L | L | Differential area inference triggers immediate flush; merge buffer is opt-in per-source |
| Aaron deletes the idempotency JSON by accident | L | M | File is in MinIO with versioning enabled (already on for this bucket per project conventions); last 7 versions retained |

## 9. Dependencies

- **P1 + P1.5 + ADR-0006 soak completes 2026-05-18 clean.** Hard gate.
- **P2 (threaded tasks).** Soft dependency — P3 envelope carries `task_id` and `thread_root_id` slots that are no-ops until P2 ships, but the slots must exist from day one.
- **Tailscale presence on Aaron's phone.** For Telegram-Bot → oho-runner over Tailscale, the n8n instance reaches the runner via the existing LXC bridge. Email Worker uses Tailscale Funnel.
- **`OHO_RUNNER_TOKEN`, `OHO_CAPTURE_AT_REST_KEY`, `WHISPER_SIDECAR_URL`** in `.env`.
- **Cloudflare account with Email Routing enabled** for `aarondy3777.33mail.com`.
- **iOS device with Shortcuts** (already in use).

## 10. Parallel sub-lanes within P3

The work splits into 4 sub-lanes that can ship in waves; each lane is testable independently because they all converge on the same envelope.

| Lane | Sub-scope | Sequencing |
|---|---|---|
| **P3.A — Envelope + endpoint** | Envelope schema, `/capture` route, idempotency store, inference cascade, audit log, redaction pass | **First** — nothing else ships until this is in prod with a manual-capture test passing |
| **P3.B — Telegram v2** | Slash commands, voice via Whisper, merge buffer, raw-audio storage | **Second** — proves the envelope on the highest-volume surface |
| **P3.C — Email + share-sheet + voice-phone** | Cloudflare Worker, iOS Shortcuts (voice + share-sheet), Android intent share | **Third** — three surfaces but each is small once the envelope is stable |
| **P3.D — Wearable + agent-quick-add refactor** | Biohacking pipeline emitter, refactor of `tools/agent_quick_add.py` to emit envelope, watch dictation | **Fourth** — wraps the loop and proves the envelope works for non-human sources |

## 11. Effort

| Lane | Engineering days (single dev, focused) | Notes |
|---|---|---|
| P3.A | 3 | Envelope schema + endpoint is small once you trust the existing oho-runner pattern |
| P3.B | 4 | Telegram v2 is most code; merge buffer + Whisper sidecar each ~1d |
| P3.C | 4 | Cloudflare Worker (0.5d) + each Shortcut (0.5d) + tests (2d) |
| P3.D | 2 | Biohacking emitter (1d) + agent-quick-add refactor (0.5d) + watch dictation (0.5d) |
| **Total** | **13** | About 2.5 calendar weeks at Aaron's typical evening + weekend pace |

## 12. Verification strategy + sample tests

**Unit tier:**
- `tests/test_capture_envelope.py`: schema validation, missing-field rejection, version-bump compatibility.
- `tests/test_capture_idempotency.py`: dup detection, content-hash collision, 30-day prune.
- `tests/test_inference_cascade.py`: explicit > regex > AI > default ordering; each tier independently mockable.
- `tests/test_telegram_adapter.py`: slash-command parsing, voice routing, merge-buffer flush conditions.
- `tests/test_email_adapter.py`: subject parsing, signature stripping, In-Reply-To threading.
- `tests/test_redaction.py`: signature stripping, phone-number masking, secret rejection.

**Integration tier:**
- `tests/integration/test_capture_endpoint_live.py`: POST against a local runner, verify envelope written to MinIO + brain-dump file diff matches + idempotency store updated.
- `tests/integration/test_voice_capture_e2e.py`: file an OGG to `/capture`, assert transcription completes within timeout and lands in the right section.

**Audit tier:**
- `scripts/audit_captures.py`: runs daily via vault-health-report; flags any capture envelope without a matching brain-dump diff (orphan) and any brain-dump line without a backing envelope (untraceable).

**Manual UAT checklist (per surface):**
- Telegram: send `/task` happy-path; voice memo; 3 rapid messages (merge); a message with an API key (rejection).
- Email: forward with valid subject; missing subject hints; reply threading; oversized attachment (drop).
- Voice (phone): airplane mode → queue → reconnect → replay.
- Share-sheet: from Safari, Chrome iOS, Firefox Android.
- Watch: dictation captures with imperfect transcription (verify it lands in review queue, not MTL).

## 13. Open questions (for Aaron)

1. **Is `capture@aarondy3777.33mail.com` the right address, or do you want a dedicated subdomain (e.g. `capture@oho.aarondy.com`)?** The 33mail forwarder works but exposes the alias publicly once you share it; a dedicated subdomain feels cleaner.
2. **For voice transcripts: do you want local whisper.cpp as default or OpenAI Whisper API?** Local is private + free but flakier on the MiniPC. API is $0.006/minute (cheap), great quality, but ships raw audio to OpenAI.
3. **Allowlist policy on the email Worker — open or restricted?** Restricted (allowlist your own domains + known clients) keeps spam out but means you need to add new senders manually. Open accepts anything DKIM-passing.
4. **What's the right window for Telegram conversation-merge — 90s, 60s, 120s?** Cheap to change; just need your gut.
5. **Should wearable auto-captures be opt-in per-day (you tag a day) or always-on (any sleep <60 score)?** Always-on risks noise; opt-in risks forgetting.
6. **Should we surface a Telegram `/undo <capture_id>` command in v1, or defer?** Implementation is small; UX value is huge for confidence.

---

# PART B — P4: Decision-Ready Briefings

## 1. Goal + Magical Moments

**Goal.** The morning briefing becomes a **decision instrument**: in under 200 words of HTML it answers "what's the ONE thing today, what are the 3 unblock decisions, what did I commit to yesterday and did it happen, what's my energy window today?" Everything else — task lists by area, due-this-week tables, completion stats — lives in the Daily Command Center, not the email. The email is the trigger. The command center is the depth.

**Magical moments.**

1. **The cold-start.** Aaron wakes at 5:55am, picks up his phone, sees one email: "Tuesday — your ONE thing is the Echelon offer-page copy (1.5h estimated, your A-energy window is 7-10am)." He hits "Open command center" and starts.
2. **The accountability nudge.** Below the ONE thing: "Yesterday's commit: 'finish Union project draft.' Status: still open — slipped to today. Do/delegate/drop?" One tap on `do` extends it; one tap on `drop` archives it with reason. Aaron's truthful with himself even on bad days.
3. **The 3 unblock decisions.** Mid-briefing, three explicit decisions: "Should you proceed with hip surgery in Q3? Options: yes/no/delay. AI-suggested default based on your prior captures: *yes*. Decide today." Each links to a vault note with full context.
4. **The conflict warning.** "⚠ Cross-domain conflict: business has 2 A-tasks due today; family has Christy's birthday dinner at 6pm. Cap business at one A-task before 4pm." The briefing is *aware of the whole life*, not just the next item on the list.
5. **The energy-window match.** "Your Oura recovery is 47 today (red). Today's recommended A-task energy: low. Move the offer-page copy to tomorrow; pick up the 30-min outreach email instead." Briefing adapts to biology, not just deadlines.
6. **The faith touch.** "Today's prayer queue: pray for the Wednesday Bible study attendees. Sermon prep: 2 days until Sunday." Doesn't get drowned out by tasks.
7. **The weekly thread.** "This week's rocks: 3/5 advancing. Faith rock at risk — no session captured in 9 days." Today's #1 is shown *as part of the week*, not in isolation.
8. **The voice digest.** On long-drive days, Aaron taps "Listen" → a 2-minute generated podcast (NotebookLM) plays the briefing aloud. Different surface, same content, same provenance.

## 2. Scope (in/out) + relationship to threaded tasks (P2)

**In scope (P4 v1):**
- New script `tools/build_briefing.py` — the briefing generator. Idempotent, fail-safe, with deterministic fallback.
- New oho-runner endpoint `POST /build-briefing` (joins `/process-brain-dump` and `/build-command-center`).
- HTML email template with sections: header, today's ONE thing, accountability line, 3 unblock decisions, energy window, cross-domain conflicts, weekly thread, faith integration, links.
- Telegram morning-ping channel: a short summary version posted to Aaron's Telegram around the same time as the email.
- Daily vault note: a new section in the daily-note-creator's template — "🌅 Today's Briefing" — that gets the same content as the email but rendered for Obsidian.
- Voice digest (optional): NotebookLM auto-generated audio overview, pushed to a podcast feed Aaron can subscribe to on his phone.
- Provenance: every fact has a tooltip/footnote pointing back to its source file/line.
- AI-fallback model: deterministic non-AI version that works if OpenRouter is down.
- Slip detection: anything overdue >7 days surfaced for explicit do/delegate/drop.
- Tone calibration: "Aaron, …" personalisation, warm + decisive.

**Out of scope (v1):**
- Two-way response — Aaron decides via the command center (Dataview TASK checks), not via email reply.
- Generated commitment contracts (P5 territory).
- A dedicated mobile app.
- Multi-recipient briefings (Christy gets her own version of family-only items — defer to v2).
- Real-time chat with the briefing — covered in the future "AI coach" P7.

**Relationship to P2 (threaded tasks).** The accountability line is the killer feature here, and it requires stable `task_id`s. Without P2, "yesterday's commitment" can only be inferred by string-matching descriptions, which is brittle. With P2, it's a clean join: "what was my #1 task in yesterday's command center? what's its current state?"

**Therefore: P4 v0.5 ships with string-match accountability (best effort, marked with a "ⓘ best-effort match" indicator). P4 v1.0 ships after P2 with stable-ID accountability.** Both are useful; the v0.5 version proves the concept while P2 cooks.

The "weekly thread" view similarly degrades gracefully: pre-P2 it uses area-grouping; post-P2 it uses real task threads.

## 3. Architecture

### 3.1 Briefing generator architecture

```
                         ┌─────────────────────────────────────┐
                         │  tools/build_briefing.py            │
                         │  (idempotent, deterministic-first)  │
                         └──────────────┬──────────────────────┘
                                        │
              ┌─────────────────────────┼───────────────────────────┐
              │                         │                           │
              ▼                         ▼                           ▼
       READ inputs                APPLY logic                  WRITE outputs
       ────────────              ─────────────                ──────────────
   MTL  (s3 get)              priority engine                HTML email body
   review-queue.md            energy-window match             Telegram digest text
   last-bd-summary            slip detector                   vault note section
   yesterday's daily note     decision extractor              run log JSON
   99_System/captures/        cross-domain conflict           briefing record JSON
   biohacking nightly        weekly thread builder           (audit at
   sermon-prep state         faith-queue extractor            99_System/state/
   capture envelopes         AI tone-pass (optional)          last-briefing.json)
                             provenance assembly
```

The script runs in three deterministic passes followed by an optional AI tone-pass:

**Pass 1 — Data assembly (no AI).**
Read all sources via existing `tools/build_command_center.py` helpers (refactor: extract them into `tools/briefing_data.py` shared module). Same parsers, same VALID_AREAS, same priority pickers.

**Pass 2 — Decision engine (no AI).**
- `pick_top_priority()` — already exists in build_command_center; reuse.
- `extract_decisions(text)` — regex over the vault for `[decision:: needed]` markers; each decision must declare `[options:: a | b | c]` and `[deadline:: YYYY-MM-DD]`. Up to 3 surface in the briefing.
- `detect_slip(open_tasks, today)` — anything `due < today - 7d` is a slip.
- `detect_cross_domain_conflict(open_tasks, calendar_events)` — count A-tasks per area for today; if any area is >1, flag.
- `match_energy_window(top_priority, energy)` — read latest health envelope from captures; if energy=low and top_priority.estimated_effort=high, *recommend* (don't enforce) a lower-effort A-task swap.
- `build_weekly_thread(open_tasks, week_start)` — group A-tasks by area for the week; show today's #1 highlighted within it.
- `extract_accountability(yesterday_briefing, today_state)` — compare yesterday's claimed #1 to today's MTL state. Pre-P2 best-effort; post-P2 by task_id.
- `extract_faith_items()` — sermon-prep state (a small JSON in `99_System/state/sermon-prep.json` maintained by the faith-life integration skill); prayer queue from `30_Knowledge Library/Bible Studies & Notes/_prayer-queue.md`.

**Pass 3 — Render (no AI).**
Each section renders to HTML + plain text using `string.Template`. The plain text is the deterministic-safe version that gets emailed if the AI tone-pass fails.

**Pass 4 — Tone pass (AI, optional, with fallback).**
Send the deterministic body to OpenRouter (gemma-3-4b free tier — same model used for cheap cascade). Prompt: "Lightly rephrase these section openers in Aaron's voice — warm, decisive, no corporate-speak. Do not change any tasks, dates, or facts." If the AI returns content that doesn't match expected structure (length, sections, fact-anchors) — reject and use the deterministic version.

CLAUDE.md's regex-first rule applies: **the briefing must be valid without AI**. The AI pass is a stylistic polish, never load-bearing.

### 3.2 Sequence — Morning briefing run

```
[cron 6:55am CDT]
   │
   ▼
[oho-runner /build-briefing]
   │
   ├─► tools/build_briefing.py
   │     ├─ assemble data (≈3-5s)
   │     ├─ decision engine (≈1s)
   │     ├─ render (≈1s)
   │     ├─ AI tone pass (≈3s, optional, w/ 5s timeout)
   │     └─ write briefing record (99_System/state/last-briefing.json)
   │
   ├─► return {html, plain, telegram_text, vault_section, provenance_map}
   │
   ▼
[n8n morning-briefing-v3 workflow]
   ├─► Email send (SMTP)
   ├─► Telegram send (HTTP, Aaron's chat)
   ├─► S3 write: today's daily note (if not yet created, daily-note-creator handles section injection)
   └─► (optional) NotebookLM podcast generation kicked off async
```

The new workflow `morning-briefing-v3` is **almost trivial** — n8n's job is just to ferry the runner's output into the channels. All logic lives in Python. This is the P1.5 pattern applied to briefings.

### 3.3 Sequence — Voice digest (optional, opt-in)

```
[Aaron toggles "voice digest" preference]
   ▼
[briefing run completes → record at 99_System/state/last-briefing.json]
   ▼
[Cron 7:15am CDT — separate workflow]
   ▼
[Call notebooklm skill, push briefing as source, request audio overview]
  notebooklm use d056e9d5-64d9-4f64-aa94-faff603de835
  notebooklm source add <briefing-vault-note> --title "OHO Briefing 2026-05-12"
  notebooklm generate audio --notebook <id>
   ▼
[Download audio file → upload to MinIO at 99_System/podcasts/<date>.mp3]
   ▼
[Update private podcast feed XML at 99_System/podcasts/feed.xml]
   ▼
[Aaron's podcast app polls — new episode appears]
```

This uses the **same `d056e9d5-…` authuser=1 NotebookLM workspace** documented in CLAUDE.md. The notebooklm skill already handles the auth + script invocation.

## 4. Data model

### 4.1 Briefing record (the audit trail)

Written to `99_System/state/last-briefing.json` after every successful run, mirroring the brain-dump operator summary pattern from ADR-0006:

```json
{
  "version": 1,
  "run_finished_at": "2026-05-12T11:55:00Z",
  "run_for_date": "2026-05-12",
  "status": "success | degraded | failed",
  "ai_pass_used": true,
  "ai_pass_fell_back": false,
  "channels_sent": ["email", "telegram", "vault-note"],
  "today_top_priority": {
    "capture_id_or_task_id": "task_..._12345",
    "desc": "Echelon offer-page copy",
    "area": "business",
    "priority": "A",
    "due": "2026-05-15",
    "provenance": {
      "file": "10_Active Projects/Active Personal/!!! MASTER TASK LIST.md",
      "line": 87
    }
  },
  "accountability": {
    "yesterday_top": { ... },
    "yesterday_top_state_today": "completed | open | slipped | dropped | unknown",
    "match_quality": "exact_task_id | string_match | none"
  },
  "decisions_surfaced": [
    {
      "id": "decision-2026-05-08-hip-surgery",
      "question": "Proceed with hip surgery in Q3?",
      "options": ["yes", "no", "delay"],
      "ai_suggested": "yes",
      "deadline": "2026-05-15",
      "provenance": { "file": "...", "line": ... }
    }
  ],
  "slip_count": 3,
  "cross_domain_conflict_detected": true,
  "energy_window": "low",
  "energy_source": "oura_recovery_47",
  "weekly_thread": {
    "rocks_advancing": 3,
    "rocks_total": 5,
    "rocks_at_risk": ["faith"]
  },
  "faith_items": {
    "sermon_days_until": 2,
    "prayer_queue_count": 4
  },
  "html_length": 1842,
  "plain_length": 487,
  "telegram_length": 312
}
```

The Daily Command Center reads `99_System/state/last-briefing.json` to surface the briefing's decisions in the "Do This First" callout — closing the loop between the email surface and the in-vault surface.

### 4.2 Decision marker format (vault convention)

For decisions to be picked up by `extract_decisions()`, Aaron writes them in a vault file (typically `10_Active Projects/Decisions/` or inline in a project note):

```markdown
- [ ] [decision:: needed] Should I proceed with hip surgery in Q3?
  [options:: yes | no | delay]
  [deadline:: 2026-05-15]
  [context:: [[Hip Decision - Context]]]
  [ai_suggest:: yes]
```

Once Aaron resolves: change to `- [x] [decision:: yes]` and the briefing stops surfacing it.

This is consistent with the canonical task format — same `[k:: v]` discipline, processable by Dataview, machine-readable for the briefing.

## 5. Failure modes + guardrails

| Failure | Symptom | Guardrail |
|---|---|---|
| AI tone-pass returns invalid HTML | Email garbled | Validator checks: section count, fact anchors, link integrity; failure → deterministic fallback |
| AI hallucinates a fact | Wrong claim in briefing | Every fact has a provenance anchor in the briefing record; if AI removes/changes anchors, fallback |
| Energy data unavailable | Briefing wrongly assumes "default" energy | Energy window = `unknown` (not `high` or `low`); briefing renders without energy-aware advice |
| Yesterday's briefing missing | No accountability line | Render as "First briefing — no prior commitment to check"; not an error |
| MTL parse fails | No tasks rendered | Briefing fails-loud: sends an email titled "⚠ Briefing failed — MTL unreadable" with stderr tail |
| Decisions count >3 | Important ones buried | Surface top 3 by deadline proximity; remaining in a `[!example]-` collapsed section of the command center |
| No `[decision:: needed]` markers exist | Section empty | Renders the section with "No active decisions — capture one with `[decision:: needed]`" — keeps the muscle warm |
| Faith state file missing | Section empty | Renders empty section, doesn't crash; weekly digest flags the missing state |
| NotebookLM podcast generation fails | No audio for the day | Logged; email still sent; no retry until next day |
| Telegram chat unreachable | No mobile ping | Email succeeds; failure logged; weekly digest flags pattern |
| Briefing run takes >60s | n8n task-runner stall (CLAUDE.md task-runner-slots constraint) | Runner timeout = 90s with hard kill; deterministic fallback runs in <10s, so a 60s+ run means AI is stuck — kill it, run fallback, send |

## 6. Privacy + security

**Faith content.** Prayer queue items often contain sensitive names. The briefing renders prayer items as initials by default (`Pray for J. on Wednesday`); full names live in the vault but never in email or Telegram. Configurable per-item with `[render:: full-name]`.

**Decision content.** Some decisions are private (hip surgery, work transitions). Each decision marker can carry `[private:: true]` — those render as "1 private decision needs attention. See command center." in the email; full text only in the vault. Default is non-private.

**Telegram channel.** Telegram's data residency is non-trivial. Aaron's briefing is sent to *his own* Telegram chat (bot → Aaron). Bot tokens are stored in n8n credentials (encrypted at rest). The Telegram digest never carries decision-text for `[private:: true]` decisions; it just signals their existence.

**Voice digest.** NotebookLM is Google's, not local. Aaron's briefing — including yesterday's commits, decisions, prayer items — is uploaded to NotebookLM if the voice digest is enabled. Default: voice digest is **off**. Aaron opts in explicitly. If on, prayer items render with initials only in the briefing source (i.e., NotebookLM gets the same redacted version).

**Provenance links.** The briefing email includes file paths but never the file *content*. Aaron clicks through to Obsidian (via `obsidian://open?...`) to see the source. Email body stays small and leak-resistant.

## 7. Acceptance criteria

- `tools/build_briefing.py` exists; idempotent; runs in <10s deterministic, <15s with AI pass.
- `POST /build-briefing` on oho-runner returns the briefing record.
- Email length: HTML body ≤ 12KB, ≤ 200 words of prose (excluding tables); plain-text mirror ≤ 800 chars.
- Telegram digest ≤ 320 chars (fits in 1 message).
- Vault daily note section "🌅 Today's Briefing" is injected into today's daily note (if it exists; otherwise the daily-note-creator picks it up).
- Today's #1 task is always shown with provenance (file + line).
- Accountability line renders correctly when yesterday's briefing exists; renders graceful empty state when not.
- Up to 3 `[decision:: needed]` markers are surfaced; private ones masked.
- Slip detection surfaces overdue-by->7-days items with do/delegate/drop options (rendered as Dataview-checkable lines in the command center; the email just summarises the count).
- Cross-domain conflict detection flags when an area has >1 A-task due today vs the weekly cap.
- Energy-window match runs when biohacking captures are present in the last 24h.
- Weekly thread view shows rocks advancing/at risk.
- Faith section renders (sermon countdown, prayer count) when state files exist.
- AI tone-pass has a hard 5s timeout; deterministic fallback kicks in on timeout or invalid output.
- Briefing record JSON written to `99_System/state/last-briefing.json`; the command center reads it.
- Provenance audit: every claim in the briefing has either a file+line anchor OR explicit "AI tone-pass — no claim added" tag.
- pytest suite covers: data assembly, every decision-engine function, render fallbacks, AI tone-pass validation, energy-window matching, accountability matching.
- No new code-heavy cron slot is consumed at minute :30, :03, :13, :23, :33 (CLAUDE.md task-runner constraint). Briefing runs at `:55` (currently unused) — explicitly tested via the existing `tests/test_workflow_templates.py::test_code_heavy_workflows_do_not_share_cron_minutes`.

## 8. Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AI tone-pass drifts into sycophancy / corporate-speak | M | M | Validator rejects briefings with banned phrases ("seamlessly", "robust", "leverage", "deliver value"); deterministic body is the baseline |
| Aaron gets briefing-fatigue and starts ignoring email | M | H | Telegram + voice digest channels — different surfaces for different days; weekly digest tracks "did Aaron open the briefing" via a tracking pixel (opt-in) |
| Decisions surfaced are stale (Aaron forgot to mark resolved) | M | M | Decisions older than `deadline + 14d` are auto-archived with reason="auto-archived stale"; surfaced in weekly digest |
| Energy window is wrong on a recovery day Aaron doesn't agree with | L | L | Energy window is a *suggestion*, never enforcement; Aaron can override with `[ignore_energy:: today]` in his daily note |
| Cross-domain conflict false positives (e.g., calendar event was an old TBD) | M | L | Calendar events older than 7d → ignored; only confirmed events within 48h are counted |
| Provenance links break (file moved) | M | M | Briefing record stores both path AND content-hash; broken-link audit runs weekly |
| NotebookLM podcast costs/quota | L | L | Voice digest opt-in; quota stays well within free tier |
| Briefing renders without P2 → accountability is sketchy | H | M | Marked explicitly "ⓘ best-effort match" until P2; tests for both modes exist day one |

## 9. Dependencies

- **P1 + P1.5 + ADR-0006 soak through 2026-05-18.** Hard gate.
- **P3.A (envelope + endpoint) in prod.** Briefing reads capture envelopes for the energy window and decision context.
- **P2 (threaded tasks)** for full-fidelity accountability. P4 v0.5 ships pre-P2; P4 v1.0 requires P2.
- **Sermon-prep state file** at `99_System/state/sermon-prep.json` (small — defaults to "no sermon scheduled" if absent; faith-life integration skill maintains).
- **Prayer queue** at `30_Knowledge Library/Bible Studies & Notes/_prayer-queue.md` — must exist with `- [ ]` items.
- **OpenRouter key** (already in `.env`) — same one used by AI cascade in P3.
- **Telegram bot token** (already in n8n credentials for telegram-capture).
- **NotebookLM CLI** (already installed; voice digest requires).

## 10. Parallel sub-lanes within P4

| Lane | Sub-scope | Sequencing |
|---|---|---|
| **P4.A — Data + decision engine** | `tools/build_briefing.py` skeleton, all deterministic logic, briefing record schema, pytest suite | **First** — must produce a working deterministic briefing before any AI |
| **P4.B — Render + email channel** | HTML email template, plain-text fallback, vault note injection, `/build-briefing` endpoint, new n8n workflow `morning-briefing-v3` | **Second** — sends the briefing to email + vault |
| **P4.C — Tone pass + AI validation** | OpenRouter prompt, validator, fallback path | **Third** — purely additive; can ship after B is live |
| **P4.D — Telegram digest + voice digest** | Telegram channel, NotebookLM hook, podcast feed | **Fourth** — extra channels; ship when A-C are clean |

P4.A and P4.B can ship together as P4 v0.5 (deterministic-only, email + vault); P4.C upgrades to v0.7 (AI-polished); P4.D unlocks v1.0 (multi-channel).

## 11. Effort

| Lane | Engineering days |
|---|---|
| P4.A | 4 | Decision engine is the hard part; lots of small functions |
| P4.B | 2 | Templates + n8n shell |
| P4.C | 2 | Validator + prompt-eng |
| P4.D | 2 | Telegram is small; voice digest is mostly notebooklm CLI scripting |
| **Total** | **10** | About 2 calendar weeks |

## 12. Verification strategy + sample tests

**Unit:**
- `tests/test_build_briefing.py`: data-assembly, decision extraction, slip detection, energy match, cross-domain conflict, weekly thread, faith items.
- `tests/test_briefing_render.py`: HTML + plain + Telegram length budgets, banned-phrase filter, fact-anchor preservation.
- `tests/test_briefing_fallback.py`: AI returns garbage → deterministic ships; AI times out → deterministic ships; AI returns valid → AI ships.
- `tests/test_briefing_accountability.py`: pre-P2 best-effort string match; post-P2 task_id match (skipped until P2).

**Integration:**
- `tests/integration/test_briefing_e2e.py`: write known MTL + decisions + capture envelopes; trigger `/build-briefing`; assert email content matches snapshot.
- `tests/integration/test_briefing_idempotency.py`: same inputs → same briefing record bytewise.

**Audit:**
- `scripts/audit_briefings.py`: nightly check that yesterday's briefing record exists and has provenance anchors for every claim; flag any with `match_quality=none` for >3 consecutive days.

**Manual UAT:**
- Receive the email for 3 days in a row and rate (1-5) on: (1) did the ONE thing feel right, (2) did the accountability line match reality, (3) did the energy window feel right.
- After 14 days of soak, the per-day score should average ≥ 4.0.

## 13. Open questions (for Aaron)

1. **What time should the briefing land?** Current morning-briefing runs at 7:30am CDT. Earlier (6:00am) catches your before-shower window; later (7:30am) catches commute. Suggest 6:30am to land before kids wake.
2. **Telegram digest — do you want it daily or only on "bad-energy / conflict / slip" days?** Always-on builds the habit; conditional avoids noise.
3. **Voice digest — opt-in default off?** I've been assuming yes.
4. **For decision-default suggestions: do you want the AI to *pick* a default ("AI suggests: yes") or just lay out options?** Picking is more decision-instrument; laying-out is more neutral.
5. **Faith-prayer-queue render: initials only, or full names if you mark `[render:: full-name]`?** I lean toward initials default + explicit opt-in for full names.
6. **Cross-domain conflict cap: how many A-tasks per day is "too many"?** Current draft: 1 per area, 3 total. Adjustable.
7. **Should the briefing include a Christy-facing version (family-only items)?** Defer to v2 — Christy version is a 2-week project on its own.

---

# PART C — Cross-Phase Integration

Every P3 capture surface feeds the P4 briefing along a specific path. This section shows the explicit mapping so we can verify the integration end-to-end.

| P3 Surface | What it contributes to the P4 briefing |
|---|---|
| **Telegram /task** | Inbound A/B/C tasks → MTL → today's #1 candidate, weekly thread, accountability source |
| **Telegram /note** | Quick notes don't drive briefing directly but show in command center; ratio of notes vs tasks per day is a "captured-yesterday" signal in the briefing |
| **Telegram /article** | Article queue size shown in the "weekly thread" section as a signal of unprocessed reading |
| **Telegram voice memo** | Transcript becomes a brain-dump entry; high-priority transcripts that mention "decide", "vs", "options" auto-tag as `[decision:: candidate]` for human review and possible promotion to the decisions section |
| **Email forward** | Subject hints feed area/priority directly. Email threads with `[decision]` in subject → auto-create `[decision:: needed]` markers in `10_Active Projects/Decisions/<date>-<slug>.md`. **This is the single biggest decision-instrument feeder** |
| **Voice memo (phone)** | Same as Telegram voice but offline-tolerant. Used for "shower thoughts" → tomorrow's #1 |
| **Voice memo (watch)** | Lower-quality transcripts → review queue. Briefing surfaces "3 captures need a look" in the command center, not the email |
| **Share-sheet / bookmarklet** | URL captures fill the article queue; article-count in weekly thread |
| **Coding-session quick-add** | Project-context tasks → MTL with high `[priority]` accuracy (Aaron knows what he meant). Often feeds today's #1 directly. Provenance: agent + session marker |
| **Wearable wellness auto-capture** | Sleep/HRV/recovery → energy-window field in briefing record → recommended A-task swap. **Direct line from biology to today's decisions.** |

**Provenance closure:** when the briefing says "Today's #1 — Echelon offer-page copy", Aaron can click through to the task in MTL, which has `[source:: [[capture-2026-05-11-voice-phone]]]` linking to the original voice memo. He can then play back the OGG to verify he meant what the transcript says. **End-to-end auditable.**

**Decision audit closure:** when the briefing surfaces a decision, the decision marker carries `[context:: [[Decision Source]]]`. Source can be: a vault note (manual), an email thread (auto-created from `[decision]` subject), or a voice memo's interpretation. The morning briefing's decision section always shows the source link.

**Energy-window closure:** when the briefing says "energy: low, recommended task swap", the captures section of the briefing record names the source envelope (`source: biohacking-pipeline`, `received_at: 2026-05-12T04:30:00Z`). Aaron can verify the Oura input that drove the recommendation.

---

# Risks across P3 + P4 combined

| Risk | Mitigation |
|---|---|
| Aaron over-captures → noise → briefing degrades | Weekly digest tracks capture-volume; if >50/day for a week, suggest a per-source rate limit |
| Aaron under-captures → briefing is thin | Briefing thinness itself surfaces this — "no captures yesterday" line in the briefing prompts reflection |
| AI cascade in P3 misroutes → P4 surfaces wrong items | Confidence bands + review queue prevent auto-routing; review queue shown in P4 briefing |
| Time-zone bugs (P3 captures vs P4 today's-date logic) | All envelopes UTC; all renderers America/Chicago-aware; `tests/test_timezone.py` covers crossover boundaries |
| Briefing depends on P3 envelope but P3 endpoint is down | Briefing degrades gracefully — no energy info, no decision auto-extraction; deterministic core still ships |

---

# Sequencing summary

```
Week 1-2:  P3.A (envelope + endpoint)
Week 2:    P4.A (data + decision engine) starts in parallel — same dev OR second dev
Week 3:    P3.B (Telegram v2) + P4.B (render + email channel) ship → first end-to-end briefing
Week 4:    P3.C (email/share/voice) + P4.C (AI tone pass)
Week 5:    P3.D (wearable + agent-quick-add refactor) + P4.D (Telegram + voice digest)
Week 6:    Soak — both phases running, audit script runs nightly
Week 7+:   P2 (threaded tasks) work begins — at which point briefing accountability upgrades to v1.0
```

If Aaron prioritises briefing impact: **ship P3.A + P4.A + P4.B in week 1-2** for an immediate decision-ready email. Telegram extensions and voice come after.

If Aaron prioritises capture coverage: **ship P3.A + P3.B + P3.C in weeks 1-3** for broad capture, then P4 layers on top.

The spec supports both orderings because the integration is by envelope, not by build order.

---

# Open questions (consolidated, for Aaron)

P3:
1. Capture email address — keep 33mail forwarder or stand up `capture@oho.aarondy.com`?
2. Whisper provider — local default or API default?
3. Email allowlist — restricted or open?
4. Telegram merge window — 60s / 90s / 120s?
5. Wearable capture — always-on or opt-in per-day?
6. Telegram `/undo` in v1 or v2?

P4:
7. Briefing time — 6:00 / 6:30 / 7:30am CDT?
8. Telegram digest cadence — daily or only-when-actionable?
9. Voice digest — opt-in default off?
10. Decision AI suggestions — pick a default or lay out options?
11. Prayer queue render — initials default or full-name default?
12. Cross-domain A-task cap — 1 per area, 3 total?
13. Christy-facing family briefing v2 timing?

Cross-phase:
14. If both phases are in flight simultaneously, do you want a single dev (you) sequencing them, or are you bringing the agent guild (polychronos-team) in to parallelise?
15. Should P3.A + P4.A go through `gsd-plan-phase` for the formal phase plan, or stay design-first and skip the GSD wrapper?

---

# Files this design implies (not created by this spec — listed for the future implementation phase)

**New tooling:**
- `tools/build_briefing.py`
- `tools/briefing_data.py` (shared with build_command_center)
- `tools/capture_envelope.py` (pydantic schema + validators)
- `tools/inference_cascade.py` (regex + AI tier)
- `tools/redaction.py`

**New runner endpoints (in `services/oho_runner/app.py`):**
- `POST /capture`
- `POST /build-briefing`

**New sidecar service:**
- `services/whisper_sidecar/` (FastAPI wrapper around whisper.cpp with OpenAI Whisper API fallback)

**New scripts:**
- `scripts/audit_captures.py`
- `scripts/audit_briefings.py`

**New workflows:**
- `workflows/n8n/telegram-capture-v2.json`
- `workflows/n8n/morning-briefing-v3.json`
- `workflows/n8n/voice-digest.json`

**New Cloudflare Worker:**
- `infra/cloudflare-email-worker/` (TS/JS — Cloudflare Worker source + wrangler config; NOT in the runner)

**New Apple Shortcuts (documented, exported as `.shortcut` blobs):**
- `OHO Voice Capture`
- `Share to OHO`
- `OHO Watch Dictation`

**State files (vault):**
- `99_System/state/capture-idempotency.json`
- `99_System/state/last-briefing.json`
- `99_System/state/sermon-prep.json`
- `99_System/captures/<date>/<capture_id>.json` (rolling)

**Tests** (per acceptance-criteria sections above).

**Docs to update:**
- `CLAUDE.md` — register new endpoints, cron slot at `:55`, capture envelope contract
- `docs/RUNBOOK.md` — operator procedures for new failure modes
- `AGENTS.md` — Codex/OpenAI mirror of capture commands
- `docs/AI_TOOLING.md` — register Whisper sidecar and any new MCP touchpoints
- A new ADR — `docs/adr/0007-capture-envelope.md` — should be authored when implementation begins

---

_End of design spec._

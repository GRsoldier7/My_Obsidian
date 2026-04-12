# ObsidianHomeOrchestrator — Full Memory Snapshot
**Date:** 2026-04-12 | **Branch:** polish/prod-ready | **Commits this session:** 48f6631, c25a279, 69137af, b8c673a, cebbdcf, 1498829, 5a684f7

---

## WHO IS AARON (User Profile)

Aaron runs ObsidianHomeOrchestrator as the automation layer for his personal Life OS. 8 life domains: faith, family, business, consulting, work, health, home, personal. Day job: BAM (Business Analytics Manager) at Parallon. Side: Echelon Seven startup, AI/automation consulting.

**What he wants from Claude:** Root cause analysis, not symptom patches. Real fixes verified on live infrastructure. Memory + NotebookLM updated so future sessions don't re-discover context. Parallel tool calls, fast execution.

**Hard rule:** If a prior session "passed it off as working" he expects the next session to verify, not trust.

---

## SYSTEM ARCHITECTURE

- **n8n:** Proxmox LXC CT-202 at `http://192.168.1.121:5678`
- **MinIO:** Docker on MiniPC at `http://192.168.1.240:9000` | bucket: `obsidian-vault` (no prefix)
- **Deploy:** `python3 /tmp/deploy_workflows.py` (NOT setup-n8n.sh — find_cred_id is unreliable)
- **MinIO cred in n8n:** `z9qTyG2NVVbhHkg0` (name: "MinIO S3") — the ONLY one OHO workflows reference
- **SMTP cred:** `lWGOwsktldwb3iEj` | **OpenRouter cred:** `Z7liUYc3Toq3q7W7`
- **Error handler workflow ID:** `jIOFmhr37mXEhlHz`
- **NotebookLM notebook:** `a428969b-c3f1-480b-b54c-876974650674` (OHO Life OS Project Memory)

---

## WHAT WAS FIXED THIS SESSION (Short-Term Memory)

### Overnight Failure Cascade — Root Causes Found and Fixed

**Root Cause 1 — Dead MinIO credential never re-applied (commit 48f6631)**
- Credential `z9qTyG2NVVbhHkg0` had stale secret. Prior session patched repo JSON but never deployed to n8n.
- Fix: PATCH credential via n8n API with current `.env` keys. Re-deploy all 11 workflows.

**Root Cause 2 — n8n executionOrder v1 double-execution (commit 48f6631)**
- `system-health-monitor` + `weekly-digest-v2` had parallel S3 reads both wiring into one downstream node — ran twice per execution (2x emails, 2x logs, 2x Sunday digests).
- Fix: chain S3 reads sequentially so merge node sees single input.

**Root Cause 3 — n8n filesystem-v2 binary storage (commit c25a279)**
- `Buffer.from(bin.data, 'base64')` decoded the string `"filesystem-v2"` into garbage — ALL S3 reads returned empty content silently. Dashboard showed 0 tasks. Overdue alerts showed nothing. Morning briefing parsed 0 tasks.
- Fix: `await this.helpers.getBinaryDataBuffer(0, 'data')` in every Code node. Also added Decode MTL intermediate node for indirect reads (morning-briefing, vault-health-report).
- Verified via webhook test: 39 tasks read correctly.

**Root Cause 4 — email→log sequential wiring (Codex fix, landed commit 69137af)**
- Log nodes downstream of `emailSend` output → log filenames became `*-undefined.json` because email doesn't reliably pass JSON fields through.
- Fix: Build node fans to Email AND log-writer simultaneously (parallel, not sequential). Email is a dead-end with no downstream.
- Guardrail: `scripts/audit_workflow_connections.py` blocks this pattern. `tests/test_workflow_templates.py` enforces it.

**Root Cause 5 — setup-n8n.sh swallowing failures (Codex fix, landed commit 69137af)**
- `|| echo '{}'` masked partial deploys silently.
- Fix: fail-fast error handling throughout. `audit_workflow_credentials.py` validates credential hygiene.

### Phase 0 Open Bugs Fixed (commit 5a684f7)

**Daily note creator — IF node typeValidation: strict**
- `Not Exists?` compared `$json.error` (object/undefined) against string type with strict validation → always routed to skip branch → notes for Apr 11, 12 never written.
- Fix: `typeValidation: strict` → `typeValidation: loose`.

**Live dashboard callouts not persisting**
- `Should Write?` IF node checked `$json._skip !== true` with strict bool. When dashboard builds normally, `_skip` is undefined → strict comparison fails → S3 write always skipped → old plain-markdown version stayed in MinIO.
- Fix: removed `Should Write?` entirely. Build Dashboard already has early-return `_skip: true` for MTL failures. Wired Build Dashboard directly to S3: Write Dashboard.
- **Verified live:** `[!tip]` and `[!abstract]` confirmed in MinIO at 19:00 UTC.

**Article enricher queue starvation**
- `toProcess.slice(0, 8)` always picked first 8 URLs — Facebook/X blocked links at position 1–4 permanently, blocking 100+ legitimate URLs.
- Fix: `toProcess.slice().sort(() => Math.random() - 0.5).slice(0, 8)` — randomized batch.
- Verified in Node.js: 61 URLs processed correctly, batch of 8 returned.

### Brain Dump Reset — Full Rebuild (commit 069131a)
- Old approach: regex to clear emoji section headers — broke on every file.
- New approach: extract H1 title + tags from current file → rebuild entire canonical 7-section template from scratch → write back. `status: empty` in frontmatter.
- Applied immediately to 5 dirty brain dumps (Business, Personal, Coding, Bible post, Website & Business). 11 lost tasks recovered to MTL.

### Live Dashboard — Obsidian Callouts (commit 069131a)
- Rewrote Build Dashboard with 9-section Obsidian callout hierarchy:
  - `[!tip]` → #1 Priority CTA (computed)
  - `[!danger]` → Overdue (severity tiers)
  - `[!warning]` → Due Today + undated Priority A
  - `[!info]` → Upcoming 7 days (collapsed)
  - `[!note]` → Q2 Rocks with live Priority A count (collapsed)
  - `[!abstract]` → Domain Pulse table (collapsed)
  - `[!success]` → Quick Wins (collapsed)
  - `[!example]` → System Status (collapsed)

---

## DURABLE PATTERNS (Long-Term Memory)

### n8n Binary Reads — filesystem-v2 Mode
ALL S3 download content must be read with `await this.helpers.getBinaryDataBuffer(0, 'data')`. Never `Buffer.from(bin.data, 'base64')` — in filesystem-v2 mode, `bin.data` is the string `"filesystem-v2"` not base64 content. The binary data is on disk, not inline.

For INDIRECT reads (Code node not directly after S3 download): insert a "Decode X" intermediate Code node that reads binary and stores text in `json._text`. Downstream Code nodes use `$('Decode X').first().json._text`.

### n8n Parallel Fan-Out Pattern (Email Must Be Dead-End)
Correct topology:
```
Build Node → [Email (dead-end), Build Log → Convert → S3 Write Log, Convert Note → S3 Write Note]
```
Email must have NO downstream connections. `audit_workflow_connections.py` enforces this. `test_workflow_templates.py` prevents regression.

### n8n IF Node — typeValidation
Use `typeValidation: loose` for any existence check on `$json.error` or `$json._skip`. Strict validation fails silently when the actual type doesn't match the declared type, routing to the wrong branch with no error.

### n8n Double-Execution Rule
With `executionOrder: v1`, any node with 2+ incoming connections from different upstream branches runs ONCE PER BRANCH. Always chain S3 reads sequentially. Never wire two nodes into the same downstream unless using an explicit Merge node.

### n8n Cron is UTC
`scheduleTrigger` cron expressions are UTC. `settings.timezone` only affects display. CDT = UTC-5:
- 7AM CDT → `0 12 * * *`
- 6AM CDT → `0 11 * * *`
- 5PM CDT Friday → `0 22 * * 5`

### continueOnFail Everywhere
Every S3, HTTP, SMTP node needs `continueOnFail: true`. Missing it on any single node causes the global error handler to fire → error email. With 12 workflows running hourly, even 1% failures = inbox noise.

### MinIO Credential
When S3 ops fail mysteriously: first PATCH credential `z9qTyG2NVVbhHkg0` via `PATCH /api/v1/credentials/z9qTyG2NVVbhHkg0` with current MINIO_ACCESS_KEY/SECRET from `.env`. Don't create a new one — orphans all workflow references.

### Deploy Pattern
Always use `/tmp/deploy_workflows.py` (hardcoded cred IDs, PUT to live n8n). Never rely on `setup-n8n.sh`'s `find_cred_id` — it silently fails. After deploy, spot-check one workflow's deployed node code via n8n API to confirm the update took.

### Brain Dump Reset
After extraction: rebuild FULL template from scratch (H1 title + tags extracted from original, all 7 canonical sections restored with placeholder comments, frontmatter: `status: empty`, `last_processed: today`). NEVER use regex on emoji section headers.

---

## IMPLEMENTATION ROADMAP (4 Phases)

### Phase 0 — P0 Bugs ✅ DONE
1. Daily note IF node → typeValidation: loose ✅
2. Article enricher queue starvation → randomized batch ✅
3. Dashboard callouts → removed broken Should Write? node ✅

### Phase 1 — Stabilize (Next)
- [ ] Verify brain dump extraction + reset at tomorrow's 7AM CDT run
- [ ] Verify morning briefing email has real task counts
- [ ] Add undated Priority A reminder section to daily note template
- [ ] Build `scripts/archive-completed-tasks.py` (move `- [x]` to monthly archive)

### Phase 2 — Weekend Planner (New Feature)
**Trigger:** Friday 5PM CDT (`0 22 * * 5` UTC)
**Manual pre-req:** Google Calendar OAuth2 in n8n UI → `GCAL_CRED_ID` in `.env`
**Hard-coded:** Sunday 8:30–11:30 AM = church BLOCKED
**New files:** `workflows/n8n/weekend-planner.json`, `tests/test_weekend_planner.py`, `docs/google-calendar-setup.md`
**Outputs:** HTML email (morning-briefing style) + Obsidian vault note at `40_Timeline_Weekly/Weekend/YYYY-MM-DD-weekend-plan.md`
**Slot structure:** Sat deep work 8-12AM (business) → afternoon home/health → evening family/faith → Sun pre-church 8-8:30AM → POST-CHURCH 12-2PM faith/family → afternoon home/personal

### Phase 3 — Long Tail
Telegram bot, v1 legacy workflow cleanup, Bitwarden MCP, article enricher v2 with failure-count state tracking, GCal write.

### Never Implement
Playwright NotebookLM auth, regex brain dump reset, email→log sequential wiring, Dataview in vault notes, hardcoded Q2 percentages, `|| echo '{}'` in deploy scripts.

---

## CURRENT SYSTEM HEALTH

| Layer | Score | Notes |
|-------|-------|-------|
| Infrastructure | 🟢 95% | 0 errors in last 5 executions |
| Code quality + tests | 🟢 90% | 135 tests, 2 audit scripts |
| Daily note creation | 🟡 ? | Fix deployed; verify tomorrow 6AM CDT |
| Dashboard callouts | ✅ 100% | Confirmed live 19:00 UTC [!tip] present |
| Article enrichment | 🟡 ? | Fix deployed; verify 20:00 UTC run |
| Brain dump extraction | 🟡 60% | Verify tomorrow 7AM CDT |
| Morning briefing | 🟡 50% | Verify tomorrow 7AM CDT |
| MTL tasks (50 open) | 🟢 | 11 tasks recovered from brain dumps |
| **Overall** | **🟡 65%** | Up from 55% — Phase 0 fixes land |

---

## WHAT TO VERIFY NEXT SESSION

1. `40_Timeline_Weekly/Daily/2026-04-13.md` exists in MinIO at 6AM CDT → daily note IF fix worked
2. `00_Inbox/articles-to-process.md` has `[title::]` entries → article enrichment fix worked
3. Brain dump files in MinIO: `status: empty` after 7AM CDT → extraction + reset working
4. Morning briefing email at 7AM CDT has real overdue/due-today task counts (not zero)
5. Error handler (`jIOFmhr37mXEhlHz`) had ZERO new firings since Phase 0 deploy

---

## NOTEBOOKLM AUTH

**Notebook:** `a428969b-c3f1-480b-b54c-876974650674`
**Auth method:** browser_cookie3 (NOT Playwright — Google blocks it)
```bash
source ~/.notebooklm-venv/bin/activate
~/.notebooklm-venv/bin/python3 scripts/notebooklm-auth.py
notebooklm auth check
```
Cookies expire every 7-30 days. Re-run auth script when check fails.

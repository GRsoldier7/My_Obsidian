# Hygiene + Carry-Forwards Spec — 2026-05-12

**Context.** P1 + P1.5 + ADR-0006 are live in prod and inside the 7-day soak window (clean through 2026-05-18). The 6 items below are the explicit "Pending (carry-forward…)" list from `CLAUDE.md` plus the agent-orch-lxc GitGuardian item. None of them touch the brain-dump pipeline, the OHO runner sidecar, the daily command center generator, or the receipt audit — so all 6 can ship **in parallel with the soak**.

**Scope discipline.** This spec is read-only with respect to the soak gate: nothing here may modify `tools/bd_integrity.py`, `tools/process_brain_dump.py`, `services/oho_runner/`, `tools/build_command_center.py`, the live n8n workflows for brain-dump-processor-v2 / morning-briefing / live-dashboard-updater, or the deploy orchestrator. The `--no-reset` deprecation (item 4) is the one exception and is explicitly gated on the soak clearing.

Mini-spec format per item: **Why · Pre-conditions · Steps · Verification · Risks · Effort · Aaron-action-required? · Parallel-safe?**

---

## Item 1 — GCAL OAuth2 → `GCAL_CRED_ID` → Weekend Planner re-deploy

**Why.** `weekend-planner.json` ships with `__GCAL_CRED_ID__` placeholders on both `gcal-saturday` and `gcal-sunday` nodes; the workflow is INACTIVE until a real credential ID hydrates the placeholder. Friday 5PM CDT briefing is currently dark.

**Pre-conditions.**
- A Google account whose calendar Aaron actually wants summarised (likely his primary + any shared family/work calendars).
- n8n reachable at `http://192.168.1.121:5678` and credential-write access.
- `.env` writable on the dev machine.
- `setup-n8n.sh` / `deploy_workflows.py` already understands `__GCAL_CRED_ID__` (it does — same pattern as `__MINIO_CRED_ID__`).

**Steps.**
1. In Google Cloud Console (Aaron's personal GCP project, or create one named `oho-n8n`): enable **Google Calendar API**, create an **OAuth 2.0 Client ID** of type **Web application**, and add the n8n callback URL: `http://192.168.1.121:5678/rest/oauth2-credential/callback`. Authorized JS origin: `http://192.168.1.121:5678`. Copy the client ID + secret.
2. In n8n UI → **Credentials → Add Credential → "Google Calendar OAuth2 API"**. Paste client ID + secret. Set **OAuth Scope** to exactly: `https://www.googleapis.com/auth/calendar.readonly` (least privilege; matches `docs/google-calendar-setup.md`). Complete the OAuth dance with the chosen Google account. Name the credential exactly **`Google Calendar`** (downstream audit-friendly).
3. Copy the credential ID from the URL: `http://192.168.1.121:5678/credentials/<ID>/edit`.
4. Append to `.env` on the dev box (not committed): `GCAL_CRED_ID=<ID>`.
5. Re-hydrate + re-deploy just this workflow:
   ```bash
   set -a && source .env && set +a
   python3 scripts/deploy_workflows.py weekend-planner   # or bash scripts/setup-n8n.sh
   ```
6. In n8n UI, open the imported workflow (live name may have an emoji prefix per MEMORY note) and confirm both GCal nodes show credential `Google Calendar` (not the placeholder string).
7. Activate the workflow.

**Verification.**
- Manually trigger the workflow. Expected output: HTML+text email to `NOTIFICATION_EMAIL` and a vault note under `40_Timeline_Weekly/Daily/` or wherever the workflow writes its note. The two GCal nodes either return events or — because they're configured `continueOnFail: true` — return empty and the email shows "No events scheduled."
- Run `python3 scripts/audit_workflow_credentials.py` — must remain OK (this audit doesn't touch GCal but we're not regressing the S3 audit).
- After Friday 5PM CDT, confirm scheduled run fires (check `99_System/logs/weekend-planner-<date>.json`).

**Risks.**
- **Token expiry.** Google refresh tokens for OAuth-installed apps don't auto-rotate in n8n's flow; if Aaron revokes app access from his Google account the workflow silently 401s. Mitigation: error-handler workflow already catches node failures.
- **Calendar share permissions.** If the family / spouse calendar isn't shared with the authorising account, those events won't appear. Workflow must use the right account on the OAuth screen.
- **Rate limit.** Calendar API free quota is generous (1M req/day); two calls per Friday is trivial. Non-issue unless someone adds a per-minute schedule.
- **Wrong calendar ID.** Workflow defaults to `primary`. If Aaron wants a non-primary calendar, edit the workflow JSON's `calendar.id` BEFORE step 5.

**Effort.** S (15-30 min, dominated by OAuth-app creation in GCP).

**Aaron-action-required?** YES — only Aaron can complete the OAuth consent screen with his Google credentials. An agent cannot impersonate the human in the browser.

**Parallel-safe?** Y — touches a separate workflow and a new env var. Does not interact with the brain-dump pipeline or the runner sidecar.

---

## Item 2 — OpenRouter API key rotation

**Why.** Routine hygiene. The key currently powers the ai-brain sub-workflow (Llama 3.3 70B + gemma + nemotron cascade) and is referenced by `OPENROUTER_API_KEY` in `.env`. Long-lived keys with no rotation policy are an OWASP A07 finding waiting to happen.

**Pre-conditions.**
- Aaron has access to https://openrouter.ai/settings/keys.
- The current key still works (no incident-driven rotation).
- A list of every consumer (this spec enumerates them — see Verification).

**Steps.**
1. **Generate new key.** OpenRouter dashboard → create a new key named `oho-n8n-2026-05` (date-stamped for future audit). Leave the old key **active**.
2. **Add as a second n8n credential.** In n8n UI → Credentials → duplicate or create a new HTTP Header Auth credential with header `Authorization: Bearer <NEW_KEY>`. Name it temporarily `OpenRouter API (new)`. Note its ID.
3. **Update `.env`** locally: `OPENROUTER_API_KEY=<NEW_KEY>`.
4. **Swap on the sub-workflow.** The ai-brain workflow is the single consumer pattern; downstream workflows call it. Open ai-brain in n8n, repoint the OpenRouter HTTP node to the new credential, save, and run a manual test (invoke from another workflow with a `classify` job). Confirm a 200 from OpenRouter and the cascade returns text.
5. **Rename credentials** so the audit story stays clean: rename `OpenRouter API` → `OpenRouter API (old, revoke after 2026-05-19)`, then rename `OpenRouter API (new)` → `OpenRouter API`. n8n credential IDs do not change on rename.
6. **Soak 24-48h.** Watch for failures in `99_System/logs/ai-brain-*.json` and the consumer logs (telegram-capture, brain-dump-processor-v2 fallback, morning-briefing if AI triage is enabled).
7. **Revoke old key.** OpenRouter dashboard → delete the old key. Update `.env.example` if any commentary references key naming.
8. **Re-run audits.** `make audit-ai-tooling` and `python3 scripts/audit_workflow_credentials.py`.

**Verification — consumer enumeration (everything that touches OpenRouter).**
- `workflows/n8n/ai-brain.json` — direct caller (the sub-workflow).
- `workflows/n8n/brain-dump-processor-v2.json` — AI fallback path (regex is primary; AI fires only on regex miss).
- `workflows/n8n/telegram-capture.json` — possible classify call (verify before rotation by grepping the JSON for `openrouter` or `OpenRouter`).
- `workflows/n8n/morning-briefing.json` / `workflows/n8n/weekly-digest-v2.json` / `workflows/n8n/article-processor.json` / `workflows/n8n/link-enricher.json` — may invoke ai-brain for summarise/brief/triage/review jobs. Treat the sub-workflow as the single integration point; if ai-brain works after rotation, all callers work.

**Risks.**
- **Downtime gap if the new key is created and old is revoked before swap.** Mitigation: keep both keys live until step 7.
- **Credential ID change.** If you accidentally delete-and-recreate the n8n credential instead of editing it, the workflow JSON references break. Mitigation: edit-in-place at step 4 OR re-run hydrate/deploy if the ID changed.
- **OpenRouter free-tier rate-limit confusion.** Rotation does not reset rate-limit windows; pre-existing 429s are unrelated.

**Effort.** S (20-30 min, including soak monitoring).

**Aaron-action-required?** PARTIAL. Aaron generates and revokes the key on openrouter.ai (cannot be automated). An agent can do every n8n / `.env` step once Aaron pastes the new key.

**Parallel-safe?** Y — does not modify any code or workflow JSON in the repo. Pure credential rotation.

---

## Item 3 — MTL backfill (`[due::]` 11% populated, `[completion::]` 0%)

**Why.** Dataview queries in the daily command center and morning-briefing rely on `[due::]` for "overdue" + "due today" slicing; coverage at 11% means most of the slicer is blind. `[completion::]` at 0% means we have no historical signal for weekly digest / quarterly retrospective work later (P5). Backfill restores analytic value without changing the canonical task format.

**Pre-conditions.**
- A current snapshot of the MTL pulled from MinIO (or directly via S3 GET to `obsidian-vault/10_Active Projects/Active Personal/!!! MASTER TASK LIST.md`).
- Read-only S3 credentials are sufficient for the dry-run. Write back is opt-in (`--apply`).
- The canonical task regex is `^- \[([ x])\] .*` with inline-field captures.

**What's automatable vs needs Aaron's judgment.**
| Field | Auto-fillable from | Needs Aaron |
| --- | --- | --- |
| `[completion::]` on `- [x]` tasks | Git blame on prior MTL revisions in the repo if it was ever committed; failing that, S3 versioning timestamps if enabled; failing that, leave blank with a TODO marker. **In practice for OHO: MTL lives only in MinIO, not git, so completion timestamps are mostly NOT recoverable.** | Manual review of recently-completed tasks where Aaron remembers the date. |
| `[due::]` on undated open tasks | **Almost nothing is safely auto-inferable.** Task age + area + priority is a weak heuristic that will be wrong often. Auto-tagging dates is exactly the kind of "fix" that corrupts a canonical structure silently. | All of it. Script should only **flag** undated tasks for review, not invent dates. |
| `[area::]` (out of scope but worth noting) | Already required by the format. Should be linted for missing values during the same pass. | — |

**Honest stance.** The script must NOT hallucinate dates. CLAUDE.md says "infers from context (task age + area + priority heuristic)" but on reflection that's a footgun: a wrong `[due::]` is worse than a missing one because Dataview will treat it as authoritative. The script should instead produce a **structured review report** for Aaron to triage.

**Spec for `scripts/backfill_mtl_metadata.py`.**
1. **Read** MTL from MinIO via boto3 (using `.env` MinIO creds).
2. **Parse** every line matching `^- \[([ x])\] .*` and capture:
   - checkbox state
   - description (text up to the first `[`)
   - all `[key:: value]` pairs
   - line number for stable identification
3. **Classify** each task into one of: `open_no_due`, `open_has_due`, `closed_no_completion`, `closed_has_completion`, `malformed`.
4. **For `closed_no_completion`:** attempt three strategies in order — (a) git blame on any committed copy of MTL in this repo, (b) MinIO object-version timestamps (if MinIO versioning is on; check via `s3.list_object_versions`), (c) leave blank and write a `<!-- needs-completion-date -->` HTML comment on the same line. Only auto-fill if the source had `≥day` granularity matching to within 24h.
5. **For `open_no_due`:** never auto-fill. Append to a review report: `99_System/reports/mtl-backfill-review-<YYYYMMDD>.md` with one bullet per task: `- [area: business, priority: A, age: 47d] "Ship the SOW draft for ACME" — needs [due::]`.
6. **Flags.**
   - `--dry-run` (default): print diff + write the review report only.
   - `--apply`: write the modified MTL back via verified S3 put (head_object check after).
   - `--review-only`: just write the report, do not modify MTL at all (useful for weekly cadence).
   - `--verbose`: print every classification decision.
7. **Idempotency.**
   - Never modify a task that already has `[due::]` or `[completion::]`.
   - Re-runs on the same MTL must produce byte-identical output (deterministic ordering of inline-field keys; stable HTML-comment marker text).
   - The review report is overwritten on each run, not appended.
8. **Tests** (under `tests/test_backfill_mtl_metadata.py`):
   - Idempotency: run twice → second run produces zero changes.
   - Dry-run safety: dry-run never writes to S3 (mock boto3, assert `put_object` not called).
   - Hallucination guard: a task with no recoverable timestamp gets the TODO marker, not a fabricated date.
   - Format preservation: inline-field ordering and area/priority values pass through untouched on tasks the script didn't target.

**Verification.**
- `make test` — new test file green.
- Run `--dry-run` against prod MTL; manually spot-check 5 review-report entries.
- Run `--apply` against a staging copy of MTL in a non-canonical key (e.g. `99_System/scratch/MTL-test.md`) and diff.
- Only after that, apply to canonical MTL. Backup first: `aws s3 cp s3://obsidian-vault/'10_Active Projects/Active Personal/!!! MASTER TASK LIST.md' s3://obsidian-vault/99_System/backup/MTL-pre-backfill-<date>.md`.

**Risks.**
- **Corrupting MTL.** Mitigated by mandatory dry-run, backup, and idempotency guarantee.
- **Heuristic creep.** Future temptation to add "smart" date inference. Spec forbids it; tests must guard.
- **Concurrent edit.** Aaron may edit MTL in Obsidian while the script runs. Mitigation: ETag-based conditional put if MinIO supports it, OR a "last modified within 60s" pre-flight abort.

**Effort.** M (4-6h: ~2h script, ~2h tests, ~1h staging verification, ~1h triage of the first review report).

**Aaron-action-required?** PARTIAL. An agent can write and dry-run the script. Only Aaron should run `--apply` against canonical MTL after reviewing the report. The review-report triage itself is entirely Aaron's judgment.

**Parallel-safe?** Y in dry-run / review-only mode (read-only). NO during `--apply` — that should be serialised against any active brain-dump-processor run to avoid clobbering an in-flight MTL append. Run `--apply` outside the 6-8AM CDT window.

---

## Item 4 — `--no-reset` flag deprecation (after ≥7 clean soak days)

**Why.** `--no-reset` was a P1 rollout safety valve — extract tasks but skip the gated state-machine reset so a failed run couldn't lose source content. Now that receipts + gated reset are running in prod with verified writes, the flag is dead weight: it doubles the test surface, splits the orchestrator into two paths, and invites accidental misuse ("let me just toggle the flag…").

**Pre-conditions — hard gate.**
- 7 consecutive days of clean `python3 scripts/audit_extraction_receipts.py` reports.
- Zero `partial` or `error` final states in `99_System/extraction-receipts/` for the same 7 days.
- Soak window declared closed (per CLAUDE.md: not before 2026-05-19).
- No open issues against the runner sidecar or brain-dump pipeline.

**Steps.**
1. **Day 7 + 1.** Verify gate above by counting receipts: every receipt's `summary.final_status` should be `extracted`. Any `partial` or `error` resets the clock.
2. **Phase A — flip default (separate commit).**
   - In `tools/process_brain_dump.py`: argparse default for `--no-reset` becomes `False` (it likely already is — confirm). Add a `--legacy-no-reset` alias if external callers might still pass `--no-reset`.
   - Mark the flag DEPRECATED in `--help` text.
   - Add a deprecation warning printed to stderr when the flag is passed: `WARNING: --no-reset is deprecated; will be removed after 2026-06-01.`
   - Update `tests/test_brain_dump_orchestrator.py` to assert the warning fires.
   - Run all tests, confirm 311+ pass.
3. **Phase B — remove flag (separate commit, ≥7 days after Phase A).**
   - Delete the `--no-reset` argparse entry from `tools/process_brain_dump.py`.
   - Delete `_extract_no_reset` function and any branch reading `no_reset is True`.
   - Delete the `no_reset` parameter from the relevant call signatures (currently `def f(... no_reset: bool = False)`).
   - Delete `tests/test_brain_dump_integrity.py` and `tests/test_brain_dump_orchestrator.py` cases scoped to the no-reset path.
   - Search for callers: `grep -rn "no_reset\|no-reset" .` should be empty after this commit (excluding archived/CHANGELOG references).
   - Update `services/oho_runner/main.py` if it accepts a `no_reset` field in the request body — drop the field and any forwarding logic.
   - Update `docs/runbook-deploy-python-to-lxc.md` and CLAUDE.md "P1 — integrity layer" section to remove the gradual-rollout language.
4. **Tag the milestone.** `git tag p1-flag-deprecated` for archaeology.

**Verification.**
- Phase A: deprecation warning visible in test output; default behaviour unchanged for the prod cron.
- Phase B: `grep -rn "no_reset\|no-reset" tools/ services/ scripts/ tests/` returns nothing. `make test` green. One full prod cycle (next 7AM CDT brain-dump run) produces a clean receipt with `final_status: extracted`.

**Risks.**
- **Premature removal.** If a soak day was clean only because there were zero brain-dump edits that day, we don't actually have 7 days of stress. Mitigate by requiring at least 3 days within the 7 where the processor did real work (non-zero `verified_sections`).
- **Hidden caller.** Some manual script or Aaron's shell history might still pass `--no-reset`. Phase A's stderr warning catches this without breaking the call; Phase B's removal will break it loudly. That's the desired behaviour.

**Effort.** S (Phase A: 1h. Phase B: 2h including ripple cleanup).

**Aaron-action-required?** NO. Fully agent-doable once the gate is verified.

**Parallel-safe?** Y for both phases — they touch `tools/process_brain_dump.py` and tests, which are not edited by any other item in this spec. Caveat: Phase B should not land on a Friday (operational hygiene: don't break things on the way into a weekend).

---

## Item 5 — agent-orch-lxc Telegram bot token rotation + scrub (CROSS-REPO)

**Why.** GitGuardian flagged a live Telegram bot token in a public-eligible artifact: `.planning/ROADMAP.md` (~line 96) and `DT_AgentTeam.txt` in the `GRsoldier7/agent-orch-lxc` repo, PR #1. A live bot token in any committed file means anyone who can read the repo can send messages as the bot — including DM-ing Aaron and impersonating workflows.

**Cross-repo notice.** This item is **NOT** for the ObsidianHomeOrchestrator repo. It's a hygiene carry-forward tracked here because OHO and agent-orch-lxc share an operator (Aaron) and Telegram is the capture surface for both. Work happens in `GRsoldier7/agent-orch-lxc`.

**Aaron-action-required — explicit.** Only Aaron can rotate a Telegram bot token. Rotation requires authenticating to `@BotFather` from a Telegram client logged into Aaron's account. No agent can do this. The scrub + history-rewrite decision is agent-doable; the rotation is not.

**Pre-conditions.**
- Aaron is logged into Telegram on a device where `@BotFather` is accessible.
- The bot name / handle is known (likely `oho_capture_bot` or similar — Aaron to confirm).
- The repo is cloned locally.

**Steps.**
1. **Rotate the token (Aaron only).** Telegram → `@BotFather` → `/mybots` → select the bot → **API Token** → **Revoke current token**. Save the new token in a password manager. NEVER paste it in chat or commit it.
2. **Update every live consumer of the old token.**
   - n8n credential `Telegram` (if it exists) — update the bot token field.
   - Any local `.env` files: `~/code/agent-orch-lxc/.env`, OHO `.env` if it shares the same bot, any docker-compose env files.
   - Any webhook URL registered with Telegram: `https://api.telegram.org/bot<TOKEN>/setWebhook` will need to be re-called with the new token to confirm the webhook URL is still active.
3. **Scrub the repo (agent-doable, once Aaron confirms rotation done).** In the agent-orch-lxc repo:
   - Replace the literal token in `.planning/ROADMAP.md` line ~96 with the placeholder `__TELEGRAM_BOT_TOKEN__` (matching OHO's `__MINIO_CRED_ID__` style).
   - Same for `DT_AgentTeam.txt`.
   - Add `.env*` and any local secrets path to `.gitignore` if not already.
   - Commit: `chore(secrets): replace live telegram token with placeholder after BotFather rotation`.
4. **Decision: history-rewrite vs accept-rotation.**
   - **Accept rotation (recommended).** Since the token is already revoked at step 1, the secret in git history is now powerless. Adding a `SECURITY.md` note saying "Token previously in git history was revoked 2026-MM-DD" is sufficient. This is the lower-risk path.
   - **History rewrite (only if repo is public or you want to clean the record).** Use `git filter-repo` (not `filter-branch`) to remove the token from history. Force-push to a fresh branch. This rewrites SHAs and breaks any open PRs / forks. Coordinate with PR #1 author. Only do this if the repo is public.
   - Default: pick **accept rotation** unless agent-orch-lxc is public. Document the choice in the commit message.
5. **Add a pre-commit hook.** Install `gitleaks` or `detect-secrets` as a `pre-commit` hook to prevent recurrence. One-line config; same pattern as OHO's other audits.
6. **Re-run GitGuardian.** Re-trigger PR #1's GitGuardian scan; should now pass.

**Verification.**
- `git log -p .planning/ROADMAP.md DT_AgentTeam.txt | grep -E "[0-9]{9,10}:[A-Za-z0-9_-]{30,}"` returns no matches in the working tree (still in history if accept-rotation; gone if history-rewrite).
- Send a `/start` to the bot from Aaron's Telegram client — confirm the new token routes (n8n webhook fires).
- GitGuardian status on PR #1 is green.

**Risks.**
- **Webhook gap.** Between revoking the old token and updating the n8n credential, the bot is dead. Mitigate: do step 2 within minutes of step 1.
- **Forgotten consumer.** If another script holds the old token, it 401s silently. Mitigate: `grep -r` for token patterns across all Aaron's repos before declaring done.
- **History-rewrite collateral.** Breaks PR refs, forks, anyone with the repo cloned. Only do it if you actually need to.

**Effort.** S (15-30 min, dominated by waiting on Aaron to rotate).

**Aaron-action-required?** YES for rotation. NO for the scrub + history decision (agent-doable once token is rotated).

**Parallel-safe?** Y — cross-repo, no overlap with anything in OHO.

---

## Item 6 — NotebookLM stale-ID cleanup

**Why.** Multiple stale notebook IDs were left in tool config + memory files during the authuser=0 / authuser=1 reconciliation on 2026-05-11. Risk: a future session picks the wrong ID and pushes content to a non-canonical (or deleted) notebook, OR the notebooklm CLI fails opaquely on RPC-null. Canonical ID is `d056e9d5-64d9-4f64-aa94-faff603de835` on `authuser=1`.

**Pre-conditions.**
- `notebooklm` CLI auth state is `authuser=1` (per the 2026-05-11 re-auth via Playwright).
- The canonical notebook is reachable: `notebooklm use d056e9d5-64d9-4f64-aa94-faff603de835` returns success.

**Steps.**
1. **Verify canonical ID.**
   ```bash
   notebooklm use d056e9d5-64d9-4f64-aa94-faff603de835
   notebooklm info   # or whatever the CLI status command is
   ```
   Expected: notebook resolves, title matches "ObsidianHomeOrchestrator — Life OS Project Memory".
2. **Audit existing tool config — current state already correct.** Files audited 2026-05-12:
   - `.claude/nlm-notebook-ids.env` → already lists `d056e9d5-…` as active; stales are commented out. ✓
   - `.claude/notebooklm.json` → already lists `d056e9d5-…` as active with stales in `stale_do_not_use`. ✓
   - `CLAUDE.md` NotebookLM table → already documents the canonical ID, three stales, and the deleted `fee28c3f-…` fallback. ✓
3. **Reconcile MEMORY.md drift.** The user-memory file lists `fee28c3f-…` as active — that's the deleted authuser=0 fallback. Action: update the memory pointer (this is in `/home/aaron/.claude/projects/.../memory/MEMORY.md`, NOT in the OHO repo). Update via the standard memory-edit flow:
   - Edit `reference_notebooklm_project_notebook.md` (the file referenced from MEMORY.md) to point to `d056e9d5-…` on `authuser=1`.
   - Strike-through or remove the line claiming `fee28c3f-…` is active.
4. **Update `.claude/skills/notebooklm/SKILL.md`** if it hardcodes an ID. Search for any of: `d056e9d5`, `a428969b`, `844aa6a1`, `fee28c3f`. Ensure only `d056e9d5-…` appears in active examples; stales (if any) should be in a "do not use" block or removed.
5. **Greenfield grep across the repo.**
   ```bash
   grep -rn "a428969b\|844aa6a1\|fee28c3f" --include="*.md" --include="*.json" --include="*.env" .
   ```
   Acceptable hits: commented-out lines in the two `.claude/` files documenting the stale list; the CLAUDE.md notebook table; this spec file. Unacceptable hits: anywhere else.
6. **Optional: add an audit script.** `scripts/audit_notebooklm_ids.py` that asserts the canonical ID appears in both `.claude/nlm-notebook-ids.env` and `.claude/notebooklm.json` and matches. Wire into `make audit-ai-tooling`. Effort: tiny; value: prevents the next drift event.

**Verification.**
- `notebooklm use d056e9d5-…` succeeds.
- `notebooklm source add <a test file>` succeeds without RPC-null.
- `grep` audit above clean.
- `make audit-ai-tooling` green (if step 6 was implemented).

**Risks.**
- **Wrong authuser at runtime.** If the CLI re-authenticates on a different Google profile, the canonical ID becomes inaccessible. Mitigation: the `/tmp/nlm_login.py` Playwright helper documented in CLAUDE.md is the canonical re-auth path.
- **Deleting too aggressively.** If we scrub all stale IDs from CLAUDE.md, future-Aaron loses the archaeology for why the migration happened. Keep them in a "stale — do not use" annotated block. Current CLAUDE.md already does this correctly.

**Effort.** XS (30 min, mostly verification and a small audit script).

**Aaron-action-required?** NO. Fully agent-doable.

**Parallel-safe?** Y — pure documentation + config cleanup. No runtime impact.

---

## Cross-cutting summary

| # | Item | Effort | Aaron-required? | Parallel-safe? | Soak-gate impact |
|---|------|--------|-----------------|----------------|------------------|
| 1 | GCAL OAuth → Weekend Planner | S | YES (OAuth) | Y | none |
| 2 | OpenRouter key rotation | S | PARTIAL (key gen) | Y | none |
| 3 | MTL backfill (dry-run + report) | M | PARTIAL (apply step) | Y (dry-run); N (apply during 6-8AM) | none |
| 4 | `--no-reset` deprecation | S | NO | Y (Phase A); avoid Friday (Phase B) | **gated by clean soak** |
| 5 | agent-orch-lxc token scrub | S | YES (BotFather) | Y (cross-repo) | none |
| 6 | NotebookLM stale-ID cleanup | XS | NO | Y | none |

**Risks that span >1 item.**
- Items 1, 2, 5 all require Aaron to hold a secret in hand (OAuth client secret, OpenRouter key, Telegram token). If any of those get pasted into chat or committed, that's a same-class incident. The mitigation is identical: paste into `.env` directly in the IDE, never into Claude's conversation.
- Items 2 and 5 both involve "old credential live during overlap." Sequencing matters: new-credential exists → swap consumers → revoke old. Don't revoke before swap. This pattern should be the same for any future credential rotation in OHO.

**Open questions.**
- Item 3: does MinIO have object versioning enabled on `obsidian-vault`? If yes, we have a real completion-timestamp source. If no, we should turn it on regardless (cheap insurance). Worth confirming before writing the script.
- Item 5: is `GRsoldier7/agent-orch-lxc` public or private? Drives the history-rewrite-vs-accept-rotation decision. Default assumption here: private → accept rotation.
- Item 4: is anything other than the cron + manual operator runs calling `process_brain_dump.py` with `--no-reset`? Suspect not, but a `grep` across Aaron's other repos before Phase B would close the loop.

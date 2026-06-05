# OHO — Next Steps (canonical operator checklist)

Single ordered list. Highest priority at top. Cross-references [CURRENT-STATE.md](CURRENT-STATE.md). Refresh this doc whenever priority shifts.

---

## ✅ Completed 2026-05-16 — do NOT re-prompt

### ~~1. Rotate OpenRouter API key~~ ✅ rotated 2026-05-16

Operator confirmed. Key present in `.env` (`sk-or-` prefix, 73 chars). n8n cred refreshed. Incident at [`docs/security/2026-05-16-INCIDENT-job-search-leak.md`](security/2026-05-16-INCIDENT-job-search-leak.md) marked RESOLVED. **Do not prompt for this rotation again.** Next due: 2026-08-14 (90d cadence).

### ~~2. Rotate Telegram bot token~~ ✅ rotated 2026-05-16

Operator confirmed. Lives in n8n cred only (not `.env` — by operator preference). Next due: 2026-08-14. **Do not prompt for this rotation again.**

## 🔴 Operator-only — outstanding

### 3. GCAL OAuth → `GCAL_CRED_ID` (cred shell created; consent step remaining)

n8n cred shell `uAySKd53I6zgvFjx` already exists in n8n DB (POSTed during prior session). Google client redirect URI must include the Tailscale FQDN. Three steps:

1. **Update Google OAuth client redirect URIs** at [console.cloud.google.com/auth/clients](https://console.cloud.google.com/auth/clients) → add (or replace localhost with):

    ```text
    https://n8n.tailfab8a7.ts.net/rest/oauth2-credential/callback
    ```

2. **Click consent** in browser: [n8n cred page](https://n8n.tailfab8a7.ts.net/credentials/uAySKd53I6zgvFjx) → "Sign in with Google" → Allow.

3. After consent, run from laptop:

    ```bash
    set -a && source .env && set +a
    make gcal-finalize         # writes GCAL_CRED_ID=uAySKd53I6zgvFjx to .env
    bash scripts/setup-n8n.sh  # re-deploys Weekend Planner with cred wired
    ```

Tailscale serve already gives n8n a public-TLD HTTPS hostname → Google accepts the redirect URI directly. No localhost/SSH-tunnel/restart trick needed. The `scripts/n8n_localhost_toggle.sh` is FALLBACK for environments without Tailscale.

---

## 🟡 Operator-when-ready (any order, no urgency)

### ~~4. Land the held artifacts~~ ✅ landed 2026-05-17 (`a6d2b2d`) + extended 2026-05-25 (`7a38f5f`, `36ed420`)

CI gate at `.github/workflows/audit-pr.yml` is live; sticky failure comment added 2026-05-25 (`1fc577a`). Pre-commit hook at `.githooks/pre-commit` installable via `make hooks-install`.

### 4b. (Optional) Provision real storage for `/mnt/ssd-storage` — only if Immich is wanted

The 2026-06-05 ENOSPC incident was caused by `sync-photos-nas-to-ssd.sh` (cron `0 3 * * 3,6`)
copying 48G of NAS photos onto a "local SSD" that doesn't exist → it landed on `pve-root` and
filled the OS disk. **The cron is now DISABLED** (commented in `root@pve` crontab; backup at
`/root/crontab.bak.20260605-ohofix`); photos remain safe on the Synology NAS. No action needed
unless you want a local Immich library. If so:

1. Carve a dedicated LV from the 816G `pve-data` thin pool, `mkfs.ext4`, mount at `/mnt/ssd-storage`, add to fstab.
2. Enable the `ssd-fast` Proxmox storage (remove `disable` in `/etc/pve/storage.cfg`).
3. Re-enable the photo-sync cron line on `pve`.

Until then: leave disabled. Full write-up: `docs/session-logs/2026-06-05-enospc-host-root-disk-full.md`; playbook in RUNBOOK § Disk-Full.

### 5. MTL backfill dry-run

```bash
set -a && source .env && set +a
make backfill-mtl-review
# Inspect 99_System/reports/mtl-backfill-review-2026-05-16.md in Obsidian
# Decide if you want make backfill-mtl-apply (writes TODO markers; never invents dates)
```

### 6. Update PR #2 description

```bash
# Updated draft at /tmp/pr2-update.md (or roll your own from CURRENT-STATE.md).
gh pr edit 2 --body-file /tmp/pr2-update.md
```

---

## ✅ Soak gate — CLEARED 2026-05-18

Day 7 brain-dump-processor returned `status: success`. Receipt audit green Sun + Mon. Phase C / Phase F code work UNBLOCKED as of 2026-05-19.

### ~~7. Verify soak audit clean Sun + Mon~~ ✅ done — both runs green

### ~~7.5. Merge the pre-staged Phase C/F skeletons~~ ✅ already on `polish/prod-ready`

All 4 skeleton modules + 63 tests verified ancestors of `polish/prod-ready` HEAD as of 2026-05-27. `feature/phase-c-f-skeletons` branch can be deleted at operator convenience.

### ~~8. Once soak clean: promote ADRs~~ ✅ promoted 2026-05-27

ADR-0008 and ADR-0009 now `Status: Accepted` with explicit notes about skeleton-mode (Phase F's `SKELETON_MODE = True`) + Plan-only state (Phase C's Apply/Verify still stubbed). Day-2 work on each is the next code commitment.

### 9. Deprecate `--no-reset` flag

```bash
# In tools/process_brain_dump.py and any callers — strip the --no-reset flag.
# Update tests. Commit.
make verify
```

---

## 🔵 Post-soak engineering work (Mon 2026-05-18+)

In priority order. Each is its own commit / PR.

### 10. Fix `vault-health-report.json` `executeCommand` regression

The Sunday 8PM workflow has been silently failing since ~2026-04 (no MinIO run logs). Plan per [CURRENT-STATE.md § Open incidents](CURRENT-STATE.md):

- Add `POST /audit-receipts` endpoint to `services/oho_runner/app.py` (mirror `/process-brain-dump` pattern: bearer-auth, asyncio-locked, subprocess to `scripts/audit_extraction_receipts.py --json-output`).
- Switch the n8n node from `executeCommand` to `httpRequest` against the new endpoint.
- Add audit: `tests/test_workflow_no_executecommand.py` that asserts NO workflow JSON uses `n8n-nodes-base.executeCommand`.
- Test: simulated run, verify findings JSON makes it to the email.

**Note on the silent S3-list bail caught 2026-05-27:** while investigating
item 10b below, the execution trace for `vault-health-report` showed it
bailing at `S3: List Brain Dumps` (the first S3 node after `Set Dates`)
before reaching the `executeCommand` node at all. Two bugs stacked:
(a) the `executeCommand` one tracked here, and (b) the same S3-empty-output
class flagged in 10b. The fix for (a) will likely sidestep (b) by replacing
the entire S3-list + Code-collect chain with an `httpRequest` to the runner.
Verify both during item 10's smoke test.

### 10b. Fix `system-health-monitor.json` silent S3-chain bail (NEW, 2026-05-27)

Workflow active per n8n API, fires every 6h, n8n reports `status: success`
on every run — but ZERO log objects in MinIO since deployed. Execution
trace `lastNodeExecuted = S3: Check North Star` (bails after 3 of ~10
nodes). 30-34 ms runtime — far too fast for the full S3 chain.

**Hypothesis (unproven without live deploy):** `n8n-nodes-base.s3` `headObject`
op in n8n 2.x doesn't emit a downstream item when the file exists +
`continueOnFail: true` (it only emits an item when the file 404s, via the
error path). `daily-note-creator-v2` survives because its file usually
404s at cron time (file doesn't exist for today yet). `system-health-monitor`
chains `headObject` → `headObject` against files that always exist → first
headObject succeeds silently, no item passes, chain dies.

**Diff vs working pattern:**

- daily-note-creator-v2 (works): `Code (Set Today)` → `S3 headObject` → `IF (Not Exists?)` — IF tolerates empty items
- system-health-monitor (broken): `Code (Init Checks)` → `S3 headObject` → `S3 headObject` → `Code (Evaluate)` — second S3 needs an input item, doesn't get one

**Three fix options (pick one when this lands):**

1. **`alwaysOutputData: true`** on both `S3: Check North Star` and `S3: Check MTL`. One-line per node. Cheapest. Test by triggering manually post-deploy + checking MinIO for `health-monitor-*.json` within 1 minute.

2. **Replace headObject with httpRequest HEAD** against MinIO directly. More portable, no n8n S3 quirk. ~10 lines per check.

3. **Move both checks into one Code node** that uses `boto3` / fetch to do both HEADs and emit a single item. Most refactor; eliminates the chained-S3 pattern entirely.

Recommend (1) for first deploy; if still broken, jump to (2). Worth fixing alongside item 10 so we have a complete deploy of the health-workflow tier.

**Allowlisted in `tests/test_workflow_templates._LOG_WRITE_OPTIONAL` so CI stays green; remove from the allowlist once the proven-working JSON lands.**

### 11. Phase C kickoff — threaded tasks (ADR-0009)

Spec at `docs/superpowers/specs/2026-05-12-P2-threaded-tasks-spec.md`. Order:

1. ~~`tools/task_id.py` — pure ID generator + tests~~ ✅ **pre-staged on `feature/phase-c-f-skeletons` (17 tests green); merge at step 7.5 above.**
2. `scripts/migrate_threaded_tasks.py` — 3-phase Plan / Apply / Verify, calls `task_id.generate_task_id()`.
3. `scripts/audit_threaded_tasks.py` — 15-min cron during cutover week.
4. MTL ↔ backing-file bidirectional sync.
5. Command Center renderer update.
6. Runner endpoints `/tasks/split`, `/tasks/merge`, `/tasks/archive`.

### 12. Phase F kickoff — broker-client (ADR-0008)

Spec at `docs/superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md`. Foundation seeded except the runtime + dictionary wiring:

1. ~~`tools/privacy_classifier.py` — reads `infra/data-classes.yaml`~~ ✅ **pre-staged on `feature/phase-c-f-skeletons` (19 tests green; `SKELETON_MODE = True`); merge at step 7.5 above.**
   - Day-2: implement Tier 3-8 dictionary lookups (kid-names / family-names / biomarkers / faith-terms / client-IDs).
   - Day-2: implement Tier 9 PII gates (`not_in_allowlist` for emails, `luhn_check` for credit-cards).
   - Day-2: signature verification for Tier 1 caller-asserted-override (Ed25519 against `infra/agent-keys.yaml`).
   - Day-2: flip `SKELETON_MODE = False`; each stubbed-mode test must update in lockstep.
2. `clients/agent_orch_client.py` — talks to CT 215.
3. Comms endpoints on `services/oho_runner` — inbox / outbox-ack / audit-tail / health.
4. Eval-suite expansion — fill `evals/comms_privacy/` from 25 → 200 fixtures.

### 13. Mass-migrate S3 writes to `tools/s3_verified.py`

The helper is committed. Callers to migrate (per Codex P1):

- `tools/process_brain_dump.py:1380-1385` (telemetry append; needs IfMatch).
- `tools/build_command_center.py:95-136` (command-center RMW; needs IfMatch).
- `scripts/migrate_brain_dump_frontmatter.py:88-96` (frontmatter RMW; needs IfMatch).
- `scripts/archive_completed_tasks.py:200` (log write; verify).
- `scripts/backfill_mtl_metadata.py:458` (log write; verify).
- 17 n8n S3 upload nodes — add downstream `headObject` verify OR move write to Python via a new runner endpoint.

Add an audit: `tests/test_no_unverified_put_object.py` that walks `tools/` + `scripts/` + `services/` and fails on any `put_object` outside the allowlist (`tools/s3_verified.py` is the allowlist).

### 14. Split `tests/test_process_brain_dump_e2e.py`

Per Codex P1: currently entirely excluded by `make verify`. Split:

- `tests/test_process_brain_dump_e2e.py` — marked `@pytest.mark.live`; runs with `RUN_INTEGRATION_TESTS=1`.
- `tests/test_process_brain_dump_pipeline.py` — mocked full-pipeline coverage; in default `make test` scope.

### 15. Tighten setup-n8n.sh hygiene

Post-soak, refactor the secret-handling surface:

- Replace `curl -H "X-N8N-API-KEY: $KEY"` with a Python n8n REST helper that uses stdin / env (no argv).
- Replace `curl -H "Authorization: Bearer $TOKEN"` in `deploy_oho_runner.py:628,635` likewise.
- Stop writing `OHO_RUNNER_TOKEN={token}` via shell echo (`deploy_oho_runner.py:567`); use a temp file with `chmod 0600`.

---

## 🟣 Optional / future

### 16. History rewrite of leaked credentials

`git filter-repo` to scrub the OpenRouter key suffix + Google IDs from history. Destructive (force-push + collaborator re-clones). **Not required** if rotation is done — but available if Aaron prefers a clean tree.

### 17. Promote runlog audit into `audit-all`

`scripts/audit_workflow_runlogs.py` exists but isn't in `make audit-all`. Add.

### 18. Wave-X H3 SLO conformance auditor

`scripts/audit_slo_conformance.py` reads MinIO run-logs and computes per-workflow conformance against [`docs/SLO-life-os.md`](SLO-life-os.md). Output to `99_System/state/slo-status.json` for the Command Center.

### 19. Decision Journal scaffold

ADR-0007 Phase D (P2.5) rides on threaded task IDs. After Phase C lands, scaffold `40_Decisions/<area>/d-2026wNN-XXXX.md` template + `scripts/decision_new.py`.

---

## How to keep this list honest

After every meaningful change:

1. `make verify` — establish green baseline.
2. Update [CURRENT-STATE.md](CURRENT-STATE.md) hard-numbers table.
3. Strike completed rows here. Don't delete — strike with `~~text~~` so the audit trail survives.
4. Push the commit. PR #2 picks it up.

Cron-style reminder: once a week, re-read this doc top-to-bottom. Anything that's been stuck for 3+ weeks → break into smaller items or drop.

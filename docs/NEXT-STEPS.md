# OHO — Next Steps (canonical operator checklist)

Single ordered list. Highest priority at top. Cross-references [CURRENT-STATE.md](CURRENT-STATE.md). Refresh this doc whenever priority shifts.

---

## ✅ Completed 2026-05-16 — do NOT re-prompt

### ~~1. Rotate OpenRouter API key~~ ✅ rotated 2026-05-16

Operator confirmed. Key present in `.env` (`sk-or-` prefix, 73 chars). n8n cred refreshed. Incident at [`docs/security/2026-05-16-INCIDENT-job-search-leak.md`](security/2026-05-16-INCIDENT-job-search-leak.md) marked RESOLVED. **Do not prompt for this rotation again.** Next due: 2026-08-14 (90d cadence).

### ~~2. Rotate Telegram bot token~~ ✅ rotated 2026-05-16

Operator confirmed. Lives in n8n cred only (not `.env` — by operator preference). Next due: 2026-08-14. **Do not prompt for this rotation again.**

## 🔴 Operator-only — outstanding

### 3. GCAL OAuth → `GCAL_CRED_ID`

n8n UI → Credentials → Google Calendar OAuth2 → consent → copy ID → `.env` → re-deploy Weekend Planner.

---

## 🟡 Operator-when-ready (any order, no urgency)

### 4. Land the held artifacts

`.github/workflows/audit-pr.yml` + `.githooks/pre-commit` are drafted, tested, ready. Both introduce durable persistence (durable-policy hold). Land:

```bash
git add .github/workflows/audit-pr.yml .githooks/pre-commit
git commit -m "ci: every-PR audit gate + local pre-commit hook"
git push origin polish/prod-ready
# Then per-clone:
git config core.hooksPath .githooks
```

Once landed, also extend `.githooks/pre-commit` to include the newer audits:

```bash
# Replace the audit list in .githooks/pre-commit with:
#   python3 scripts/audit_planning_docs.py --allow-orphans
#   python3 scripts/audit_data_classes.py --strict
#   python3 scripts/audit_secrets_rotation.py >/dev/null
#   python3 scripts/audit_workflow_secrets.py >/dev/null   # NEW from 2026-05-16
```

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

## 🟢 Soak-completion checks (do on Mon 2026-05-18)

### 7. Verify soak audit clean Sun + Mon

```bash
make audit-extraction-receipts          # Sunday evening
make audit-extraction-receipts          # Monday morning
```

Both green → soak gate clears → Phase C / Phase F code work can begin.

### 7.5. Merge the pre-staged Phase C/F skeletons

The skeletons (`tools/task_id.py` + `tools/privacy_classifier.py` + their tests) sit on `feature/phase-c-f-skeletons`. Merge into `polish/prod-ready` and PR-the-merge or fast-forward.

```bash
git checkout polish/prod-ready
git merge --ff-only feature/phase-c-f-skeletons
make verify    # confirm 36 new tests still green
git push origin polish/prod-ready
```

If `--ff-only` refuses (polish/prod-ready advanced), do a regular merge and resolve any conflict — the skeleton files are new, so conflicts are unlikely.

### 8. Once soak clean: promote ADRs

`docs/adr/0008-cross-host-comms.md` and `docs/adr/0009-threaded-tasks.md` move from `Status: Proposed` → `Status: Accepted`. One-line edit per ADR.

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

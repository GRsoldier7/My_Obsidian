# OHO — Next Steps (canonical operator checklist)

Single ordered list. Highest priority at top. Cross-references [CURRENT-STATE.md](CURRENT-STATE.md). Refresh this doc whenever priority shifts.

---

## 🔴 Operator-only — do today (you only, Claude cannot)

### 1. Rotate OpenRouter API key — INCIDENT-CLASS

Per [`docs/security/2026-05-16-INCIDENT-job-search-leak.md`](security/2026-05-16-INCIDENT-job-search-leak.md):

```bash
# 1. https://openrouter.ai/keys → revoke the current key
# 2. Issue a new key, copy it
# 3. Update .env
#       OPENROUTER_API_KEY=<new-key>
# 4. Update n8n cred "OpenRouter API" at http://192.168.1.121:5678
# 5. Bump the row in docs/security/secrets-rotation.md
#       last_rotated: 2026-05-16   next_due: 2026-08-14
# 6. Verify:
make audit-all
make verify
```

**Why now:** 24-char suffix in public git history since 2026-04-02. Rotation IS the remediation. History rewrite is optional.

### 2. Rotate Telegram bot token

Per [`docs/runbooks/rotate-telegram-token.md`](runbooks/rotate-telegram-token.md). Unblocks both this repo and `agent-orch-lxc` Phase 4. ≤15 min @BotFather + 2 file edits + cred update.

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

### 8. Once clean: promote ADRs

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

Spec is detailed at `docs/superpowers/specs/2026-05-12-P2-threaded-tasks-spec.md`. Order:

1. `tools/task_id.py` — pure ID generator + tests.
2. `scripts/migrate_threaded_tasks.py` — 3-phase Plan / Apply / Verify.
3. `scripts/audit_threaded_tasks.py` — 15-min cron during cutover week.
4. MTL ↔ backing-file bidirectional sync.
5. Command Center renderer update.
6. Runner endpoints `/tasks/split`, `/tasks/merge`, `/tasks/archive`.

### 12. Phase F kickoff — broker-client (ADR-0008)

Spec is at `docs/superpowers/specs/2026-05-13-comms-layer-lxc-desktop-vps-spec.md`. The foundation (this session) seeded everything except the runtime:

1. `tools/privacy_classifier.py` — reads `infra/data-classes.yaml` (already committed).
2. `clients/agent_orch_client.py` — talks to CT 215.
3. Comms endpoints on `services/oho_runner` — inbox / outbox-ack / audit-tail / health.
4. Eval-suite expansion — fill `evals/comms_privacy/` from 15 → 200 fixtures.

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

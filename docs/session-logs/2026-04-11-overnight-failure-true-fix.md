# ObsidianHomeOrchestrator Overnight Failure — True Root-Cause Fix

> Superseded in part by [2026-04-11-credential-root-cause-reanalysis.md](./2026-04-11-credential-root-cause-reanalysis.md).
> The later analysis corrects the MinIO diagnosis: the recurring failure was not just a stale secret. It also involved mixed `s3` / `awsS3` workflow families, live-vs-repo drift, and a broken SMTP payload in `setup-n8n.sh` that could stop redeploys halfway through.

**Date:** 2026-04-11
**Branch:** polish/prod-ready
**Commit:** 48f6631
**Session lead:** Claude Opus 4.6 (1M context)

## Symptom

Overnight 2026-04-10 → 2026-04-11, the live n8n stack on Proxmox CT-202 generated 20–36 error emails. `live-dashboard-updater` (hourly) and `system-health-monitor` (every 6 h) were the loudest. `morning-briefing` also failed every morning.

## What the prior session got wrong

Commit `bf34424` ("fix+optimize(qa): full system hardening") claimed to bulk-patch the dead MinIO cred `z9qTyG2NVVbhHkg0` across all 12 workflows. It did patch the JSON files in the repo — but **never re-deployed to live n8n**. The live workflows kept calling the dead credential. Tests passed because they exercised Python tools locally; the n8n execution paths were never touched.

## Root cause #1 — Dead MinIO credential never re-applied

Three MinIO credentials exist in n8n:

| ID | Name | Type | Used by |
|---|---|---|---|
| `LTRuRgfeUawXu3tr` | MinIO S3 (Generic) | s3 | (legacy) |
| `73vWB22hTYrodZ3G` | MinIO S3 v2 | aws | (job-search-pipeline) |
| `z9qTyG2NVVbhHkg0` | **MinIO S3** | aws | **all OHO workflows** |

The third one's stored secret was stale. Error log showed `Credential with ID "z9qTyG2NVVbhHkg0" does not exist for type "s3"` — misleading; it existed but the secret couldn't authenticate.

**Fix:** PATCH `/api/v1/credentials/z9qTyG2NVVbhHkg0` with current `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` from `.env`. Then re-deploy every workflow JSON to refresh node references and add safeguards.

## Root cause #2 — n8n executionOrder v1 double-execution bug

With `settings.executionOrder: "v1"`, when a node has TWO incoming connections from parallel branches, it runs **once per incoming branch** rather than once with merged input. `system-health-monitor` and `weekly-digest-v2` both had:

```
Trigger → [S3 Read A, S3 Read B] → Build
```

`Build` ran twice → 2 emails, 2 log writes per execution. **Sunday weekly digest was emailing twice every week.**

**Fix:** chain the parallel S3 reads sequentially (`Trigger → A → B → Build`) so `Build` sees a single input. Cross-references via `$('Other Node').first().json` still work fine.

## Other fixes shipped together

| Workflow | Fix |
|---|---|
| `live-dashboard-updater` | If MTL read fails, return `_skip:true` and gate the S3 write behind an IF — prevents overwriting the good dashboard with an empty one. |
| `brain-dump-processor-v2` | continueOnFail on List/Download/Email + new **No-Work Log** path so morning-briefing always finds yesterday's log even when no brain dumps were captured. |
| `overdue-task-alert-v2` | continueOnFail on S3 Read MTL + Email. |
| `error-handler` | continueOnFail on Email so the S3 log always writes (if SMTP is also down you still need the audit trail). |
| `vault-health-report`, `morning-briefing`, `daily-note-creator` | email continueOnFail. |
| `daily-note-creator-v2` | date computation switched from `toISOString().split('T')[0]` (UTC) to `toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })`. |
| `telegram-capture` | bad webhook secrets now emit `_skip:true` instead of throwing — was triggering global error handler on every probe. |
| All deployed workflows | `errorWorkflow=jIOFmhr37mXEhlHz` wired automatically by deploy script. |

## Verification done in-session

- `python3 scripts/health_check.py` → PASS (4/4)
- boto3 end-to-end against live MinIO with current key: `list` / `get` / `put` / `head` / `delete` on every prefix the workflows touch — all OK
- All 11 workflows redeployed via direct n8n API (`/tmp/deploy_workflows.py`) and re-activated
- Spot-check on morning-briefing's deployed JSON: all S3 nodes show `cred_id=z9qTyG2NVVbhHkg0`, `continueOnFail=true`, `errorWorkflow=jIOFmhr37mXEhlHz`

## Pending verification

- Next `live-dashboard-updater` hourly run (14:00 UTC) — should succeed cleanly
- Next `morning-briefing` run (12:00 UTC tomorrow = 7 AM CDT)
- A full 24 h cycle of error-email count — target zero false alerts

## Reusable lessons (for future Claude sessions)

1. **n8n parallel-branch double exec** is a real footgun. Sequential chain is safer than parallel + implicit merge.
2. **Every external call needs continueOnFail** — every n8n S3/HTTP/SMTP node, not just the obvious ones. Otherwise transient blips cascade through the global error handler.
3. **`setup-n8n.sh`'s `find_cred_id` is unreliable** — silent failure swallowed by `set -e` + `2>/dev/null`. Prefer direct API calls with hardcoded credential IDs.
4. **Repo JSON ≠ live n8n state.** A commit that changes workflow files is HALF a fix. The other half is the deploy + activation + verification.
5. **n8n cron is UTC.** Per-workflow timezone is display-only. Compute Chicago dates explicitly inside Code nodes.

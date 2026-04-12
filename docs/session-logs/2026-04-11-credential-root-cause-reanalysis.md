# ObsidianHomeOrchestrator Credential Root-Cause Reanalysis

**Date:** 2026-04-11
**Repo state:** `polish/prod-ready`

## Why the credential issue kept coming back

This was not just a bad secret.

There were three separate failure vectors interacting:

1. The repo historically mixed two S3 node families:
   - `n8n-nodes-base.s3` using `credentials.s3`
   - `n8n-nodes-base.awsS3` using `credentials.aws`
2. Live n8n had drifted away from the repo. Some workflows were republished onto `credentials.s3`, while `article-processor` was still on legacy `awsS3`.
3. The deploy script itself had a bug in the SMTP payload. On current n8n versions, `smtp` credentials with `"secure": false` also require `"disableStartTls": false`. Because that field was missing, `setup-n8n.sh` could die halfway through and leave live n8n in a partially repaired state.

That is why rotating or re-selecting credentials in the UI could appear to help one workflow family while leaving the other one broken.

## Live failure signatures observed before the true fix

- `Credential with ID "z9qTyG2NVVbhHkg0" does not exist for type "s3".`
  This hit `live-dashboard-updater`, `overdue-task-alert-v2`, and `error-handler` after those workflows were pointed at `credentials.s3`.
- `403 AccessDenied` / `Forbidden - perhaps check your credentials?`
  This hit workflows still bound to a real-but-wrong MinIO credential object.
- `article-processor` could report `success` even when the queue read failed.
  Root cause: its queue-read node used `onError: continueRegularOutput`, so the parse step treated a failed read as an empty queue.

## Fixes applied

### Repo hardening

- Standardized workflow templates on `n8n-nodes-base.s3`.
- Migrated `workflows/n8n/article-processor.json` off legacy `awsS3`.
- Removed the silent queue-read masking path from `article-processor`.
- Added `scripts/audit_workflow_credentials.py` to fail fast if `s3` and `awsS3` families are mixed again.

### Deploy-path hardening

- Fixed `scripts/setup-n8n.sh` SMTP payload to include:

```json
"disableStartTls": false
```

Without that field, the script could stop after touching MinIO and before finishing workflow import.

### Live n8n repair performed on 2026-04-11

`set -a && source .env && set +a && bash scripts/setup-n8n.sh`

Result:

- MinIO credential `z9qTyG2NVVbhHkg0` updated via API
- SMTP credential `lWGOwsktldwb3iEj` updated via API
- OpenRouter credential `Z7liUYc3Toq3q7W7` updated via API
- All active ObsidianHomeOrchestrator workflows re-imported and re-activated

Notable live timestamps after the successful redeploy:

- `📚 Article Processor — 8AM & 7PM` updated at `2026-04-11T14:01:32.698Z`
- `🚨 Error Handler — Global` updated at `2026-04-11T14:01:32.223Z`
- `⚠️ Overdue Task Alert v2 — 8AM Daily` updated at `2026-04-11T14:01:33.465Z`
- `🌅 Morning Briefing — 7AM Daily` updated at `2026-04-11T14:01:34.008Z`

## Current state after repair

- Live `article-processor` now uses `n8n-nodes-base.s3` for all MinIO nodes.
- Live `article-processor` now throws if the queue read fails instead of pretending the queue is empty.
- Live `morning-briefing`, `overdue-task-alert-v2`, `live-dashboard-updater`, and `error-handler` all reference the same canonical MinIO credential name and ID.
- `python3 scripts/health_check.py` passed after redeploy.

## Remaining verification window

The remaining confidence step is scheduled execution after the 2026-04-11 14:01 UTC redeploy:

- `📊 Live Dashboard Updater — Hourly`: next scheduled run after redeploy
- `🌅 Morning Briefing — 7AM Daily`: next run on **2026-04-12 12:00:00 UTC**
- `⚠️ Overdue Task Alert v2 — 8AM Daily`: next run on **2026-04-12 13:00:00 UTC**

## Operator takeaway

If this symptom comes back, do **not** assume the answer is “switch the credential again.”

Check these in order:

1. `python3 scripts/audit_workflow_credentials.py`
2. `set -a && source .env && set +a && bash scripts/setup-n8n.sh`
3. Confirm the affected live workflow `updatedAt` changed after the redeploy
4. Then inspect the next execution result

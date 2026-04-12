# 2026-04-12 QA Revalidation And Guardrails

## Summary

This pass was a full QA revalidation after the April 11 credential-family fix.
The core MinIO credential drift issue remained fixed, but QA surfaced a second
class of failure: several n8n workflow templates routed log-writing nodes
through `Email:` nodes and implicitly assumed `emailSend` would preserve the
upstream JSON payload. In live executions that caused broken log filenames such
as `morning-briefing-undefined.json`.

## Root Cause Confirmed

1. The original repeated breakage was caused by mixed `n8n-nodes-base.s3` and
   `n8n-nodes-base.awsS3` families across workflow templates.
2. After that was fixed, a separate workflow-graph defect remained:
   log-building/writing nodes were connected downstream of `Email:` nodes in
   several workflows, so fields like `today`, `logKey`, and `logContent` were
   no longer reliable.

## Changes Made

### Workflow template fixes

The following workflows were rewired so logging branches from the pre-email node
instead of depending on `emailSend` output:

- `workflows/n8n/morning-briefing.json`
- `workflows/n8n/overdue-task-alert-v2.json`
- `workflows/n8n/vault-health-report.json`
- `workflows/n8n/error-handler.json`
- `workflows/n8n/weekly-digest-v2.json`

### Deploy safety

`scripts/setup-n8n.sh` now:

- runs `scripts/audit_workflow_connections.py` before deploy
- fails fast if workflow update fails
- fails fast if workflow import fails
- fails fast if activation fails
- no longer swallows failed create responses with `|| echo '{}'`

### New guardrails

- Added `scripts/audit_workflow_connections.py`
  - blocks any workflow where an `Email:` node feeds a log node
- Added `tests/test_workflow_templates.py`
  - asserts email nodes do not feed log nodes
  - asserts `setup-n8n.sh` does not swallow workflow import failures
- Fixed `tests/conftest.py`
  - mocked env overrides now skip `@pytest.mark.integration`
- Fixed `tests/test_process_brain_dump_e2e.py`
  - integration marker no longer relies on a subprocess wrapper

## Validation Performed

### Local

- `python3 scripts/audit_workflow_credentials.py` ✅
- `python3 scripts/audit_workflow_connections.py` ✅
- `bash -n scripts/setup-n8n.sh` ✅
- `pytest tests/ -v --ignore=tests/test_process_brain_dump_e2e.py -k "not integration"` ✅
- `set -a && source .env && set +a && python3 scripts/e2e_test.py` ✅
- `set -a && source .env && set +a && python3 scripts/health_check.py` ✅

### Integration

- `RUN_INTEGRATION_TESTS=1 pytest tests/ -v -m integration` passed when rerun
  outside the Codex shell sandbox.
- Inside the default Codex sandbox, the same integration run hit a network
  permission error while opening the live MinIO socket. That was environmental,
  not a product regression.

### Live n8n

- Redeployed with `set -a && source .env && set +a && bash scripts/setup-n8n.sh`
- Verified updated live workflow graphs for:
  - `🌅 Morning Briefing — 7AM Daily`
  - `⚠️ Overdue Task Alert v2 — 8AM Daily`
  - `Vault Health Report - Weekly Sunday`
  - `📊 Weekly Needle Mover Digest v2 — Sunday 6PM`
  - `🚨 Error Handler — Global`
- Confirmed active versions now contain the corrected branch topology.

## Current Confidence

Confidence is materially higher than before this QA pass:

- local tests are green
- direct live MinIO E2E is green
- deploy is fail-fast instead of partially silent
- the known email/log workflow defect is fixed in repo and in live n8n
- the live deployed graphs match the patched templates

## Remaining Limitation

The available n8n MCP execution endpoint would not manually fire these
schedule-triggered workflows via API, so same-minute runtime proof for the new
log filenames was not available through the API surface in this session.
The strongest available evidence is:

- prior successful scheduled executions
- direct live stack health + E2E passing
- successful redeploy
- live workflow graph inspection showing the corrected connections

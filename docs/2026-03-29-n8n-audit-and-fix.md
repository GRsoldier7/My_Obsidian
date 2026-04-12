# n8n Workflow Audit & Fix — 2026-03-29

## Context
Full audit of the ObsidianHomeOrchestrator repo and live n8n instance (http://192.168.1.121:5678) revealed critical issues causing 99.8% workflow failure rate (5,541 failures out of 5,554 executions in 7 days).

## Root Causes Found

### 1. PolyChronos Inbox Processor — Failure Factory (CRITICAL)
- **Workflow ID:** `Y5rnu63Ms2NNjoRq`
- **Problem:** Running every 2 minutes, hitting `http://100.76.55.60:3001/status` (Tailscale IP, unreachable)
- **Impact:** 720 failures/day = ~5,040 failures/week = 99% of all failures
- **Fix:** Deactivated via API. Workflow needs Tailscale connectivity or a valid endpoint before reactivation.

### 2. MinIO S3 Credential — InvalidAccessKeyId (CRITICAL)
- **Credential ID (old):** `[OLD_MINIO_CRED_ID]`
- **Problem:** Access key stored in n8n (`[REDACTED]...`) did not match any key in MinIO. All S3 operations failed.
- **Impact:** Daily Note Creator failing every day since Mar 25. Brain Dump Processor S3 reads failing.
- **Fix:** Deleted old credential, created new one (ID: `[MINIO_CRED_ID]`) with correct access key from MinIO service account `Claude_Code` (access key: `[REDACTED_MINIO_ACCESS_KEY]`). Updated all 5 workflows referencing MinIO.

### 2a. Mixed S3 Node Families Caused Credential Drift (CRITICAL)
- **Problem:** The repo mixed `n8n-nodes-base.s3` nodes and legacy `n8n-nodes-base.awsS3` nodes while reusing one `__MINIO_CRED_ID__` placeholder and one credential name (`MinIO S3`).
- **Why this re-broke after credential changes:** n8n binds credential IDs by both ID and credential type. A credential object valid for type `aws` is not valid for a node asking for type `s3`, even if the name is the same. That created an oscillating failure pattern where one workflow family could be "fixed" while the other still failed with `credential does not exist for type s3`.
- **Secondary problem:** some workflows swallowed S3 read failures and continued with empty/default outputs, which made broken storage access look like successful runs.
- **Fix:** Standardized repo workflows on `n8n-nodes-base.s3` only, migrated `article-processor.json` off legacy `awsS3`, and added a deployment preflight (`scripts/audit_workflow_credentials.py`) that hard-fails if `awsS3` and `s3` families are mixed again.

### 3. Weekly Digest Merge Node — Configuration Error (HIGH)
- **Workflow ID:** `qQ4fidC1K755758J`
- **Problem:** Merge node in `combine` mode with `mergeByPosition` was throwing "You need to define at least one pair of fields in 'Fields to Match'" when S3 downloads failed.
- **Fix:** Changed Merge mode from `combine/mergeByPosition` to `append`. The downstream code node reads items by node name (`$('S3: Get North Star').first()`), so it only needs both nodes to complete — no merge logic needed.

### 4. Brain Dump Processor — staticData TypeError (MEDIUM)
- **Workflow ID:** `8TJ3vq809NyVnVF2`
- **Problem:** "Parse & Analyze All" node used `$workflow.staticData` which is undefined in some n8n versions.
- **Fix:** Already fixed in live workflow (uses `$getWorkflowStaticData("global")` now). Mar 29 execution succeeded.

### 5. Repo/Live Workflow Divergence (MEDIUM)
- **Problem:** Repo had simple versions of workflows. Live n8n had evolved versions with OpenRouter/Llama 3.3 70B integration, AI-powered triage, and additional S3 reads.
- **Fix:** Exported all 7 live workflows from n8n to sync the repo. Repo now reflects the actual running state.

### 6. Credential Name Mismatch in setup-n8n.sh (MEDIUM)
- **Problem:** `setup-n8n.sh` created credentials as `MinIO — obsidian-vault` and `Gmail SMTP`, but workflows expected `MinIO S3` and `Gmail SMTP (Aaron)`. The sed replacement looked for `MINIO_CRED_ID`/`SMTP_CRED_ID` placeholders that didn't exist in the JSON files.
- **Fix:** Standardized on workflow names (`MinIO S3`, `Gmail SMTP (Aaron)`). All workflow JSONs now use `__MINIO_CRED_ID__`, `__SMTP_CRED_ID__`, `__OPENROUTER_CRED_ID__`, and `__NOTIFICATION_EMAIL__` placeholders. Setup script hydrates these before import.

### 7. Hardcoded Values Throughout (LOW)
- **Problem:** Email addresses, credential IDs, and some config values hardcoded across workflow JSONs.
- **Fix:** All replaced with placeholders. `.env.example` documents every variable and its consumer.

## Files Changed

### Workflow Templates (repo copies with placeholders)
| File | Status | Credential Refs |
|------|--------|----------------|
| `workflows/n8n/brain-dump-processor.json` | Exported from live n8n | MinIO, SMTP, OpenRouter |
| `workflows/n8n/daily-note-creator.json` | Exported from live n8n | MinIO, OpenRouter |
| `workflows/n8n/overdue-task-alert.json` | Exported from live n8n | MinIO, SMTP, OpenRouter |
| `workflows/n8n/weekly-digest.json` | Exported + Merge fix | MinIO, SMTP, OpenRouter |
| `workflows/n8n/ai-brain.json` | NEW — exported from live n8n | OpenRouter |
| `workflows/n8n/article-processor.json` | NEW — exported from live n8n | MinIO, OpenRouter |
| `workflows/n8n/job-search-pipeline.json` | NEW — exported from live n8n | (none) |

### Scripts & Config
| File | Change |
|------|--------|
| `scripts/setup-n8n.sh` | Full rewrite: 3 credentials (MinIO, SMTP, OpenRouter), 6 workflows, Python-based hydration, JSON validation, read-only field stripping |
| `.env.example` | Added `OPENROUTER_API_KEY`, `NOTIFICATION_EMAIL`, consumer annotations for every variable |
| `.gitignore` | Added `.claude/worktrees/` to prevent token leaks |
| `tools/process_brain_dump.py` | `--vault-path` now falls back to `OBSIDIAN_VAULT_PATH` env var |

## Live n8n State After Fix

### Credentials
| Name | Type | ID | Status |
|------|------|-----|--------|
| MinIO S3 | s3 | `[MINIO_CRED_ID]` | NEW — correct access key |
| Gmail SMTP (Aaron) | smtp | `[SMTP_CRED_ID]` | Unchanged |
| OpenRouter API | httpHeaderAuth | `[OPENROUTER_CRED_ID]` | Unchanged |

### Workflows
| Workflow | Schedule | Status |
|----------|----------|--------|
| Brain Dump Processor — Daily 7AM | 7:00 AM daily | ACTIVE |
| Daily Note Creator — 6AM | 6:00 AM daily | ACTIVE |
| Overdue Task Alert — 8AM Daily | 8:00 AM daily | ACTIVE |
| Weekly Needle Mover Digest — Sunday 6PM | Sunday 6:00 PM | ACTIVE |
| AI Brain — Shared Intelligence Layer | (sub-workflow) | ACTIVE |
| Article Processor — 8AM & 7PM | 8:00 AM + 7:00 PM | ACTIVE |
| PolyChronos Inbox Processor | Every 2 min (BROKEN) | **DEACTIVATED** |

### 8. Homelab/ Prefix — Paths Were All Wrong (CRITICAL)
- **Problem:** ALL workflow S3 paths prepended `Homelab/` (e.g., `Homelab/000_Master Dashboard/North Star.md`). But the actual vault files in MinIO are at the bucket root (e.g., `000_Master Dashboard/North Star.md`). Remotely Save syncs without the `Homelab/` prefix. This meant every S3 read/write silently failed (NoSuchKey) and workflows "succeeded" by processing empty data.
- **Impact:** Every workflow was functionally broken even when credentials were correct. No brain dumps were being processed, no task lists read, no daily notes created.
- **Fix:** Removed all `Homelab/` prefix references from every workflow JSON — both hardcoded `fileKey` parameters and `const PREFIX = 'Homelab'` in JavaScript code nodes. Updated `.env.example` to mark `MINIO_VAULT_PREFIX` as reference-only. All S3 paths now point directly to bucket-root paths matching the actual MinIO structure.
- **Verification:** boto3 direct read tests confirm North Star (5986 bytes), Master Task List (6264 bytes), Brain Dump Faith (1267 bytes) all readable at corrected paths. Write+delete test also passes.

## Remaining Items
- [ ] PolyChronos Inbox Processor needs valid endpoint before reactivation
- [ ] Job Search Pipeline not managed by setup-n8n.sh (separate system)
- [ ] E2E test: manually trigger Daily Note Creator to confirm S3 writes work with new credential
- [ ] Monitor n8n failure rate over next 24h to confirm fix

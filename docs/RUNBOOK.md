# ObsidianHomeOrchestrator — Operations Runbook

> Audience: Aaron (operator). Everything you need to debug, rotate credentials, or re-deploy the Life OS stack from scratch.

---

## Table of Contents

1. [Stack Overview](#stack-overview)
2. [Daily Health Check](#daily-health-check)
3. [Log Locations](#log-locations)
4. [Manual Trigger Commands](#manual-trigger-commands)
5. [Credential Rotation Playbook](#credential-rotation-playbook)
6. [Common Failures & Decision Tree](#common-failures--decision-tree)
7. [Re-deploy from Scratch](#re-deploy-from-scratch)
8. [Bitwarden MCP Session Refresh](#bitwarden-mcp-session-refresh)
9. [MCP Server Capabilities](#mcp-server-capabilities)
10. [Telegram Bot Setup](#telegram-bot-setup)
11. [Oncall Checklist](#oncall-checklist)

---

## Stack Overview

```
Obsidian Vault (Mac)
        │
        ▼ (Remotely-Save plugin syncs files)
MinIO S3 (192.168.1.240:9000)
  Bucket: obsidian-vault   [NO prefix — files at bucket root]
        │
        ▼ (n8n reads/writes via S3 nodes)
n8n (192.168.1.121:5678)  ← Proxmox LXC CT-202
  14 active workflows
        │
        ├── OpenRouter API (AI extraction)
        ├── Gmail SMTP (alert emails)
        └── PostgreSQL (execution history)
```

**Vault path on network share:** `/Volumes/home/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator` (Mac mount)

---

## Daily Health Check

```bash
cd /path/to/ObsidianHomeOrchestrator
set -a && source .env && set +a
python3 scripts/health_check.py
```

Expected output — all `[PASS]`:
```
[PASS] minio: Bucket 'obsidian-vault' accessible at http://192.168.1.240:9000
[PASS] n8n: n8n healthy at http://192.168.1.121:5678
[PASS] vault_files: All 4 required files present
[PASS] brain_dumps: N brain dump file(s) found
Overall: PASS
```

Or via make (Phase 7):
```bash
make health
```

---

## Log Locations

All workflow runs write a JSON log to MinIO:

```
99_System/logs/{workflow-name}-{YYYY-MM-DD}.json
```

| Workflow | Log key pattern |
|----------|----------------|
| Brain Dump Processor | `99_System/logs/brain-dump-processor-2026-04-08.json` |
| Daily Note Creator | `99_System/logs/daily-note-creator-2026-04-08.json` |
| Morning Briefing | `99_System/logs/morning-briefing-2026-04-08.json` |
| Overdue Task Alert | `99_System/logs/overdue-task-alert-2026-04-08.json` |
| Weekly Digest | `99_System/logs/weekly-digest-2026-04-08.json` |
| Vault Health Report | `99_System/logs/vault-health-report-2026-04-08.json` |
| Live Dashboard Updater | `99_System/logs/live-dashboard-updater-2026-04-08.json` |
| System Health Monitor | `99_System/logs/system-health-monitor-2026-04-08.json` |

**Read a log via MinIO Console:** http://192.168.1.240:9001 → Browser → obsidian-vault → 99_System/logs/

**Read a log via CLI:**
```bash
set -a && source .env && set +a
python3 -c "
import boto3, json, os
from botocore.client import Config
s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'],
    aws_access_key_id=os.environ['MINIO_ACCESS_KEY'],
    aws_secret_access_key=os.environ['MINIO_SECRET_KEY'],
    config=Config(signature_version='s3v4'), region_name='us-east-1')
log = s3.get_object(Bucket='obsidian-vault',
    Key='99_System/logs/brain-dump-processor-2026-04-08.json')
print(json.dumps(json.loads(log['Body'].read()), indent=2))
"
```

---

## Manual Trigger Commands

### Run brain dump processor manually
```bash
set -a && source .env && set +a
python3 tools/process_brain_dump.py --verbose
```

### Dry run (no writes to MinIO)
```bash
set -a && source .env && set +a
python3 tools/process_brain_dump.py --dry-run --verbose
```

### Process a specific brain dump file
```bash
set -a && source .env && set +a
python3 tools/process_brain_dump.py --file "BrainDump — Personal.md" --verbose
```

### Trigger a workflow via n8n API
```bash
# Replace WORKFLOW_ID with the n8n workflow ID (visible in n8n UI URL)
curl -X POST http://192.168.1.121:5678/api/v1/workflows/WORKFLOW_ID/execute \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Run e2e test
```bash
set -a && source .env && set +a
python3 scripts/e2e_test.py
```

### Validate environment
```bash
set -a && source .env && set +a
python3 scripts/validate_env.py
```

---

## Credential Rotation Playbook

### MinIO access key rotation

1. Open MinIO Console: http://192.168.1.240:9001
2. Navigate to: Identity → Service Accounts → find the OHO service account
3. Click "Rotate" → copy new Access Key + Secret Key
4. Update `.env`: set `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`
5. Re-run the workflow audit before redeploying:
   ```bash
   python3 scripts/audit_workflow_credentials.py
   ```
6. Re-run setup to push new creds to n8n:
   ```bash
   set -a && source .env && set +a
   bash scripts/setup-n8n.sh
   ```
7. Verify: `python3 scripts/health_check.py` → minio: PASS

If you see `Credential with ID "..." does not exist for type "s3"`, do not just re-select credentials in the UI. That symptom can mean live workflows are still out of sync with the repo or a legacy `awsS3` workflow is still present.

### OpenRouter API key rotation

1. Go to https://openrouter.ai → Keys → Revoke old key → Create new key
2. Update `.env`: set `OPENROUTER_API_KEY`
3. Re-run setup:
   ```bash
   set -a && source .env && set +a
   bash scripts/setup-n8n.sh
   ```
4. Verify: Run brain dump processor dry-run → no auth errors

### Gmail App Password rotation

1. Go to https://myaccount.google.com → Security → 2-Step Verification → App passwords
2. Delete old "OHO n8n" app password → create new one
3. Update `.env`: set `SMTP_PASS` to the new 16-character password
4. Re-run setup:
   ```bash
   set -a && source .env && set +a
   bash scripts/setup-n8n.sh
   ```
5. Trigger morning briefing workflow in n8n UI to confirm email sends

### n8n API key rotation

1. Open n8n: http://192.168.1.121:5678 → Settings → API → delete old key → Create new
2. Update `.env`: set `N8N_API_KEY`
3. Verify: `python3 scripts/validate_env.py` → exits 0

---

## Common Failures & Decision Tree

### Symptom: No morning briefing email received

```
1. Check n8n dashboard → is morning-briefing workflow ACTIVE?
   YES → go to 2
   NO  → activate it in n8n UI

2. Check last execution in n8n → any errors?
   YES, SMTP error → rotate Gmail App Password (see above)
   YES, MinIO error → check MinIO connectivity (health_check.py)
   NO executions → check schedule trigger (should be 12:00 UTC = 7AM CDT)

3. Check spam folder in Gmail
```

### Symptom: Brain dump not processed

```
1. Check 00_Inbox/brain-dumps/ in MinIO — is the file there?
   NO  → Remotely-Save plugin may not have synced; open Obsidian and force sync
   YES → go to 2

2. Check n8n → brain-dump-processor-v2 last execution
   FAILED → check error: usually OpenRouter rate limit or MinIO auth
   NEVER RAN → check schedule trigger (daily 12:00 UTC = 7AM CDT)

3. Run manually:
   python3 tools/process_brain_dump.py --verbose
   Look for "ERROR" or "RATE_LIMIT" in output

4. OpenRouter rate limit?
   YES → wait 1 hour; free tier limits are per-model. Cascade will try 3 models.
   If all 3 fail → processor falls back to regex-only extraction (still works, no AI enrichment)
```

### Symptom: Tasks not appearing in Obsidian

```
1. Check 00_Inbox/processed/ in MinIO — is the output file there?
   NO  → brain dump processor failed (see above)
   YES → go to 2

2. Has Remotely-Save synced recently?
   Open Obsidian → check status bar or force sync
   Sync interval default: 5 minutes

3. Check task format in the processed file — must match canonical format:
   - [ ] Task description [area:: faith] [priority:: A]
   If malformed → Dataview queries won't find it
```

### Symptom: n8n workflows showing 0% success rate

```
1. python3 scripts/health_check.py → check n8n: PASS or FAIL?
   FAIL → n8n LXC may be down
   
2. SSH to Proxmox → check CT-202:
   pct status 202
   pct start 202  (if stopped)

3. Once n8n is up → re-run setup-n8n.sh to re-activate all workflows:
   set -a && source .env && set +a && bash scripts/setup-n8n.sh
```

### Symptom: MinIO unreachable

```
1. Ping 192.168.1.240 — is the MiniPC up?
   NO  → power cycle MiniPC
   YES → go to 2

2. curl http://192.168.1.240:9000/minio/health/live
   200 → MinIO healthy, check credentials
   non-200 or timeout → MinIO container down

3. SSH to MiniPC → docker ps | grep minio
   If not running: docker start minio (or docker compose up -d)
```

---

## Re-deploy from Scratch

Full re-deployment if n8n is wiped or credentials lost:

```bash
# 1. Clone repo
git clone https://github.com/GRsoldier7/ObsidianHomeOrchestrator
cd ObsidianHomeOrchestrator

# 2. Set up environment
cp .env.example .env
# Edit .env — fill in all required vars (see validate_env.py for the full list)

# 3. Validate env
set -a && source .env && set +a
python3 scripts/validate_env.py

# 4. Run setup (creates n8n credentials + imports all 11 workflows)
bash scripts/setup-n8n.sh

# 5. Verify
python3 scripts/health_check.py
python3 scripts/e2e_test.py
```

Expected time: ~10 minutes on a working homelab stack.

---

## Bitwarden MCP Session Refresh

The Bitwarden MCP session token expires when the vault locks. When Claude Code loses access to Bitwarden tools:

```bash
# 1. Unlock vault (enter master password when prompted)
bw unlock --raw
# Copy the session token printed to stdout

# 2. Update settings.json
# Edit ~/.claude/settings.json → find "BW_SESSION" → paste new token

# 3. Restart Claude Code
# Bitwarden + all other MCP servers will re-activate on next launch
```

To check if Bitwarden server is configured:
```bash
cat ~/.claude/settings.json | python3 -c "import json,sys; cfg=json.load(sys.stdin); print(json.dumps(cfg.get('mcpServers',{}), indent=2))"
```

---

## MCP Server Capabilities

Configured in `~/.claude/settings.json`. These give Claude Code direct access to the stack:

| Server | What it enables | When to use |
|--------|----------------|-------------|
| **Bitwarden** | Pull secrets from self-hosted Vaultwarden | Rotating credentials without editing .env |
| **Filesystem** | Read/write vault files directly | Inspect or edit Obsidian notes without shell |
| **n8n MCP** | List workflows, trigger executions, view logs | Debug failing workflows in one chat turn |
| **PostgreSQL** | Read-only query of n8n execution DB | "What failed last night?" in one query |
| **Sequential Thinking** | Structured multi-step reasoning | Complex workflow design tasks |

---

## Telegram Bot Setup

Status: **pending** (Phase 8). When ready:

```bash
# 1. Create bot via @BotFather in Telegram
#    /newbot → follow prompts → copy the token

# 2. Add to .env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_WEBHOOK_SECRET=some_random_secret_32_chars

# 3. Register webhook
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=http://192.168.1.121:5678/webhook/telegram-capture" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"

# 4. Send a test message to the bot → verify file appears in 00_Inbox/brain-dumps/
```

---

## Oncall Checklist

**Morning (automated — verify at 8AM CDT):**
- [ ] Morning briefing email received
- [ ] n8n dashboard: 0 failed executions in last 24h

**Weekly (Sunday):**
- [ ] Weekly digest email received (6PM CDT)
- [ ] Vault health report email received (8PM CDT)
- [ ] Check OpenRouter quota: https://openrouter.ai/account
- [ ] Review 99_System/logs/ for any repeated errors

**Monthly:**
- [ ] Rotate MinIO access key
- [ ] Rotate OpenRouter API key
- [ ] Check MinIO disk usage (console → Monitoring → Metrics)
- [ ] `pytest --cov=tools` still passing

**After any credential rotation:**
1. Run `python3 scripts/validate_env.py` → exits 0
2. Run `bash scripts/setup-n8n.sh` → all workflows re-imported
3. Run `python3 scripts/health_check.py` → all PASS
4. Run `python3 scripts/e2e_test.py` → 11/11 pass

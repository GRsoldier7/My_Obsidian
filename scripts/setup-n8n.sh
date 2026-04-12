#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# ObsidianHomeOrchestrator — n8n Setup Script
#
# Setup: reuses credential IDs from existing workflows when possible,
# creates fresh credentials when needed, hydrates workflow templates
# with real IDs, imports/updates all workflows, and activates them.
#
# Workflow JSONs in workflows/n8n/ are TEMPLATES containing these
# placeholders (never commit real IDs to git):
#   __MINIO_CRED_ID__       → replaced with the real MinIO cred ID
#   __SMTP_CRED_ID__        → replaced with the real SMTP cred ID
#   __OPENROUTER_CRED_ID__  → replaced with the real OpenRouter cred ID
#   __NOTIFICATION_EMAIL__  → replaced with NOTIFICATION_EMAIL env var
#
# Usage:
#   set -a && source .env && set +a && bash scripts/setup-n8n.sh
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKFLOW_DIR="$SCRIPT_DIR/../workflows/n8n"

# ── Read config from environment (with defaults where safe) ─────
N8N_HOST="${N8N_HOST:-http://192.168.1.121:5678}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://192.168.1.240:9000}"
SMTP_HOST="${SMTP_HOST:-smtp.gmail.com}"
SMTP_PORT="${SMTP_PORT:-587}"
NOTIFICATION_EMAIL="${NOTIFICATION_EMAIL:-${SMTP_USER:-}}"

# ── Canonical credential names (must match workflow JSONs) ──────
MINIO_CRED_NAME="MinIO S3"
SMTP_CRED_NAME="Gmail SMTP (Aaron)"
OPENROUTER_CRED_NAME="OpenRouter API"

# ── Validate required env vars ──────────────────────────────────
required_vars=(N8N_API_KEY MINIO_ACCESS_KEY MINIO_SECRET_KEY SMTP_USER SMTP_PASS OPENROUTER_API_KEY)
missing=()
for var in "${required_vars[@]}"; do
  [[ -z "${!var:-}" ]] && missing+=("$var")
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: Missing required environment variables:"
  for v in "${missing[@]}"; do echo "   - $v"; done
  echo ""
  echo "Set them in .env and run:  source .env && bash $0"
  echo ""
  echo "Required:"
  echo "  N8N_API_KEY       — Generate at n8n > Settings > API > Create API Key"
  echo "  MINIO_ACCESS_KEY  — MinIO service account access key"
  echo "  MINIO_SECRET_KEY  — MinIO service account secret key"
  echo "  SMTP_USER         — Gmail address (e.g. your-email@gmail.com)"
  echo "  SMTP_PASS         — Gmail App Password"
  echo "  OPENROUTER_API_KEY — OpenRouter API key (free tier at openrouter.ai)"
  echo ""
  echo "Optional (have defaults):"
  echo "  N8N_HOST            — Default: http://192.168.1.121:5678"
  echo "  MINIO_ENDPOINT      — Default: http://192.168.1.240:9000"
  echo "  SMTP_HOST           — Default: smtp.gmail.com"
  echo "  SMTP_PORT           — Default: 587"
  echo "  NOTIFICATION_EMAIL  — Default: \$SMTP_USER"
  exit 1
fi

if [[ -z "$NOTIFICATION_EMAIL" ]]; then
  echo "ERROR: NOTIFICATION_EMAIL and SMTP_USER are both empty."
  exit 1
fi

echo "Running workflow credential audit..."
python3 "$SCRIPT_DIR/audit_workflow_credentials.py"
python3 "$SCRIPT_DIR/audit_workflow_connections.py"
echo "OK — workflow credential family is consistent"
echo ""

API="$N8N_HOST/api/v1"

# ── Helper: n8n API call ────────────────────────────────────────
n8n_api() {
  local method="$1" path="$2"
  shift 2
  curl -sf -X "$method" "$API$path" \
    -H "X-N8N-API-KEY: $N8N_API_KEY" \
    -H "Content-Type: application/json" \
    "$@"
}

# ── Helper: find referenced credential IDs from existing workflows ──────────
# n8n does not support GET /credentials over the public REST API, so we
# recover IDs from workflow node credential bindings instead.
find_cred_id_from_workflows() {
  local cred_name="$1" cred_key="$2"
  local workflow_ids wf_id found_id

  workflow_ids=$(
    n8n_api GET "/workflows" 2>/dev/null | \
      python3 -c '
import json, sys
for workflow in json.load(sys.stdin).get("data", []):
    print(workflow["id"])
' 2>/dev/null || true
  )

  for wf_id in $workflow_ids; do
    found_id=$(
      n8n_api GET "/workflows/$wf_id" 2>/dev/null | \
        TARGET_NAME="$cred_name" TARGET_KEY="$cred_key" python3 -c '
import json, os, sys

target_name = os.environ["TARGET_NAME"]
target_key = os.environ["TARGET_KEY"]
workflow = json.load(sys.stdin)

for node in workflow.get("nodes", []):
    cred = node.get("credentials", {}).get(target_key)
    if cred and cred.get("name") == target_name:
        print(cred.get("id", ""))
        break
' 2>/dev/null || true
    )

    if [[ -n "$found_id" ]]; then
      echo "$found_id"
      return 0
    fi
  done
}

upsert_credential() {
  local current_id="$1" label="$2" payload="$3"
  local response new_id

  if [[ -n "$current_id" ]]; then
    echo "FOUND via workflow reference (ID: $current_id) — attempting update..." >&2
    if n8n_api PATCH "/credentials/$current_id" -d "$payload" > /dev/null 2>&1; then
      echo "OK — $label updated" >&2
      echo "$current_id"
      return 0
    fi
    echo "STALE or incompatible credential ID ($current_id) — creating a fresh $label credential..." >&2
  else
    echo "Creating..." >&2
  fi

  response=$(n8n_api POST "/credentials" -d "$payload")
  new_id=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  if [[ -z "$new_id" ]]; then
    echo "ERROR: Failed to create $label credential." >&2
    echo "Response: $response" >&2
    return 1
  fi

  echo "OK — $label credential created (ID: $new_id)" >&2
  echo "$new_id"
}

# ── Step 0: Test connectivity ───────────────────────────────────
echo "Connecting to n8n at $N8N_HOST..."
if ! n8n_api GET "/workflows" > /dev/null 2>&1; then
  echo "ERROR: Cannot reach n8n API. Check N8N_HOST and N8N_API_KEY."
  echo "  N8N_HOST=$N8N_HOST"
  exit 1
fi
echo "OK — n8n API connected"
echo ""

# ── Step 1: Create or find MinIO credential ─────────────────────
echo "--- MinIO S3 Credential ---"
MINIO_CRED_ID="${MINIO_CRED_ID:-$(find_cred_id_from_workflows "$MINIO_CRED_NAME" "s3" || true)}"
MINIO_CRED_PAYLOAD='{
  "name": "'"$MINIO_CRED_NAME"'",
  "type": "s3",
  "data": {
    "endpoint": "'"$MINIO_ENDPOINT"'",
    "region": "us-east-1",
    "accessKeyId": "'"$MINIO_ACCESS_KEY"'",
    "secretAccessKey": "'"$MINIO_SECRET_KEY"'",
    "forcePathStyle": true,
    "ignoreSSLIssues": false
  }
}'
MINIO_CRED_ID=$(upsert_credential "$MINIO_CRED_ID" "MinIO S3" "$MINIO_CRED_PAYLOAD")

# ── Step 2: Create or find SMTP credential ──────────────────────
echo ""
echo "--- Gmail SMTP Credential ---"
SMTP_CRED_ID="${SMTP_CRED_ID:-$(find_cred_id_from_workflows "$SMTP_CRED_NAME" "smtp" || true)}"
SMTP_CRED_PAYLOAD='{
  "name": "'"$SMTP_CRED_NAME"'",
  "type": "smtp",
  "data": {
    "host": "'"$SMTP_HOST"'",
    "port": '"$SMTP_PORT"',
    "secure": false,
    "disableStartTls": false,
    "user": "'"$SMTP_USER"'",
    "password": "'"$SMTP_PASS"'"
  }
}'
SMTP_CRED_ID=$(upsert_credential "$SMTP_CRED_ID" "SMTP" "$SMTP_CRED_PAYLOAD")

# ── Step 3: Create or find OpenRouter credential ────────────────
echo ""
echo "--- OpenRouter API Credential ---"
OPENROUTER_CRED_ID="${OPENROUTER_CRED_ID:-$(find_cred_id_from_workflows "$OPENROUTER_CRED_NAME" "httpHeaderAuth" || true)}"
OPENROUTER_CRED_PAYLOAD='{
  "name": "'"$OPENROUTER_CRED_NAME"'",
  "type": "httpHeaderAuth",
  "data": {
    "name": "Authorization",
    "value": "Bearer '"$OPENROUTER_API_KEY"'"
  }
}'
OPENROUTER_CRED_ID=$(upsert_credential "$OPENROUTER_CRED_ID" "OpenRouter API" "$OPENROUTER_CRED_PAYLOAD")

echo ""
echo "Credential IDs:"
echo "   MinIO:      $MINIO_CRED_ID"
echo "   SMTP:       $SMTP_CRED_ID"
echo "   OpenRouter: $OPENROUTER_CRED_ID"
echo "   Email:      $NOTIFICATION_EMAIL"

# ── Step 3: Hydrate workflow templates and import ────────────────
echo ""
echo "--- Importing Workflows ---"

# Create temp directory for hydrated copies (cleaned up on exit)
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Get existing workflows for update-vs-create check
EXISTING_WORKFLOWS=$(n8n_api GET "/workflows" 2>/dev/null || echo '{"data":[]}')

# ── v2 Workflows (import these — v1 kept for rollback) ──────────────────────
WORKFLOWS=(
  "error-handler.json"
  "ai-brain.json"
  "article-processor.json"
  "brain-dump-processor-v2.json"
  "daily-note-creator-v2.json"
  "overdue-task-alert-v2.json"
  "weekly-digest-v2.json"
  "morning-briefing.json"
  "telegram-capture.json"
  "live-dashboard-updater.json"
  "link-enricher.json"
  "vault-health-report.json"
  "system-health-monitor.json"
)
# V1 legacy (kept for rollback, do NOT activate alongside v2):
# "brain-dump-processor.json" "daily-note-creator.json"
# "overdue-task-alert.json"   "weekly-digest.json"

ERROR_WORKFLOW_ID=""

for wf_file in "${WORKFLOWS[@]}"; do
  wf_template="$WORKFLOW_DIR/$wf_file"
  if [[ ! -f "$wf_template" ]]; then
    echo "SKIP: $wf_file (file not found)"
    continue
  fi

  # Hydrate: replace all placeholders with real values
  wf_hydrated="$TMPDIR/$wf_file"
  ERROR_WORKFLOW_ID="$ERROR_WORKFLOW_ID" WF_FILE="$wf_file" python3 -c "
import json, os, sys
with open('$wf_template') as f:
    wf = json.load(f)
# Strip read-only and non-API fields
for field in ['tags', 'staticData', 'id', 'triggerCount', 'updatedAt', 'versionId', 'createdAt']:
    wf.pop(field, None)
if 'settings' in wf:
    allowed = {'executionOrder', 'saveManualExecutions', 'callerPolicy', 'errorWorkflow', 'timezone'}
    wf['settings'] = {k: v for k, v in wf['settings'].items() if k in allowed}
else:
    wf['settings'] = {}
# Standardize the global error handler on deploys after the handler itself exists
error_workflow_id = os.environ.get('ERROR_WORKFLOW_ID')
if error_workflow_id and os.environ.get('WF_FILE') != 'error-handler.json':
    wf.setdefault('settings', {})
    wf['settings']['errorWorkflow'] = error_workflow_id
raw = json.dumps(wf)
# Replace placeholders
raw = raw.replace('__MINIO_CRED_ID__', '$MINIO_CRED_ID')
raw = raw.replace('__SMTP_CRED_ID__', '$SMTP_CRED_ID')
raw = raw.replace('__OPENROUTER_CRED_ID__', '$OPENROUTER_CRED_ID')
raw = raw.replace('__NOTIFICATION_EMAIL__', '$NOTIFICATION_EMAIL')
with open('$wf_hydrated', 'w') as f:
    f.write(raw)
"

  # Validate JSON
  if ! python3 -c "import json; json.load(open('$wf_hydrated'))" 2>/dev/null; then
    echo "ERROR: $wf_file failed JSON validation after hydration"
    continue
  fi

  wf_json=$(cat "$wf_hydrated")
  wf_name=$(echo "$wf_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])" 2>/dev/null)

  # Check if workflow already exists by name
  existing_id=$(echo "$EXISTING_WORKFLOWS" | python3 -c "
import sys, json
data = json.load(sys.stdin).get('data', [])
for w in data:
    if w.get('name') == '''$wf_name''':
        print(w['id'])
        break
" 2>/dev/null || true)

  if [[ -n "$existing_id" ]]; then
    echo "  UPDATE: $wf_name (ID: $existing_id)"
    if ! n8n_api PUT "/workflows/$existing_id" -d "$wf_json" > /dev/null 2>&1; then
      echo "  ERROR: Failed to update $wf_name (ID: $existing_id)"
      exit 1
    fi
    if ! n8n_api POST "/workflows/$existing_id/activate" > /dev/null 2>&1; then
      echo "  ERROR: Failed to activate $wf_name (ID: $existing_id)"
      exit 1
    fi
    echo "  OK — updated and activated"
    if [[ "$wf_file" == "error-handler.json" ]]; then
      ERROR_WORKFLOW_ID="$existing_id"
    fi
  else
    echo "  IMPORT: $wf_name"
    if ! import_result=$(n8n_api POST "/workflows" -d "$wf_json" 2>/dev/null); then
      echo "  ERROR: Failed to import $wf_name"
      exit 1
    fi
    new_id=$(echo "$import_result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
    if [[ -z "$new_id" ]]; then
      echo "  ERROR: Import returned no workflow id. Response: $import_result"
      exit 1
    fi
    if ! n8n_api POST "/workflows/$new_id/activate" > /dev/null 2>&1; then
      echo "  ERROR: Failed to activate $wf_name (ID: $new_id)"
      exit 1
    fi
    echo "  OK — imported and activated (ID: $new_id)"
    if [[ "$wf_file" == "error-handler.json" ]]; then
      ERROR_WORKFLOW_ID="$new_id"
    fi
  fi
done

# ── Step 4: Verify ──────────────────────────────────────────────
echo ""
echo "--- Verification ---"
FINAL_WORKFLOWS=$(n8n_api GET "/workflows" 2>/dev/null || echo '{"data":[]}')
echo "$FINAL_WORKFLOWS" | python3 -c "
import sys, json
data = json.load(sys.stdin).get('data', [])
targets = ['Brain Dump', 'Daily Note', 'Overdue', 'Weekly', 'Morning', 'Telegram', 'Dashboard', 'Link', 'Health', 'Error']
found = 0
for w in data:
    name = w.get('name', '')
    if any(t in name for t in targets):
        status = 'ACTIVE' if w.get('active') else 'INACTIVE'
        print(f'   [{status}]  {name}')
        found += 1
if found == 0:
    print('   WARNING: No matching workflows found')
" 2>/dev/null

echo ""
echo "==================================================="
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Verify stack health: python3 scripts/health_check.py"
echo "  2. Run end-to-end validation: python3 scripts/e2e_test.py"
echo "  3. If Telegram capture is in use, set on n8n host:"
echo "     TELEGRAM_BOT_TOKEN and WEBHOOK_URL"
echo "     Then register: /webhook/telegram-capture"
echo "  4. Disable v1 workflows after confirming v2 works:"
echo "     brain-dump-processor, daily-note-creator, overdue-task-alert, weekly-digest"
echo "  5. Check recent executions in n8n for any residual credential drift"
echo "==================================================="

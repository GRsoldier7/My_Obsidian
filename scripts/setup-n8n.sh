#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# ObsidianHomeOrchestrator — n8n Setup Script
#
# Idempotent setup: creates credentials, hydrates workflow templates
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
#   source .env && bash scripts/setup-n8n.sh
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
  echo "  SMTP_USER         — Gmail address (e.g. aaron.deyoung@gmail.com)"
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

# ── Helper: find credential ID by exact name ────────────────────
find_cred_id() {
  local cred_name="$1"
  n8n_api GET "/credentials" 2>/dev/null | \
    python3 -c "
import sys, json
data = json.load(sys.stdin).get('data', [])
for c in data:
    if c.get('name') == '$cred_name':
        print(c['id'])
        break
" 2>/dev/null || true
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
MINIO_CRED_ID=$(find_cred_id "$MINIO_CRED_NAME")

if [[ -n "$MINIO_CRED_ID" ]]; then
  echo "EXISTS (ID: $MINIO_CRED_ID) — updating credentials..."
  n8n_api PATCH "/credentials/$MINIO_CRED_ID" -d '{
    "name": "'"$MINIO_CRED_NAME"'",
    "type": "aws",
    "data": {
      "region": "us-east-1",
      "accessKeyId": "'"$MINIO_ACCESS_KEY"'",
      "secretAccessKey": "'"$MINIO_SECRET_KEY"'",
      "customEndpoints": true,
      "s3Endpoint": "'"$MINIO_ENDPOINT"'",
      "sessionToken": "",
      "sesEndpoint": "",
      "sqsEndpoint": "",
      "ssmEndpoint": "",
      "snsEndpoint": "",
      "rekognitionEndpoint": "",
      "lambdaEndpoint": ""
    }
  }' > /dev/null 2>&1
  echo "OK — MinIO credential updated"
else
  echo "Creating..."
  MINIO_CRED_RESPONSE=$(n8n_api POST "/credentials" -d '{
    "name": "'"$MINIO_CRED_NAME"'",
    "type": "aws",
    "data": {
      "region": "us-east-1",
      "accessKeyId": "'"$MINIO_ACCESS_KEY"'",
      "secretAccessKey": "'"$MINIO_SECRET_KEY"'",
      "customEndpoints": true,
      "s3Endpoint": "'"$MINIO_ENDPOINT"'",
      "sessionToken": "",
      "sesEndpoint": "",
      "sqsEndpoint": "",
      "ssmEndpoint": "",
      "snsEndpoint": "",
      "rekognitionEndpoint": "",
      "lambdaEndpoint": ""
    }
  }')
  MINIO_CRED_ID=$(echo "$MINIO_CRED_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
  if [[ -z "$MINIO_CRED_ID" ]]; then
    echo "ERROR: Failed to create MinIO credential."
    echo "Response: $MINIO_CRED_RESPONSE"
    exit 1
  fi
  echo "OK — MinIO credential created (ID: $MINIO_CRED_ID)"
fi

# ── Step 2: Create or find SMTP credential ──────────────────────
echo ""
echo "--- Gmail SMTP Credential ---"
SMTP_CRED_ID=$(find_cred_id "$SMTP_CRED_NAME")

if [[ -n "$SMTP_CRED_ID" ]]; then
  echo "EXISTS (ID: $SMTP_CRED_ID) — updating credentials..."
  n8n_api PATCH "/credentials/$SMTP_CRED_ID" -d '{
    "name": "'"$SMTP_CRED_NAME"'",
    "type": "smtp",
    "data": {
      "host": "'"$SMTP_HOST"'",
      "port": '"$SMTP_PORT"',
      "secure": false,
      "user": "'"$SMTP_USER"'",
      "password": "'"$SMTP_PASS"'"
    }
  }' > /dev/null 2>&1
  echo "OK — SMTP credential updated"
else
  echo "Creating..."
  SMTP_CRED_RESPONSE=$(n8n_api POST "/credentials" -d '{
    "name": "'"$SMTP_CRED_NAME"'",
    "type": "smtp",
    "data": {
      "host": "'"$SMTP_HOST"'",
      "port": '"$SMTP_PORT"',
      "secure": false,
      "user": "'"$SMTP_USER"'",
      "password": "'"$SMTP_PASS"'"
    }
  }')
  SMTP_CRED_ID=$(echo "$SMTP_CRED_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
  if [[ -z "$SMTP_CRED_ID" ]]; then
    echo "ERROR: Failed to create SMTP credential."
    echo "Response: $SMTP_CRED_RESPONSE"
    exit 1
  fi
  echo "OK — SMTP credential created (ID: $SMTP_CRED_ID)"
fi

# ── Step 3: Create or find OpenRouter credential ────────────────
echo ""
echo "--- OpenRouter API Credential ---"
OPENROUTER_CRED_ID=$(find_cred_id "$OPENROUTER_CRED_NAME")

if [[ -n "$OPENROUTER_CRED_ID" ]]; then
  echo "EXISTS (ID: $OPENROUTER_CRED_ID) — updating..."
  n8n_api PATCH "/credentials/$OPENROUTER_CRED_ID" -d '{
    "name": "'"$OPENROUTER_CRED_NAME"'",
    "type": "httpHeaderAuth",
    "data": {
      "name": "Authorization",
      "value": "Bearer '"$OPENROUTER_API_KEY"'"
    }
  }' > /dev/null 2>&1
  echo "OK — OpenRouter credential updated"
else
  echo "Creating..."
  OPENROUTER_CRED_RESPONSE=$(n8n_api POST "/credentials" -d '{
    "name": "'"$OPENROUTER_CRED_NAME"'",
    "type": "httpHeaderAuth",
    "data": {
      "name": "Authorization",
      "value": "Bearer '"$OPENROUTER_API_KEY"'"
    }
  }')
  OPENROUTER_CRED_ID=$(echo "$OPENROUTER_CRED_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
  if [[ -z "$OPENROUTER_CRED_ID" ]]; then
    echo "ERROR: Failed to create OpenRouter credential."
    echo "Response: $OPENROUTER_CRED_RESPONSE"
    exit 1
  fi
  echo "OK — OpenRouter credential created (ID: $OPENROUTER_CRED_ID)"
fi

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

WORKFLOWS=(
  "brain-dump-processor.json"
  "daily-note-creator.json"
  "overdue-task-alert.json"
  "weekly-digest.json"
  "ai-brain.json"
  "article-processor.json"
)

for wf_file in "${WORKFLOWS[@]}"; do
  wf_template="$WORKFLOW_DIR/$wf_file"
  if [[ ! -f "$wf_template" ]]; then
    echo "SKIP: $wf_file (file not found)"
    continue
  fi

  # Hydrate: replace all placeholders with real values
  wf_hydrated="$TMPDIR/$wf_file"
  python3 -c "
import json, sys
with open('$wf_template') as f:
    wf = json.load(f)
# Strip read-only and non-API fields
for field in ['tags', 'staticData', 'id', 'triggerCount', 'updatedAt', 'versionId', 'createdAt']:
    wf.pop(field, None)
if 'settings' in wf:
    allowed = {'executionOrder', 'saveManualExecutions', 'callerPolicy', 'errorWorkflow', 'timezone'}
    wf['settings'] = {k: v for k, v in wf['settings'].items() if k in allowed}
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
    n8n_api PUT "/workflows/$existing_id" -d "$wf_json" > /dev/null 2>&1
    n8n_api POST "/workflows/$existing_id/activate" > /dev/null 2>&1
    echo "  OK — updated and activated"
  else
    echo "  IMPORT: $wf_name"
    import_result=$(n8n_api POST "/workflows" -d "$wf_json" 2>/dev/null || echo '{}')
    new_id=$(echo "$import_result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
    if [[ -n "$new_id" ]]; then
      n8n_api POST "/workflows/$new_id/activate" > /dev/null 2>&1
      echo "  OK — imported and activated (ID: $new_id)"
    else
      echo "  ERROR: Import failed. Response: $import_result"
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
targets = ['Brain Dump', 'Daily Note', 'Overdue Task', 'Weekly']
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
echo "  1. Verify Remotely Save in Obsidian is syncing to:"
echo "     Bucket: obsidian-vault | Prefix: Homelab/"
echo "  2. Ensure brain dump files exist in vault"
echo "  3. Test: Run 'Daily Note Creator' manually in n8n"
echo "==================================================="

#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# ObsidianHomeOrchestrator — n8n Setup Script
# Creates credentials, imports workflows, activates all 4 workflows
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

N8N_HOST="${N8N_HOST:-http://192.168.1.121:5678}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKFLOW_DIR="$SCRIPT_DIR/../workflows/n8n"

# ── Validate required env vars ──────────────────────────────────
required_vars=(N8N_API_KEY MINIO_ACCESS_KEY MINIO_SECRET_KEY SMTP_USER SMTP_PASS)
missing=()
for var in "${required_vars[@]}"; do
  [[ -z "${!var:-}" ]] && missing+=("$var")
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "❌ Missing required environment variables:"
  for v in "${missing[@]}"; do echo "   - $v"; done
  echo ""
  echo "Set them in .env and run:  source .env && bash $0"
  echo ""
  echo "Required:"
  echo "  N8N_API_KEY       — Generate at n8n → Settings → API → Create API Key"
  echo "  MINIO_ACCESS_KEY  — MinIO Claude_Cowork service account access key"
  echo "  MINIO_SECRET_KEY  — MinIO Claude_Cowork service account secret key"
  echo "  SMTP_USER         — Gmail address (aaron.deyoung@gmail.com)"
  echo "  SMTP_PASS         — Gmail App Password (Google Account → Security → 2FA → App Passwords)"
  exit 1
fi

API="$N8N_HOST/api/v1"
AUTH="-H X-N8N-API-KEY:$N8N_API_KEY"

echo "🔗 Connecting to n8n at $N8N_HOST..."
status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 $AUTH "$API/workflows" 2>/dev/null)
if [[ "$status" != "200" ]]; then
  echo "❌ Cannot reach n8n API (HTTP $status). Check N8N_HOST and N8N_API_KEY."
  exit 1
fi
echo "✅ n8n API connected"

# ── Step 1: Create MinIO credential ─────────────────────────────
echo ""
echo "📦 Creating MinIO credential..."
MINIO_CRED_RESPONSE=$(curl -s -X POST "$API/credentials" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MinIO — obsidian-vault",
    "type": "aws",
    "data": {
      "region": "us-east-1",
      "accessKeyId": "'"$MINIO_ACCESS_KEY"'",
      "secretAccessKey": "'"$MINIO_SECRET_KEY"'",
      "customEndpoints": true,
      "s3Endpoint": "http://192.168.1.240:9000",
      "s3ForcePathStyle": true
    }
  }')

MINIO_CRED_ID=$(echo "$MINIO_CRED_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
if [[ -z "$MINIO_CRED_ID" ]]; then
  echo "⚠️  MinIO credential may already exist. Checking..."
  MINIO_CRED_ID=$(curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" "$API/credentials" | \
    python3 -c "import sys,json; creds=json.load(sys.stdin).get('data',[]); print(next((c['id'] for c in creds if 'MinIO' in c.get('name','')), ''))" 2>/dev/null)
  if [[ -n "$MINIO_CRED_ID" ]]; then
    echo "✅ MinIO credential exists (ID: $MINIO_CRED_ID)"
  else
    echo "❌ Failed to create MinIO credential. Response: $MINIO_CRED_RESPONSE"
    exit 1
  fi
else
  echo "✅ MinIO credential created (ID: $MINIO_CRED_ID)"
fi

# ── Step 2: Create Gmail SMTP credential ────────────────────────
echo ""
echo "📧 Creating Gmail SMTP credential..."
SMTP_CRED_RESPONSE=$(curl -s -X POST "$API/credentials" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Gmail SMTP",
    "type": "smtp",
    "data": {
      "host": "smtp.gmail.com",
      "port": 587,
      "secure": false,
      "user": "'"$SMTP_USER"'",
      "password": "'"$SMTP_PASS"'"
    }
  }')

SMTP_CRED_ID=$(echo "$SMTP_CRED_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
if [[ -z "$SMTP_CRED_ID" ]]; then
  echo "⚠️  SMTP credential may already exist. Checking..."
  SMTP_CRED_ID=$(curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" "$API/credentials" | \
    python3 -c "import sys,json; creds=json.load(sys.stdin).get('data',[]); print(next((c['id'] for c in creds if 'Gmail' in c.get('name','') or 'SMTP' in c.get('name','')), ''))" 2>/dev/null)
  if [[ -n "$SMTP_CRED_ID" ]]; then
    echo "✅ SMTP credential exists (ID: $SMTP_CRED_ID)"
  else
    echo "❌ Failed to create SMTP credential. Response: $SMTP_CRED_RESPONSE"
    exit 1
  fi
else
  echo "✅ Gmail SMTP credential created (ID: $SMTP_CRED_ID)"
fi

echo ""
echo "🔑 Credential IDs:"
echo "   MinIO: $MINIO_CRED_ID"
echo "   SMTP:  $SMTP_CRED_ID"

# ── Step 3: Get existing workflows ──────────────────────────────
echo ""
echo "📋 Checking existing workflows..."
EXISTING_WORKFLOWS=$(curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" "$API/workflows")

# ── Step 4: Update credential IDs in workflows and import/update ─
echo ""
echo "📥 Updating workflows with real credential IDs..."

WORKFLOWS=(
  "brain-dump-processor.json"
  "daily-note-creator.json"
  "overdue-task-alert.json"
  "weekly-digest.json"
)

for wf_file in "${WORKFLOWS[@]}"; do
  wf_path="$WORKFLOW_DIR/$wf_file"
  if [[ ! -f "$wf_path" ]]; then
    echo "❌ Workflow file not found: $wf_path"
    continue
  fi

  # Replace placeholder credential IDs with real ones
  wf_json=$(cat "$wf_path" | \
    sed "s/\"id\": \"MINIO_CRED_ID\"/\"id\": \"$MINIO_CRED_ID\"/g" | \
    sed "s/\"id\": \"SMTP_CRED_ID\"/\"id\": \"$SMTP_CRED_ID\"/g")

  wf_name=$(echo "$wf_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])" 2>/dev/null)

  # Check if workflow already exists by name
  existing_id=$(echo "$EXISTING_WORKFLOWS" | python3 -c "
import sys,json
data = json.load(sys.stdin).get('data', [])
name = '$wf_name'
for w in data:
    if w.get('name') == name:
        print(w['id'])
        break
" 2>/dev/null)

  if [[ -n "$existing_id" ]]; then
    # Update existing workflow
    echo "   🔄 Updating: $wf_name (ID: $existing_id)"
    update_result=$(curl -s -X PUT "$API/workflows/$existing_id" \
      -H "X-N8N-API-KEY: $N8N_API_KEY" \
      -H "Content-Type: application/json" \
      -d "$wf_json")

    # Activate
    curl -s -X PATCH "$API/workflows/$existing_id" \
      -H "X-N8N-API-KEY: $N8N_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"active": true}' > /dev/null 2>&1
    echo "   ✅ Updated and activated"
  else
    # Import new workflow
    echo "   📥 Importing: $wf_name"
    import_result=$(curl -s -X POST "$API/workflows" \
      -H "X-N8N-API-KEY: $N8N_API_KEY" \
      -H "Content-Type: application/json" \
      -d "$wf_json")

    new_id=$(echo "$import_result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
    if [[ -n "$new_id" ]]; then
      # Activate
      curl -s -X PATCH "$API/workflows/$new_id" \
        -H "X-N8N-API-KEY: $N8N_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"active": true}' > /dev/null 2>&1
      echo "   ✅ Imported and activated (ID: $new_id)"
    else
      echo "   ❌ Import failed: $import_result"
    fi
  fi
done

# ── Step 5: Verify all workflows are active ─────────────────────
echo ""
echo "🔍 Verifying workflow status..."
FINAL_WORKFLOWS=$(curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" "$API/workflows")
echo "$FINAL_WORKFLOWS" | python3 -c "
import sys, json
data = json.load(sys.stdin).get('data', [])
targets = ['Brain Dump', 'Daily Note', 'Overdue Task', 'Weekly']
for w in data:
    name = w.get('name', '')
    if any(t in name for t in targets):
        status = '✅ ACTIVE' if w.get('active') else '❌ INACTIVE'
        print(f'   {status}  {name}')
" 2>/dev/null

echo ""
echo "═══════════════════════════════════════════════════"
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Verify Remotely Save in Obsidian is syncing to:"
echo "     Bucket: obsidian-vault | Prefix: Homelab/"
echo "  2. Ensure 8 brain dump files exist in vault"
echo "  3. Test: Run 'Daily Note Creator' manually in n8n"
echo "═══════════════════════════════════════════════════"

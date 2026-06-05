# Google Calendar OAuth2 Setup for Weekend Planner

This guide walks through connecting Google Calendar to n8n so the Weekend Planner workflow can read your Saturday and Sunday events.

---

## 1. Create the Credential in n8n

1. Open n8n at `http://192.168.1.121:5678`
2. Go to **Settings → Credentials → Add Credential**
3. Search for and select **Google Calendar OAuth2 API**
4. Set the **OAuth Scope** to:
   ```
   https://www.googleapis.com/auth/calendar.readonly
   ```
5. Follow the OAuth consent flow to connect your Google account
6. Name the credential exactly: **Google Calendar**
7. Click **Save**

---

## 2. Get the Credential ID

After saving, look at the URL in your browser. It will look like:

```
http://192.168.1.121:5678/credentials/abc123xyz/edit
```

The segment between `/credentials/` and `/edit` is the credential ID (e.g., `abc123xyz`). Copy it.

---

## 3. Add to `.env`

Open `/Volumes/home/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator/.env` and add:

```bash
GCAL_CRED_ID=abc123xyz
```

Replace `abc123xyz` with your actual credential ID.

---

## 4. How `__GCAL_CRED_ID__` Gets Replaced

The workflow JSON (`workflows/n8n/weekend-planner.json`) stores the placeholder `__GCAL_CRED_ID__` in GCal node credentials. The deploy script (`deploy_workflows.py`) substitutes all `__PLACEHOLDER__` tokens with values from `.env` at deploy time — the same pattern used for `__MINIO_CRED_ID__`, `__SMTP_CRED_ID__`, etc.

If you are editing `.env` and `setup-n8n.sh` directly, ensure it contains:

```bash
sed -i "s/__GCAL_CRED_ID__/${GCAL_CRED_ID}/g" /tmp/weekend-planner.json
```

---

## 5. Deploy the Workflow

Run the deploy script targeting only the Weekend Planner:

```bash
set -a && source .env && set +a
python3 /tmp/deploy_workflows.py weekend-planner
```

Or to deploy all workflows:

```bash
set -a && source .env && set +a
bash scripts/setup-n8n.sh
```

---

## 6. Verify in n8n

1. Go to **Workflows** in n8n
2. Open **Weekend Planner — Friday 5PM**
3. Click **GCal: Saturday Events** → check that the credential shows **Google Calendar** (not `__GCAL_CRED_ID__`)
4. Use **Test Workflow** (or manually trigger) to confirm events are returned

---

## Notes

- The GCal nodes use `continueOnFail: true`, so the workflow will run and generate the vault note and email even without GCal connected — the event sections will simply show "No events scheduled."
- Only `calendar.readonly` scope is requested. The workflow never creates or modifies calendar events.
- If you have multiple Google accounts, ensure you authorize the correct one during the OAuth flow.
- The `primary` calendar ID is used by default. To use a different calendar, edit the `calendar.id` field in the workflow JSON before deploying.

# Runbook — Deploy the brain-dump processor runner to n8n LXC

**Target:** Proxmox LXC CT-202 at `192.168.1.121`
**Runtime shape:** n8n runs in Docker; n8n calls a dedicated `oho-runner`
HTTP sidecar; the sidecar runs `/opt/oho/tools/process_brain_dump.py`.

---

## TL;DR

Do **not** use n8n `executeCommand` for the P1 brain-dump processor.

The live n8n host is on n8n 2.x inside Docker. In that environment:

- `n8n-nodes-base.executeCommand` is not available to active-workflow
  registration.
- `/opt/oho` on the LXC host is not visible inside the n8n container unless
  explicitly mounted.

The supported P1 architecture is:

```text
n8n workflow
  -> HTTP Request node
  -> http://oho-runner:8080/process-brain-dump
  -> FastAPI runner sidecar
  -> python3 -u /opt/oho/tools/process_brain_dump.py
  -> MinIO verified writes + receipts + archives
```

---

## What CT-202 needs

### 1. Repo at `/opt/oho`

Verify:

```bash
ls -la /opt/oho/tools/process_brain_dump.py
ls -la /opt/oho/tools/bd_integrity.py
ls -la /opt/oho/services/oho_runner/app.py
```

If the repo is not there, copy the canonical repo to `/opt/oho`. Include the
repo `.env` on the LXC host, but never commit it.

### 2. Runner `.env`

Create `/opt/oho/services/oho_runner/.env` from the example:

```bash
cd /opt/oho/services/oho_runner
cp .env.example .env
```

Set at least:

```text
OHO_RUNNER_TOKEN=<long random bearer token>
OHO_RUNNER_WORKDIR=/opt/oho
OHO_RUNNER_TIMEOUT=180
```

Generate the token on the LXC:

```bash
openssl rand -hex 32
```

Create an n8n `httpHeaderAuth` credential named exactly:

```text
OHO Runner Auth
```

Header name:

```text
Authorization
```

Header value:

```text
Bearer <same OHO_RUNNER_TOKEN>
```

### 3. Runner sidecar

Build and start the sidecar:

```bash
cd /opt/oho/services/oho_runner
docker compose up -d --build
```

Verify from the LXC host:

```bash
docker compose ps
curl -sS http://localhost:8080/health
```

Verify from inside the n8n container. The URL must use Docker DNS, not
`127.0.0.1`:

```bash
docker exec -it n8n-n8n-1 sh -lc 'curl -sS http://oho-runner:8080/health'
```

Expected health fields:

```json
{
  "status": "ok",
  "script_present": true,
  "env_present": true,
  "token_configured": true
}
```

### 4. Optional host-side Python smoke test

The runner container is self-contained. Host-side Python is useful for manual
debugging only.

On Debian 13, prefer apt packages over `pip --user`:

```bash
apt update
apt install -y python3-boto3 python3-openai python3-dotenv python3-pytest python3-moto
```

Then:

```bash
cd /opt/oho
set -a && source .env && set +a
python3 -u tools/process_brain_dump.py --dry-run
```

Expected: valid JSON with `"status": "success"`.

---

## Deploy only the brain-dump workflow

Do **not** run `scripts/setup-n8n.sh` for this cutover unless you intentionally
want to reconcile all workflow templates.

Use the surgical deploy tool:

```bash
cd /opt/oho
set -a && source .env && set +a

python3 scripts/deploy_n8n_workflow.py \
  workflows/n8n/brain-dump-processor-v2.json \
  --workflow-id 1SiacuC68kFgYayV \
  --assert-nodes 7 \
  --assert-no-execute-command \
  --assert-http-url-contains oho-runner \
  --assert-http-url-contains /process-brain-dump
```

The script performs:

1. Backup of the live workflow JSON to `/opt/oho/backups/n8n/`.
2. Placeholder hydration, including `__OHO_RUNNER_CRED_ID__`.
3. `PUT /api/v1/workflows/<id>` for this workflow only.
4. Re-fetch assertions before activation.

Activate only after assertions pass:

```bash
python3 scripts/deploy_n8n_workflow.py \
  workflows/n8n/brain-dump-processor-v2.json \
  --workflow-id 1SiacuC68kFgYayV \
  --assert-nodes 7 \
  --assert-no-execute-command \
  --assert-http-url-contains oho-runner \
  --assert-http-url-contains /process-brain-dump \
  --activate
```

---

## Manual runner test

From inside the n8n container:

```bash
docker exec -it n8n-n8n-1 sh -lc '
  curl -sS -X POST http://oho-runner:8080/process-brain-dump \
    -H "Authorization: Bearer <OHO_RUNNER_TOKEN>"
'
```

Expected response:

```json
{
  "exit_code": 0,
  "stdout_json": {
    "status": "success"
  },
  "timed_out": false
}
```

If the brain dumps were already drained, `stdout_json.files_with_content` may be
`0`; that is a valid no-work run.

---

## Post-deploy verification

Run:

```bash
cd /opt/oho
set -a && source .env && set +a

python3 scripts/health_check.py
python3 scripts/audit_extraction_receipts.py
```

Then manually click **Execute Workflow** in n8n for:

```text
🧠 Brain Dump Processor v2 — Daily 7AM
```

For a same-day second run, expected behavior is:

- Runner returns `files_with_content: 0`.
- n8n parse node sets `top_status: "no_work"`.
- `Has Work?` false branch flows through `Is Error?`.
- `Is Error?` false branch is intentionally unwired, so no email sends.
- No new task data is written.

Inspect MinIO after a real content run:

```text
99_System/extraction-receipts/
99_System/archive/brain-dumps/<YYYY-MM-DD>/
99_System/logs/brain-dump-processor-<YYYY-MM-DD>.json
00_Inbox/processed/
```

---

## Failure modes + recovery

| Symptom | Likely cause | Fix |
|---|---|---|
| n8n cannot reach `http://oho-runner:8080/health` | Runner is not on `n8n_default`, or wrong container name/network | `cd services/oho_runner && docker compose ps`; confirm compose network is `n8n_default` |
| HTTP 401 from `/process-brain-dump` | Token mismatch between runner `.env` and n8n credential | Update `OHO Runner Auth` credential or runner `.env`; restart runner |
| HTTP 409 from `/process-brain-dump` | Another processor run is active | Wait for current run; inspect runner logs |
| `stdout_json` is null | Python emitted non-JSON or exited before summary | Inspect `stderr_tail` and `stdout_raw` in the n8n execution |
| Runner health says `script_present: false` | `/opt/oho` bind mount missing/wrong | Fix `services/oho_runner/docker-compose.yml` volume and restart |
| Audit R1 reports receipt missing | Receipt stem normalization drift | Use `tools.bd_integrity.slug_for_filename`; run `tests/test_audit_extraction_receipts.py` |

Runner logs:

```bash
cd /opt/oho/services/oho_runner
docker compose logs --tail=100 oho-runner
```

Rollback to the previous live workflow body:

```bash
cd /opt/oho
set -a && source .env && set +a

# Pick a backup from /opt/oho/backups/n8n, then PUT it back manually or with
# the n8n UI. Do not run setup-n8n.sh unless you intend to reconcile all workflows.
ls -lah /opt/oho/backups/n8n/
```

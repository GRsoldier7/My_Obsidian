# Runbook — Deploy Python brain-dump processor to n8n LXC

**Target:** Proxmox LXC CT-202 at `192.168.1.121` (the n8n host)
**Reason:** Per ADR-0005 § 9, the brain-dump-processor-v2 workflow shells out to
`python3 tools/process_brain_dump.py` instead of re-implementing the integrity
layer in JavaScript. The n8n process needs Python + the repo + `.env`.

---

## TL;DR — Do I need a new LXC?

**No.** Reuse the existing n8n LXC (CT-202). Justification:

| Resource | brain-dump-processor.py needs | CT-202 has |
|---|---|---|
| Python 3.12+ | yes (verify once) | almost certainly yes |
| pip packages | `boto3`, `openai`, `python-dotenv` (~80MB) | install via `pip3 install --user` |
| RAM (peak) | ~50–80MB during a run | n8n already uses ≥150MB; LXC presumably has ≥512MB |
| CPU | 5–10s once per day at 7AM CDT | trivially available |
| Disk | ~150MB total (Python deps + repo) | trivially available |
| Network | MinIO (192.168.1.240) + OpenRouter HTTPS | already reachable from CT-202 (n8n hits both) |
| Isolation concern | none — runs the same kind of code n8n itself runs | n/a |

A dedicated LXC would be over-engineering for a once-daily, 10-second
job. If you ever scale the Python workload (e.g. real-time webhook
ingestion) we revisit.

---

## Inspection — run this first on CT-202

SSH to the LXC and run the block below. It's read-only (no changes)
and tells you exactly what's missing.

```bash
echo "=== OS ===" && uname -a
echo "=== Python ===" && python3 --version 2>&1
echo "=== pip3 ===" && pip3 --version 2>&1 || echo "pip3 missing"
echo "=== Required packages ===" && python3 -c "import boto3,openai,dotenv; print('boto3',boto3.__version__,'openai',openai.__version__,'dotenv ok')" 2>&1 || echo "missing one of: boto3 / openai / python-dotenv"
echo "=== Repo location candidates ===" && for p in /opt/oho /mnt/home/!!\ AI_Scripts_Automations_Projects/Projects_Repos/ObsidianHomeOrchestrator /home/oho/repo; do [ -d "$p" ] && echo "FOUND $p" || echo "absent $p"; done
echo "=== MinIO reachable? ===" && curl -sS -m 3 -o /dev/null -w "minio: HTTP %{http_code}\n" http://192.168.1.240:9000/minio/health/live
echo "=== OpenRouter reachable? ===" && curl -sS -m 3 -o /dev/null -w "openrouter: HTTP %{http_code}\n" https://openrouter.ai/
echo "=== n8n process ===" && pgrep -af n8n | head -3
```

Expected GOOD output:
- Python 3.12 or higher
- boto3 / openai / dotenv all import successfully (or "missing one of …" if not yet installed)
- One of the repo paths is `FOUND`
- MinIO returns HTTP 200, OpenRouter returns HTTP 2xx or 3xx
- n8n is running

Anything else → see the relevant section below.

---

## What the LXC needs

### 1. Python 3.12+

Verify:
```bash
python3 --version   # ≥ 3.12
```

If not present: `apt install python3 python3-pip python3-venv` (or whatever
the LXC's distro uses).

### 2. Python packages

Install at the system or n8n-user level:
```bash
pip3 install --user --upgrade boto3 openai python-dotenv
```

`python-dotenv` is optional (the workflow sources `.env` via shell), but
install it anyway — `tools/process_brain_dump.py` falls back to it if the
shell didn't source `.env`.

The processor imports only stdlib (`re`, `json`, `hashlib`, `unicodedata`,
`datetime`, `dataclasses`, `pathlib`, `argparse`, `logging`) plus the three
above. No other deps.

### 3. Repo at `${OHO_REPO_PATH}` (default `/opt/oho`)

Two options. Pick one:

**Option A — NAS mount (preferred if the LXC already mounts `/Volumes/home/`):**
```bash
# As root:
ln -s "/mnt/home/!! AI_Scripts_Automations_Projects/Projects_Repos/ObsidianHomeOrchestrator" /opt/oho
```
The repo stays a single source of truth — `git pull` on the Mac, the LXC
sees the new code immediately. No sync needed.

**Option B — rsync on a cron (if the NAS isn't mounted on the LXC):**
```bash
# From the Mac (or wherever the canonical repo lives), every 5 min:
rsync -avz --delete --exclude='.git' --exclude='__pycache__' --exclude='.pytest_cache' \
  "/Volumes/home/.../ObsidianHomeOrchestrator/" \
  root@192.168.1.121:/opt/oho/
```

Verify:
```bash
ls -la /opt/oho/tools/process_brain_dump.py    # must exist
ls -la /opt/oho/tools/bd_integrity.py          # must exist
```

### 4. `.env` at `${OHO_REPO_PATH}/.env`

Required variables (see `.env.example`):
```
MINIO_ENDPOINT=http://192.168.1.240:9000
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_BUCKET=obsidian-vault
OPENROUTER_API_KEY=...
```

If using NAS mount (Option A), the `.env` is already there. If using rsync,
include `.env` explicitly (it's normally gitignored).

### 5. Optional environment override

If the repo lives somewhere other than `/opt/oho`, set in the n8n LXC's
shell environment (e.g. `/etc/environment` or systemd service unit):
```
OHO_REPO_PATH=/your/custom/path
```

---

## Smoke test — does the LXC run the processor?

SSH to the LXC, then:
```bash
cd ${OHO_REPO_PATH:-/opt/oho}
set -a && source .env && set +a
python3 -u tools/process_brain_dump.py --dry-run 2>&1 | tail -20
```

Expected output: a JSON summary on stdout, INFO log lines on stderr.
Stdout's last block should be valid JSON like:

```json
{
  "status": "success",
  "files_discovered": 11,
  "files_with_content": 2,
  ...
}
```

If stdout isn't valid JSON, the workflow's "Parse Python Output" node will
fall to the no-work email branch with `top_status: 'parse_error'`.

---

## Re-enable the n8n workflow

Once the smoke test passes:

```bash
curl -X POST -H "X-N8N-API-KEY: $N8N_API_KEY" \
  http://192.168.1.121:5678/api/v1/workflows/1SiacuC68kFgYayV/activate
```

Then trigger a manual run from the n8n UI to confirm the gated path runs
end-to-end. Inspect:
- the digest email (or no-work email)
- `99_System/extraction-receipts/` (one new receipt per file with content)
- `99_System/archive/brain-dumps/<YYYY-MM-DD>/` (raw archives)
- `99_System/logs/brain-dump-processor-<YYYY-MM-DD>.json` (run log)
- `00_Inbox/brain-dumps/*.md` frontmatter — `status` should be `extracted`
  for files that processed cleanly, `partial` if some downstream write failed.

---

## Failure modes + recovery

| Symptom | Likely cause | Fix |
|---|---|---|
| Workflow execution fails with non-zero exit | Python script itself errored at env-gate (MinIO unreachable, creds missing) | Inspect stderr in the n8n execution log; fix env / creds; re-run |
| `top_status: parse_error` in the no-work email | Python emitted non-JSON to stdout (e.g. an unhandled exception printed traceback) | Inspect `parse_error` and `raw_stderr_tail` fields in the email; fix the script issue |
| Audit `audit_extraction_receipts.py` reports R5 findings | `status: extracted` files still have content sections | Likely a logic bug in `bd_integrity.apply_reset` — re-read the code, write a test, fix |
| Audit reports R4 findings | A file has been `partial` for >7 days | Investigate the failed-section reason in the file's retention block; fix the underlying transient (MinIO write, etc.); re-run the workflow |
| Files repeatedly land in `partial` after retries | Persistent downstream failure | Check the retention block's stated reason; the ARTICLES_FILE or MTL is unreachable / locked; investigate that target |

---

## Rollback

If step 6's thin-scheduler workflow misbehaves, revert to the prior version:

```bash
cd ${OHO_REPO_PATH:-/opt/oho}
git checkout 2024dba -- workflows/n8n/brain-dump-processor-v2.json
bash scripts/setup-n8n.sh   # re-imports the older workflow
```

The Python integrity layer (commits `641011d`, `cd66a20`, `2024dba`,
`c8e7013`) stays in place — only the n8n workflow JSON reverts. Manual
`python3 tools/process_brain_dump.py` invocations continue to work with
full P1 gates.

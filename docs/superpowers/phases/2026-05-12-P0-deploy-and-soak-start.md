# P0 — Deploy P1 + P1.5 + ADR-0006 to CT-202 and Start the ≥7-Day Soak

**Date:** 2026-05-12
**Owner:** Aaron DeYoung (operator). Claude assists; Aaron pulls the trigger.
**Target:** Proxmox LXC CT-202 (`192.168.1.121`), Docker network `n8n_default`.
**Branch:** `polish/prod-ready` (46 commits ahead of `master`).
**Status when this opens:** code complete (commit `a1bd438`), 311/312 tests pass,
all 5 audits green, **nothing is running in prod yet**.

---

## 1. Goal

Get the P1 integrity layer (ADR-0005), the P1.5 HTTP-runner sidecar, and the
ADR-0006 daily command center deployed to CT-202 cleanly, then **observe for
≥7 consecutive days with zero unattended failures** so the soak gate opens and
P2 (threaded tasks) becomes eligible.

### Why this is the blocking gate

Per CLAUDE.md (`docs/adr/0005-…`) and saved memory `feedback_p1_integrity_first.md`:

> P1 is non-negotiable, boring, hard to break. While P1 is open: no new capture
> surfaces, no insights/coach scripts, no domain UX scope.

P1+P1.5 must run clean in prod for **≥7 days** before P2 starts. While that
gate is open, every other roadmap item (P2 task IDs, P3 capture-from-anywhere,
P4–P7) is frozen. This phase is the only domino that matters. If it falls
over, the entire v1.0 plan slips. If it lands clean and stays clean, the rest
of the roadmap unlocks in dependency order.

---

## 2. Pre-flight checklist

**Everything in this list MUST be true before running `make deploy-runner-dry`.
Do not skip a line. If a line fails, fix it before continuing — do not work
around it.**

### 2.1 Local repo state

- [ ] Current branch is `polish/prod-ready`.
  ```bash
  git rev-parse --abbrev-ref HEAD          # → polish/prod-ready
  git status --porcelain                   # → empty (clean tree)
  ```
- [ ] `git log -1 --oneline` shows `a1bd438` (or newer with all 3 milestones) at HEAD.
- [ ] Local test suite green:
  ```bash
  make test          # 311 pass, 1 skip
  make audit-workflows
  make audit-ai-tooling
  set -a && source .env && set +a && python3 scripts/audit_extraction_receipts.py
  ```
  If any audit fails, **stop**. Fix it locally and re-commit before deploying.

### 2.2 Secrets and env

- [ ] `.env` exists at repo root and is **not** committed:
  ```bash
  git check-ignore .env                    # → .env
  ```
- [ ] Required env vars present (verified by the orchestrator's preflight step
  but check locally first to avoid wasted SSH round-trips):
  - `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
  - `OPENROUTER_API_KEY`
  - `N8N_HOST` (e.g. `http://192.168.1.121:5678`), `N8N_API_KEY`
  - `OHO_RUNNER_TOKEN` — **generate fresh** if missing:
    ```bash
    echo "OHO_RUNNER_TOKEN=$(openssl rand -hex 32)" >> .env
    ```
    Token must be 64 hex chars (`openssl rand -hex 32` output).
  - `LXC_SSH_HOST` (default `root@192.168.1.121` — verify Aaron's SSH key is
    in `root@pve`'s `authorized_keys`, or override to whatever path actually
    works).

### 2.3 n8n credentials (live)

- [ ] `MinIO S3` (`type: s3`, NOT `aws`) exists. Look up by ID, not name —
  live workflows have emoji-prefixed names that diverge from repo templates.
  ```bash
  curl -fsS -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_HOST/api/v1/credentials" \
    | jq '.data[] | select(.type=="s3") | {id, name, type}'
  ```
- [ ] `Gmail SMTP` (`type: smtp`) exists. Same lookup pattern.
- [ ] `OpenRouter API` (`type: httpHeaderAuth`) exists.
- [ ] `OHO Runner Auth` (`type: httpHeaderAuth`) **may or may not exist**. If
  it doesn't, the orchestrator's `n8n-cred` step will create it. If it does,
  confirm its `value` matches the current `OHO_RUNNER_TOKEN` in `.env` — a
  drift here causes silent 401s for the runner endpoints.

### 2.4 MinIO health

- [ ] Bucket reachable:
  ```bash
  set -a && source .env && set +a
  python3 scripts/health_check.py
  # expect: [PASS] minio: Bucket 'obsidian-vault' accessible
  ```
- [ ] Bucket versioning is **ON** (rollback path for receipts/state files):
  ```bash
  python3 -c "
  import boto3, os
  from botocore.client import Config
  s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'],
      aws_access_key_id=os.environ['MINIO_ACCESS_KEY'],
      aws_secret_access_key=os.environ['MINIO_SECRET_KEY'],
      config=Config(signature_version='s3v4'), region_name='us-east-1')
  print(s3.get_bucket_versioning(Bucket=os.environ['MINIO_BUCKET']))
  "
  # expect: {'Status': 'Enabled', ...}
  ```
- [ ] The 11 brain-dump files in `00_Inbox/brain-dumps/` have the canonical
  ADR-0005 frontmatter. If not, run `scripts/migrate_brain_dump_frontmatter.py --dry-run`
  first, then with `--apply` outside the 7AM CDT window. (Per ADR-0005 the
  migration was already supposed to land; verify before deploying.)

### 2.5 LXC reachability

Two paths must both work — pick whichever is wired in the operator's environment:

- **Preferred (Aaron's pattern):** `pct exec` from the Proxmox host `pve`.
  ```bash
  ssh pve 'pct status 202'                 # → status: running
  ssh pve 'pct exec 202 -- docker ps --format "{{.Names}}"' | grep -E 'n8n|oho'
  ```
- **What `deploy_oho_runner.py` uses today:** direct SSH to the LXC. Confirm
  it works before relying on it:
  ```bash
  ssh -o ConnectTimeout=5 root@192.168.1.121 'echo ok && hostname'
  ```
  If direct SSH to the LXC isn't set up, either:
  - Forward through pve: add to `~/.ssh/config`:
    ```
    Host ct-202
      HostName 192.168.1.121
      ProxyJump pve
      User root
    ```
    then `LXC_SSH_HOST=ct-202 make deploy-runner-dry`.
  - Or run the orchestrator from pve itself and override
    `LXC_SSH_HOST=root@localhost`.

### 2.6 LXC disk + runtime

- [ ] Free disk ≥ 1 GB on `/`:
  ```bash
  ssh pve 'pct exec 202 -- df -h /'        # Use% < 90%
  ```
- [ ] Docker daemon healthy:
  ```bash
  ssh pve 'pct exec 202 -- docker info --format "{{.ServerVersion}} {{.OperatingSystem}}"'
  ```
- [ ] `n8n_default` external network exists (the runner compose file expects it):
  ```bash
  ssh pve 'pct exec 202 -- docker network ls | grep n8n_default'
  ```
- [ ] `/opt/oho` exists OR the operator is comfortable with `rsync` creating it.

### 2.7 No live brain-dump run is mid-flight

The 7AM CDT cron must **not** be firing while we deploy. Deploy outside the
window `06:50 → 07:20 CDT`. If the operator must deploy during the window:

- [ ] Temporarily deactivate `brain-dump-processor-v2` in n8n UI.
- [ ] Re-activate after `make deploy-runner` completes (or let `step_activate`
  do it).

### 2.8 Rollback readiness

- [ ] The current live workflow JSONs are backed up. `deploy_n8n_workflow.py`
  writes its own backups to `/opt/oho/backups/n8n/` on each run; before the
  first deploy of P1.5 we should also pull a snapshot to the dev box:
  ```bash
  set -a && source .env && set +a
  for name in brain-dump-processor-v2 live-dashboard-updater; do
    wf_id=$(curl -fsS -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_HOST/api/v1/workflows" \
      | jq -r --arg n "$name" '.data[] | select(.name|contains($n)) | .id' | head -1)
    curl -fsS -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_HOST/api/v1/workflows/$wf_id" \
      > "backups/local/pre-p15-${name}-$(date -u +%Y%m%dT%H%M%SZ).json"
  done
  ```

---

## 3. The 10-step deploy

The orchestrator is [scripts/deploy_oho_runner.py](../../../scripts/deploy_oho_runner.py).
Every step is idempotent. Default mode is **dry-run** — must pass `--apply`
(or `make deploy-runner`) to make changes.

**Execute the dry-run first. Read the printed plan. Only then apply.**

```bash
set -a && source .env && set +a
make deploy-runner-dry           # read-only, ~10s. PREVIEW.
# Review the per-step plan, the rsync --dry-run diff, the n8n cred payload.
make deploy-runner               # apply. ~3–5 minutes.
```

After the run, a JSON log lands in
`99_System/logs/deploy-oho-runner-<UTC-timestamp>.json` — keep this for the
post-deploy verification step.

### Step 0 — `preflight`

**Runs:** Validates `.env`, repo state, required env vars, OHO token shape
(64 hex chars), SSH reachability, n8n API reachability.

**Expected output:**
```
  ✓ SSH to root@192.168.1.121 works
  ✓ n8n API reachable at http://192.168.1.121:5678
  ✓ preflight clean — all required env present, n8n + SSH reachable
```

**Success signal:** `preflight  [ok]` in summary table.

**Failure signal:** any `missing env vars`, `SSH … failed`, `n8n API not reachable`.

**If it fails:** the orchestrator **aborts hard** before any destructive op
(exit 2) and writes a JSON log. Fix the env/network issue. There is no
"resume from preflight" because by definition nothing has changed.

**Resume:** N/A — re-run from scratch.

### Step 1 — `inspect`

**Runs:** Pipes `scripts/lxc_inspect.sh` to the LXC over SSH; gathers
read-only state (running containers, network membership, disk, env file
presence, repo path). Per Aaron's memory `feedback_inspect_before_deploy.md`,
this **must run before any destructive op**.

**Expected output:** A `(no output)`-free block of LXC state. Look for:
- `n8n_default` network present
- `n8n` container running
- `/opt/oho` exists (or note that it doesn't — sync will create it)

**Success signal:** `inspect  [ok]` (exit 0) or `[warn]` (informational
non-zero — `lxc_inspect.sh` is best-effort).

**Failure signal:** `inspect  [fail]` — SSH refused, script piping broke, or
the LXC is unreachable.

**If it fails:** check SSH config (see §2.5). The `inspect` step is
read-only, so a failure here is purely a connectivity issue.

**Resume:** `python3 scripts/deploy_oho_runner.py --apply --from-step inspect`.

### Step 2 — `sync`

**Runs:** `rsync -az --delete` from local repo to `${OHO_REPO_PATH:-/opt/oho}`
on the LXC. Excludes `.git/`, `__pycache__`, `.venv`, `.env`, `*.pyc`,
`.pytest_cache/`, `99_System/`, `tests/`. The `.env` exclusion is intentional —
the runner-env step (next) composes a runner-scoped env separately.

**Dry-run:** prints `rsync --dry-run` top 20 lines. Confirm: no surprising
deletes, no unexpected adds.

**Expected output:**
```
  ✓ synced repo → root@192.168.1.121:/opt/oho/
```

**Success signal:** `sync  [ok]`.

**Failure signal:** rsync non-zero exit. Common causes: SSH key auth failure,
disk full on LXC, permission denied on `/opt/oho/`.

**If it fails:**
- `df -h /` on LXC — if full, expand or prune.
- `ls -ld /opt/oho` on LXC — must be writable by the SSH user.
- Network drop — retry. rsync is idempotent.

**Resume:** `--from-step sync`. The state on the LXC after a partial rsync is
just whatever was already there; re-running converges.

### Step 3 — `runner-env`

**Runs:** Copies `/opt/oho/.env` → `/opt/oho/services/oho_runner/.env`, then
replaces any existing `OHO_RUNNER_TOKEN=…` line with the value from local
`.env`. `chmod 600`.

**Why:** the runner container has `env_file: .env` in its compose; the local
copy of the repo is the source of truth for MinIO/OpenRouter creds, but the
token must be derived deterministically from `OHO_RUNNER_TOKEN` so the n8n
cred and the runner agree.

**Expected output:**
```
  ✓ OK:wrote /opt/oho/services/oho_runner/.env (mode 600)
```

**Failure signal:** `MISSING:repo_env` (means rsync didn't land `.env` — but
we **excluded** `.env`, so the runner-env step assumes `/opt/oho/.env` already
exists on the LXC. **First-time deploys must pre-stage `/opt/oho/.env` on the
LXC manually.** See §13 open question 1.)

**If it fails:**
- If `MISSING:repo_env`: `scp .env root@192.168.1.121:/opt/oho/.env` once,
  then re-run.
- If `chmod` fails: check SSH user has rights on `/opt/oho`.

**Resume:** `--from-step runner-env`.

### Step 4 — `compose`

**Runs:** `cd /opt/oho/services/oho_runner && docker compose up -d --build`,
then polls `docker inspect -f '{{.State.Health.Status}}'` up to 12×5s for the
healthcheck to flip to `healthy`.

**Expected output:**
```
  healthcheck attempt 1: starting
  healthcheck attempt 2: healthy
  ✓ oho-runner container is healthy
```

**Success signal:** `compose  [ok]`.

**Failure signal:** `TIMEOUT waiting for healthy` after 60s; image build
errors; "network n8n_default not found".

**If it fails:**
- `docker network ls | grep n8n_default` — create externally if missing:
  `docker network create n8n_default` (only if n8n itself isn't already
  managing this; usually n8n's compose owns the network).
- Image build error: `cd /opt/oho/services/oho_runner && docker compose build`
  manually to see the full failure.
- Healthcheck times out but container is `Up`: `docker logs oho-runner` —
  most often a Python import error (Dockerfile drift) or `OHO_RUNNER_TOKEN`
  unset (the runner reports `token_configured: false` in `/health`).

**Resume:** `--from-step compose`.

### Step 5 — `smoke-runner`

**Runs:** Three probes from inside the LXC, using the public `curlimages/curl`
image on the `n8n_default` network (so we test the same DNS path that n8n
itself will use):
1. `GET /health` → expect `"status":"ok"`.
2. `POST /process-brain-dump` with valid bearer → expect anything except 401
   (200 / 409 / 5xx are all acceptable; we just need the auth boundary to pass).
3. `POST /process-brain-dump` with bad bearer → expect **exactly 401**.

**Expected output:**
```
  ✓ /health → {"status":"ok","service":"oho-runner",...}
  ✓ bearer auth boundary correct (good=200, bad=401)
```

**Success signal:** `smoke-runner  [ok]`.

**Failure signal:**
- `health probe failed` — runner not reachable at `oho-runner:8080` from the
  `n8n_default` network. Re-check compose network membership.
- `bad-token probe expected HTTP 401, got 200` — **critical**: bearer auth
  isn't enforced. Stop. Re-check `app.py` is the committed version.
- `good-token probe got 401` — token drift between repo `.env` and runner
  env file. Re-run `--from-step runner-env`.

**If it fails:** the runner is broken; do not proceed to n8n-cred. The n8n
side will only consume a working runner.

**Resume:** `--from-step smoke-runner`.

### Step 6 — `n8n-cred`

**Runs:** `POST /api/v1/credentials` with `name="OHO Runner Auth"`,
`type="httpHeaderAuth"`, `data={"name": "Authorization", "value": "Bearer <token>"}`.

**Expected output:**
```
  ✓ created `OHO Runner Auth` (id=abc123…)
```
or, on re-run:
```
  ✓ `OHO Runner Auth` already exists — leaving as-is
```

**Success signal:** `n8n-cred  [ok]` with either branch.

**Failure signal:** non-400 HTTP from n8n, or a 400 with a body that doesn't
contain "already exists".

**If it fails:**
- HTTP 401: `N8N_API_KEY` is wrong/rotated. Refresh from n8n UI → Settings
  → API.
- Token in n8n cred doesn't match runner env: delete the cred in n8n UI
  (Settings → Credentials → OHO Runner Auth → Delete), re-run this step.

**Resume:** `--from-step n8n-cred`.

### Step 7 — `hydrate-deploy`

**Runs:** For each of `brain-dump-processor-v2.json` and
`live-dashboard-updater.json`, invokes `scripts/deploy_n8n_workflow.py`. That
script:
1. Backs up the live workflow body to `/opt/oho/backups/n8n/` (or local —
   depending on where it's invoked from).
2. Substitutes `__OHO_RUNNER_CRED_ID__` etc. with live IDs.
3. `PUT /api/v1/workflows/<id>`.
4. Re-fetches and asserts: `--assert-no-execute-command`,
   `--assert-http-url-contains /process-brain-dump` (and `/build-command-center`
   for the dashboard updater).

**Expected output:**
```
  ✓ deployed workflows/n8n/brain-dump-processor-v2.json
  ✓ deployed workflows/n8n/live-dashboard-updater.json
```

**Success signal:** `hydrate-deploy  [ok]`.

**Failure signal:**
- An assertion fails (e.g. `--assert-no-execute-command` finds an
  executeCommand node — should be impossible at this point, but it gates
  before activation).
- `__OHO_RUNNER_CRED_ID__` placeholder isn't resolved (the cred wasn't
  discoverable). This means step 6 wrote a cred but the deploy script can't
  find its ID — usually because the public API hides credential IDs from
  list endpoints. The deploy script has a fallback path; if it still can't
  find it, set the env var manually:
  `OHO_RUNNER_CRED_ID=<id from n8n UI> python3 scripts/deploy_oho_runner.py --apply --from-step hydrate-deploy`.

**If it fails:** the live workflow body is **not yet updated** (the script
asserts before PUT). Safe to retry.

**Resume:** `--from-step hydrate-deploy`.

### Step 8 — `activate`

**Runs:** `POST /api/v1/workflows/<id>/activate` for `brain-dump-processor-v2`
and `live-dashboard-updater`. Looks the workflow up by **name** — note that
this is one of the few places the orchestrator does NOT use ID. Per memory
`feedback_n8n_workflow_name_emoji_prefix.md`, live names have emoji prefixes.
**If the live workflow is named `🧠 Brain Dump Processor v2 — Daily 7AM`**,
this step will fail to find it.

**Expected output:**
```
  ✓ activated `brain-dump-processor-v2` (id=abc123…)
  ✓ activated `live-dashboard-updater` (id=def456…)
```

**Success signal:** `activate  [ok]`.

**Failure signal:** `workflow not found`. → Edit the orchestrator's
`WORKFLOWS_TO_ACTIVATE` list to match the live emoji-prefixed names, OR (better)
patch the orchestrator to do a `contains` match. **This is the most likely
hand-tweak required during a live deploy.**

**If it fails:** Activate manually in n8n UI (Settings → toggle Active on each
workflow). The workflow body has already been deployed correctly in step 7;
activation is a separate API call.

**Resume:** `--from-step activate`.

### Step 9 — `smoke-pipeline`

**Runs:** `POST /api/v1/workflows/<id>/execute` for `brain-dump-processor-v2`,
then polls `/executions/<exe_id>` every 5s up to 120s for `finished: true`.

**Expected output:**
```
  · triggered execution 1234; polling for completion…
  ✓ execution 1234 finished: status=success
```

**Success signal:** `smoke-pipeline  [ok]` AND a receipt JSON exists in
`99_System/extraction-receipts/` for any file that had content AND
`99_System/state/last-brain-dump-summary.json` was updated.

**Acceptable variants:**
- `status=success` with `files_with_content: 0` is fine — means no brain
  dumps had un-processed content at the moment, which is the normal state
  outside the 7AM window.
- `status=unknown` (the orchestrator's fallback when n8n doesn't populate a
  status field for some workflow versions) → check n8n UI Executions tab
  directly.

**Failure signal:**
- `execution did not finish within 120s` — runner subprocess is hung. SSH in,
  `docker logs oho-runner --tail=100`. If subprocess is doing real work
  (large brain dump), increase poll budget or just check the UI.
- `status=error` — check the n8n UI for the node-level error.

**If it fails:** see §6 (tripwires) and §11 (failure-mode matrix). Most
common: bearer auth misalignment (silently fixed by re-running `--from-step
runner-env compose smoke-runner`) or the runner can't reach MinIO from the
container (network issue — n8n_default vs. host network).

**Resume:** `--from-step smoke-pipeline`. This step is purely a read; safe to
re-run.

### Step 10 — `report`

**Runs:** Always. Writes `99_System/logs/deploy-oho-runner-<UTC>.json` with
per-step status, elapsed_ms, artifacts (cred id, execution id, runner health
snapshot). Prints the summary table.

**Final post-deploy actions (manual, outside the orchestrator):**

```bash
# One-time: seed the daily command center
set -a && source .env && set +a
make build-home
# Verify it landed
python3 -c "
import boto3, os
from botocore.client import Config
s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'],
    aws_access_key_id=os.environ['MINIO_ACCESS_KEY'],
    aws_secret_access_key=os.environ['MINIO_SECRET_KEY'],
    config=Config(signature_version='s3v4'), region_name='us-east-1')
h = s3.head_object(Bucket=os.environ['MINIO_BUCKET'],
    Key='000_Master Dashboard/!!! DAILY COMMAND CENTER.md')
print(f\"ContentLength={h['ContentLength']}, LastModified={h['LastModified']}\")
"
```

Open the vault in Obsidian. The new `!!! DAILY COMMAND CENTER.md` should
float to the top of `000_Master Dashboard/` and render with all seven H2
sections. If `🧠 New From Brain Dumps` shows the "summary missing" warning,
that's expected until the next real brain-dump run.

---

## 4. First-24-hour observation plan

After the deploy lands, the **first 24 hours** are the high-risk window. Do
not consider the soak counter started until the 7AM CDT brain-dump run on
the morning AFTER deploy fires cleanly.

### 4.1 Within 1 hour of deploy

- [ ] **Runner logs clean:**
  ```bash
  ssh pve 'pct exec 202 -- docker logs oho-runner --tail=100'
  ```
  Look for the FastAPI startup banner and zero `ERROR`/`WARNING` lines beyond
  the healthcheck noise.
- [ ] **Health probe still green:**
  ```bash
  ssh pve 'pct exec 202 -- curl -fsS http://oho-runner:8080/health'
  # OR via the n8n container's network:
  ssh pve 'pct exec 202 -- docker exec n8n-n8n-1 sh -lc "curl -fsS http://oho-runner:8080/health"'
  ```
  Confirm `script_present: true` for both jobs, `env_present: true`,
  `token_configured: true`, `lock_held: false`.
- [ ] **live-dashboard-updater (`:03`)** fired in n8n Executions tab. The
  workflow runs hourly so within an hour we should see one green run that
  successfully called `/build-command-center`.
- [ ] **`!!! DAILY COMMAND CENTER.md` was rebuilt** at the `:03` mark of the
  hour after deploy. Verify via MinIO `LastModified`.

### 4.2 At the next 7AM CDT window

This is the moment of truth. The brain-dump cron fires.

- [ ] **n8n Executions tab** shows `brain-dump-processor-v2` (under whatever
  emoji-prefixed live name) ran at 12:00 UTC = 7AM CDT and finished green.
- [ ] **Runner logs** show one `running (PYTHON, '-u', 'tools/process_brain_dump.py')`
  line followed by one `done exit=0 duration=...` line.
- [ ] **Receipt landed:** for each brain-dump file with content,
  `99_System/extraction-receipts/<source>-<YYYYMMDD>-<sha8>.json` exists and
  has `summary.all_sections_verified: true` (or, if not, `final_status:
  partial` and a `last_partial_reasons` populated in the source frontmatter).
- [ ] **Archive landed:** `99_System/archive/brain-dumps/<YYYY-MM-DD>/<file>.md`
  exists for each processed file.
- [ ] **Run log truthful:**
  ```bash
  make logs                                     # tails today's JSON
  ```
  Confirm: `reset_applied` field is **absent** (replaced by `reset_summary`),
  `files_by_state` totals add up, `receipts_written` matches the number of
  files with content.
- [ ] **No error-handler email** arrived in Aaron's inbox.
- [ ] **Audit clean:**
  ```bash
  set -a && source .env && set +a
  python3 scripts/audit_extraction_receipts.py
  # expect: exit 0, "All rules passed"
  ```
- [ ] **Command center rebuilt at 7:03 AM CDT** with the new captures
  surfaced in `🧠 New From Brain Dumps`. Verify by opening the vault.

### 4.3 Throughout day 1

- [ ] System Health Monitor fires every 6h (`:33`) — green every time.
- [ ] Morning briefing email arrives at 7:30 AM CDT with the new captures.
- [ ] No "Task request timed out after 60 seconds" emails — no task-runner
  contention.
- [ ] `link-enricher` (`:13`) and `article-processor` (`:23 08`, `:23 19`)
  fire on their normal schedules and don't conflict with the runner.

---

## 5. Soak-window observability dashboard

For each of days 1–7 (and ideally 1–14), the operator runs the **morning
check** at the same time each day. Goal: catch drift before it compounds.

### 5.1 Daily 8 AM CDT morning check (≤ 2 min)

```bash
set -a && source .env && set +a
make health                                       # MinIO + n8n + vault files
python3 scripts/audit_extraction_receipts.py      # receipts audit
make logs                                         # today's brain-dump run log
```

Then in the n8n UI:

- Executions tab, filter by Status: **error** in last 24h → must be **0**.
- Executions tab, all workflows: confirm the morning runs all finished.

### 5.2 Metrics to track day-over-day

Keep a one-line ledger somewhere stable (or just let the run logs serve as
the ledger; this is what the audit cares about):

| Metric | Where it lives | Target |
|---|---|---|
| brain-dump executions succeeded | n8n Executions tab + `99_System/logs/brain-dump-processor-<date>.json` | 1/day, no failures |
| brain-dump skip_reason | run log `top_status` + per-file `skip_reason` | `success` / `no_work` only — **no `minio_*`** |
| receipts written | run log `receipts_written` | = # files with content |
| receipt audit | `audit_extraction_receipts.py` exit code | 0 every day |
| files in `status: partial` > 7 days | audit rule 4 | 0 |
| files in `status: scanning` > 1 hour | audit rule 3 | 0 |
| double-extraction events | content_hash of a file processed twice with different `last_processed_hash` writes | 0 |
| task-runner timeouts in n8n logs | `health_check.py [n8n_task_runner_recent_errors]` | PASS every day |
| MinIO bytes written | archive + receipts + processed/ — should grow monotonically | growing |
| error-handler emails | Aaron's inbox | 0 |
| command center stale > 36h | the `> [!warning]+` block at the top of the file | absent |

### 5.3 Weekly check (Sunday evening)

After `vault-health-report` fires (Sunday 8 PM CDT), confirm the email shows:
- Inbox health: brain-dump count + processed/ count + receipt-audit summary.
- No new "stuck" files (>7 day partial, stale scanning).

---

## 6. Tripwires that ABORT the soak and require rollback

Any one of these, at any time during the soak window, **stops the counter and
triggers §7 rollback**. The soak is binary — no "this happened but probably
fine" leniency. Each is a real symptom of a real class of bug we shipped P1
to eliminate.

| # | Tripwire | Why it aborts the soak |
|---|---|---|
| T1 | Any `skip_reason: minio_offline`, `minio_auth_error`, or `minio_list_failed` in a run log that isn't immediately followed by a green retry within the same hour | Brain-dump pipeline silently skipping = the exact P0 failure mode. |
| T2 | `scripts/audit_extraction_receipts.py` exits non-zero | Receipt-to-run-log integrity broke. P1 contract violated. |
| T3 | Any n8n execution with `Task request timed out after 60 seconds` | Task-runner stall — code-heavy slot contention or runaway Code node. |
| T4 | Any S3 PUT in the runner logs that isn't followed by a successful `head_object` (verified write contract broken) | Goes to the heart of the P1 gate semantics. |
| T5 | Two receipts for the same `<source>-<YYYYMMDD>` with **different** `content_hash` values in the same day | Double-extraction. The state machine failed to gate. |
| T6 | A brain-dump source ends a day in `status: scanning` (stale lock) | Crash mid-run, recovery didn't trip. Audit rule 3 should catch this. |
| T7 | A source ends 7+ days in `status: partial` | Unattended failure on a section write. Audit rule 4. |
| T8 | The `reset_applied: true` literal appears in any n8n Code node body | Test 8 of ADR-0005's static-analysis test was bypassed in deploy. Severe. |
| T9 | `!!! DAILY COMMAND CENTER.md` is older than 36h | Either `live-dashboard-updater` is broken or `/build-command-center` is. |
| T10 | Runner returns HTTP 5xx more than 3× in any 1-hour window | Sidecar instability — Python crash, timeout, OOM. |
| T11 | Any error-handler email | The `error-handler` workflow fires on any other workflow's failure. Single email = single incident = abort. |
| T12 | MTL gains a duplicate task (same description appended twice within 7d) | Append idempotency broken — likely a re-extraction without receipt gating. |

**Special case — recoverable transients:** If a tripwire fires once during a
2-hour window where the operator can confirm an external cause (MinIO
restarted, LXC was rebooted, n8n was upgraded), AND the next scheduled run
recovers cleanly without operator intervention, the operator MAY choose to
NOT reset the soak counter, but MUST document the incident in
`docs/superpowers/phases/2026-05-12-P0-deploy-and-soak-start.md` under §6.1
below. Default behavior: reset the counter.

### 6.1 Incident log (append-only during soak)

```
yyyy-mm-dd HH:MM  TRIPWIRE  T?  <one-line description>  RESET|KEEP  <link to artifact>
```

Empty until something fires. If still empty at day 7, the soak passes.

---

## 7. Rollback procedure

When any tripwire fires (or the operator decides the system is unsafe), run
this **in order**. Do not skip steps. Each step has a verification gate.

### 7.1 Stop the bleed (≤ 5 minutes)

```bash
set -euo pipefail
set -a && source .env && set +a

# 1. Deactivate the two cron-driven workflows so nothing else fires.
for name in brain-dump-processor-v2 live-dashboard-updater; do
  wf_id=$(curl -fsS -H "X-N8N-API-KEY: $N8N_API_KEY" \
    "$N8N_HOST/api/v1/workflows" \
    | jq -r --arg n "$name" '.data[] | select(.name|contains($n)) | .id' | head -1)
  [ -z "$wf_id" ] && echo "WARN: $name not found" && continue
  http=$(curl -fsS -o /dev/null -w '%{http_code}' \
    -H "X-N8N-API-KEY: $N8N_API_KEY" \
    -X POST "$N8N_HOST/api/v1/workflows/$wf_id/deactivate")
  [ "$http" = "200" ] || { echo "FAIL: deactivate $name http=$http"; exit 1; }
  echo "OK: deactivated $name ($wf_id)"
done
```

### 7.2 Stop the runner

```bash
ssh pve 'pct exec 202 -- bash -c "cd /opt/oho/services/oho_runner && docker compose stop"'
# Verify
ssh pve 'pct exec 202 -- docker ps --filter name=oho-runner --format "{{.Names}} {{.Status}}"'
# expect: empty output (no row) — container is stopped
```

### 7.3 Snapshot state files (so the post-mortem has data)

```bash
ts=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p backups/rollback/$ts
set -a && source .env && set +a
python3 - <<PY
import boto3, os, sys, json
from botocore.client import Config
s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'],
    aws_access_key_id=os.environ['MINIO_ACCESS_KEY'],
    aws_secret_access_key=os.environ['MINIO_SECRET_KEY'],
    config=Config(signature_version='s3v4'), region_name='us-east-1')
bucket = os.environ['MINIO_BUCKET']
for prefix in ['99_System/extraction-receipts/',
               '99_System/state/',
               '99_System/logs/',
               '99_System/archive/brain-dumps/',
               '00_Inbox/brain-dumps/']:
    for obj in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get('Contents', []):
        local = f"backups/rollback/${ts}/" + obj['Key']
        os.makedirs(os.path.dirname(local), exist_ok=True)
        s3.download_file(bucket, obj['Key'], local)
        print(local)
PY
echo "OK: snapshot at backups/rollback/$ts"
```

### 7.4 Restore prior workflow bodies (if P1.5 deploy was the cause)

Use the backups in `/opt/oho/backups/n8n/` (written automatically by
`deploy_n8n_workflow.py`) or the local pre-deploy snapshots from §2.8.

```bash
# Identify the right backup file by timestamp — the one just before this deploy:
ssh pve 'pct exec 202 -- ls -lh /opt/oho/backups/n8n/' | head -20

# PUT it back via n8n REST API (replace WF_ID, PATH):
curl -fsS -H "X-N8N-API-KEY: $N8N_API_KEY" -H "Content-Type: application/json" \
  -X PUT "$N8N_HOST/api/v1/workflows/$WF_ID" \
  -d @backups/local/pre-p15-brain-dump-processor-v2-<ts>.json
```

### 7.5 Decide: revert to which state?

Three rollback levels:

- **L1 — workflow-only:** restore the previous workflow JSONs, keep the
  runner stopped, but leave receipts / state files / migration intact.
  Pipeline returns to the **pre-P1.5** behavior (whatever the live workflows
  did before this deploy, including the P1 integrity layer that landed in
  `f3f8325`). Use when the failure is clearly in the HTTP boundary.

- **L2 — drop P1 too:** revert workflows to the pre-P1 commits (`2b518b1`
  era). The state machine, receipts, and gated reset go quiet — the audit
  will scream because old behavior writes no receipts. The audit should be
  *temporarily disabled* in `vault-health-report` to silence the alert
  storm. Use when the integrity layer itself is malfunctioning.

- **L3 — full P0 baseline:** worst case, revert all of P1+P1.5+ADR-0006 and
  return to the 2026-05-03 P0 state. This is essentially "the system as it
  was when we recovered from the 11-day silent failure." Receipts and state
  files are kept in MinIO as historical artifacts but ignored.

Choose the lowest level that addresses the tripwire. L1 by default.

### 7.6 Document the failure

Append to this file under §6.1 incident log, then write a 1-page
post-mortem at `docs/post-mortems/2026-MM-DD-tripwire-T?.md` covering:
- Tripwire fired (which one).
- Symptom + first observation timestamp.
- Diagnostic steps + what they showed.
- Root cause.
- Why P1's tests didn't catch it.
- Fix design — a new test that would have caught it.
- Soak counter reset to 0, restart date.

### 7.7 Fix forward

Land the fix on a fresh branch, get tests green, then **start §3 deploy
again from step 0 (`preflight`)**. The soak counter resets to day 0.

---

## 8. Soak-exit gate

The soak window opens the morning AFTER the deploy's first clean 7AM CDT
brain-dump run. It closes when **all** of the following are simultaneously
true at the same morning check:

| Criterion | How to check | Source of truth |
|---|---|---|
| **≥7 consecutive days** since the soak started | wall clock | calendar |
| **7+ daily brain-dump runs all succeeded** (`top_status: success` or `no_work`) | `99_System/logs/brain-dump-processor-<date>.json` for each day in range | run logs |
| **Zero double-extractions** | grep for duplicate `<source>-<YYYYMMDD>` keys with different content_hashes in `99_System/extraction-receipts/` | receipts |
| **Receipt audit passes every day** | `scripts/audit_extraction_receipts.py` exit 0 every day | audit script |
| **Zero human interventions** beyond the daily 2-min morning check | operator's incident log §6.1 is empty | this doc |
| **Zero error-handler emails** | Aaron's inbox | email |
| **`live-dashboard-updater` ran 24×/day, every day** | n8n Executions tab | n8n |
| **`!!! DAILY COMMAND CENTER.md` never stale > 36h** | head_object LastModified delta | MinIO |
| **No task-runner timeouts** | `health_check.py [n8n_task_runner_recent_errors]` PASS every check | health_check |
| **vault-health-report Sunday email green** for the Sunday inside the window | Aaron's inbox | email |

If even one criterion fails on day 7, the soak extends another **24 hours**
(not a full restart) — but only if the failure was a one-shot anomaly that
self-resolved. A second failure inside the same window restarts the counter
at 0.

**On the morning the gate passes:** create a commit on `polish/prod-ready`
that flips the `ADR-0005` status from `Accepted` to `Implemented` and records
the soak-completion date in `docs/adr/0005-…`. P2 design work
(`docs/adr/<date>-threaded-tasks.md`) is now eligible to start. Update
CLAUDE.md "Current Status" section.

---

## 9. Concurrent hygiene tasks that DON'T touch the soak gate

These are safe to ship in parallel with the soak because they don't change
the brain-dump path, the runner, or the command-center generator:

- GCAL OAuth2 → `GCAL_CRED_ID` → re-deploy Weekend Planner.
- OpenRouter key rotation.
- MTL backfill of `[due::]` and `[completion::]` metadata.
- Documentation polish, CLAUDE.md tidies, ADR cross-links.

**Anything that touches `tools/process_brain_dump.py`, `tools/bd_integrity.py`,
`tools/build_command_center.py`, `services/oho_runner/`, or the two
workflows in §3 is gated by the soak.** No exceptions.

A sibling agent owns the carry-forward queue above; this phase does not
deep-dive them.

---

## 10. `--no-reset` deprecation gate

Per ADR-0005 step 8 of the rollout, the `--no-reset` safety flag on
`tools/process_brain_dump.py` stays in place as the escape hatch during P1.
The decision to deprecate it is made **after** the soak gate opens.

### Criteria to deprecate `--no-reset`

After the soak passes (§8 all green for ≥7 days), AND one additional weekend
passes with no tripwires, the operator MAY:

1. Open a `chore/deprecate-no-reset` branch.
2. Remove the `--no-reset` CLI flag from `tools/process_brain_dump.py`.
3. Remove the `run.no_reset` field from the receipt schema (bump
   `schema_version` to 2; old receipts remain valid for audit, which keys
   off `schema_version`).
4. Delete tests that asserted `--no-reset` behavior (Test 12 of ADR-0005).
5. Update CLAUDE.md "Pending" section to remove the Step-8 line.

### Criteria to KEEP `--no-reset` as a documented escape hatch

If during the soak the operator used `--no-reset` even once (for safe
debugging or to inspect a stranded file before clearing), keep the flag and
move it from "deprecation candidate" to "documented operational tool" in
`docs/RUNBOOK.md`. The escape hatch is cheap; the discipline of deciding
intentionally is the point.

Default recommendation: **deprecate**. The integrity layer's gate semantics
make the safety net redundant for the steady state. Aaron can always restore
the flag if a future incident demands it.

---

## 11. Failure-mode matrix

| Failure cause | Early signal | Diagnostic command | Fix |
|---|---|---|---|
| Bearer token drift (runner ↔ n8n cred) | 401 on `/process-brain-dump` in runner logs OR `step_smoke_runner` good-token probe returns 401 | `ssh pve 'pct exec 202 -- docker logs oho-runner --tail=30'` | Re-run `--from-step runner-env compose smoke-runner n8n-cred` |
| Runner container down | n8n HTTP node "ECONNREFUSED" | `docker ps --filter name=oho-runner` | `cd /opt/oho/services/oho_runner && docker compose up -d` |
| Runner can't reach MinIO from inside container | runner subprocess exit ≠ 0 with `EndpointConnectionError` in `stderr_tail` | `docker exec oho-runner python3 -c "import os; print(os.environ.get('MINIO_ENDPOINT'))"` | Confirm runner-env step wrote MinIO vars; restart container |
| Cron-minute collision | "Task request timed out after 60 seconds" email | `pytest tests/test_workflow_templates.py::test_code_heavy_workflows_do_not_share_cron_minutes -q` | Move offending workflow to `:43` or `:53` |
| Receipt audit fails: stale `scanning` lock | audit rule 3 output | `python3 scripts/audit_extraction_receipts.py --verbose` | Audit auto-recovers within 1h; if not, manually edit frontmatter to revert `status` to last known good |
| Receipt audit fails: 7-day partial | audit rule 4 output | same | Inspect the file's retention block, fix the specific write target, re-run brain-dump manually |
| `!!! DAILY COMMAND CENTER.md` stale > 36h | command center's own warning banner; or MinIO LastModified | `set -a && source .env && set +a && make build-home` (manual rebuild) | Investigate why `live-dashboard-updater :03` didn't fire — usually a runner 5xx |
| Double extraction | duplicate task in MTL OR two receipts same day same source | `python3 scripts/audit_extraction_receipts.py` rule 1 | Critical — abort soak, rollback, post-mortem |
| Source frontmatter drift | audit rule 6 "missing fields" | inspect file via `make logs` or MinIO console | Re-run `scripts/migrate_brain_dump_frontmatter.py --dry-run` then `--apply` |
| Open `:43`/`:53` slot stolen by another workflow | new cron in n8n UI; test_workflow_templates fails | the collision-guard test | Reassign, run test, redeploy |
| `OHO Runner Auth` cred deleted in n8n UI by accident | 401 on `/process-brain-dump` from n8n, but smoke-runner good probe still passes | n8n UI Credentials list | `python3 scripts/deploy_oho_runner.py --apply --only-step n8n-cred hydrate-deploy` |
| `OHO_RUNNER_TOKEN` regenerated and only one side updated | smoke-runner good-token=401 | compare `.env` (local) vs runner env (LXC) vs n8n cred value | Pick one, propagate. `--from-step runner-env`. |
| LXC reboot leaves runner not started | health_check FAILs; n8n logs ECONNREFUSED | `docker ps -a --filter name=oho-runner` | `restart: always` in compose should handle, but if not: `docker compose up -d` |
| MinIO bucket versioning OFF | rollback path doesn't exist for receipts | `s3.get_bucket_versioning` | Enable in MinIO Console immediately; no soak-blocker but a soak-prerequisite |

---

## 12. Verification before "soak complete"

On the morning the operator believes the gate has passed (day 7+), run this
exact verification block. It MUST all pass before the operator commits the
ADR-0005 status flip.

```bash
set -euo pipefail
set -a && source .env && set +a

# 1. Audits — all 5 must pass.
make audit-workflows
make audit-ai-tooling
python3 scripts/audit_workflow_runlogs.py
python3 scripts/audit_extraction_receipts.py

# 2. Health — must be all PASS.
python3 scripts/health_check.py

# 3. Test suite — must be 311 pass, 1 skip.
make test

# 4. Per-day run log verification — every day in the window has a green log.
python3 - <<'PY'
import boto3, datetime as dt, json, os, sys
from botocore.client import Config
s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'],
    aws_access_key_id=os.environ['MINIO_ACCESS_KEY'],
    aws_secret_access_key=os.environ['MINIO_SECRET_KEY'],
    config=Config(signature_version='s3v4'), region_name='us-east-1')
bucket = os.environ['MINIO_BUCKET']
# Walk back 7 days
today = dt.date.today()
fail = False
for i in range(7):
    d = today - dt.timedelta(days=i)
    key = f"99_System/logs/brain-dump-processor-{d.isoformat()}.json"
    try:
        body = json.loads(s3.get_object(Bucket=bucket, Key=key)['Body'].read())
    except Exception as e:
        print(f"FAIL  {d}: no log ({e})"); fail = True; continue
    top = body.get('top_status') or body.get('status')
    if top not in ('success', 'no_work'):
        print(f"FAIL  {d}: top_status={top}"); fail = True; continue
    if 'reset_applied' in body:
        print(f"FAIL  {d}: stale reset_applied field"); fail = True; continue
    print(f"OK    {d}: top_status={top}, receipts={body.get('receipts_written', 0)}")
sys.exit(1 if fail else 0)
PY

# 5. MTL diff — no duplicate tasks appended in the window.
# (Manual: inspect 10_Active Projects/Active Personal/!!! MASTER TASK LIST.md
#  in Obsidian; the audit's per-source content_hash gating already prevents
#  this, but eyeball confirm.)

# 6. Command center freshness — LastModified within last 1h.
python3 - <<'PY'
import boto3, datetime as dt, os
from botocore.client import Config
s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'],
    aws_access_key_id=os.environ['MINIO_ACCESS_KEY'],
    aws_secret_access_key=os.environ['MINIO_SECRET_KEY'],
    config=Config(signature_version='s3v4'), region_name='us-east-1')
h = s3.head_object(Bucket=os.environ['MINIO_BUCKET'],
    Key='000_Master Dashboard/!!! DAILY COMMAND CENTER.md')
age = dt.datetime.now(dt.timezone.utc) - h['LastModified']
print(f"command center age: {age}")
assert age < dt.timedelta(hours=2), f"stale: {age}"
print("OK: command center fresh")
PY
```

If every block prints OK and exits zero, the soak is complete.

---

## 13. Open questions / asks for Aaron

These are decisions the deploy script can't make automatically. Resolve
before or during the deploy:

1. **First-time `/opt/oho/.env` seeding on the LXC.** The rsync explicitly
   excludes `.env`. If this is the very first deploy and no prior `.env`
   sits at `/opt/oho/.env`, step 3 (`runner-env`) will fail with
   `MISSING:repo_env`. Confirm with `ssh pve 'pct exec 202 -- test -f /opt/oho/.env && echo yes || echo no'`.
   If `no`, run `scp .env root@192.168.1.121:/opt/oho/.env` once before the
   apply.

2. **Live workflow names with emoji prefixes.** Step 8 (`activate`) looks up
   workflows by exact name. If the live names are
   `🧠 Brain Dump Processor v2 — Daily 7AM` and similar (per memory
   `feedback_n8n_workflow_name_emoji_prefix.md`), step 8 will fail to find
   them. Options:
   - Patch `WORKFLOWS_TO_ACTIVATE` in the orchestrator to use the live names.
   - Patch `n8n_find_workflow_id` to do a `name.contains()` match.
   - Activate manually in n8n UI after step 7 lands cleanly.
   Recommend patching to `contains()` semantics as a one-line fix.

3. **`pct` vs SSH paradigm.** The orchestrator uses direct SSH to
   `root@192.168.1.121` by default. Aaron's saved preference is `pct exec`
   from pve. If direct SSH isn't set up, either configure `ProxyJump` (§2.5)
   or wrap the orchestrator's SSH calls with a `pct`-aware variant. The
   simplest workaround: set `LXC_SSH_HOST=pve` and edit the orchestrator's
   remote-command builder to prefix with `pct exec 202 -- `. Out of scope for
   this phase; flag for a follow-up.

4. **Workflow re-import scope.** `scripts/setup-n8n.sh` reconciles ALL
   workflow templates. `deploy_n8n_workflow.py` reconciles ONE. The phase
   uses the surgical tool — confirm Aaron doesn't want a broader reconcile
   in the same window. (Default: no. Reconcile only what this phase ships.)

5. **Audit emails on rule failure.** `audit_extraction_receipts.py` runs as
   part of `vault-health-report` (Sunday 8 PM CDT). During the soak, do we
   want a more aggressive daily audit alert? Recommend: yes, add a once-daily
   cron at `:43` calling the audit and sending email-on-fail. Out of scope
   for this phase; flag as a soak-window-only safety net to add if any
   tripwire fires non-fatally.

6. **What counts as "manual brain-dump run" during soak?** The morning check
   includes `make logs` which is read-only. If Aaron triggers
   `make run` or `make dry-run` to test something, that counts as a "human
   intervention" per §8 criterion 5 — restarting the counter. Confirm.
   Recommend: `dry-run` (no S3 writes) is allowed; `run` is not, unless
   responding to a tripwire (in which case the counter has already reset).

---

## End

This file is the single source of truth for the P0 deploy + soak. It is
append-only during the soak window (incidents in §6.1, verification artifacts
in §12 output). When the gate passes, copy the final §6.1 ledger into the
ADR-0005 status-flip commit message and mark this phase complete.

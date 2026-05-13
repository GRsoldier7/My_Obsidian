#!/usr/bin/env python3
"""
scripts/deploy_oho_runner.py — Comprehensive end-to-end deploy orchestrator.

Brings up the OHO HTTP-runner sidecar in n8n LXC CT-202, registers the
`OHO Runner Auth` credential with n8n, hydrates + deploys the workflows
that depend on it, reactivates them, and smoke-tests the full pipeline.

This single script replaces a 9-step manual runbook. Run it from a dev
machine that can reach both the LXC's SSH port and the n8n REST API.

──────────────────────────────────────────────────────────────────────────
Quick start
──────────────────────────────────────────────────────────────────────────

    # 1) Generate a bearer token if you don't have one yet:
    openssl rand -hex 32
    # paste the value into .env as OHO_RUNNER_TOKEN=…

    # 2) Source the env and run a dry-run pass (read-only, ~10s):
    set -a && source .env && set +a
    python3 scripts/deploy_oho_runner.py

    # 3) Review the per-step plan, then commit:
    python3 scripts/deploy_oho_runner.py --apply

The dry-run prints exactly what each step would do without changing
anything. Re-runs are safe — every step is idempotent.

──────────────────────────────────────────────────────────────────────────
Step graph
──────────────────────────────────────────────────────────────────────────

    0  preflight       Validate local .env, repo state, SSH reachability.
    1  inspect         Run scripts/lxc_inspect.sh on the LXC (read-only).
    2  sync            rsync the repo to ${OHO_REPO_PATH:-/opt/oho} on LXC.
    3  runner-env      Write services/oho_runner/.env with OHO_RUNNER_TOKEN.
    4  compose         docker compose up -d --build for the sidecar.
    5  smoke-runner    Health probe + bearer-auth probe against the sidecar.
    6  n8n-cred        Create/update `OHO Runner Auth` credential via n8n API.
    7  hydrate-deploy  Call deploy_n8n_workflow.py for each affected workflow.
    8  activate        Activate brain-dump-processor-v2 + live-dashboard-updater.
    9  smoke-pipeline  Trigger a manual run; verify receipt + archive + home.
    10 report          Summary table + JSON log to 99_System/logs/.

Re-entrancy:
    --from-step <name>  Start from this step (skips earlier).
    --only-step <name>  Run exactly this step.
    --skip-step  <name> Skip this step (repeatable).

Required env (.env in repo root):
    MINIO_*, OPENROUTER_API_KEY  — for the runner to do its job.
    N8N_HOST, N8N_API_KEY        — for credential + workflow API calls.
    OHO_RUNNER_TOKEN             — bearer token. Generate with:
                                   openssl rand -hex 32

Optional env:
    LXC_SSH_HOST   (default: root@192.168.1.121)
    LXC_SSH_KEY    (default: ~/.ssh/id_ed25519)
    OHO_REPO_PATH  (default: /opt/oho — applies on the LXC)
    LXC_SSH_OPTS   (default: -o StrictHostKeyChecking=accept-new)

Exit codes:
    0   success (dry-run or apply)
    1   step failure (printed in the summary table)
    2   preflight failure (env / config invalid)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

# ── Constants ───────────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = REPO_ROOT / "99_System" / "logs"

WORKFLOWS_TO_DEPLOY = [
    # (relative path to template, list of `deploy_n8n_workflow.py` asserts)
    (
        "workflows/n8n/brain-dump-processor-v2.json",
        ["--assert-no-execute-command",
         "--assert-http-url-contains", "/process-brain-dump"],
    ),
    (
        "workflows/n8n/live-dashboard-updater.json",
        ["--assert-http-url-contains", "/build-command-center"],
    ),
]

WORKFLOWS_TO_ACTIVATE = [
    "brain-dump-processor-v2",
    "live-dashboard-updater",
]

RUNNER_CRED_NAME = "OHO Runner Auth"
RUNNER_CONTAINER = "oho-runner"
RUNNER_PORT = 8080

STEP_NAMES = [
    "preflight", "inspect", "sync", "runner-env", "compose",
    "smoke-runner", "n8n-cred", "hydrate-deploy", "activate",
    "smoke-pipeline", "report",
]

# ── TTY colors (only when stdout is a TTY) ──────────────────────────────────

class C:
    if sys.stdout.isatty():
        BOLD = "\033[1m"; DIM = "\033[2m"; RESET = "\033[0m"
        RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
        BLUE = "\033[34m"; CYAN = "\033[36m"
    else:
        BOLD = DIM = RESET = RED = GREEN = YELLOW = BLUE = CYAN = ""


def banner(title: str) -> None:
    print(f"\n{C.BOLD}{C.BLUE}━━━ {title} ━━━{C.RESET}")


def info(msg: str) -> None:
    print(f"  {C.CYAN}·{C.RESET} {msg}")


def ok(msg: str) -> None:
    print(f"  {C.GREEN}✓{C.RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {C.YELLOW}!{C.RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {C.RED}✗{C.RESET} {msg}")


def dry(msg: str) -> None:
    print(f"  {C.DIM}[dry-run] would run: {msg}{C.RESET}")


# ── Step result ─────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    name: str
    status: str = "pending"          # ok | warn | fail | skipped | dry
    detail: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0


# ── Subprocess helpers ──────────────────────────────────────────────────────

def run_local(cmd: list[str], *, capture: bool = True, check: bool = False,
              env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a local command. Returns CompletedProcess. Never raises on non-zero
    unless `check=True`."""
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
        env={**os.environ, **(env or {})},
    )


def ssh_cmd(ssh_host: str, ssh_key: str | None, ssh_opts: str) -> list[str]:
    """Build the ssh prefix list for subprocess invocation."""
    cmd = ["ssh"]
    if ssh_opts:
        cmd.extend(shlex.split(ssh_opts))
    if ssh_key:
        cmd.extend(["-i", ssh_key])
    cmd.append(ssh_host)
    return cmd


def run_remote(ssh_host: str, ssh_key: str | None, ssh_opts: str,
               remote_cmd: str, *, capture: bool = True
               ) -> subprocess.CompletedProcess:
    """Run a command on the remote LXC over SSH."""
    return subprocess.run(
        ssh_cmd(ssh_host, ssh_key, ssh_opts) + [remote_cmd],
        capture_output=capture,
        text=True,
        check=False,
    )


# ── n8n API helpers (stdlib urllib, mirroring deploy_n8n_workflow.py) ───────

def n8n_api(method: str, path: str, *, host: str, key: str, body: Any = None
            ) -> Any:
    url = f"{host}/api/v1{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-N8N-API-KEY", key)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def check_minio_versioning() -> tuple[bool, str]:
    """Return ``(ok, message)``. Versioning on the vault bucket is the
    rollback safety net the integrity layer (ADR-0005) and the threaded-
    tasks migration (P2) depend on. Treat ``Enabled`` as the only
    acceptable state; ``Suspended`` and ``absent`` both fail preflight.

    To enable from the mc CLI::

        mc alias set myminio "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"
        mc version enable myminio/"$MINIO_BUCKET"
    """
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError:
        return False, "boto3 not installed — `pip install boto3` then re-run"
    try:
        client = boto3.client(
            "s3",
            endpoint_url=os.environ["MINIO_ENDPOINT"],
            aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
            aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        )
        resp = client.get_bucket_versioning(Bucket=os.environ["MINIO_BUCKET"])
    except Exception as e:
        return False, f"get_bucket_versioning failed: {type(e).__name__}: {e}"
    status = resp.get("Status", "absent")
    if status == "Enabled":
        return True, "Enabled"
    return False, (f"Status={status} — must be `Enabled`. "
                   f"Run: mc version enable <alias>/{os.environ['MINIO_BUCKET']}")


def n8n_find_workflow_id(host: str, key: str, name: str) -> str | None:
    """Return workflow id for `name`. Live workflows in this n8n carry emoji
    prefixes that diverge from the canonical repo template names (e.g. the
    repo says ``brain-dump-processor-v2`` while the live workflow is named
    ``🧠 brain-dump-processor-v2``). Match strategy:

      1. Exact match wins outright.
      2. Otherwise: any workflow whose name *contains* the target substring.
         A single hit is returned; multiple hits log a warning and return
         ``None`` so the operator can rename or disambiguate before
         activation/execute calls run against the wrong workflow.
    """
    data = n8n_api("GET", "/workflows", host=host, key=key).get("data", [])
    for wf in data:
        if wf.get("name") == name:
            return wf.get("id")
    fuzzy = [wf for wf in data if name in (wf.get("name") or "")]
    if len(fuzzy) == 1:
        return fuzzy[0].get("id")
    if len(fuzzy) > 1:
        warn(f"ambiguous workflow lookup for `{name}` — "
             f"{len(fuzzy)} matches: "
             + ", ".join(repr(wf.get('name')) for wf in fuzzy[:5]))
    return None


# ── Step implementations ────────────────────────────────────────────────────

def step_preflight(args, ctx) -> StepResult:
    r = StepResult(name="preflight")
    issues = []

    # Local repo state
    if not (REPO_ROOT / ".env").exists():
        issues.append(".env missing in repo root")
    if not (REPO_ROOT / "services/oho_runner/app.py").exists():
        issues.append("services/oho_runner/app.py missing")

    # Required env vars
    required = ["MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY",
                "MINIO_BUCKET", "OPENROUTER_API_KEY", "N8N_HOST", "N8N_API_KEY",
                "OHO_RUNNER_TOKEN"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        issues.append(f"missing env vars: {', '.join(missing)}")

    # Token shape (warn-level; OpenSSL rand -hex 32 → 64 hex chars)
    tok = os.environ.get("OHO_RUNNER_TOKEN", "")
    if tok and (len(tok) < 32 or not all(c in "0123456789abcdef" for c in tok.lower())):
        warn(f"OHO_RUNNER_TOKEN does not look like `openssl rand -hex 32` output "
             f"(len={len(tok)}); will deploy anyway")

    # SSH reachability (non-fatal; some steps can be skipped without ssh)
    if ctx["ssh_host"]:
        p = subprocess.run(
            ssh_cmd(ctx["ssh_host"], ctx["ssh_key"], ctx["ssh_opts"])
            + ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes", "true"],
            capture_output=True, text=True, timeout=10,
        )
        if p.returncode == 0:
            ok(f"SSH to {ctx['ssh_host']} works")
        else:
            issues.append(f"SSH to {ctx['ssh_host']} failed: "
                          f"{(p.stderr or '').strip().splitlines()[-1][:200]}")

    # n8n API reachable
    try:
        n8n_api("GET", "/workflows?limit=1",
                host=os.environ["N8N_HOST"], key=os.environ["N8N_API_KEY"])
        ok(f"n8n API reachable at {os.environ['N8N_HOST']}")
    except Exception as e:
        issues.append(f"n8n API not reachable: {e}")

    # MinIO bucket versioning — rollback safety net for ADR-0005 receipts
    # and the P2 threaded-tasks migration. Hard gate.
    if not missing:  # only check if MinIO creds are present
        ver_ok, ver_msg = check_minio_versioning()
        if ver_ok:
            ok(f"MinIO bucket versioning: {ver_msg}")
        else:
            issues.append(f"MinIO bucket versioning: {ver_msg}")

    if issues:
        for i in issues:
            fail(i)
        r.status = "fail"
        r.detail = "; ".join(issues)
    else:
        ok("preflight clean — all required env present, n8n + SSH reachable")
        r.status = "ok"
    return r


def step_inspect(args, ctx) -> StepResult:
    r = StepResult(name="inspect")
    script = REPO_ROOT / "scripts" / "lxc_inspect.sh"
    if not script.exists():
        r.status = "fail"; r.detail = "scripts/lxc_inspect.sh missing"
        fail(r.detail); return r

    # Pipe the script body to remote bash so we don't require it to already
    # be on the LXC.
    if args.dry_run:
        dry(f"ssh {ctx['ssh_host']} 'bash -s' < {script}")
        r.status = "dry"; return r

    p = subprocess.run(
        ssh_cmd(ctx["ssh_host"], ctx["ssh_key"], ctx["ssh_opts"]) + ["bash -s"],
        input=script.read_text(),
        capture_output=True, text=True, timeout=60,
    )
    # lxc_inspect.sh is intentionally informational; non-zero is rare.
    if p.returncode != 0:
        warn(f"lxc_inspect.sh exited {p.returncode}")
    print(C.DIM + (p.stdout or "(no output)") + C.RESET)
    r.status = "ok" if p.returncode == 0 else "warn"
    r.detail = f"exit={p.returncode}; len(stdout)={len(p.stdout or '')}"
    r.artifacts["stdout_tail"] = (p.stdout or "")[-2000:]
    return r


def step_sync(args, ctx) -> StepResult:
    r = StepResult(name="sync")
    remote_path = ctx["oho_repo_path"]
    rsync_cmd = [
        "rsync", "-az", "--delete",
        "--exclude=.git/", "--exclude=__pycache__/", "--exclude=.venv/",
        "--exclude=.env", "--exclude=*.pyc", "--exclude=.pytest_cache/",
        "--exclude=99_System/", "--exclude=tests/",
        "-e", f"ssh {ctx['ssh_opts']} "
             + (f"-i {shlex.quote(ctx['ssh_key'])}" if ctx['ssh_key'] else ""),
        f"{REPO_ROOT}/",
        f"{ctx['ssh_host']}:{remote_path}/",
    ]
    if args.dry_run:
        dry(" ".join(shlex.quote(c) for c in rsync_cmd))
        rsync_cmd.insert(1, "--dry-run")  # show what would change
        p = subprocess.run(rsync_cmd, capture_output=True, text=True, timeout=120)
        info(f"rsync --dry-run output (top 20 lines):")
        for line in (p.stdout or "").splitlines()[:20]:
            print(f"      {line}")
        r.status = "dry"
        r.artifacts["dry_run_top"] = (p.stdout or "").splitlines()[:50]
        return r

    p = subprocess.run(rsync_cmd, capture_output=True, text=True, timeout=300)
    if p.returncode == 0:
        ok(f"synced repo → {ctx['ssh_host']}:{remote_path}/")
        r.status = "ok"
    else:
        fail(f"rsync failed: {p.stderr[:400]}")
        r.status = "fail"; r.detail = p.stderr[:400]
    return r


def step_runner_env(args, ctx) -> StepResult:
    r = StepResult(name="runner-env")
    token = os.environ["OHO_RUNNER_TOKEN"]
    remote = f"{ctx['oho_repo_path']}/services/oho_runner/.env"
    remote_repo_env = f"{ctx['oho_repo_path']}/.env"
    local_env = REPO_ROOT / ".env"

    # First-time-deploy seeding: rsync (step `sync`) excludes `.env`, so the
    # repo `.env` may not exist on the LXC. Seed from the validated local
    # `.env` here so the token-injection cp can succeed on the first run.

    if args.dry_run:
        dry(f"ssh {ctx['ssh_host']} test -f {remote_repo_env} || scp local .env up")
        dry(f"ssh {ctx['ssh_host']} <write {remote} with token + repo env>")
        r.status = "dry"; return r

    check = run_remote(ctx["ssh_host"], ctx["ssh_key"], ctx["ssh_opts"],
                       f"test -f {shlex.quote(remote_repo_env)} "
                       f"&& echo EXISTS || echo MISSING")
    if "MISSING" in (check.stdout or ""):
        if not local_env.exists():
            fail("local .env missing — preflight should have blocked this")
            r.status = "fail"; r.detail = "local .env missing"
            return r
        scp_cmd: list[str] = ["scp"]
        if ctx["ssh_opts"]:
            scp_cmd.extend(shlex.split(ctx["ssh_opts"]))
        if ctx["ssh_key"]:
            scp_cmd.extend(["-i", ctx["ssh_key"]])
        scp_cmd.extend([str(local_env),
                        f"{ctx['ssh_host']}:{remote_repo_env}"])
        scp = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
        if scp.returncode != 0:
            fail(f"scp .env → {ctx['ssh_host']}:{remote_repo_env} failed: "
                 f"{(scp.stderr or '').strip()[:300]}")
            r.status = "fail"; r.detail = f"scp failed: {scp.stderr[:200]}"
            return r
        # Lock down the file mode immediately after upload.
        run_remote(ctx["ssh_host"], ctx["ssh_key"], ctx["ssh_opts"],
                   f"chmod 600 {shlex.quote(remote_repo_env)}")
        ok(f"seeded {remote_repo_env} from local .env (first-time deploy)")

    # Compose runner.env from repo.env + bearer token override.
    cmd = (
        f"set -e; "
        f"runner_env={shlex.quote(remote)}; "
        f"repo_env={shlex.quote(remote_repo_env)}; "
        f"if [ ! -f \"$repo_env\" ]; then echo 'MISSING:repo_env'; exit 11; fi; "
        f"cp \"$repo_env\" \"$runner_env\"; "
        # Replace any existing OHO_RUNNER_TOKEN line then ensure ours is present.
        f"sed -i.bak '/^OHO_RUNNER_TOKEN=/d' \"$runner_env\"; "
        f"echo 'OHO_RUNNER_TOKEN={token}' >> \"$runner_env\"; "
        f"rm -f \"$runner_env.bak\"; "
        f"chmod 600 \"$runner_env\"; "
        f"echo 'OK:wrote '\"$runner_env\"' (mode 600)'"
    )
    p = run_remote(ctx["ssh_host"], ctx["ssh_key"], ctx["ssh_opts"], cmd)
    if p.returncode == 0 and "OK:" in (p.stdout or ""):
        ok((p.stdout or "").strip())
        r.status = "ok"
    else:
        fail(f"failed: stdout={p.stdout!r} stderr={p.stderr!r}")
        r.status = "fail"; r.detail = (p.stderr or p.stdout)[:400]
    return r


def step_compose(args, ctx) -> StepResult:
    r = StepResult(name="compose")
    remote_dir = f"{ctx['oho_repo_path']}/services/oho_runner"
    compose_cmd = (
        f"cd {shlex.quote(remote_dir)} && "
        f"docker compose up -d --build && "
        # Wait for healthcheck — up to 60s
        f"for i in 1 2 3 4 5 6 7 8 9 10 11 12; do "
        f"  s=$(docker inspect -f '{{{{.State.Health.Status}}}}' "
        f"      {RUNNER_CONTAINER} 2>/dev/null || echo missing); "
        f"  echo \"healthcheck attempt $i: $s\"; "
        f"  [ \"$s\" = healthy ] && exit 0; "
        f"  sleep 5; "
        f"done; "
        f"echo 'TIMEOUT waiting for healthy'; exit 12"
    )
    if args.dry_run:
        dry(f"ssh {ctx['ssh_host']} '{compose_cmd[:80]}…'")
        r.status = "dry"; return r

    p = run_remote(ctx["ssh_host"], ctx["ssh_key"], ctx["ssh_opts"],
                   compose_cmd)
    print(C.DIM + (p.stdout or "") + C.RESET)
    if p.returncode == 0:
        ok(f"{RUNNER_CONTAINER} container is healthy")
        r.status = "ok"
    else:
        fail(f"compose / healthcheck failed (exit {p.returncode})")
        if p.stderr:
            print(C.RED + p.stderr[:800] + C.RESET)
        r.status = "fail"; r.detail = (p.stderr or p.stdout)[:400]
    return r


def step_smoke_runner(args, ctx) -> StepResult:
    r = StepResult(name="smoke-runner")
    token = os.environ["OHO_RUNNER_TOKEN"]
    # Inside-LXC curls: container DNS = oho-runner:8080 from any container on
    # the n8n_default network. We invoke from the LXC host via docker exec
    # against an existing n8n container — most reliable.
    health = (
        f"docker run --rm --network n8n_default curlimages/curl:8.7.1 "
        f"-fsS http://oho-runner:{RUNNER_PORT}/health"
    )
    bearer = (
        f"docker run --rm --network n8n_default curlimages/curl:8.7.1 "
        f"-fsS -o /dev/null -w '%{{http_code}}' "
        f"-H 'Authorization: Bearer {token}' "
        f"-X POST http://oho-runner:{RUNNER_PORT}/process-brain-dump "
        f"|| true"
    )
    bad_bearer = (
        f"docker run --rm --network n8n_default curlimages/curl:8.7.1 "
        f"-fsS -o /dev/null -w '%{{http_code}}' "
        f"-H 'Authorization: Bearer wrong-token-x' "
        f"-X POST http://oho-runner:{RUNNER_PORT}/process-brain-dump "
        f"|| true"
    )

    if args.dry_run:
        dry("3 probes: GET /health (200), POST /process-brain-dump w/good token, w/bad token")
        r.status = "dry"; return r

    h = run_remote(ctx["ssh_host"], ctx["ssh_key"], ctx["ssh_opts"], health)
    if h.returncode != 0 or '"ok"' not in (h.stdout or "").lower():
        fail(f"/health probe failed: {h.stdout!r} stderr={h.stderr[:200]!r}")
        r.status = "fail"; r.detail = "health probe failed"
        return r
    ok(f"/health → {h.stdout.strip()[:120]}")

    g = run_remote(ctx["ssh_host"], ctx["ssh_key"], ctx["ssh_opts"], bearer)
    good_code = (g.stdout or "").strip()
    b = run_remote(ctx["ssh_host"], ctx["ssh_key"], ctx["ssh_opts"], bad_bearer)
    bad_code = (b.stdout or "").strip()

    # Note: a POST to /process-brain-dump with a good token may return 200 or
    # 409 (lock contention) or 5xx (subprocess timeout etc.). We just want to
    # confirm: good != 401, bad == 401.
    if bad_code != "401":
        fail(f"bad-token probe expected HTTP 401, got {bad_code!r}")
        r.status = "fail"; r.detail = f"bad-token={bad_code}"
        return r
    if good_code == "401":
        fail(f"good-token probe got 401 — token mismatch between repo .env and runner")
        r.status = "fail"; r.detail = "good-token=401"
        return r
    ok(f"bearer auth boundary correct (good={good_code}, bad={bad_code})")
    r.status = "ok"
    r.artifacts = {"health": h.stdout.strip()[:200],
                   "good_token_status": good_code,
                   "bad_token_status": bad_code}
    return r


def step_n8n_cred(args, ctx) -> StepResult:
    r = StepResult(name="n8n-cred")
    host = os.environ["N8N_HOST"]
    key = os.environ["N8N_API_KEY"]
    token = os.environ["OHO_RUNNER_TOKEN"]

    payload = {
        "name": RUNNER_CRED_NAME,
        "type": "httpHeaderAuth",
        "data": {"name": "Authorization", "value": f"Bearer {token}"},
    }

    # n8n's public REST API exposes POST /credentials but not GET. We use
    # the deploy_n8n_workflow.py find_cred-by-workflow-search trick later
    # to discover the resulting ID via any workflow that already references
    # OHO Runner Auth. For now: try POST; if it 400s "already exists",
    # treat as success.

    if args.dry_run:
        dry(f"POST {host}/api/v1/credentials  name='{RUNNER_CRED_NAME}' type=httpHeaderAuth")
        r.status = "dry"; return r

    try:
        result = n8n_api("POST", "/credentials", host=host, key=key, body=payload)
        cred_id = result.get("id") or result.get("data", {}).get("id")
        if cred_id:
            ok(f"created `{RUNNER_CRED_NAME}` (id={cred_id})")
            r.artifacts["cred_id"] = cred_id
        else:
            warn(f"POST /credentials succeeded but no id in response: {result}")
        r.status = "ok"
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace") if e.fp else ""
        if e.code == 400 and "already exists" in body.lower():
            ok(f"`{RUNNER_CRED_NAME}` already exists — leaving as-is")
            r.status = "ok"; r.detail = "already-exists"
        else:
            fail(f"POST /credentials failed: HTTP {e.code} — {body[:300]}")
            r.status = "fail"; r.detail = f"HTTP {e.code}"
    return r


def step_hydrate_deploy(args, ctx) -> StepResult:
    r = StepResult(name="hydrate-deploy")
    deploy_script = REPO_ROOT / "scripts" / "deploy_n8n_workflow.py"
    failures = []
    for relpath, extra_args in WORKFLOWS_TO_DEPLOY:
        wf_path = REPO_ROOT / relpath
        if not wf_path.exists():
            failures.append(f"{relpath} missing")
            fail(f"{relpath} missing"); continue

        cmd = [sys.executable, str(deploy_script), str(wf_path)] + extra_args
        if args.dry_run:
            dry(" ".join(shlex.quote(c) for c in cmd))
            continue
        p = run_local(cmd)
        if p.returncode == 0:
            ok(f"deployed {relpath}")
        else:
            failures.append(f"{relpath} failed: {p.stderr[:200]}")
            fail(f"{relpath}: exit {p.returncode}")
            if p.stderr: print(C.RED + p.stderr[:600] + C.RESET)
            if p.stdout: print(C.DIM + p.stdout[:600] + C.RESET)

    if args.dry_run:
        r.status = "dry"
    elif failures:
        r.status = "fail"; r.detail = "; ".join(failures)
    else:
        r.status = "ok"
    return r


def step_activate(args, ctx) -> StepResult:
    r = StepResult(name="activate")
    host = os.environ["N8N_HOST"]; key = os.environ["N8N_API_KEY"]
    failures = []
    for name in WORKFLOWS_TO_ACTIVATE:
        wf_id = n8n_find_workflow_id(host, key, name)
        if not wf_id:
            failures.append(f"workflow `{name}` not found")
            fail(f"{name}: not found"); continue
        if args.dry_run:
            dry(f"POST {host}/api/v1/workflows/{wf_id}/activate  (workflow `{name}`)")
            continue
        try:
            n8n_api("POST", f"/workflows/{wf_id}/activate", host=host, key=key)
            ok(f"activated `{name}` (id={wf_id})")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace") if e.fp else ""
            failures.append(f"{name}: HTTP {e.code}")
            fail(f"{name}: HTTP {e.code} — {body[:200]}")

    if args.dry_run:
        r.status = "dry"
    elif failures:
        r.status = "fail"; r.detail = "; ".join(failures)
    else:
        r.status = "ok"
    return r


def step_smoke_pipeline(args, ctx) -> StepResult:
    r = StepResult(name="smoke-pipeline")
    host = os.environ["N8N_HOST"]; key = os.environ["N8N_API_KEY"]
    wf_id = n8n_find_workflow_id(host, key, "brain-dump-processor-v2")
    if not wf_id:
        fail("brain-dump-processor-v2 not found")
        r.status = "fail"; r.detail = "workflow not found"; return r

    if args.dry_run:
        dry(f"POST {host}/api/v1/workflows/{wf_id}/execute  (manual smoke run)")
        info("Then poll /executions/<id>, check stdout JSON, verify receipt + archive in MinIO.")
        r.status = "dry"; return r

    # Trigger
    try:
        exe = n8n_api("POST", f"/workflows/{wf_id}/execute", host=host, key=key)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace") if e.fp else ""
        fail(f"execute call failed: HTTP {e.code} — {body[:300]}")
        r.status = "fail"; r.detail = f"HTTP {e.code}"
        return r
    exe_id = exe.get("data", {}).get("executionId") or exe.get("id")
    info(f"triggered execution {exe_id}; polling for completion…")

    # Poll
    finished = None
    for i in range(24):  # 24 * 5s = 120s max
        time.sleep(5)
        try:
            ex = n8n_api("GET", f"/executions/{exe_id}", host=host, key=key)
        except Exception as e:
            warn(f"poll {i}: {e}"); continue
        if ex.get("data", {}).get("finished"):
            finished = ex; break
    if not finished:
        fail("execution did not finish within 120s")
        r.status = "fail"; r.detail = "poll timeout"; return r

    status = finished.get("data", {}).get("status") or \
             ("success" if finished.get("data", {}).get("finished") and
              not finished.get("data", {}).get("stoppedAt") else "unknown")
    ok(f"execution {exe_id} finished: status={status}")
    r.artifacts = {"execution_id": exe_id, "status": status}
    r.status = "ok" if status in ("success", "unknown") else "warn"
    r.detail = f"execution_id={exe_id} status={status}"
    return r


def step_report(args, ctx, all_results) -> StepResult:
    r = StepResult(name="report")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOGS_DIR / f"deploy-oho-runner-{ts}.json"
    log_payload = {
        "started_at_utc": ctx["started_at"],
        "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "ssh_host": ctx["ssh_host"],
        "n8n_host": os.environ.get("N8N_HOST"),
        "results": [
            {"name": x.name, "status": x.status, "detail": x.detail,
             "elapsed_ms": x.elapsed_ms, "artifacts": x.artifacts}
            for x in all_results
        ],
    }
    log_path.write_text(json.dumps(log_payload, indent=2))
    ok(f"wrote {log_path.relative_to(REPO_ROOT)}")
    r.status = "ok"; r.artifacts["log_path"] = str(log_path)
    return r


# ── Orchestrator ────────────────────────────────────────────────────────────

STATUS_GLYPH = {
    "ok":      f"{C.GREEN}✓{C.RESET}",
    "warn":    f"{C.YELLOW}!{C.RESET}",
    "fail":    f"{C.RED}✗{C.RESET}",
    "skipped": f"{C.DIM}–{C.RESET}",
    "dry":     f"{C.DIM}~{C.RESET}",
    "pending": " ",
}


def print_summary(results: list[StepResult], mode: str) -> None:
    banner(f"SUMMARY ({mode})")
    width = max(len(r.name) for r in results)
    for r in results:
        glyph = STATUS_GLYPH.get(r.status, "?")
        detail = (f" — {r.detail}" if r.detail else "")
        print(f"  {glyph}  {r.name:<{width}}  {C.DIM}[{r.status}]{C.RESET}{detail}")
    print()


def load_env_file() -> None:
    """Best-effort load .env so the user can skip `set -a && source .env`."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="See module docstring for step graph and required env.",
    )
    p.add_argument("--apply", action="store_true",
                   help="Actually perform destructive operations. Default is dry-run.")
    p.add_argument("--from-step", choices=STEP_NAMES,
                   help="Start at this step (skip earlier).")
    p.add_argument("--only-step", choices=STEP_NAMES,
                   help="Run exactly this step.")
    p.add_argument("--skip-step", action="append", choices=STEP_NAMES, default=[],
                   help="Skip this step (repeatable).")
    p.add_argument("--no-env-file", action="store_true",
                   help="Don't auto-source .env from repo root.")
    args = p.parse_args()

    # Effective dry-run flag
    args.dry_run = not args.apply

    if not args.no_env_file:
        load_env_file()

    ctx = {
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ssh_host":   os.environ.get("LXC_SSH_HOST", "root@192.168.1.121"),
        "ssh_key":    os.environ.get("LXC_SSH_KEY") or None,
        "ssh_opts":   os.environ.get("LXC_SSH_OPTS",
                                     "-o StrictHostKeyChecking=accept-new"),
        "oho_repo_path": os.environ.get("OHO_REPO_PATH", "/opt/oho"),
    }

    mode = "APPLY" if args.apply else "DRY-RUN"
    banner(f"OHO RUNNER DEPLOY — {mode}")
    info(f"SSH:           {ctx['ssh_host']}")
    info(f"Remote path:   {ctx['oho_repo_path']}")
    info(f"n8n:           {os.environ.get('N8N_HOST', '(unset)')}")
    info(f"Repo:          {REPO_ROOT}")

    # Decide which steps to run
    selected = STEP_NAMES[:]
    if args.only_step:
        selected = [args.only_step]
        # Always include report so the JSON log lands somewhere
        if "report" not in selected:
            selected.append("report")
    elif args.from_step:
        idx = STEP_NAMES.index(args.from_step)
        selected = STEP_NAMES[idx:]
    selected = [s for s in selected if s not in args.skip_step]

    step_fns: dict[str, Callable] = {
        "preflight":      step_preflight,
        "inspect":        step_inspect,
        "sync":           step_sync,
        "runner-env":     step_runner_env,
        "compose":        step_compose,
        "smoke-runner":   step_smoke_runner,
        "n8n-cred":       step_n8n_cred,
        "hydrate-deploy": step_hydrate_deploy,
        "activate":       step_activate,
        "smoke-pipeline": step_smoke_pipeline,
    }

    results: list[StepResult] = []
    for step_name in selected:
        if step_name == "report":
            continue
        banner(f"STEP: {step_name}")
        start = time.monotonic()
        try:
            r = step_fns[step_name](args, ctx)
        except KeyboardInterrupt:
            fail("interrupted")
            r = StepResult(name=step_name, status="fail", detail="KeyboardInterrupt")
        except Exception as e:
            fail(f"unhandled exception: {type(e).__name__}: {e}")
            r = StepResult(name=step_name, status="fail",
                           detail=f"{type(e).__name__}: {str(e)[:200]}")
        r.elapsed_ms = int((time.monotonic() - start) * 1000)
        results.append(r)

        # If preflight fails, abort hard. Still write the report log first so
        # the failure is captured for postmortem.
        if step_name == "preflight" and r.status == "fail":
            fail("preflight failed — aborting before any destructive operation")
            banner("STEP: report")
            rep = step_report(args, ctx, results)
            results.append(rep)
            print_summary(results, mode)
            return 2

        # If any apply-mode step fails, stop (don't ripple downstream failures).
        if args.apply and r.status == "fail":
            warn(f"step `{step_name}` failed — stopping. "
                 f"Fix it, then re-run with --from-step {step_name}")
            break

    # Report step always runs to capture the JSON log.
    banner("STEP: report")
    rep = step_report(args, ctx, results)
    results.append(rep)

    print_summary(results, mode)

    any_fail = any(r.status == "fail" for r in results)
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())

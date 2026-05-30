"""OHO Runner — dedicated HTTP service for OHO Python tools.

Endpoints
---------
GET  /health               — unauthenticated; minimal liveness only.
GET  /health/jobs          — bearer auth; verbose per-job diagnostics (command
                             tuples, script presence, workdir + python paths).
POST /process-brain-dump   — bearer auth; runs ``python3 -u tools/process_brain_dump.py``.
POST /build-command-center — bearer auth; runs ``python3 -u tools/build_command_center.py``
                             (ADR-0006 — daily command center generator).
POST /audit-receipts       — bearer auth; runs ``python3 -u scripts/audit_extraction_receipts.py
                             --json-output`` (NEXT-STEPS item 10 — replaces
                             vault-health-report's dropped ``executeCommand`` path).

All POST endpoints execute in /opt/oho with env loaded from /opt/oho/.env.

Hardening
---------
* No arbitrary command parameter — the per-job command tuples are hard-coded
  at import time in ``JOBS`` and cannot be influenced by request input.
* Bearer token comparison via ``hmac.compare_digest`` (constant-time).
* Single concurrent run guarded by an ``asyncio.Lock``; concurrent calls get 409.
  This serialises ALL jobs (including across endpoints) — by design, since
  concurrent jobs would compete for the same MinIO + tooling resources.
* Subprocess timeout (default 180s); exceeding it returns exit_code=-9.
* Subprocess uses an argv tuple (not a shell string) — no shell expansion path.
* Unauthenticated ``/health`` is minimal liveness only — no workdir/python paths,
  no command tuples, no job names. Those are recon for the authed POST endpoints
  and now live behind bearer auth at ``/health/jobs`` (deepsec other-info-disclosure,
  2026-05-30).
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import sys
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException

WORKDIR = os.environ.get("OHO_RUNNER_WORKDIR", "/opt/oho")
PYTHON = sys.executable
TIMEOUT_SEC = int(os.environ.get("OHO_RUNNER_TIMEOUT", "180"))
TOKEN = os.environ.get("OHO_RUNNER_TOKEN", "")

# Hard-coded job dispatch table. Each key is the URL path suffix (and FastAPI
# route); each value is the argv tuple executed in WORKDIR. To add a new job:
# add a new entry here AND add an explicit @app.post handler below — never
# accept a job name from the request body.
JOBS: dict[str, tuple[str, ...]] = {
    "process-brain-dump":   (PYTHON, "-u", "tools/process_brain_dump.py"),
    "build-command-center": (PYTHON, "-u", "tools/build_command_center.py"),
    "audit-receipts":       (PYTHON, "-u", "scripts/audit_extraction_receipts.py",
                             "--json-output"),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("oho-runner")

app = FastAPI(title="OHO Runner", version="1.1")
_run_lock = asyncio.Lock()


def _load_env_file(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1]
                env[k.strip()] = v
    except FileNotFoundError:
        pass
    return env


def _check_auth(authorization: str | None) -> None:
    if not TOKEN:
        raise HTTPException(status_code=503, detail="server token not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    expected = f"Bearer {TOKEN}".encode("utf-8")
    actual = authorization.encode("utf-8")
    if len(actual) != len(expected) or not hmac.compare_digest(expected, actual):
        raise HTTPException(status_code=401, detail="invalid token")


@app.get("/health")
async def health() -> dict[str, Any]:
    # Unauthenticated liveness ONLY. Deliberately minimal — no workdir/python
    # paths, no per-job command tuples or job names. Those are recon for the
    # authenticated POST endpoints; verbose diagnostics moved to bearer-auth
    # /health/jobs (deepsec other-info-disclosure, 2026-05-30). The aggregate
    # all_scripts_present preserves the "is this deploy intact" signal without
    # leaking names or paths.
    env_path = os.path.join(WORKDIR, ".env")
    all_scripts_present = all(
        os.path.isfile(os.path.join(WORKDIR, cmd[2]))
        for cmd in JOBS.values()
        if len(cmd) >= 3
    )
    return {
        "status": "ok",
        "service": "oho-runner",
        "version": app.version,
        "workdir_exists": os.path.isdir(WORKDIR),
        "env_present": os.path.isfile(env_path),
        "all_scripts_present": all_scripts_present,
        "lock_held": _run_lock.locked(),
        "timeout_sec": TIMEOUT_SEC,
        "token_configured": bool(TOKEN),
    }


@app.get("/health/jobs")
async def health_jobs(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Verbose per-job diagnostics — bearer auth only (recon-sensitive: exposes
    command tuples, script presence, and the workdir + python paths)."""
    _check_auth(authorization)
    job_status = {}
    for job_name, cmd in JOBS.items():
        # cmd[2] is the script path relative to WORKDIR.
        script = os.path.join(WORKDIR, cmd[2]) if len(cmd) >= 3 else None
        job_status[job_name] = {
            "command": list(cmd),
            "script_present": bool(script and os.path.isfile(script)),
        }
    return {
        "workdir": WORKDIR,
        "python": PYTHON,
        "jobs": job_status,
    }


async def _dispatch(job_key: str, authorization: str | None) -> dict[str, Any]:
    _check_auth(authorization)
    if job_key not in JOBS:
        # Defensive: only reachable if the dispatch table and route table drift.
        raise HTTPException(status_code=404, detail=f"unknown job: {job_key}")
    if _run_lock.locked():
        raise HTTPException(status_code=409, detail="another run is in progress")
    async with _run_lock:
        return await _run(JOBS[job_key])


@app.post("/process-brain-dump")
async def process_brain_dump(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await _dispatch("process-brain-dump", authorization)


@app.post("/build-command-center")
async def build_command_center(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await _dispatch("build-command-center", authorization)


@app.post("/audit-receipts")
async def audit_receipts(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Replace vault-health-report's ``executeCommand`` regression (NEXT-STEPS
    item 10). Runs the same receipt audit n8n used to invoke directly via the
    n8n-1.x `executeCommand` node, which the n8n 2.x active-workflow
    registry dropped. Workflow side switches from `executeCommand` to
    `httpRequest` against this endpoint."""
    return await _dispatch("audit-receipts", authorization)


async def _run(command: tuple[str, ...]) -> dict[str, Any]:
    started = time.monotonic()
    env = os.environ.copy()
    env.update(_load_env_file(os.path.join(WORKDIR, ".env")))
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")

    log.info("running %s in %s (timeout=%ss)", command, WORKDIR, TIMEOUT_SEC)
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=WORKDIR,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        log.exception("could not spawn subprocess")
        raise HTTPException(status_code=500, detail=f"spawn failed: {e}")

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SEC)
    except asyncio.TimeoutError:
        log.warning("subprocess timed out after %ss; killing", TIMEOUT_SEC)
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        return {
            "exit_code": -9,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "stdout_json": None,
            "stdout_raw": "",
            "stderr_tail": f"<timed out after {TIMEOUT_SEC}s>",
            "timed_out": True,
        }

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")

    parsed: Any | None = None
    try:
        parsed = json.loads(stdout)
    except (ValueError, json.JSONDecodeError):
        parsed = None

    log.info(
        "done exit=%s duration=%dms stdout_bytes=%d stderr_bytes=%d parsed=%s",
        proc.returncode, duration_ms, len(stdout_b), len(stderr_b), parsed is not None,
    )

    return {
        "exit_code": proc.returncode,
        "duration_ms": duration_ms,
        "stdout_json": parsed,
        "stdout_raw": stdout if parsed is None else None,
        "stderr_tail": stderr[-4000:],
        "timed_out": False,
    }

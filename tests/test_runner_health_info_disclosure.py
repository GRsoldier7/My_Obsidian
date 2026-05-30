"""Regression: unauthenticated /health must not leak runner recon.

deepsec finding `other-info-disclosure` (2026-05-30): the unauthenticated
/health endpoint disclosed workdir + python paths and the exact command
tuples / script presence for every privileged job — useful recon for
attacking the authenticated POST endpoints. The verbose diagnostics moved
behind bearer auth at /health/jobs; /health is now minimal liveness only.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

RUNNER_DIR = Path(__file__).resolve().parents[1] / "services" / "oho_runner"

# Fields that must NEVER appear in the unauthenticated /health body — they are
# recon for the authenticated command-runner endpoints.
RECON_KEYS = {"workdir", "python", "jobs", "command", "script_present"}

TOKEN = "test-token-deadbeef"


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("OHO_RUNNER_TOKEN", TOKEN)
    sys.path.insert(0, str(RUNNER_DIR))
    try:
        app_mod = importlib.import_module("app")
        app_mod = importlib.reload(app_mod)  # pick up the patched TOKEN env
        yield TestClient(app_mod.app)
    finally:
        sys.path.remove(str(RUNNER_DIR))
        sys.modules.pop("app", None)


def test_health_is_unauthenticated_and_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "oho-runner"
    # liveness signals preserved
    for key in ("token_configured", "all_scripts_present", "lock_held", "env_present"):
        assert key in body


def test_health_leaks_no_recon_fields(client):
    body = client.get("/health").json()
    leaked = RECON_KEYS & set(body)
    assert not leaked, f"/health leaked recon fields: {leaked}"
    # And no value in the body should expose a command tuple or absolute path.
    serialized = str(body)
    assert "tools/process_brain_dump.py" not in serialized
    assert "/opt/oho" not in serialized


def test_health_jobs_requires_auth(client):
    assert client.get("/health/jobs").status_code == 401
    assert client.get(
        "/health/jobs", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401


def test_health_jobs_returns_detail_when_authed(client):
    r = client.get("/health/jobs", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    body = r.json()
    assert "jobs" in body and "workdir" in body
    assert "process-brain-dump" in body["jobs"]
    assert body["jobs"]["process-brain-dump"]["command"][-1].endswith(
        "process_brain_dump.py"
    )

"""
Phase 4 of ADR-0006 — verify the command-center build is wired into
live-dashboard-updater via the OHO runner sidecar (NOT via executeCommand,
which n8n 2.x rejects at activation time per ADR-0005's revision).

These tests lock the contract so a future edit can't accidentally:
  - drop the httpRequest node,
  - point it at the wrong runner endpoint,
  - forget continueOnFail (a command-center failure must not poison the
    primary Live Dashboard write),
  - swap to executeCommand (would brick activation),
  - share an extra cron slot (already locked by the existing slot test, but
    we re-assert the workflow stays at exactly one cron).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / "workflows" / "n8n" / "live-dashboard-updater.json"
RUNNER_APP_PATH = REPO_ROOT / "services" / "oho_runner" / "app.py"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _node(workflow: dict, name: str) -> dict | None:
    for n in workflow.get("nodes", []):
        if n.get("name") == name:
            return n
    return None


# ── Workflow JSON contract ──────────────────────────────────────────────────


def test_command_center_node_exists_and_uses_http_request(workflow):
    node = _node(workflow, "Run: build_command_center.py (via OHO runner)")
    assert node is not None, (
        "live-dashboard-updater is missing the command-center build node "
        "(ADR-0006 Phase 4)"
    )
    assert node.get("type") == "n8n-nodes-base.httpRequest", (
        "command-center build must use httpRequest (NOT executeCommand — "
        "n8n 2.x rejects executeCommand at activation; see ADR-0005 revision)"
    )


def test_command_center_node_targets_correct_runner_endpoint(workflow):
    node = _node(workflow, "Run: build_command_center.py (via OHO runner)")
    params = node.get("parameters", {})
    assert params.get("method") == "POST"
    assert params.get("url") == "http://oho-runner:8080/build-command-center"
    assert params.get("authentication") == "genericCredentialType"
    assert params.get("genericAuthType") == "httpHeaderAuth"
    # Must NOT send a body — runner ignores it; surface area minimization.
    assert params.get("sendBody") is False


def test_command_center_node_uses_runner_credential_placeholder(workflow):
    node = _node(workflow, "Run: build_command_center.py (via OHO runner)")
    creds = node.get("credentials", {}).get("httpHeaderAuth", {})
    assert creds.get("id") == "__OHO_RUNNER_CRED_ID__", (
        "must use the same placeholder as brain-dump-processor-v2 so "
        "setup-n8n.sh hydrates a single shared credential"
    )
    assert creds.get("name") == "OHO Runner Auth"


def test_command_center_node_continues_on_fail(workflow):
    """A command-center build failure must NOT poison the primary Live
    Dashboard write that already succeeded earlier in the chain."""
    node = _node(workflow, "Run: build_command_center.py (via OHO runner)")
    assert node.get("continueOnFail") is True


def test_command_center_node_has_retry_and_timeout(workflow):
    node = _node(workflow, "Run: build_command_center.py (via OHO runner)")
    assert node.get("retryOnFail") is True
    assert node.get("maxTries") == 3
    assert node.get("waitBetweenTries") == 5000
    timeout = node.get("parameters", {}).get("options", {}).get("timeout")
    assert isinstance(timeout, int) and 30000 <= timeout <= 120000, (
        f"timeout {timeout}ms outside 30-120s range; build_command_center.py "
        "is light I/O — anything longer suggests something else is wrong"
    )


def test_command_center_node_runs_after_dashboard_write(workflow):
    """Wiring lock: S3: Write Dashboard → Run: build_command_center.py.
    Order matters — Live Dashboard is the primary surface and must be
    durable before we touch the command center.
    """
    conns = workflow.get("connections", {})
    write_branches = conns.get("S3: Write Dashboard", {}).get("main", [])
    assert write_branches, (
        "S3: Write Dashboard has no outgoing connection — command-center "
        "node is unwired"
    )
    targets = [c.get("node") for c in (write_branches[0] or [])]
    assert "Run: build_command_center.py (via OHO runner)" in targets


def test_live_dashboard_updater_still_has_exactly_one_schedule_trigger(workflow):
    """No new cron slot was introduced — same :03 hourly slot is reused."""
    triggers = [
        n for n in workflow.get("nodes", [])
        if n.get("type") == "n8n-nodes-base.scheduleTrigger"
    ]
    assert len(triggers) == 1
    expr = triggers[0]["parameters"]["rule"]["interval"][0]["expression"]
    assert expr == "3 * * * *", f"cron drifted from :03 hourly to {expr!r}"


def test_no_execute_command_node_introduced(workflow):
    """Belt-and-suspenders: same regression guard the brain-dump processor
    has. n8n 2.x can't activate executeCommand."""
    bad = [
        n.get("name") for n in workflow.get("nodes", [])
        if n.get("type") == "n8n-nodes-base.executeCommand"
    ]
    assert not bad, (
        f"executeCommand reintroduced into live-dashboard-updater: {bad!r}. "
        f"Use httpRequest → oho-runner instead (ADR-0005 revision)."
    )


# ── Runner-side structural lock (text-based; fastapi not in test env) ───────


def test_runner_app_declares_build_command_center_job():
    """The workflow targets /build-command-center; the runner must register
    a matching POST handler AND have the command in its hard-coded JOBS map.
    """
    src = RUNNER_APP_PATH.read_text(encoding="utf-8")
    # Hard-coded job entry — pinned by string match; refactors that change
    # the literal must update this test deliberately.
    assert '"build-command-center"' in src, (
        "services/oho_runner/app.py JOBS map missing 'build-command-center' "
        "entry — workflow will get 404 at runtime"
    )
    assert 'tools/build_command_center.py' in src, (
        "JOBS entry for build-command-center must point at "
        "tools/build_command_center.py"
    )
    # Route registered.
    assert '@app.post("/build-command-center")' in src, (
        "FastAPI POST route /build-command-center missing in app.py"
    )


def test_runner_app_keeps_brain_dump_endpoint():
    """Brain-dump endpoint must keep working — refactor must not regress it."""
    src = RUNNER_APP_PATH.read_text(encoding="utf-8")
    assert '"process-brain-dump"' in src
    assert '@app.post("/process-brain-dump")' in src
    assert 'tools/process_brain_dump.py' in src


def test_runner_uses_shared_lock_for_dispatch():
    """Both endpoints must serialize through the same _run_lock so concurrent
    jobs can't race on MinIO. Ensures the refactor preserved this property.
    """
    src = RUNNER_APP_PATH.read_text(encoding="utf-8")
    # One module-level lock, used in dispatch.
    assert "_run_lock = asyncio.Lock()" in src
    assert "if _run_lock.locked():" in src
    assert "async with _run_lock:" in src


def test_runner_dispatch_validates_job_name_against_dispatch_table():
    """Defensive guard: the dispatcher must verify the job key is in JOBS
    before running, so a route/dispatch-table drift can't execute a
    non-listed command."""
    src = RUNNER_APP_PATH.read_text(encoding="utf-8")
    assert "if job_key not in JOBS:" in src

"""Static smoke tests for scripts/deploy_oho_runner.py.

We can't exercise the network paths in unit tests (SSH, docker, n8n API),
but we can verify the script's contract: imports cleanly, exposes the
expected step graph, each step name has a handler, --help works.
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "deploy_oho_runner.py"


@pytest.fixture(scope="module")
def deploy_module():
    spec = importlib.util.spec_from_file_location("deploy_oho_runner", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses needs the module registered in sys.modules to resolve
    # string-form type annotations like `dict | None`.
    sys.modules["deploy_oho_runner"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop("deploy_oho_runner", None)
        raise
    return mod


def test_script_exists_and_is_executable():
    assert SCRIPT_PATH.exists()
    assert SCRIPT_PATH.stat().st_mode & 0o111, "script must be executable"


def test_help_flag_works():
    p = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert p.returncode == 0
    assert "end-to-end deploy orchestrator" in p.stdout
    assert "--apply" in p.stdout
    assert "--from-step" in p.stdout


def test_step_names_match_handlers(deploy_module):
    """Every step in STEP_NAMES (except `report`) must have a handler in the
    dispatch table. `report` is invoked unconditionally outside the loop."""
    expected_handlers = set(deploy_module.STEP_NAMES) - {"report"}
    # Build the dispatch dict the same way main() does — but extract it
    # without running main(). The dict literal lives inside main(), so we
    # smoke-test by checking each expected name has a top-level `step_<name>`
    # function defined.
    for name in expected_handlers:
        fn_name = "step_" + name.replace("-", "_")
        assert hasattr(deploy_module, fn_name), \
            f"missing handler function `{fn_name}` for step `{name}`"


def test_required_env_list_includes_runner_token(deploy_module):
    """Preflight must demand OHO_RUNNER_TOKEN — that's the load-bearing new
    variable this whole deploy depends on. Surface it as a regression test
    so a future refactor doesn't quietly drop the check."""
    src = SCRIPT_PATH.read_text()
    assert "OHO_RUNNER_TOKEN" in src
    # And it must appear inside the preflight function specifically.
    preflight_idx = src.index("def step_preflight")
    next_def_idx = src.index("\ndef ", preflight_idx + 1)
    preflight_body = src[preflight_idx:next_def_idx]
    assert "OHO_RUNNER_TOKEN" in preflight_body


def test_workflows_to_deploy_match_runner_endpoints(deploy_module):
    """The two workflows we deploy must point at the runner endpoints the
    sidecar actually exposes. Drift here means we'd deploy workflows that
    can't reach their runner job."""
    urls = []
    for relpath, extra_args in deploy_module.WORKFLOWS_TO_DEPLOY:
        # Find the --assert-http-url-contains <X> pair in extra_args.
        for i, a in enumerate(extra_args):
            if a == "--assert-http-url-contains" and i + 1 < len(extra_args):
                urls.append(extra_args[i + 1])
    assert "/process-brain-dump" in urls
    assert "/build-command-center" in urls


def test_runner_endpoints_are_declared_in_app_py():
    """Mirror of the above — the runner side must actually expose the
    endpoints the deploy script asserts on."""
    app_py = (REPO_ROOT / "services" / "oho_runner" / "app.py").read_text()
    assert '"process-brain-dump"' in app_py
    assert '"build-command-center"' in app_py
    assert '@app.post("/process-brain-dump")' in app_py
    assert '@app.post("/build-command-center")' in app_py


def test_workflow_lookup_is_emoji_prefix_tolerant(deploy_module, monkeypatch):
    """Live n8n workflows in this stack carry emoji prefixes that diverge
    from the canonical repo template names (memory:
    feedback_n8n_workflow_name_emoji_prefix). Lookup must succeed both for
    exact match and for a single contains-match — and refuse ambiguous
    matches rather than guess."""
    target = "brain-dump-processor-v2"

    def fake_api(method, path, *, host, key, body=None):
        return {"data": [
            {"id": "wf-101", "name": "🧠 brain-dump-processor-v2"},
            {"id": "wf-201", "name": "📰 article-processor"},
        ]}

    monkeypatch.setattr(deploy_module, "n8n_api", fake_api)
    assert deploy_module.n8n_find_workflow_id(
        "http://n8n", "k", target) == "wf-101"


def test_workflow_lookup_prefers_exact_over_fuzzy(deploy_module, monkeypatch):
    """An exact match must win over any number of fuzzy ones."""
    target = "brain-dump-processor-v2"

    def fake_api(method, path, *, host, key, body=None):
        return {"data": [
            {"id": "wf-101", "name": "🧠 brain-dump-processor-v2"},
            {"id": "wf-102", "name": "brain-dump-processor-v2"},  # exact
            {"id": "wf-103", "name": "old-brain-dump-processor-v2-backup"},
        ]}

    monkeypatch.setattr(deploy_module, "n8n_api", fake_api)
    assert deploy_module.n8n_find_workflow_id(
        "http://n8n", "k", target) == "wf-102"


class _FakeBoto3:
    """Inject via sys.modules so the in-function `import boto3` resolves
    to a controllable stub during tests."""

    def __init__(self, versioning_status: str | None = "Enabled",
                 raise_on_call: Exception | None = None):
        self._status = versioning_status
        self._raise = raise_on_call

    def client(self, *args, **kwargs):
        return self

    def get_bucket_versioning(self, *, Bucket):
        if self._raise is not None:
            raise self._raise
        if self._status is None:
            return {}
        return {"Status": self._status}


def test_minio_versioning_enabled_is_ok(deploy_module, monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3("Enabled"))
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "k")
    monkeypatch.setenv("MINIO_SECRET_KEY", "s")
    monkeypatch.setenv("MINIO_BUCKET", "obsidian-vault")
    ok, msg = deploy_module.check_minio_versioning()
    assert ok is True
    assert msg == "Enabled"


def test_minio_versioning_suspended_fails(deploy_module, monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3("Suspended"))
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "k")
    monkeypatch.setenv("MINIO_SECRET_KEY", "s")
    monkeypatch.setenv("MINIO_BUCKET", "obsidian-vault")
    ok, msg = deploy_module.check_minio_versioning()
    assert ok is False
    assert "Suspended" in msg
    assert "mc version enable" in msg


def test_minio_versioning_absent_fails(deploy_module, monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3(None))
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "k")
    monkeypatch.setenv("MINIO_SECRET_KEY", "s")
    monkeypatch.setenv("MINIO_BUCKET", "obsidian-vault")
    ok, msg = deploy_module.check_minio_versioning()
    assert ok is False
    assert "absent" in msg


def test_workflow_lookup_refuses_ambiguous(deploy_module, monkeypatch):
    """Multiple fuzzy hits without an exact must return None so the
    operator disambiguates rather than the script guessing."""
    target = "brain-dump-processor-v2"

    def fake_api(method, path, *, host, key, body=None):
        return {"data": [
            {"id": "wf-101", "name": "🧠 brain-dump-processor-v2"},
            {"id": "wf-102", "name": "old-brain-dump-processor-v2-archive"},
        ]}

    monkeypatch.setattr(deploy_module, "n8n_api", fake_api)
    assert deploy_module.n8n_find_workflow_id(
        "http://n8n", "k", target) is None

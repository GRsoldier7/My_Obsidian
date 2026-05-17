"""Tests for clients/agent_orch_client.py — Phase F skeleton."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from clients import agent_orch_client as aoc  # noqa: E402
from tools import privacy_classifier as pc  # noqa: E402

DATA_CLASSES_YAML = REPO_ROOT / "infra" / "data-classes.yaml"


@pytest.fixture(scope="module")
def ruleset() -> pc.RuleSet:
    return pc.load_ruleset(DATA_CLASSES_YAML)


@pytest.fixture
def client(ruleset) -> aoc.BrokerClient:
    return aoc.BrokerClient(
        base_url="http://100.122.188.108:9001",
        worker_id="oho-runner",
        bearer_token="test-token-32-chars-padding-here",
        classifier_ruleset=ruleset,
    )


# ── Construction guards ──────────────────────────────────────────────────────
def test_constructor_rejects_non_http_url(ruleset):
    with pytest.raises(ValueError):
        aoc.BrokerClient(
            base_url="redis://x:6379",
            worker_id="oho",
            bearer_token="t",
            classifier_ruleset=ruleset,
        )


def test_constructor_requires_bearer_token(ruleset):
    with pytest.raises(ValueError):
        aoc.BrokerClient(
            base_url="http://x:9001",
            worker_id="oho",
            bearer_token="",
            classifier_ruleset=ruleset,
        )


def test_constructor_strips_trailing_slash(ruleset):
    c = aoc.BrokerClient("http://x:9001/", "w", "t", ruleset)
    assert c.base_url == "http://x:9001"


# ── Privacy gate ─────────────────────────────────────────────────────────────
def test_check_egress_returns_verdict(client):
    req = aoc.TaskCreateRequest(text="grocery list: milk", metadata={"area": "home"})
    verdict = client.check_egress(req)
    assert isinstance(verdict, pc.Verdict)


def test_post_task_refused_on_sensitive_area_faith(client):
    """Sensitive [area:: faith] payloads MUST NOT egress to the broker by default."""
    req = aoc.TaskCreateRequest(
        text="Sermon prep notes.",
        metadata={"area": "faith"},
    )
    with pytest.raises(aoc.PrivacyDenial):
        client.post_task(req)


def test_post_task_refused_on_sensitive_area_family(client):
    req = aoc.TaskCreateRequest(text="Family dinner plan.", metadata={"area": "family"})
    with pytest.raises(aoc.PrivacyDenial):
        client.post_task(req)


def test_post_task_refused_on_sensitive_area_health(client):
    req = aoc.TaskCreateRequest(text="Pre-op checklist.", metadata={"area": "health"})
    with pytest.raises(aoc.PrivacyDenial):
        client.post_task(req)


def test_post_task_sensitive_with_explicit_allow_passes_privacy_gate(client):
    """Explicit `allow_egress_to: {'broker'}` lets a sensitive payload through.
    HTTP transport is mocked to avoid a live request."""
    req = aoc.TaskCreateRequest(text="Sermon", metadata={"area": "faith"})
    # The privacy gate now allows; httpx call should fire — mock it
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"task_id": "abc"}
    fake_resp.raise_for_status = MagicMock()
    fake_client_ctx = MagicMock()
    fake_client_ctx.__enter__.return_value.post.return_value = fake_resp
    with patch.object(aoc, "httpx") as mock_httpx:
        mock_httpx.Client.return_value = fake_client_ctx
        out = client.post_task(req, allow_egress_to={"broker"})
    assert out == {"task_id": "abc"}


def test_post_task_public_payload_passes(client):
    """Public payloads always pass the gate."""
    req = aoc.TaskCreateRequest(text="Tip: postgres has generated columns.",
                                metadata={"area": "personal"})
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"task_id": "abc"}
    fake_resp.raise_for_status = MagicMock()
    fake_client_ctx = MagicMock()
    fake_client_ctx.__enter__.return_value.post.return_value = fake_resp
    with patch.object(aoc, "httpx") as mock_httpx:
        mock_httpx.Client.return_value = fake_client_ctx
        out = client.post_task(req)
    assert out == {"task_id": "abc"}


# ── HTTP calls (mocked) ──────────────────────────────────────────────────────
def test_lease_task_204_returns_none(client):
    fake_resp = MagicMock()
    fake_resp.status_code = 204
    fake_client_ctx = MagicMock()
    fake_client_ctx.__enter__.return_value.post.return_value = fake_resp
    with patch.object(aoc, "httpx") as mock_httpx:
        mock_httpx.Client.return_value = fake_client_ctx
        out = client.lease_task()
    assert out is None


def test_lease_task_200_returns_dict(client):
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"task_id": "xyz", "text": "do it"}
    fake_resp.raise_for_status = MagicMock()
    fake_client_ctx = MagicMock()
    fake_client_ctx.__enter__.return_value.post.return_value = fake_resp
    with patch.object(aoc, "httpx") as mock_httpx:
        mock_httpx.Client.return_value = fake_client_ctx
        out = client.lease_task()
    assert out == {"task_id": "xyz", "text": "do it"}


def test_complete_task_calls_correct_endpoint(client):
    result = aoc.TaskResult(task_id="abc", worker_id="oho-runner", state="completed", output="ok")
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"ack": True}
    fake_resp.raise_for_status = MagicMock()
    fake_post = MagicMock(return_value=fake_resp)
    fake_client_ctx = MagicMock()
    fake_client_ctx.__enter__.return_value.post = fake_post
    with patch.object(aoc, "httpx") as mock_httpx:
        mock_httpx.Client.return_value = fake_client_ctx
        client.complete_task(result)
    url_used = fake_post.call_args[0][0]
    assert url_used.endswith("/tasks/abc/complete")


def test_heartbeat_carries_worker_id(client):
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"ok": True}
    fake_resp.raise_for_status = MagicMock()
    fake_post = MagicMock(return_value=fake_resp)
    fake_client_ctx = MagicMock()
    fake_client_ctx.__enter__.return_value.post = fake_post
    with patch.object(aoc, "httpx") as mock_httpx:
        mock_httpx.Client.return_value = fake_client_ctx
        client.heartbeat()
    body = fake_post.call_args.kwargs["json"]
    assert body["worker_id"] == "oho-runner"


# ── Stubs ─────────────────────────────────────────────────────────────────────
def test_subscribe_events_is_stubbed(client):
    with pytest.raises(NotImplementedError):
        client.subscribe_events()


# ── Headers ──────────────────────────────────────────────────────────────────
def test_headers_carry_bearer_token(client):
    headers = client._headers()
    assert headers["Authorization"].startswith("Bearer ")
    assert "test-token" in headers["Authorization"]
    assert headers["Content-Type"] == "application/json"

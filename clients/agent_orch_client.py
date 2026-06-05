"""
clients/agent_orch_client.py — HTTP client for the CT 215 agent-orch broker.

Per ADR-0008 + the 2026-05-13 agent-orch-lxc recon: CT 215 already ships a
FastAPI brokerage spine at `http://100.122.188.108:9001` with per-worker bearer
tokens + Redis-backed durable queue under the `agent:orch:*` ACL prefix on CT
205. OHO becomes a well-behaved client — POSTs tasks, leases them when it
plays worker, completes them, heartbeats — instead of building a parallel
broker.

Endpoints (matching CT 215 `agents/orchestrator/control_api.py`):
  - POST /tasks                       — create a task; broker enqueues
  - POST /tasks/lease                 — claim the next available task
  - POST /tasks/{id}/complete         — report task completion (or failure)
  - POST /workers/heartbeat           — extend our worker's lease window
  - GET  /events  (SSE)               — subscribe to broker-side events
  - GET  /metrics/snapshot            — current queue depth + worker state

Auth: bearer token issued per-worker. OHO's worker_id is `oho-runner`; the
token lives in OHO's `/opt/oho/.env` as `AGENT_ORCH_BROKER_TOKEN` and on the
broker's `worker-tokens.yaml`. Tokens rotate per docs/security/secrets-rotation.md.

PHASE STATUS: SKELETON. Phase F kickoff is post-soak.
This file is on the `feature/phase-c-f-skeletons` branch.

Privacy classifier integration: every outbound payload runs through
`tools.privacy_classifier.classify` before the POST. Sensitive payloads
without an explicit `allow_egress_to: ["broker"]` are REFUSED at the client —
no broker round trip. This is the load-bearing safety property of ADR-0008.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import privacy_classifier as pc  # noqa: E402

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


@dataclass
class TaskCreateRequest:
    text: str
    user_id: str = "aaron"
    free_models_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def payload_dict(self) -> dict[str, Any]:
        """Shape for privacy_classifier.classify(). The text + any
        metadata that could carry PII is what the classifier sees."""
        return {"text": self.text, "fields": self.metadata}


@dataclass
class TaskResult:
    task_id: str
    worker_id: str
    state: str           # 'completed' | 'failed'
    output: str = ""
    error: str = ""


class PrivacyDenial(RuntimeError):
    """Raised when the privacy classifier blocks an outbound task."""


class BrokerClient:
    """Thin client for the CT 215 broker. Stateless except for the bearer +
    worker_id; safe to construct per-call. Production wire-up Phase F day-3."""

    def __init__(
        self,
        base_url: str,
        worker_id: str,
        bearer_token: str,
        classifier_ruleset: pc.RuleSet,
        *,
        timeout_s: float = 10.0,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(f"base_url must be http(s): got {base_url!r}")
        if not bearer_token:
            raise ValueError("bearer_token required")
        self.base_url = base_url.rstrip("/")
        self.worker_id = worker_id
        self.bearer_token = bearer_token
        self.classifier_ruleset = classifier_ruleset
        self.timeout_s = timeout_s

    # ── Privacy gate ─────────────────────────────────────────────────────
    def check_egress(self, req: TaskCreateRequest) -> pc.Verdict:
        """Run the payload through the classifier. Returns Verdict. Caller
        decides what to do — see post_task() for the standard deny path."""
        verdict = pc.classify(req.payload_dict(), req.metadata.get("hints"), self.classifier_ruleset)
        return verdict

    def _egress_allowed(self, verdict: pc.Verdict, allow_egress_to: set[str] | None) -> bool:
        """Apply the egress_policy for `to_broker`. `allow_egress_to` is the
        explicit override the caller can set."""
        policy = pc.egress_verdict(verdict.privacy_class, "to_broker", self.classifier_ruleset)
        if policy == "allow":
            return True
        if policy == "hard_deny":
            return False
        if "explicit" in policy and "broker" in (allow_egress_to or set()):
            return True
        return False

    # ── Endpoints ────────────────────────────────────────────────────────
    def post_task(
        self,
        req: TaskCreateRequest,
        *,
        allow_egress_to: set[str] | None = None,
    ) -> dict[str, Any]:
        """POST /tasks with privacy gate. Returns the broker's response on
        success; raises PrivacyDenial if the classifier blocks egress."""
        verdict = self.check_egress(req)
        if not self._egress_allowed(verdict, allow_egress_to):
            raise PrivacyDenial(
                f"broker egress refused: class={verdict.privacy_class} "
                f"reasons={verdict.reasons}"
            )
        if httpx is None:  # pragma: no cover
            raise RuntimeError("httpx not installed; cannot POST")
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(
                f"{self.base_url}/tasks",
                headers=self._headers(),
                json={
                    "text": req.text,
                    "user_id": req.user_id,
                    "free_models_only": req.free_models_only,
                    "metadata": req.metadata,
                },
            )
            resp.raise_for_status()
            return resp.json()

    def lease_task(self) -> dict[str, Any] | None:
        """POST /tasks/lease. Returns the leased task dict, or None if the
        queue is empty."""
        if httpx is None:  # pragma: no cover
            raise RuntimeError("httpx not installed")
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(
                f"{self.base_url}/tasks/lease",
                headers=self._headers(),
                json={"worker_id": self.worker_id},
            )
            if resp.status_code == 204:
                return None
            resp.raise_for_status()
            return resp.json()

    def complete_task(self, result: TaskResult) -> dict[str, Any]:
        """POST /tasks/{id}/complete."""
        if httpx is None:  # pragma: no cover
            raise RuntimeError("httpx not installed")
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(
                f"{self.base_url}/tasks/{result.task_id}/complete",
                headers=self._headers(),
                json={
                    "worker_id": result.worker_id,
                    "state": result.state,
                    "output": result.output,
                    "error": result.error,
                },
            )
            resp.raise_for_status()
            return resp.json()

    def heartbeat(self) -> dict[str, Any]:
        """POST /workers/heartbeat."""
        if httpx is None:  # pragma: no cover
            raise RuntimeError("httpx not installed")
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(
                f"{self.base_url}/workers/heartbeat",
                headers=self._headers(),
                json={"worker_id": self.worker_id},
            )
            resp.raise_for_status()
            return resp.json()

    def subscribe_events(self):  # pragma: no cover — stubbed
        """GET /events (SSE). NOT YET IMPLEMENTED — Phase F day-4."""
        raise NotImplementedError(
            "subscribe_events() is Phase F day-4 work. The SSE reconnect-on-drop "
            "+ backpressure mirror needs an asyncio loop; lands when the comms "
            "router consumes the event stream."
        )

    # ── Private ──────────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

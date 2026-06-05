"""tools/egress_guard.py — privacy classifier wired into the OpenRouter egress path.

ADR-0008 contract enforcer. Today this guards the only LIVE AI egress in
Python (tools/process_brain_dump.py → openai client). Future broker calls
(clients/agent_orch_client.py) will reuse the same module via
``guard_for_peer("to_broker", …)``.

Usage::

    from tools import egress_guard

    allowed, verdict = egress_guard.guard_for_peer(
        peer="to_openrouter",
        text=user_prompt,
        fields={"area": file_area},
        allow_egress=None,   # set to True only when caller has explicit consent
    )
    if not allowed:
        # verdict.privacy_class + verdict.reasons say why
        log.warning("egress blocked: %s -> openrouter (%s)",
                    verdict.privacy_class, verdict.reasons)
        return None

The classifier is loaded once at module import (the YAML never changes mid-process).
A missing or malformed ``infra/data-classes.yaml`` raises at import — fail-loud is
the correct behavior because running without the contract is the bug ADR-0008 was
written to prevent.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from tools.privacy_classifier import (
    Verdict,
    classify,
    egress_verdict,
    load_ruleset,
)

log = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULESET_PATH = REPO_ROOT / "infra" / "data-classes.yaml"

# Module-level singleton — load once. Re-import the module if the YAML changes,
# which only happens at dev time / deploy time (data-classes.yaml is checked
# into git, never edited at runtime).
_RULESET = load_ruleset(DEFAULT_RULESET_PATH)


def guard_for_peer(
    *,
    peer: str,
    text: str,
    fields: dict[str, Any] | None = None,
    allow_egress: bool | None = None,
) -> tuple[bool, Verdict]:
    """Return (allowed, verdict) for sending ``text`` to ``peer``.

    Caller MUST act on the boolean — this function never raises on policy
    denial; it returns (False, verdict) and logs at WARNING.

    ``peer`` must be one of the keys in ``data-classes.yaml`` egress_policy
    (today: ``to_lxc``, ``to_desktop``, ``to_vps``, ``to_broker``, ``to_openrouter``).

    ``allow_egress`` is the explicit-allow override for ``private`` class peers.
    For ``to_openrouter`` the policy hard-denies ``sensitive`` with NO override,
    matching the Definition of Amazing #4 invariant.
    """
    payload = {"text": text or "", "fields": dict(fields or {})}
    verdict = classify(payload, hints=None, ruleset=_RULESET)

    policy_verdict = egress_verdict(verdict.privacy_class, peer, _RULESET)

    if policy_verdict == "allow":
        return True, verdict
    if policy_verdict == "hard_deny":
        log.warning(
            "EGRESS BLOCKED hard_deny peer=%s class=%s reasons=%s",
            peer, verdict.privacy_class, verdict.reasons,
        )
        return False, verdict
    if policy_verdict.startswith("hard_deny_except_explicit_allow"):
        if allow_egress is True:
            log.info(
                "egress allowed via explicit override peer=%s class=%s",
                peer, verdict.privacy_class,
            )
            return True, verdict
        log.warning(
            "EGRESS BLOCKED hard_deny_except_explicit_allow peer=%s class=%s "
            "reasons=%s (caller did not set allow_egress=True)",
            peer, verdict.privacy_class, verdict.reasons,
        )
        return False, verdict
    if policy_verdict.startswith("require_explicit_allow"):
        if allow_egress is True:
            log.info(
                "egress allowed via explicit consent peer=%s class=%s",
                peer, verdict.privacy_class,
            )
            return True, verdict
        log.warning(
            "EGRESS BLOCKED require_explicit_allow peer=%s class=%s "
            "reasons=%s (caller did not set allow_egress=True)",
            peer, verdict.privacy_class, verdict.reasons,
        )
        return False, verdict

    # Unknown policy verdict — fail-closed.
    log.error(
        "EGRESS BLOCKED unknown policy=%r peer=%s class=%s reasons=%s",
        policy_verdict, peer, verdict.privacy_class, verdict.reasons,
    )
    return False, verdict


def reload_for_tests(yaml_path: Path | str | None = None) -> None:
    """Test-only: replace the module-level ruleset. Production code never calls this."""
    global _RULESET
    _RULESET = load_ruleset(Path(yaml_path) if yaml_path else DEFAULT_RULESET_PATH)

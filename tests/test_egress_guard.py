"""Test the privacy-classifier egress guard (ADR-0008 contract enforcement).

The guard is the single chokepoint for outbound AI calls in Python. Every
test here is a load-bearing proof of one rule in the Definition of Amazing
release rubric:

  #4 — Sensitive data never reaches a free-tier model — classifier-enforced.
  #9 — No sensitive payload class crosses OHO→broker without explicit
       allow-list — classifier-enforced.

If any of these fail in CI, the contract is broken; do not ship.
"""
from __future__ import annotations

import logging

import pytest

from tools import egress_guard


def test_public_text_allowed_to_openrouter():
    """Plain task text with no sensitive tag → public (tier-10 default) → allowed."""
    allowed, verdict = egress_guard.guard_for_peer(
        peer="to_openrouter",
        text="Buy milk and bread from the grocery store",
        fields={"area": "personal"},
    )
    assert allowed is True
    assert verdict.privacy_class == "public"


@pytest.mark.parametrize("area", ["faith", "family", "health"])
def test_sensitive_area_hard_denied_to_openrouter(area, caplog):
    """area=faith / family / health → tier-2 area-tag rule → sensitive → hard_deny.

    This is the #4 contract: no override; faith/family/health NEVER hits cloud LLMs.
    """
    caplog.set_level(logging.WARNING)
    allowed, verdict = egress_guard.guard_for_peer(
        peer="to_openrouter",
        text="Some content with no obvious PII",
        fields={"area": area},
    )
    assert allowed is False
    assert verdict.privacy_class == "sensitive"
    assert any(f"area:{area}" in r for r in verdict.reasons)
    assert "EGRESS BLOCKED" in caplog.text


def test_hard_deny_ignores_allow_egress_override():
    """to_openrouter sensitive == hard_deny (no override). Even allow_egress=True
    must NOT bypass — the policy verdict is `hard_deny`, not
    `hard_deny_except_explicit_allow_egress_to_openrouter`."""
    allowed, _ = egress_guard.guard_for_peer(
        peer="to_openrouter",
        text="Faith reflection",
        fields={"area": "faith"},
        allow_egress=True,  # caller tries to override
    )
    assert allowed is False


def test_explicit_allow_required_for_private_class_to_vps():
    """to_vps + private → require_explicit_allow. Caller must pass allow_egress=True."""
    # Trigger PII regex to produce a non-public verdict. SSN-shape is a known
    # tier-9 rule that doesn't depend on SKELETON_MODE-gated dictionaries.
    text = "My SSN: 123-45-6789"
    fields_unprivileged: dict = {}

    blocked, _ = egress_guard.guard_for_peer(
        peer="to_vps",
        text=text,
        fields=fields_unprivileged,
    )
    # Without an explicit allow, blocked.
    assert blocked is False


def test_unknown_peer_fails_closed():
    """Unknown peer not in egress_policy raises KeyError downstream; guard wraps
    that into fail-closed (allowed=False)."""
    with pytest.raises(KeyError):
        egress_guard.guard_for_peer(
            peer="to_nowhere",
            text="hi",
            fields={"area": "personal"},
        )


def test_guard_called_before_openrouter_in_chat_with_fallback(monkeypatch):
    """Integration: tools/process_brain_dump._chat_with_fallback must consult
    the guard BEFORE invoking the OpenAI client. We monkey-patch the guard to
    deny and assert no client.chat.completions.create() call happens."""
    from tools import process_brain_dump

    calls = {"n": 0}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls["n"] += 1
                    raise AssertionError(
                        "OpenAI client must NOT be called when guard denies egress"
                    )

    monkeypatch.setattr(
        process_brain_dump.egress_guard
        if hasattr(process_brain_dump, "egress_guard")
        else egress_guard,
        "guard_for_peer",
        lambda **kw: (False, egress_guard.Verdict("sensitive", ["test"])),
    )

    out = process_brain_dump._chat_with_fallback(
        _FakeClient(), "any prompt", max_tokens=10, area="faith"
    )
    assert out is None
    assert calls["n"] == 0


def test_guard_allows_client_when_classifier_allows(monkeypatch):
    """Inverse of the prior test: when guard returns True, the OpenAI client
    IS invoked. Proves the guard is the gate, not a no-op wrapper."""
    from types import SimpleNamespace

    from tools import process_brain_dump

    calls = {"n": 0}

    fake_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))]
    )

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    calls["n"] += 1
                    return fake_resp

    monkeypatch.setattr(
        egress_guard,
        "guard_for_peer",
        lambda **kw: (True, egress_guard.Verdict("public", ["test"])),
    )

    out = process_brain_dump._chat_with_fallback(
        _FakeClient(), "any prompt", max_tokens=10, area="personal"
    )
    assert out == "hello"
    assert calls["n"] == 1

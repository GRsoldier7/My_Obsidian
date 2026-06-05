"""Tests for tools/privacy_classifier.py — Phase F skeleton (ADR-0008).

Pins the implemented surface (tier 1, 2, 9, 10 + egress lookups) AND asserts
NotImplementedError on tiers 3-8 dictionary-matching stubs. When a stub ships,
the test flips from "expect NotImplementedError" to "assert expected behavior."
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import privacy_classifier as pc  # noqa: E402

DATA_CLASSES_YAML = REPO_ROOT / "infra" / "data-classes.yaml"


@pytest.fixture(scope="module")
def ruleset() -> pc.RuleSet:
    return pc.load_ruleset(DATA_CLASSES_YAML)


# ── Loader ────────────────────────────────────────────────────────────────────
def test_loader_parses_real_yaml(ruleset):
    assert ruleset.version == 1
    assert len(ruleset.rules) >= 10
    # Egress matrix complete
    for peer in ("to_lxc", "to_desktop", "to_vps", "to_broker", "to_openrouter"):
        assert peer in ruleset.egress_policy


def test_loader_sorts_rules_by_tier(ruleset):
    tiers = [r.tier for r in ruleset.rules]
    assert tiers == sorted(tiers)


# ── Tier 10 default ──────────────────────────────────────────────────────────
def test_classify_grocery_list_is_public(ruleset):
    payload = {"text": "Milk, eggs, bread, coffee.", "fields": {"area": "home", "priority": "C"}}
    v = pc.classify(payload, None, ruleset)
    assert v.privacy_class == "public"


# ── Tier 2 area-tag ──────────────────────────────────────────────────────────
def test_classify_area_faith_is_sensitive(ruleset):
    payload = {"text": "Sermon prep notes.", "fields": {"area": "faith", "priority": "A"}}
    v = pc.classify(payload, None, ruleset)
    assert v.privacy_class == "sensitive"
    assert any("faith" in r for r in v.reasons)


def test_classify_area_health_is_sensitive(ruleset):
    payload = {"text": "Pre-op checklist.", "fields": {"area": "health", "priority": "A"}}
    v = pc.classify(payload, None, ruleset)
    assert v.privacy_class == "sensitive"


def test_classify_area_family_is_sensitive(ruleset):
    payload = {"text": "Family dinner plan.", "fields": {"area": "family", "priority": "B"}}
    v = pc.classify(payload, None, ruleset)
    assert v.privacy_class == "sensitive"


def test_classify_area_business_NOT_sensitive(ruleset):
    """Business is NOT in the sensitive area set — guards over-classification."""
    payload = {"text": "Draft a one-page SOW.", "fields": {"area": "business", "priority": "B"}}
    v = pc.classify(payload, None, ruleset)
    # Will be public unless a downstream tier (e.g. dictionary) fires — and we
    # haven't seeded any client-identifier in this test.
    assert v.privacy_class == "public"


# ── Tier 1 caller-asserted override ──────────────────────────────────────────
def test_caller_asserted_sensitive_honored(ruleset):
    payload = {"text": "neutral content", "fields": {"area": "personal"}}
    hints = {"caller_asserted_class": "sensitive"}
    v = pc.classify(payload, hints, ruleset)
    assert v.privacy_class == "sensitive"
    assert any("caller-asserted" in r for r in v.reasons)


def test_caller_asserted_with_no_assertion_falls_through(ruleset):
    payload = {"text": "neutral content", "fields": {"area": "personal"}}
    hints = {}  # no caller_asserted_class
    v = pc.classify(payload, hints, ruleset)
    # Will hit default-public (no area-sensitive, no dictionary stub fired)
    assert v.privacy_class == "public"


def test_caller_asserted_invalid_class_ignored(ruleset):
    payload = {"text": "neutral", "fields": {"area": "personal"}}
    hints = {"caller_asserted_class": "secret"}  # invalid value
    v = pc.classify(payload, hints, ruleset)
    # Falls through to default
    assert v.privacy_class == "public"


# ── Stubbed tiers skip silently in SKELETON_MODE ─────────────────────────────
# When SKELETON_MODE flips to False (Phase F day-2), these tests update to
# assert the actual implemented behavior.

def test_tier3_kid_name_dictionary_currently_skipped(ruleset):
    """SKELETON: Tier 3 (kid-name dictionary) skips silently. Payload falls
    through to default-public. Phase F day-2: this test flips to assert sensitive."""
    payload = {"text": "Pick up Hudson from soccer.", "fields": {"area": "personal"}}
    v = pc.classify(payload, None, ruleset)
    assert v.privacy_class == "public", "SKELETON_MODE: kid-name dictionary not yet wired"


def test_tier9_pii_email_currently_skipped(ruleset):
    """SKELETON: regex hit alone insufficient — not_in_allowlist gate stubbed.
    Phase F day-2: this test flips to assert private."""
    payload = {"text": "Email jordan@example.test about renewal.", "fields": {"area": "consulting"}}
    v = pc.classify(payload, None, ruleset)
    assert v.privacy_class == "public", "SKELETON_MODE: PII allow-list gate not yet wired"


def test_skeleton_mode_flag_is_true():
    """When this flips to False, every other skeleton-mode test in this file must update."""
    assert pc.SKELETON_MODE is True, "Skeleton-mode tests need updating before flipping the flag"


# ── Egress verdict ──────────────────────────────────────────────────────────
def test_egress_sensitive_to_openrouter_is_hard_deny(ruleset):
    verdict = pc.egress_verdict("sensitive", "to_openrouter", ruleset)
    assert verdict == "hard_deny"


def test_egress_sensitive_to_vps_starts_hard_deny(ruleset):
    verdict = pc.egress_verdict("sensitive", "to_vps", ruleset)
    assert verdict.startswith("hard_deny")


def test_egress_public_to_any_is_allow(ruleset):
    for peer in ("to_lxc", "to_desktop", "to_vps", "to_broker", "to_openrouter"):
        verdict = pc.egress_verdict("public", peer, ruleset)
        assert verdict == "allow"


def test_egress_unknown_peer_raises(ruleset):
    with pytest.raises(KeyError):
        pc.egress_verdict("public", "to_mars", ruleset)


def test_egress_unknown_class_raises(ruleset):
    with pytest.raises(KeyError):
        pc.egress_verdict("secret", "to_lxc", ruleset)


# ── Fallback safety ──────────────────────────────────────────────────────────
def test_classify_falls_back_to_sensitive_if_no_rule_matches():
    """Defense-in-depth: if the YAML is somehow stripped of its default-public
    rule, we fall back to `sensitive` rather than silently leaking."""
    minimal = pc.RuleSet(version=1, rules=[], egress_policy={})
    v = pc.classify({"text": "x", "fields": {}}, None, minimal)
    assert v.privacy_class == "sensitive"
    assert "fallback" in v.reasons[0]

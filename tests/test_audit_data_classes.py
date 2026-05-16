"""Tests for scripts/audit_data_classes.py.

The audit must:
  1. Pass on the real infra/data-classes.yaml committed in this repo.
  2. Fail loudly on every contract violation it claims to detect.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_data_classes as adc  # noqa: E402


@pytest.fixture
def doc():
    return adc.load_yaml()


# ── Happy path ────────────────────────────────────────────────────────────────
def test_real_yaml_passes_audit(doc):
    findings = adc.findings_for(doc, strict=True)
    assert findings == [], f"Real data-classes.yaml has issues: {findings}"


def test_real_yaml_has_all_required_peers(doc):
    assert set(doc["egress_policy"].keys()) >= adc.REQUIRED_PEERS


def test_real_yaml_has_default_rule(doc):
    assert any(r.get("matches", {}).get("default") is True for r in doc["rules"])


# ── Negative cases ────────────────────────────────────────────────────────────
def test_audit_flags_missing_top_level_keys(doc):
    bad = copy.deepcopy(doc)
    del bad["rules"]
    findings = adc.findings_for(bad, strict=False)
    assert any("missing top-level keys" in f and "rules" in f for f in findings)


def test_audit_flags_duplicate_rule_id(doc):
    bad = copy.deepcopy(doc)
    bad["rules"].append(dict(bad["rules"][0]))  # duplicate the first rule
    findings = adc.findings_for(bad, strict=False)
    assert any("duplicate id" in f for f in findings)


def test_audit_flags_invalid_result_class(doc):
    bad = copy.deepcopy(doc)
    bad["rules"][0]["result"] = "secret"  # not one of public/private/sensitive
    findings = adc.findings_for(bad, strict=False)
    assert any("result`" in f and "secret" in f for f in findings)


def test_audit_flags_missing_peer(doc):
    bad = copy.deepcopy(doc)
    del bad["egress_policy"]["to_vps"]
    findings = adc.findings_for(bad, strict=False)
    assert any("missing peer" in f and "to_vps" in f for f in findings)


def test_audit_flags_unknown_egress_verdict(doc):
    bad = copy.deepcopy(doc)
    bad["egress_policy"]["to_vps"]["sensitive"] = "permit_freely"
    findings = adc.findings_for(bad, strict=False)
    assert any("permit_freely" in f for f in findings)


def test_audit_flags_openrouter_sensitive_override():
    """ABSOLUTE invariant — sensitive payloads NEVER egress to OpenRouter."""
    bad = adc.load_yaml()
    bad = copy.deepcopy(bad)
    bad["egress_policy"]["to_openrouter"]["sensitive"] = "allow"  # invariant breach
    findings = adc.findings_for(bad, strict=False)
    assert any("INVARIANT BREACH" in f and "to_openrouter" in f for f in findings)


def test_audit_flags_vps_sensitive_without_hard_deny():
    bad = adc.load_yaml()
    bad = copy.deepcopy(bad)
    bad["egress_policy"]["to_vps"]["sensitive"] = "allow"  # also invariant breach
    findings = adc.findings_for(bad, strict=False)
    assert any("INVARIANT BREACH" in f and "to_vps" in f for f in findings)


def test_audit_flags_low_coverage_target(doc):
    bad = copy.deepcopy(doc)
    bad["tests"]["required_coverage"] = 80.0
    findings = adc.findings_for(bad, strict=False)
    assert any("required_coverage" in f for f in findings)


def test_audit_flags_low_fixture_count(doc):
    bad = copy.deepcopy(doc)
    bad["tests"]["fixture_count_target"] = 100
    findings = adc.findings_for(bad, strict=False)
    assert any("fixture_count_target" in f for f in findings)


def test_audit_flags_missing_default_rule(doc):
    bad = copy.deepcopy(doc)
    bad["rules"] = [r for r in bad["rules"] if not r.get("matches", {}).get("default")]
    findings = adc.findings_for(bad, strict=False)
    assert any("default-public" in f for f in findings)


# ── Strict mode ───────────────────────────────────────────────────────────────
def test_strict_mode_flags_tier_disorder(doc):
    bad = copy.deepcopy(doc)
    # Swap the first two rules so tier ordering breaks (first rule is tier 1 ; second tier 2)
    bad["rules"][0], bad["rules"][1] = bad["rules"][1], bad["rules"][0]
    findings = adc.findings_for(bad, strict=True)
    assert any("tier order" in f for f in findings)


def test_non_strict_mode_allows_tier_disorder(doc):
    """Without --strict, tier order is informational, not enforced."""
    bad = copy.deepcopy(doc)
    bad["rules"][0], bad["rules"][1] = bad["rules"][1], bad["rules"][0]
    findings = adc.findings_for(bad, strict=False)
    assert not any("tier order" in f for f in findings)

"""
tools/privacy_classifier.py — deterministic privacy classifier for ADR-0008.

Reads `infra/data-classes.yaml` (the source-of-truth rule registry seeded
2026-05-16) and classifies comms-envelope payloads into ``public`` / ``private``
/ ``sensitive``. Apply rules in declared tier order; FIRST match wins.

PHASE STATUS: SKELETON. Phase F kickoff is post-soak (Mon 2026-05-18+).
This file is on the isolated ``feature/phase-c-f-skeletons`` branch.

Implemented in this skeleton (enough to round-trip the eval fixture set):
  - Rule loader (parses YAML, validates against the contract).
  - Tier 1 caller-asserted override (without signature verification — that
    arrives with the agent-key registry, Phase F day-3).
  - Tier 2 area-tag matching (faith / family / health → sensitive).
  - Tier 9 PII regex shapes (email / phone / SSN / credit-card).
  - Tier 10 default-public.
  - Egress verdict lookup against the egress_policy block.

Stubbed (silent skip — see SKELETON_MODE below) — wired post-soak when the
dictionaries and regex-gates are operator-tuned:
  - Tier 3-8 dictionary matches (kid-names / family-names / biomarkers /
    faith-terms / financial-figures / client-IDs / Google-URLs).
  - Tier 9 regex gates (luhn_check, not_in_allowlist) — regex hit alone is
    insufficient signal without these gates, so the skeleton skips the rule
    rather than over-firing.
  - Signature verification for tier-1.

In SKELETON_MODE = True (the current default), stubbed rules return None
from `_apply_rule` so payloads continue down the tier chain to default-public.
This means privacy classification is INCOMPLETE in skeleton mode; the
production wiring (Phase F day-2+) must set SKELETON_MODE = False and
implement each stub. Tests guard the migration: each stubbed-rule test
asserts current behavior + carries a TODO to flip on full wiring.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PrivacyClass = str  # 'public' | 'private' | 'sensitive'

# When True (Phase F skeleton): stubbed rules return None instead of raising,
# allowing payloads to flow to default-public. When False (production): each
# stub must be implemented — calling unimplemented behavior raises.
SKELETON_MODE = True


# ── Regexes for the implemented tiers ─────────────────────────────────────────
_PII_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PII_PHONE_RE = re.compile(r"\b\d{3}-\d{3}-\d{4}\b")
_PII_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PII_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

_SENSITIVE_AREAS = {"faith", "family", "health"}


# ── Data shapes ───────────────────────────────────────────────────────────────
@dataclass
class Rule:
    id: str
    tier: int
    matches: dict[str, Any]
    result: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class Verdict:
    privacy_class: PrivacyClass
    reasons: list[str]


@dataclass
class RuleSet:
    version: int
    rules: list[Rule]
    egress_policy: dict[str, dict[str, str]]


# ── Loader ────────────────────────────────────────────────────────────────────
def load_ruleset(path: Path | str) -> RuleSet:
    """Parse infra/data-classes.yaml into a RuleSet. Raises ValueError on a contract
    violation that the audit should have caught — defense in depth."""
    p = Path(path)
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"{p} did not parse to a dict")
    rules: list[Rule] = []
    for entry in doc.get("rules", []) or []:
        rules.append(Rule(
            id=entry["id"],
            tier=entry["tier"],
            matches=entry.get("matches", {}),
            result=entry.get("result", "public"),
            reasons=list(entry.get("reasons", [])),
        ))
    rules.sort(key=lambda r: r.tier)
    return RuleSet(
        version=int(doc.get("version", 1)),
        rules=rules,
        egress_policy=doc.get("egress_policy", {}),
    )


# ── Classification ───────────────────────────────────────────────────────────
def classify(
    payload: dict[str, Any],
    hints: dict[str, Any] | None,
    ruleset: RuleSet,
) -> Verdict:
    """First-match-wins rule application over the loaded ruleset.

    `payload` follows the comms-envelope `payload` shape: {"text": str, "fields": dict}.
    `hints` carries `caller_asserted_class` (tier 1 escape hatch) and the
    `_test_*` keys used by the eval-fixture harness to inject configurable
    dictionaries (kid-names, family-names, client-identifiers).
    """
    hints = hints or {}
    text = str(payload.get("text", ""))
    fields = payload.get("fields", {}) or {}

    for rule in ruleset.rules:
        verdict = _apply_rule(rule, text, fields, hints)
        if verdict is not None:
            return verdict

    # If no rule matched (shouldn't happen — data-classes.yaml has a default)
    # — fall back to sensitive (fail-safe).
    return Verdict("sensitive", ["fallback:no-rule-matched"])


def _apply_rule(
    rule: Rule,
    text: str,
    fields: dict[str, Any],
    hints: dict[str, Any],
) -> Verdict | None:
    """Return Verdict if this rule fires; None otherwise."""
    m = rule.matches

    # Tier 1 — caller-asserted override (signature verification stubbed)
    if m.get("signed_caller_assertion") and hints.get("caller_asserted_class"):
        # Skeleton: accept assertion without signature check. Real Phase F
        # verifies the agent's Ed25519 signature against infra/agent-keys.yaml.
        asserted = hints["caller_asserted_class"]
        if asserted in ("public", "private", "sensitive"):
            return Verdict(asserted, [f"caller-asserted:{asserted}"])

    # Tier 2 — area-tag based
    if "any_field_value" in m:
        for key, expected in m["any_field_value"].items():
            if fields.get(key) == expected:
                return Verdict(rule.result, [reason.replace("<name>", expected) for reason in rule.reasons] or [f"area:{expected}"])

    # Tier 9 — PII shapes (regex)
    if "regex" in m:
        # NOTE: some rules use regex + extra gates (luhn_check, not_in_allowlist).
        # Skeleton: pure regex match only — the gates are stubbed for Phase F.
        for pattern_src in m["regex"]:
            try:
                pat = re.compile(pattern_src)
            except re.error:
                continue
            hit = pat.search(text)
            if hit:
                if m.get("luhn_check") or m.get("not_in_allowlist"):
                    if SKELETON_MODE:
                        # Skeleton: regex hit alone is insufficient — skip rule
                        # until the gate (luhn / allow-list) is wired Phase F day-2.
                        continue
                    raise NotImplementedError(
                        f"rule {rule.id!r}: luhn_check / not_in_allowlist gates "
                        "not implemented in production mode."
                    )
                return Verdict(rule.result, rule.reasons or [f"regex:{rule.id}"])

    # Tier 3-8 — dictionary matches. Skeleton skips; Phase F day-2 wires the dictionary.
    if "whole_word_case_insensitive" in m:
        if SKELETON_MODE:
            return None
        raise NotImplementedError(
            f"rule {rule.id!r}: whole_word_case_insensitive dictionary matching "
            "not implemented in production mode."
        )

    # Tier 7 — financial: inline_field_present
    if "inline_field_present" in m:
        for field_name in m["inline_field_present"]:
            if field_name in fields:
                return Verdict(rule.result, rule.reasons or [f"field:{field_name}"])

    # Tier 10 — default
    if m.get("default") is True:
        return Verdict(rule.result, rule.reasons or ["default"])

    return None


# ── Egress verdict ───────────────────────────────────────────────────────────
def egress_verdict(
    privacy_class: PrivacyClass,
    peer: str,
    ruleset: RuleSet,
) -> str:
    """Look up the egress policy verdict for (class, peer). Raises KeyError if the
    peer isn't declared — the audit ensures all 5 peers are present, so a KeyError
    here means infra/data-classes.yaml is out of date."""
    policy = ruleset.egress_policy.get(peer)
    if not isinstance(policy, dict):
        raise KeyError(f"egress_policy has no peer {peer!r}")
    verdict = policy.get(privacy_class)
    if not isinstance(verdict, str):
        raise KeyError(f"egress_policy[{peer}] has no verdict for class {privacy_class!r}")
    return verdict

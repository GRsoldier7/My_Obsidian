#!/usr/bin/env python3
"""
scripts/audit_data_classes.py — enforce the infra/data-classes.yaml contract.

The privacy classifier (proposed in ADR-0008; not yet implemented) reads its
rules from infra/data-classes.yaml. Once the classifier ships, drifting that
YAML silently is a high-blast-radius bug. This audit catches drift in CI.

Run:
    python3 scripts/audit_data_classes.py
    python3 scripts/audit_data_classes.py --strict   # tighter checks

Exit codes:
    0   contract upheld
    1   contract violation (CI-visible failure)
    2   unexpected I/O failure
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_CLASSES_PATH = REPO_ROOT / "infra" / "data-classes.yaml"

REQUIRED_PEERS = {"to_lxc", "to_desktop", "to_vps", "to_broker", "to_openrouter"}
REQUIRED_CLASSES = {"public", "private", "sensitive"}
ALLOWED_EGRESS_VERDICTS = {
    "allow",
    "require_explicit_allow_egress_to_vps",
    "require_explicit_allow_egress_to_broker",
    "require_explicit_allow_egress_to_openrouter",
    "hard_deny",
    "hard_deny_except_explicit_allow_egress_to_vps",
    "hard_deny_except_explicit_allow_egress_to_broker",
    "hard_deny_except_explicit_allow_egress_to_openrouter",
}
REQUIRED_TOP_KEYS = {"version", "schema", "updated", "rules", "egress_policy", "tests", "audit"}


def load_yaml() -> dict[str, Any]:
    import yaml  # local import so the audit can give a clean error if PyYAML missing
    return yaml.safe_load(DATA_CLASSES_PATH.read_text(encoding="utf-8"))


def findings_for(doc: dict[str, Any], *, strict: bool) -> list[str]:
    out: list[str] = []

    # ── top-level shape ───────────────────────────────────────────────────
    missing_keys = REQUIRED_TOP_KEYS - set(doc.keys())
    if missing_keys:
        out.append(f"missing top-level keys: {sorted(missing_keys)}")
    if "version" in doc and not isinstance(doc["version"], int):
        out.append("`version` must be an integer")
    if "schema" in doc and not isinstance(doc["schema"], str):
        out.append("`schema` must be a string identifier")

    # ── rules ──────────────────────────────────────────────────────────────
    rules = doc.get("rules", [])
    if not isinstance(rules, list) or not rules:
        out.append("`rules` must be a non-empty list")
        return out

    seen_ids: set[str] = set()
    tiers_seen: list[int] = []
    has_default = False
    for idx, rule in enumerate(rules):
        prefix = f"rules[{idx}]"
        if not isinstance(rule, dict):
            out.append(f"{prefix}: not a mapping")
            continue
        for required in ("id", "tier", "matches", "result"):
            if required not in rule:
                out.append(f"{prefix}: missing `{required}`")
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid:
            out.append(f"{prefix}: `id` must be a non-empty string")
        elif rid in seen_ids:
            out.append(f"{prefix}: duplicate id `{rid}`")
        else:
            seen_ids.add(rid)
        tier = rule.get("tier")
        if not isinstance(tier, int):
            out.append(f"{prefix}: `tier` must be an integer")
        else:
            tiers_seen.append(tier)
        result = rule.get("result")
        if result not in REQUIRED_CLASSES and result != "caller_specified":
            out.append(f"{prefix}: `result` must be one of {sorted(REQUIRED_CLASSES)} or 'caller_specified' (got {result!r})")
        matches = rule.get("matches")
        if not isinstance(matches, dict) or not matches:
            out.append(f"{prefix}: `matches` must be a non-empty mapping")
        if isinstance(matches, dict) and matches.get("default") is True:
            has_default = True

    if not has_default:
        out.append("rules: must include a default-public rule (matches.default: true)")
    if strict and tiers_seen != sorted(tiers_seen):
        out.append("rules: tier order must be non-decreasing (declared order matters — first match wins)")

    # ── egress_policy ──────────────────────────────────────────────────────
    egress = doc.get("egress_policy")
    if not isinstance(egress, dict):
        out.append("`egress_policy` must be a mapping")
        return out
    missing_peers = REQUIRED_PEERS - set(egress.keys())
    if missing_peers:
        out.append(f"egress_policy: missing peer(s) {sorted(missing_peers)}")
    for peer, policy in egress.items():
        if not isinstance(policy, dict):
            out.append(f"egress_policy[{peer}]: not a mapping")
            continue
        missing_classes = REQUIRED_CLASSES - set(policy.keys())
        if missing_classes:
            out.append(f"egress_policy[{peer}]: missing class verdicts for {sorted(missing_classes)}")
        for cls, verdict in policy.items():
            if cls not in REQUIRED_CLASSES:
                out.append(f"egress_policy[{peer}]: unknown class `{cls}`")
                continue
            if verdict not in ALLOWED_EGRESS_VERDICTS:
                out.append(f"egress_policy[{peer}][{cls}]: verdict `{verdict}` not in allow-list")

    # ── invariants that protect privacy ───────────────────────────────────
    if isinstance(egress, dict):
        op = egress.get("to_openrouter")
        if isinstance(op, dict) and op.get("sensitive") != "hard_deny":
            out.append("INVARIANT BREACH: to_openrouter.sensitive must be `hard_deny` — no override allowed.")
        vps = egress.get("to_vps")
        if isinstance(vps, dict):
            if "sensitive" in vps and "hard_deny" not in vps["sensitive"]:
                out.append("INVARIANT BREACH: to_vps.sensitive must start with `hard_deny` (override allowed).")

    # ── tests block ────────────────────────────────────────────────────────
    tests = doc.get("tests", {})
    if isinstance(tests, dict):
        if tests.get("required_coverage", 0) < 95.0:
            out.append("tests.required_coverage must be >= 95.0 (ADR-0008 §15 contract)")
        if not isinstance(tests.get("fixture_count_target", 0), int) or tests.get("fixture_count_target", 0) < 200:
            out.append("tests.fixture_count_target must be >= 200 (ADR-0008 §15 contract)")

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit infra/data-classes.yaml against ADR-0008 contract")
    parser.add_argument("--strict", action="store_true", help="Enable tighter ordering checks")
    args = parser.parse_args()

    try:
        doc = load_yaml()
    except FileNotFoundError:
        print(f"FAIL: {DATA_CLASSES_PATH} not found", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"FAIL: could not parse YAML — {e}", file=sys.stderr)
        return 2

    findings = findings_for(doc, strict=args.strict)
    if findings:
        print(f"FAIL: data-classes audit found {len(findings)} issue(s):", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        return 1

    rule_count = len(doc.get("rules", []))
    peer_count = len(doc.get("egress_policy", {}))
    print(f"OK — data-classes audit passed. {rule_count} rules, {peer_count} peers, v{doc.get('version')}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

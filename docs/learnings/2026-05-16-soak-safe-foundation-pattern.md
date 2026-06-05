---
date: 2026-05-16
title: "Soak-safe foundation pattern — turn waiting time into infrastructure"
tags: [adr-0007, soak-gate, audit-driven-design, eval-harness, phase-f-prep]
relates_to:
  - docs/adr/0007-master-plan-v2.md
  - docs/adr/0008-cross-host-comms.md
  - docs/adr/0009-threaded-tasks.md
---

# Soak-safe foundation pattern

## Context

ADR-0007 (Master Plan v2) defines a **7-day soak gate** before Phase C / F code can land. The gate exists because P1+P1.5+ADR-0006 hit prod with risk and Aaron needs evidence the foundation is stable. Hard rules during the gate: **no new code-surface phases, no new capture surfaces, no new code-heavy cron slots**.

The temptation is to wait. The wrong temptation. The right temptation is to **shovel foundation into the wait window** — anything that compounds the moment the gate opens.

## What worked

### 1. Promote design contracts to enforced contracts

Each piece of Phase F design that was just YAML / Markdown got an audit script + tests. The first run of `audit_data_classes.py --strict` immediately caught a real bug in `infra/data-classes.yaml` (tier-1 `matches:` was a string, should be a mapping). The audit was the bug's bug-detector before any classifier existed.

**Pattern:** every load-bearing config file gets a same-session audit script. Don't ship config without its enforcer.

### 2. Build the eval harness before the eval target

`scripts/run_evals.py` works today in **schema-only mode** — validates fixture format, reports class/category coverage, fails on malformed JSON. The classifier itself (`tools/privacy_classifier.py`) doesn't exist yet. When it ships post-soak, the harness just adds `--run-classifier` and gets a runtime pass.

**Pattern:** the test scaffolding lands before the thing being tested. Phase F day-1 starts with 95% test infra already green.

### 3. Frozen fixture contracts before implementation

The fixture-naming convention (`F-NNNN-slug.json`, range-by-class) is enforced by `tests/test_eval_fixtures_schema.py` BEFORE the classifier reads any fixture. Got caught immediately when one fixture used the wrong number range (`F-0052` was `class: public` but the range said `private`). Fixed by renumber, not by changing the convention.

**Pattern:** lock the test-data contract first. Implementation will tempt you to change the contract to fit a regression — resist by making the contract the source of truth.

### 4. Audits as PR gates

`make audit-all` runs every offline audit in one command. `.github/workflows/audit-pr.yml` wires it to PR events. Pre-commit hook (`.githooks/pre-commit`) catches the same drift locally.

**Pattern:** a check is only a check if it RUNS. Wire it into pre-commit AND CI AND `make audit-all`. Three doors, one rule.

### 5. SLOs as a written contract before measurement

`docs/SLO-life-os.md` defines per-workflow targets *before* `scripts/audit_slo_conformance.py` exists. The doc IS the contract; the audit reads it; the Command Center renders state from the audit's output. Three layers, one source of truth.

**Pattern:** measurement infrastructure lands AFTER the targets are written, not before. Otherwise you measure what's easy, not what matters.

## What didn't (yet)

### 1. The "wait for ADR promotion" smell

Three ADRs in this session: 0007 (Accepted) + 0008 / 0009 (Proposed). Half the eval / privacy work below is "would be Phase F code" but for the soak gate. We carefully kept it on the docs / config / fixture side. **Right call** but it's worth naming the temptation: writing Phase F code under the cover of "scaffolding" violates the spirit of the soak gate even when it stays inside its letter.

**Pattern:** when you find yourself arguing "but it's pure tooling, not phase code," that's the audit you owe yourself. Re-read the rule. If it pinches, hold.

### 2. The "every script needs a Makefile target" reflex

Every new script got a Makefile target this session. Good. The next reflex: every Makefile target needs a help-line entry. Easy to forget; lint-style enforcement is missing. Future improvement: an audit that scans the Makefile for `.PHONY` targets without help entries.

## Numbers from this soak window (3 commits)

| Wave | Net new | Tests | Audits |
|---|---|---|---|
| 1 (this session start) | ADRs 0007/0008/0009 + CLAUDE.md drift + NLM cleanup + B4 backfill | 326 → 343 | 4 audits green |
| 2 | Wave-X H1 seed (data-classes + secrets-rotation + Telegram runbook + 3 eval fixtures) | 343 → 343 | 4 audits green |
| 3 | audit_data_classes + audit_secrets_rotation + run_evals + 7 fixtures | 343 → 430 | 5 audits green |
| 4 (this commit) | audit_planning_docs + GH Action + pre-commit hook + SLO doc + task-backing-file schema + more fixtures | 430 → TBD | 6 audits green (audit-all) |

Trajectory: every wave moves the **enforce** column. Soak Day 6/7 — gate-open at Mon 2026-05-18.

## Forward-applicable rules

1. **Idle ≠ wait.** Every gate has a backlog of foundation work that doesn't violate the gate. Find it.
2. **Contract before code.** Write the YAML / fixture / SLO target before the audit that enforces it. Write the audit before the runtime that uses it.
3. **Three doors per rule.** Pre-commit + CI + `make audit-all`. If a check only lives in one door, it's only enforced one third of the time.
4. **Fixture renumbers > convention changes.** When a fixture violates the range, move the fixture. Not the range.
5. **First-run debugging is the cheapest debugging.** Audit your own work the moment it lands; first-run flags the typos, the off-by-ones, the shape bugs that would have rotted for months.

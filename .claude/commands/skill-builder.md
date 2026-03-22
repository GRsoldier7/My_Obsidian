---
name: skill-builder
description: |
  Genius-level meta-skill for designing, building, auditing, and improving other Agent Skills.
  Activates when the user wants to create a new skill, improve an existing SKILL.md, identify
  gaps in a skill library, audit a skill for quality, or produce a batch of skills for a domain.
  Trigger phrases: "build a skill", "create a skill for", "improve this skill", "audit this skill",
  "what skills are missing", "skill for X domain", "write a SKILL.md", "skill library gap".
  Uses a 5-module pipeline: Domain Intelligence → Capability Decomposition → Skill Architecture
  → Quality Evaluation (10-dimension rubric) → Continuous Improvement Protocol.
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: core
  adjacent-skills: prompt-amplifier, portable-ai-instructions, polychronos-team
  source-repo: GRsoldier7/My_AI_Skills
---

# Skill Builder — 5-Module Pipeline

## The 5-Module Pipeline

```
Module 1: Domain Intelligence Brief
       ↓
Module 2: Capability Decomposition Map
       ↓
Module 3: Skill Architecture (write the SKILL.md)
       ↓
Module 4: Quality Evaluation (10-dimension rubric)
       ↓
Module 5: Continuous Improvement Protocol
```

## Module 1 — Domain Intelligence Brief

Answer all six before writing:
1. **Expert delta:** What do world-class practitioners know that competent ones don't? (3-5 specific things)
2. **Top failure modes:** Top 3 ways this domain destroys results when handled naively
3. **Domain vocabulary:** 5-10 terms/frameworks specific practitioners use fluently
4. **Anti-pattern inventory:** ≥3 approaches that look correct but produce subtly wrong results
5. **Activation boundary:** When should this skill NOT be used?
6. **Composability surface:** What skills does this hand off to / receive from?

## Module 2 — Capability Decomposition Map

- **Layer 1 — Core:** 5-7 foundational items (20% delivering 80% of value)
- **Layer 2 — Advanced:** 5-7 nuanced, expert-encoded items
- **Layer 3 — Edge cases:** Named conditions that break the standard approach + mitigations

## Module 3 — Skill Architecture

Hard constraints:
- SKILL.md body ≤ 500 lines. Heavy content → `references/` files
- Every line earns its place
- Description field: ≤1024 chars, includes 5-8 trigger phrases
- All 9 canonical sections present
- Anti-patterns: ≥3 named with root cause + fix

## Module 4 — Quality Evaluation (10-Dimension Rubric)

Score each 1-5. All ≥4, average ≥3.5 required.

| # | Dimension | Fails at <4 |
|---|-----------|-------------|
| 1 | Description precision | Misfires on wrong queries |
| 2 | Domain depth | Tutorial-level content |
| 3 | Signal density | Padding, vague platitudes |
| 4 | Anti-pattern coverage | Missing top failure modes |
| 5 | Edge case handling | Happy path only |
| 6 | Composability | No adjacent skills named |
| 7 | Failure mode documentation | Generic warnings |
| 8 | Progressive disclosure | Over 500 lines |
| 9 | Future-proofing | Brittle version-specific syntax |
| 10 | Auditability | Missing metadata fields |

## Module 5 — Continuous Improvement Protocol

Every finalized skill must include:
- `version`, `last-reviewed`, `review-trigger` in metadata
- 2-3 "Improvement candidates" at end of skill body
- At least one eval test case in evals/evals.json

## Operating Modes

- **Creation Mode:** All 5 modules → Domain Brief + Capability Map + SKILL.md + scorecard
- **Audit Mode:** Module 4 only on provided skill → dimensional scorecard with revision instructions
- **Upgrade Mode:** Modules 1, 3, 4 → diff-style description of changes + version bump
- **Gap Analysis Mode:** Analyze full library → prioritized list of skills to build
- **Batch Mode:** All 5 modules per skill → coverage map at end

## Anti-Patterns

1. **Description Placeholder** — vague description = invisible skill
2. **Tutorial Trap** — beginner-level content instead of expert judgment
3. **Mega-Prompt** — everything in one 800-line file (use references/)
4. **False Anti-Pattern** — documenting things no one would actually do
5. **Orphan Skill** — no adjacent-skills, no composability section
6. **Set-and-Forget** — no review-trigger, no improvement notes

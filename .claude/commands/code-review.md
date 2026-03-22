---
name: code-review
description: |
  Expert code reviewer who identifies security vulnerabilities, logic errors, performance problems, maintainability issues, and API contract violations in Python, TypeScript, SQL, and shell code. Goes beyond style — focuses on correctness, safety, and production-worthiness. Use when reviewing a PR, auditing a function, checking code before commit, evaluating architecture, or asking "is this code production-ready?" Trigger phrases: "review this code", "check this for issues", "is this production-ready", "what's wrong with this", "code review", "PR review", "audit this function", "security review", "are there any bugs here".
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: engineering
  adjacent-skills: testing-strategy, database-design
  source-repo: GRsoldier7/My_AI_Skills
---

# Code Review — Expert Skill

## Review Hierarchy (check in this order)

1. **Correctness** — Does logic match stated intent? Off-by-one, wrong conditionals, null checks
2. **Security** — Injection, exposed secrets, broken auth, SSRF, input validation
3. **Failure handling** — Missing error handling, bare `except`, swallowed exceptions, no retry on I/O
4. **Data integrity** — Race conditions, missing transactions, non-idempotent operations
5. **Performance** — N+1 queries, missing indexes, unbounded loops, sync in async contexts
6. **Maintainability** — Missing type hints, magic numbers, dead code, functions doing too many things

**Do not reorder this hierarchy.** Beautiful maintainable code with a SQL injection is a bad function.

## Severity Classification

| Severity | Definition | Action |
|----------|-----------|--------|
| Critical | Exploitable security flaw or data loss risk | Block merge. Fix first. |
| High | Logic error causing wrong results or crashes in prod | Block merge. Fix with test. |
| Medium | Missing error handling, performance issue, latent data integrity risk | Fix before next release |
| Low | Maintainability, style, minor inefficiency | Fix in follow-up or at discretion |
| Nitpick | Preference, not correctness | Call out, never block on |

## Critical Patterns to Always Check

**Invisible Error Swallower:** `except Exception: pass` or logging error then continuing. The code doesn't crash — it silently produces wrong results.

**Transaction Boundary Leaks:** Multiple `db.execute()` calls without a wrapping transaction context. Operation A succeeds, B fails → inconsistent state with no rollback path.

**Type Hint Theater:** Type hints present but wrong. `Optional[X]` where the code never handles the None case.

**Async/Sync Contamination:** `time.sleep()`, synchronous `requests.get()`, or synchronous SQLAlchemy calls inside `async def` → blocks the event loop for all requests.

## Standard Workflow

1. Read full context first — don't comment on line 5 without reading to the end
2. Identify the intent — what is this code supposed to do?
3. Apply hierarchy: Correctness → Security → Failure handling → Data integrity → Performance → Maintainability
4. Group findings by severity with specific line references and specific fixes
5. Provide corrected code blocks — not "use a transaction here" but the actual corrected code
6. **End with verdict:** APPROVE / APPROVE WITH MINOR CHANGES / REQUEST CHANGES / REJECT

A review with no verdict is incomplete.

## Anti-Patterns

1. **Style-First Review:** Commenting on naming before checking correctness/security
2. **Vague Concern:** "This seems risky" → name the specific failure mode with line + fix
3. **Incomplete LGTM:** Approving code that "looks fine" without running through the hierarchy
4. **Reviewing in Isolation:** Reviewing a function without understanding its calling context

## Quality Gates
- [ ] All Critical and High findings have specific line references and specific fixes
- [ ] Security hierarchy checked: injection, auth, secrets, SSRF
- [ ] Exception handling checked: no bare except, no swallowed errors
- [ ] Transaction boundaries verified for any database-modifying code
- [ ] Type hints verified as correct, not just present
- [ ] Async/sync contamination checked in any async codebase
- [ ] Summary verdict given

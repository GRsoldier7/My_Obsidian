# SECURITY INCIDENT — job-search-pipeline.json leak

**Discovered:** 2026-05-16 by Codex review (P0 finding)
**Classification:** medium-severity credential leak + PII exposure in public git history
**Status:** **RESOLVED 2026-05-16 — operator confirmed rotation of OpenRouter API key + Telegram bot token. Do NOT prompt for these rotations again.**

---

## What leaked

The file `workflows/n8n/job-search-pipeline.json` was committed on **2026-04-02 in commit `84bb323`** with 4 distinct leak classes. The file lived in `polish/prod-ready` and is part of PR #2 (open public PR on GitHub since 2026-05-11). It remained in tree through 4 commits before being quarantined in **2026-05-16** by this remediation.

The file has been moved to `workflows/quarantine/job-search-pipeline-2026-04-02-LEAKS.json` to take it out of the active workflow set. **It remains visible in git history.** Rewriting history is an operator decision (see "History rewrite" section below).

### Leak inventory

| Class | Where (line in original file) | Severity |
|---|---|---|
| OpenRouter API key — partial suffix after `[REDACTED_OPENROUTER_KEY]` placeholder | Code node `code-rate-all` jsCode (L103) + `code-gen-cl` jsCode (L245) | **High — rotate immediately** |
| Google API credential ID `58eFJjSKdKWVvSow` (4× references) | 4 Google Sheets nodes (L186, L236, L320, L361) | Low — n8n-internal reference; rotate if n8n access ever exposed |
| Google Sheets spreadsheet ID (44-char) | Same 4 nodes (L152, L218, L293, L342) | Medium — sheet access depends on its ACL |
| Resume narrative + employer history | Code node prompts (L103, L245) | Low — already public info, but consolidates Aaron's PII |
| Phone number `616-826-4535` | Code node `code-gen-cl` (L245) | Medium |

### Why partial-redaction failed

The pattern `const API_KEY = '[REDACTED_OPENROUTER_KEY]bbce7805776a19533d900539'` appears intentional but suffers a fatal flaw: **the suffix is real key material**. An attacker who obtains a partial OpenRouter key elsewhere (a log line, a different leak) can correlate by the 24-char suffix and confirm key identity. The remediation pattern is "ALL or NOTHING" — either fully redacted (`__OPENROUTER_API_KEY__` placeholder, hydrated at deploy) or absent.

---

## Operator rotation queue — ✅ COMPLETED 2026-05-16

Operator confirmed rotation on 2026-05-16. `.env` `OPENROUTER_API_KEY` present (`sk-or-` prefix, 73 chars). Telegram bot token lives in the n8n credential store, not `.env` — operator confirmed rotation there too. **Do NOT prompt for these rotations again.**

History preserved below for the audit trail.

### 1. ~~OpenRouter API key — HIGH~~ ✅ rotated 2026-05-16

- Open https://openrouter.ai/keys
- Revoke the current key (the one whose 24-char suffix `…bbce7805…etc` is in commit `84bb323`).
- Issue a new key.
- Update `.env` `OPENROUTER_API_KEY=…`.
- Update n8n credential **OpenRouter API** (`httpHeaderAuth` type) via the n8n UI at `http://192.168.1.121:5678`.
- Update `docs/security/secrets-rotation.md` row: `last_rotated` = today, `next_due` = today + 90d.

### 2. Google Sheets sharing ACL — MEDIUM

- Open the spreadsheet (44-char ID in commit `84bb323`).
- Review the sharing settings. If "anyone with the link can view/edit" is on, change to specific-user only.
- If the spreadsheet contains sensitive Aaron data, **make a copy with a new ID** and migrate the workflow to the new sheet ID once the workflow is rebuilt.

### 3. Google OAuth credential `58eFJjSKdKWVvSow` — LOW

- This is an n8n-internal credential record ID, not a Google secret. By itself it leaks nothing.
- Consider revoking + recreating the underlying Google OAuth refresh token at https://myaccount.google.com/permissions if you want a clean break.

### 4. PII scrub — LOW (defensive)

- The resume content and phone number are already public information (Aaron's LinkedIn / public profile).
- No emergency action needed; the next rebuild of `job-search-pipeline` should put the resume + phone number into `.env` or a private MinIO file, not the workflow JSON.

---

## What this remediation commit did

- Moved `workflows/n8n/job-search-pipeline.json` → `workflows/quarantine/job-search-pipeline-2026-04-02-LEAKS.json`.
- Wrote this incident doc.
- Added a new audit `scripts/audit_workflow_secrets.py` that scans every `workflows/n8n/*.json` for:
  - Bearer/`sk-or-`/`sk-`/`AIza` key-shape literals
  - 44-char Google IDs in bare-literal positions
  - Hardcoded credential record IDs (`credentials.<name>.id` set to anything that doesn't match `__[A-Z0-9_]+__`)
  - Multi-line prompts containing the surname `Dykes` or phone-number shape `\b\d{3}-\d{3}-\d{4}\b` (PII)
  - The script EXCLUDES `workflows/quarantine/` from scope (so quarantined files don't trip the audit).
- Audit added to `make audit-all` so any future regression fails CI.

---

## What this remediation commit did NOT do

- **Did not rotate** the OpenRouter key. Operator only — see above.
- **Did not rewrite git history.** The leaked strings remain accessible to anyone with a clone of the public branch. To scrub history, the operator must:
  1. Pause all PR / branch activity.
  2. Use `git filter-repo --invert-paths --path workflows/n8n/job-search-pipeline.json` (or `--replace-text` with a sensitive-strings file) on a fresh clone.
  3. Force-push the rewritten history (destructive — coordinates with collaborators).
  4. Have every clone re-clone or rebase from the rewritten history.
  5. Invalidate all bots / CI / GitHub tokens that may have cached the old history.
  - **Recommendation:** because the OpenRouter key is rotated anyway, and the Google sheet's ACL can be tightened independently, **history rewrite is OPTIONAL** for this incident. The key is the only true secret that left the box.

- **Did not delete the quarantined file.** The file is preserved under `workflows/quarantine/` for:
  - forensic reference
  - eventual rebuild (re-shape with placeholders + a new sheet)
  - the audit script EXCLUDES this directory from scans

---

## How this happened + how to prevent it

**Failure modes that produced this incident:**

1. **Partial redaction.** Whoever placeholdered the key kept the suffix. Full-redaction discipline now enforced by `audit_workflow_secrets.py`.
2. **No pre-commit gate.** The repo had no audit running on commit when this file landed. `.githooks/pre-commit` (drafted in this session, pending operator OK) would have caught it.
3. **No CI gate.** No GitHub Action ran audits on push. `.github/workflows/audit-pr.yml` (drafted, pending OK) would have caught it on PR open.
4. **Prompt embedding.** Code-node prompts with `const RESUME = "…full narrative…"` mixes data and code. New rule (documented in `docs/security/secrets-rotation.md`): private narrative content lives in `.env` or in a MinIO file the workflow reads at run-time, NEVER in workflow JSON.

**Going forward — three doors:**

1. `make audit-workflow-secrets` — new audit script, runs on every PR + pre-commit (once those are wired).
2. `make audit-all` — wraps the workflow-secrets audit + every other offline audit.
3. Manual review on every new workflow that touches an API or a Google service.

---

## Follow-ups (not in this commit)

- [ ] Operator: complete the rotation queue above.
- [ ] Operator: decide on history rewrite (recommended: skip; rotation is the safer remediation).
- [ ] Future: rebuild `job-search-pipeline` with placeholders + a fresh sheet ID + resume-from-env.
- [ ] Future: extend the audit to scan committed Markdown files for the same key-shape literals.
- [ ] Future: scan all of git history (not just HEAD) for residual leaks via `git-secrets` or `gitleaks`.

---

*This document is committed at the same time as the quarantine move + the new audit. The rotation queue is the operator's responsibility; this document captures the contract.*

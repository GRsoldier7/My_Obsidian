# P1 Integrity Layer — Completion + Operator Handoff — 2026-05-03

**Branch:** `polish/prod-ready`
**Final commit (this session):** `947e507`
**Total commits this session:** 13 (`2b518b1` through `947e507`)
**Outcome:** P1 architecturally complete on the codebase side. Step 6c (LXC deploy + workflow reactivation) is the only remaining operator action.

---

## Final state — VERIFIED via tool output

| Check | Result |
|---|---|
| pytest | **240 pass, 1 skip** (was 189 pre-session) |
| Workflow audits (4 scripts) | all green |
| Receipt audit (`audit_extraction_receipts.py`) | clean, 0 findings |
| Brain-dump source frontmatter (11 files) | canonical 8-field schema, hash-consistent |
| n8n brain-dump-processor-v2 | DEACTIVATED pending LXC deploy |
| Local memory | 11 files in `~/.claude/projects/.../memory/` |
| NotebookLM authoritative notebook | `a428969b-…` reachable, holds session logs |

---

## Codebase deliverables (this session)

### Architecture
- [docs/adr/0005-brain-dump-state-machine-and-receipts.md](../adr/0005-brain-dump-state-machine-and-receipts.md) — 482-line opinionated ADR

### Pure-function logic kernel
- [tools/bd_integrity.py](../../tools/bd_integrity.py) — state machine, hashing, receipts, gated reset (no I/O)
- [tests/test_brain_dump_integrity.py](../../tests/test_brain_dump_integrity.py) — 28 pure-function tests (incl. 3 drift-prevention guardrails)

### Migration + audits
- [scripts/migrate_brain_dump_frontmatter.py](../../scripts/migrate_brain_dump_frontmatter.py) — dry-run-default frontmatter upgrader
- [scripts/audit_extraction_receipts.py](../../scripts/audit_extraction_receipts.py) — fail-fast 6-rule audit with `--json-output`
- [tests/test_workflow_templates.py](../../tests/test_workflow_templates.py) — added executeCommand + n8n-expression guardrail

### Orchestrator wiring
- [tools/process_brain_dump.py](../../tools/process_brain_dump.py) — `process_file` rewritten to use the integrity layer; `append_tasks_to_mtl` + `append_articles` refactored to return verified-status dicts (load-bearing for the gates)
- [tests/test_brain_dump_orchestrator.py](../../tests/test_brain_dump_orchestrator.py) — 6 mock-S3 integration tests proving the gates fire correctly under MTL fail / articles fail / receipt fail / archive fail / --no-reset / clean-run scenarios

### n8n workflows
- [workflows/n8n/brain-dump-processor-v2.json](../../workflows/n8n/brain-dump-processor-v2.json) — refactored from 17 nodes to 7. n8n triggers Python; Python is the single logic kernel. AMBER-pass corrections: dropped n8n-expression `=` prefix, added the bash `${VAR:-default}` syntax check
- [workflows/n8n/vault-health-report.json](../../workflows/n8n/vault-health-report.json) — added a parallel branch (4 nodes) that runs `audit_extraction_receipts.py --json-output` and emails findings only when `findings_count > 0`

### Runbook
- [docs/runbook-deploy-python-to-lxc.md](../runbook-deploy-python-to-lxc.md) — sizing table, inspection block, 5-command activation procedure, failure modes + recovery

### Memory (`~/.claude/projects/.../memory/`)
- 11 files; latest are `project_p0_patterns.md`, `project_p1_implementation_complete.md`, `project_p2_threaded_tasks_spec.md`, `feedback_p1_integrity_first.md`, `reference_foundation_addon.md`, `reference_notebooklm_project_notebook.md`

---

## Operator action items — minimum to go live

1. SSH to LXC CT-202 (192.168.1.121).
2. Run the inspection block from [docs/runbook-deploy-python-to-lxc.md § Inspection](../runbook-deploy-python-to-lxc.md). This is read-only and tells you what's missing in 30 seconds.
3. Per the inspection results, install missing pip packages (`pip3 install --user boto3 openai python-dotenv`).
4. Make the repo accessible at `${OHO_REPO_PATH:-/opt/oho}` (NAS symlink OR rsync from Mac).
5. Smoke test: `cd /opt/oho && set -a && source .env && set +a && python3 -u tools/process_brain_dump.py --dry-run`. Stdout's last block must be valid JSON.
6. Reactivate the n8n workflow: `curl -X POST -H "X-N8N-API-KEY: $N8N_API_KEY" "http://192.168.1.121:5678/api/v1/workflows/1SiacuC68kFgYayV/activate"`.
7. Trigger a manual run from the n8n UI; verify the digest email + a receipt at `99_System/extraction-receipts/` + an archive at `99_System/archive/brain-dumps/<YYYY-MM-DD>/`.

If step 2 reveals anything unexpected (older Python, no NAS mount, etc.), paste the inspection output and we branch from there.

---

## Future work (backlog, not blocking)

| Task | When | Trigger |
|---|---|---|
| **Step 8:** decide whether to deprecate `--no-reset` | ≥7 days post-activation | Audit reports clean, no surprise resets in archives |
| **P2 ADR draft** (threaded tasks) | After P1 stabilizes | Operator's explicit go-ahead — design-first per directive |
| **P3 capture surfaces** (Telegram, email, voice) | After P2 lands | Higher capture volume only valuable on a trusted pipe |
| **P4–P7** (briefings, rituals, domain UX, insight loop) | Sequenced per the v1.0 roadmap | See `project_life_os_v1_roadmap.md` memory |

---

## Anti-hallucination notes (for the next session)

- The 2026-05-03 AMBER pass caught two latent bugs my earlier "verified" claims missed: (1) `migrate_frontmatter` setdefault preserved a stale `last_processed`; (2) `=` prefix on the executeCommand mixed n8n-expression and bash syntaxes. **Lesson:** every claim about a state file or workflow JSON should be re-read from disk, not paraphrased from memory, especially as session length grows.
- Anti-hallucination AMBER discipline is encoded in [.claude/skills/anti-hallucination/SKILL.md](../../.claude/skills/anti-hallucination) (symlink) and the project CLAUDE.md "Anti-hallucination — practical rules" section.
- The receipt audit (R6 + R7) is the live drift-detector. Run it whenever you wonder whether the integrity layer is in a consistent state: `set -a && source .env && set +a && python3 scripts/audit_extraction_receipts.py`.

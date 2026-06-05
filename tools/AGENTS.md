# tools/ — Python Logic Kernel

## Purpose
Pure logic + verified-I/O primitives the Life OS runs on. Consumed by both the
Python processors and the n8n workflows (via the oho-runner sidecar). This dir
owns extraction, integrity, privacy, task identity, and dashboard rendering. It
does **not** own scheduling (n8n/cron), deploy orchestration (`scripts/`), or
the vault itself (MinIO).

## Entry Points
- `process_brain_dump.py` — section-aware brain-dump processor (the orchestrator; does real S3 I/O + OpenRouter). 85k file — the heaviest in the repo.
- `build_command_center.py` — ADR-0006 single landing page (`000_Master Dashboard/!!! DAILY COMMAND CENTER.md`). Locked section structure.
- `bd_integrity.py` — pure-function integrity kernel (state machine, content-hash receipts, `slug_for_filename`). **No I/O.**
- `s3_verified.py` — single source of truth for verified S3 writes.
- `privacy_classifier.py` + `egress_guard.py` — ADR-0008 deny-list on the AI egress path.
- `task_id.py` — ADR-0009 stable task IDs.

## Contracts & Invariants
- **`bd_integrity.py` stays pure — no I/O, ever.** It's the single logic kernel both Python and the n8n workflow consume; same input → same output regardless of executor. Putting an S3/HTTP call here lets Python and n8n drift apart silently.
- **All S3 writes go through `s3_verified.py`** (exact byte-length / byte-exact readback; `IfMatch` for read-modify-write). Do not hand-roll a put+head_object sequence — that's the divergence `s3_verified` was created to kill (2026-05-16 Codex P1).
- **NO `Homelab/` prefix** on any vault key. Objects live at `obsidian-vault` bucket root.
- **Egress gate:** any new AI/broker egress must route through `egress_guard.py`. `faith` / `family-named` / `kid-named` / `health-biomarker` classes NEVER egress without explicit `allow_egress_to`. Classifier rules are first-match-wins in declared tier order (`infra/data-classes.yaml`).
- **Receipt-stem derivation lives only in `bd_integrity.slug_for_filename`** so the audit and the writer can never disagree.
- **Task IDs** are `t-YYYYwNN-XXXX` (ISO-year `%G` + ISO-week `%V` + 4-hex of sha256(area+desc+created_at)). Don't invent another ID scheme.
- Builders (`build_command_center`, `build_health_dashboard`) are **idempotent + verified-write** — safe to re-run.

## Status Markers (read the module docstring before wiring anything)
Each file's docstring carries a status line — honor it:
- **SKELETON** (`privacy_classifier`, `build_health_dashboard`) — `SKELETON_MODE = True`; phase-gated, may be on a `feature/*` branch. Not production-live.
- **MANUAL-ONLY** (`build_pipeline_health`, `write_processed_readme`) — no cron, no oho-runner, 0% test coverage by design. Promote to LIVE-UNTESTED + add a pytest module **before** scheduling.
- Default: extraction is **regex-primary** (zero cost); AI (OpenRouter) is fallback only.

## Anti-patterns
- Don't add I/O to `bd_integrity.py` (see above).
- Don't write to S3 outside `s3_verified.py`.
- Don't add AI egress that bypasses `egress_guard.py`.
- Don't schedule a SKELETON or MANUAL-ONLY tool into a cron slot before it has tests.
- Don't break the canonical task format `- [ ] … [area:: x] [priority:: A] [due:: YYYY-MM-DD]` — every Dataview query depends on it.

## Related Context
- Root rules + cron-slot map + credential-family rule: `../CLAUDE.md`
- Tests (per-key `head_object` mock pattern is required when touching `s3_verified`): `../tests/`
- Audits that enforce these invariants: `../scripts/audit_*.py`

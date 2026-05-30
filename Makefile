# ObsidianHomeOrchestrator Makefile
# Run: make <target>
# All targets that need secrets: set -a && source .env && set +a first
#   OR: make target ENV=1  (auto-sources .env if ENV=1)
#
# Quick reference:
#   make setup          — validate env + deploy all n8n workflows
#   make test           — run unit tests (no network required)
#   make e2e            — run end-to-end test against live MinIO
#   make health         — ping MinIO, n8n, vault files
#   make validate-env   — check all required env vars
#   make coverage       — unit tests with coverage report
#   make deploy         — full deploy: validate + setup + health check
#   make verify         — fast pre-PR gate: audit-all + unit tests
#   make audit-ai-tooling — validate AI tooling docs and MCP examples

# Force bash (recipes use `source`, `[[ ]]`, etc.). Without this, GNU Make picks
# /bin/sh — on Debian/Ubuntu that's dash, which has no `source`, no `[[`, no
# arrays. That broke `make ENV=1 health` until 2026-05-16 (Codex review P1).
SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

.PHONY: setup test e2e integration health validate-env coverage deploy verify lint-workflows audit-workflows audit-ai-tooling logs help build-home processed-readme deploy-runner deploy-runner-dry gcal-status gcal-create gcal-finalize backfill-mtl-review backfill-mtl-apply vault-cleanup-review vault-cleanup-apply audit-extraction-receipts audit-data-classes audit-secrets audit-planning-docs audit-workflow-secrets audit-workflow-runlogs audit-workflow-email-format audit-no-executecommand audit-no-argv-secrets audit-no-unverified-put-object audit-egress-classifier-wired audit-slo evals audit-all audit-ci hooks-install bootstrap-dev

PYTHON := python3
# Always invoke pytest via the same interpreter as PYTHON — avoids the case
# where `pytest` on $PATH is from a different venv than the project's python.
PYTEST := $(PYTHON) -m pytest

# Auto-source .env if ENV=1 is set
ifeq ($(ENV),1)
ENV_PREFIX := set -a && source .env && set +a &&
else
ENV_PREFIX :=
endif

# ── Primary targets ───────────────────────────────────────────────────────────

## Setup: validate env then deploy all workflows to n8n
setup: validate-env audit-workflows
	@echo "→ Deploying workflows to n8n..."
	$(ENV_PREFIX) bash scripts/setup-n8n.sh
	@echo "✓ Setup complete. Run 'make health' to verify."

## Run unit tests (no network, no secrets required)
test:
	$(PYTEST) tests/ -v --ignore=tests/test_process_brain_dump_e2e.py \
		-k "not integration" \
		--tb=short

## Run all tests including e2e (requires live MinIO + n8n)
e2e:
	$(ENV_PREFIX) $(PYTHON) scripts/e2e_test.py

## Run integration test suite (requires live stack + RUN_INTEGRATION_TESTS=1)
integration:
	$(ENV_PREFIX) RUN_INTEGRATION_TESTS=1 $(PYTEST) tests/ -v -m integration --tb=short

## Check MinIO, n8n, and vault files are healthy
health:
	$(ENV_PREFIX) $(PYTHON) scripts/health_check.py

## Check all required env vars are set
validate-env:
	$(ENV_PREFIX) $(PYTHON) scripts/validate_env.py

## Run unit tests with coverage report (target: ≥80% on tools/)
coverage:
	COVERAGE_FILE=/tmp/.oho_coverage $(PYTEST) tests/ --cov=tools --cov-report=term-missing \
		-k "not integration" \
		--tb=short

## Full deploy: validate + setup + health + e2e
deploy: validate-env audit-workflows setup health e2e
	@echo "✓ Full deploy complete — all checks passed."

# ── Workflow targets ──────────────────────────────────────────────────────────

## Validate all workflow JSON files are valid JSON
lint-workflows:
	@echo "→ Validating workflow JSONs..."
	@for f in workflows/n8n/*.json; do \
		$(PYTHON) -c "import json; json.load(open('$$f'))" && echo "  OK: $$f" || echo "  FAIL: $$f"; \
	done
	@echo "✓ Lint complete."

## Enforce a single supported MinIO credential family across all workflows
audit-workflows:
	@echo "→ Auditing workflow credential consistency..."
	@$(PYTHON) scripts/audit_workflow_credentials.py
	@$(PYTHON) scripts/audit_workflow_connections.py

# ── AI tooling targets ───────────────────────────────────────────────────────

## Validate AI tooling docs, agent instructions, and MCP examples
audit-ai-tooling:
	@$(PYTHON) scripts/audit_ai_tooling.py

# ── Operational targets ───────────────────────────────────────────────────────

## Pretty-print a workflow run-log from MinIO. Defaults: today's
## brain-dump-processor. Override:
##   make ENV=1 logs WORKFLOW=daily-note-creator
##   make ENV=1 logs WORKFLOW=link-enricher DATE=2026-05-25
##   make ENV=1 logs WORKFLOW=morning-briefing LIST=1     # list available dates
WORKFLOW ?= brain-dump-processor
DATE ?=
LIST ?=
logs:
	$(ENV_PREFIX) $(PYTHON) scripts/tail_log.py \
		--workflow $(WORKFLOW) \
		$(if $(DATE),--date $(DATE)) \
		$(if $(LIST),--list)

## Run brain dump processor manually (verbose)
run:
	$(ENV_PREFIX) $(PYTHON) tools/process_brain_dump.py --verbose

## Dry-run brain dump processor (no S3 writes)
dry-run:
	$(ENV_PREFIX) $(PYTHON) tools/process_brain_dump.py --dry-run --verbose

## Rebuild the daily command center (ADR-0006). Verified write to MinIO.
build-home:
	$(ENV_PREFIX) $(PYTHON) tools/build_command_center.py

## Drop / refresh the audit-only README in 00_Inbox/processed/. Idempotent.
processed-readme:
	$(ENV_PREFIX) $(PYTHON) tools/write_processed_readme.py

## Render the Wave-X H3 health dashboard at 99_System/health.md.
## Rolls up the last 14 days of run-logs from MinIO into one human pane.
health-dashboard:
	$(ENV_PREFIX) $(PYTHON) tools/build_health_dashboard.py

## End-to-end LXC sidecar deploy (DRY-RUN — no changes; preview the plan).
deploy-runner-dry:
	$(ENV_PREFIX) $(PYTHON) scripts/deploy_oho_runner.py

## End-to-end LXC sidecar deploy (APPLY — performs SSH + docker compose + n8n API calls).
deploy-runner:
	$(ENV_PREFIX) $(PYTHON) scripts/deploy_oho_runner.py --apply

# ── GCAL OAuth setup (one-time) ────────────────────────────────────────────────

## GCAL OAuth — print current state + next action (PATH A or PATH B).
gcal-status:
	$(ENV_PREFIX) $(PYTHON) scripts/setup_gcal_oauth.py

## GCAL OAuth — create the n8n credential shell (PATH A; requires GOOGLE_CLIENT_ID+SECRET in .env).
gcal-create:
	$(ENV_PREFIX) $(PYTHON) scripts/setup_gcal_oauth.py --create

## GCAL OAuth — after operator completes Google consent in n8n UI, write GCAL_CRED_ID to .env.
gcal-finalize:
	$(ENV_PREFIX) $(PYTHON) scripts/setup_gcal_oauth.py --finalize

# ── Hygiene B4: MTL metadata backfill (ADR-0007) ──────────────────────────────

## MTL backfill — dry-run / review-only. Writes a triage report to MinIO; never modifies MTL.
backfill-mtl-review:
	$(ENV_PREFIX) $(PYTHON) scripts/backfill_mtl_metadata.py --review-only --verbose

## MTL backfill — apply TODO markers on closed_no_completion tasks. Backs up canonical MTL first.
##  Always run `make backfill-mtl-review` first and triage the report before this target.
backfill-mtl-apply:
	$(ENV_PREFIX) $(PYTHON) scripts/backfill_mtl_metadata.py --apply --verbose

# ── Vault cleanup (UI audit 2026-05-27 win #3) ────────────────────────────────

## Vault cleanup — review-only. Lists top-level cruft + writes JSON plan to stdout.
##   - 6 rs-test-folder-* + Daily/ + Homelab/ + Scripts/ + numbered placeholders → DELETE
##   - ! TO DO/ (3 keys) → ARCHIVE to 09_Archives/cruft-<date>/
##   - 0-byte 2026-05-10.md at root → DELETE
##   No writes. Safe to run anytime.
vault-cleanup-review:
	$(ENV_PREFIX) $(PYTHON) scripts/vault_cleanup.py

## Vault cleanup — APPLY. Archives content cruft + deletes empty-folder markers +
## writes a vault-root README.md (verified). Always review first.
vault-cleanup-apply:
	$(ENV_PREFIX) $(PYTHON) scripts/vault_cleanup.py --apply

# ── Soak audit (P0.5 / ADR-0005) ──────────────────────────────────────────────

## Daily soak audit — extraction receipts integrity. Must be green for ≥7 days before Phase C.
audit-extraction-receipts:
	$(ENV_PREFIX) $(PYTHON) scripts/audit_extraction_receipts.py

# ── Phase F prep audits (ADR-0007 / ADR-0008) ─────────────────────────────────

## Enforce the infra/data-classes.yaml contract (privacy classifier source-of-truth).
audit-data-classes:
	$(PYTHON) scripts/audit_data_classes.py --strict

## Surface overdue + upcoming secret rotations from docs/security/secrets-rotation.md.
audit-secrets:
	$(PYTHON) scripts/audit_secrets_rotation.py

## Verify every ADR/spec/phase cross-reference resolves; flag missing **Status:** lines.
audit-planning-docs:
	$(PYTHON) scripts/audit_planning_docs.py --allow-orphans

## Scan n8n workflow JSONs for hardcoded secrets/IDs/PII (born from 2026-05-16 incident).
audit-workflow-secrets:
	$(PYTHON) scripts/audit_workflow_secrets.py

## Enforce canonical skip_reason enum + status:"skipped" always carries a reason.
audit-workflow-runlogs:
	$(PYTHON) scripts/audit_workflow_runlogs.py

## Enforce emailSend top-level emailFormat=html (n8n 2.13.4 silent-blank-email bug).
audit-workflow-email-format:
	$(PYTHON) scripts/audit_workflow_email_format.py

## Block n8n-nodes-base.executeCommand regressions (P1.5 / vault-health-report breakage).
## As of 2026-05-29 vault-health-report.json migrated to httpRequest against the
## /audit-receipts runner endpoint; allowlist is empty.
audit-no-executecommand:
	$(PYTHON) scripts/audit_no_executecommand.py

## Block argv-secret-leak regressions (Codex P0 #2). setup-n8n.sh + deploy_oho_runner.py
## allowlisted until their post-soak argv-hygiene refactors land.
## Block new unverified s3.put_object() call sites (Codex P1 / item 13 migration guard).
## Known violators allowlisted; remove from allowlist as each file migrates to s3_verified.*.
audit-no-unverified-put-object:
	$(PYTHON) scripts/audit_no_unverified_put_object.py

audit-no-argv-secrets:
	$(PYTHON) scripts/audit_no_argv_secrets.py --allowlist setup-n8n.sh --allowlist deploy_oho_runner.py

## Block unguarded OpenRouter calls (ADR-0008 wiring regression guard).
## Every `chat.completions.create` site must be preceded by `egress_guard.guard_for_peer`.
audit-egress-classifier-wired:
	$(PYTHON) scripts/audit_egress_classifier_wired.py

## Wave-X H3 SLO conformance skeleton (post-soak: --apply turns on MinIO read).
audit-slo:
	$(PYTHON) scripts/audit_slo_conformance.py

## Run the eval harness in schema-only mode (no classifier yet; Phase F gates the runtime pass).
evals:
	$(PYTHON) scripts/run_evals.py

## Run every offline audit in one shot (use as a pre-merge gate).
## `audit-extraction-receipts` deliberately NOT included — it needs live MinIO
## and runs as a separate daily soak signal, not on every PR.
audit-all: audit-workflows audit-ai-tooling audit-data-classes audit-secrets audit-planning-docs audit-workflow-secrets audit-workflow-runlogs audit-workflow-email-format audit-no-executecommand audit-no-argv-secrets audit-no-unverified-put-object audit-egress-classifier-wired audit-slo
	@echo "✓ All offline audits passed."

## Pre-PR gate (local): every offline audit + unit tests. ≤30s on a warm cache.
verify: audit-all
	$(PYTEST) tests/ -q --tb=short \
		--ignore=tests/test_process_brain_dump_e2e.py \
		-k "not integration"
	@echo "✓ make verify passed — safe to PR."

## CI entry point (consumed by .github/workflows/audit-pr.yml). Wraps audit-all
## + evals schema check + unit tests. Single source of truth — local `make
## verify` and CI both ultimately run the same audit suite. If CI drifts from
## local, this is the single line to inspect.
audit-ci: audit-all evals
	$(PYTEST) tests/ -q --tb=short \
		--ignore=tests/test_process_brain_dump_e2e.py \
		-k "not integration"
	@echo "✓ audit-ci passed."

# ── Developer environment bootstrap ───────────────────────────────────────────

## Install dev dependencies + activate the per-clone pre-commit hook.
## Run once after cloning. Idempotent. Use after pulling new dev deps too.
bootstrap-dev:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt
	$(MAKE) hooks-install
	@echo "✓ dev environment ready (deps installed + pre-commit hook active)."

## Activate the .githooks/pre-commit hook for THIS clone (git config core.hooksPath).
## Idempotent — safe to re-run. Operator-owned: never bypassable across clones.
hooks-install:
	@if [ ! -d .githooks ]; then \
		echo "✗ .githooks/ missing — wrong directory or stale clone"; exit 1; \
	fi
	git config core.hooksPath .githooks
	@echo "✓ pre-commit hook active (core.hooksPath=.githooks)."
	@git config --get core.hooksPath

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "ObsidianHomeOrchestrator — available targets:"
	@echo ""
	@echo "  make setup          Validate env + deploy all workflows to n8n"
	@echo "  make test           Unit tests (no network)"
	@echo "  make e2e            End-to-end test against live MinIO"
	@echo "  make integration    Integration tests (RUN_INTEGRATION_TESTS=1)"
	@echo "  make health         Ping MinIO, n8n, vault files"
	@echo "  make validate-env   Check required env vars"
	@echo "  make coverage       Unit tests with coverage report"
	@echo "  make deploy         Full deploy: validate + setup + health + e2e"
	@echo "  make lint-workflows Validate all workflow JSONs"
	@echo "  make audit-workflows Block mixed awsS3/s3 credential families"
	@echo "  make audit-ai-tooling Validate AI tooling docs and MCP examples"
	@echo "  make logs           Tail today's brain-dump-processor log"
	@echo "  make run            Run processor manually (verbose)"
	@echo "  make dry-run        Processor dry-run (no S3 writes)"
	@echo "  make build-home     Rebuild !!! DAILY COMMAND CENTER.md (ADR-0006)"
	@echo "  make deploy-runner-dry   Preview LXC sidecar deploy plan (no changes)"
	@echo "  make deploy-runner       Run the LXC sidecar deploy end-to-end"
	@echo "  make processed-readme  Drop audit-only README in 00_Inbox/processed/"
	@echo "  make backfill-mtl-review  MTL backfill dry-run + review report (HYG-B4)"
	@echo "  make backfill-mtl-apply   MTL backfill — write TODO markers (post-review only)"
	@echo "  make audit-extraction-receipts  Daily soak audit (ADR-0005)"
	@echo "  make audit-data-classes      Enforce infra/data-classes.yaml contract (ADR-0008)"
	@echo "  make audit-secrets           Overdue + upcoming secret rotations"
	@echo "  make audit-planning-docs     ADR / spec / phase cross-ref integrity"
	@echo "  make audit-workflow-secrets  Scan n8n workflow JSONs for hardcoded creds/IDs/PII"
	@echo "  make audit-no-executecommand Block n8n executeCommand regressions (P1.5)"
	@echo "  make evals                   Privacy classifier eval harness (schema-only)"
	@echo "  make audit-workflow-runlogs  skip_reason enum + status:\"skipped\" hygiene"
	@echo "  make audit-workflow-email-format  Block n8n 2.13.4 silent-blank-email bug"
	@echo "  make audit-all               Run every offline audit (pre-merge gate)"
	@echo "  make audit-ci                CI entry point: audit-all + evals + tests"
	@echo "  make verify                  audit-all + unit tests (pre-PR gate)"
	@echo "  make bootstrap-dev           Install dev deps + activate pre-commit hook"
	@echo "  make hooks-install           Activate .githooks/pre-commit for THIS clone"
	@echo ""
	@echo "  Tip: prefix with ENV=1 to auto-source .env:"
	@echo "    make ENV=1 health"
	@echo ""

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
#   make audit-ai-tooling — validate AI tooling docs and MCP examples

.PHONY: setup test e2e health validate-env coverage deploy lint-workflows audit-workflows audit-ai-tooling logs help build-home processed-readme deploy-runner deploy-runner-dry backfill-mtl-review backfill-mtl-apply audit-extraction-receipts audit-data-classes audit-secrets audit-planning-docs evals audit-all

PYTHON := python3
PYTEST := pytest

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

## Tail today's brain-dump-processor log from MinIO
logs:
	$(ENV_PREFIX) $(PYTHON) -c "\
import boto3, json, os, datetime; \
from botocore.client import Config; \
s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'], \
    aws_access_key_id=os.environ['MINIO_ACCESS_KEY'], \
    aws_secret_access_key=os.environ['MINIO_SECRET_KEY'], \
    config=Config(signature_version='s3v4'), region_name='us-east-1'); \
today = datetime.date.today().strftime('%Y-%m-%d'); \
key = f'99_System/logs/brain-dump-processor-{today}.json'; \
log = s3.get_object(Bucket=os.environ.get('MINIO_BUCKET','obsidian-vault'), Key=key)['Body'].read(); \
print(json.dumps(json.loads(log), indent=2))"

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

## End-to-end LXC sidecar deploy (DRY-RUN — no changes; preview the plan).
deploy-runner-dry:
	$(ENV_PREFIX) $(PYTHON) scripts/deploy_oho_runner.py

## End-to-end LXC sidecar deploy (APPLY — performs SSH + docker compose + n8n API calls).
deploy-runner:
	$(ENV_PREFIX) $(PYTHON) scripts/deploy_oho_runner.py --apply

# ── Hygiene B4: MTL metadata backfill (ADR-0007) ──────────────────────────────

## MTL backfill — dry-run / review-only. Writes a triage report to MinIO; never modifies MTL.
backfill-mtl-review:
	$(ENV_PREFIX) $(PYTHON) scripts/backfill_mtl_metadata.py --review-only --verbose

## MTL backfill — apply TODO markers on closed_no_completion tasks. Backs up canonical MTL first.
##  Always run `make backfill-mtl-review` first and triage the report before this target.
backfill-mtl-apply:
	$(ENV_PREFIX) $(PYTHON) scripts/backfill_mtl_metadata.py --apply --verbose

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

## Run the eval harness in schema-only mode (no classifier yet; Phase F gates the runtime pass).
evals:
	$(PYTHON) scripts/run_evals.py

## Run every audit in one shot (use as a pre-merge gate).
audit-all: audit-workflows audit-ai-tooling audit-data-classes audit-secrets audit-planning-docs
	@echo "✓ All offline audits passed."

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
	@echo "  make evals                   Privacy classifier eval harness (schema-only)"
	@echo "  make audit-all               Run every offline audit (pre-merge gate)"
	@echo ""
	@echo "  Tip: prefix with ENV=1 to auto-source .env:"
	@echo "    make ENV=1 health"
	@echo ""

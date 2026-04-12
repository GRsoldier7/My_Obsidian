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

.PHONY: setup test e2e health validate-env coverage deploy lint-workflows audit-workflows logs help

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
	@echo "  make logs           Tail today's brain-dump-processor log"
	@echo "  make run            Run processor manually (verbose)"
	@echo "  make dry-run        Processor dry-run (no S3 writes)"
	@echo ""
	@echo "  Tip: prefix with ENV=1 to auto-source .env:"
	@echo "    make ENV=1 health"
	@echo ""

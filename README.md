# ObsidianHomeOrchestrator

Automation and intelligence layer for a Life OS built on Obsidian — powered by n8n, MinIO, and Python running on a self-hosted homelab.

**Brain dumps in → structured tasks out.** Captures from anywhere land in your vault automatically. Dataview shows you the right task at the right time.

---

## What It Does

| Automation | Schedule | What happens |
|------------|----------|--------------|
| Brain Dump Processor | Daily 7AM CDT | Extracts tasks from brain dumps → Master Task List |
| Daily Note Creator | Daily 6AM CDT | Creates today's note pre-populated with due tasks |
| Morning Briefing | Daily 7AM CDT | Rich HTML email: overdue + due today + yesterday captures |
| Weekly Digest | Sunday 6PM CDT | Q2 Rock progress review email |
| Vault Health Report | Sunday 8PM CDT | Inbox health: dump count, article queue, processed count |
| Live Dashboard Updater | Hourly | Updates `000_Master Dashboard/Live Dashboard.md` |
| Link Enricher | Hourly | Enriches article URLs with og:title + description |
| Telegram Capture | Webhook | Instant brain dump / article capture via bot |
| System Health Monitor | Every 6h | Pings MinIO, n8n, OpenRouter; emails on failure |

---

## Architecture

```
Obsidian (Mac)
  ↓ Remotely-Save plugin syncs files
MinIO S3 (192.168.1.240:9000) — bucket: obsidian-vault
  ↕ n8n reads/writes via S3 nodes
n8n (192.168.1.121:5678) — Proxmox LXC CT-202
  ↓ AI extraction (free tier)
OpenRouter → gemma-3-4b → llama-3.3-70b → nemotron-120b cascade
  ↓ alerts
Gmail SMTP
```

**Canonical task format** (Dataview depends on this — never deviate):
```
- [ ] Task description [area:: faith] [priority:: A] [due:: 2026-04-15]
```

---

## Run from Scratch in 10 Minutes

### Prerequisites
- n8n running at `http://192.168.1.121:5678` (or your host)
- MinIO running at `http://192.168.1.240:9000` with bucket `obsidian-vault` created
- Python 3.12+
- `pip install boto3 openai python-dotenv requests pytest pytest-cov`

### 1. Clone and configure

```bash
git clone https://github.com/GRsoldier7/ObsidianHomeOrchestrator
cd ObsidianHomeOrchestrator
cp .env.example .env
```

Edit `.env` — fill in every required variable:

```bash
# MinIO
MINIO_ENDPOINT=http://192.168.1.240:9000
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key
MINIO_BUCKET=obsidian-vault

# OpenRouter (free at openrouter.ai)
OPENROUTER_API_KEY=sk-or-...

# n8n
N8N_HOST=http://192.168.1.121:5678
N8N_API_KEY=your_n8n_api_key        # n8n > Settings > API > Create API Key

# Gmail SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASS=your_gmail_app_password   # NOT your account password — Google > App Passwords
NOTIFICATION_EMAIL=your@gmail.com
```

### 2. Validate environment

```bash
set -a && source .env && set +a
python3 scripts/validate_env.py
```

Expected: `OK — all required vars set`

### 3. Deploy workflows to n8n

```bash
set -a && source .env && set +a
bash scripts/setup-n8n.sh
```

This creates 3 credentials (MinIO, SMTP, OpenRouter) and imports + activates all 11 workflows. Takes ~60 seconds.

### 4. Verify

```bash
set -a && source .env && set +a
python3 scripts/health_check.py    # all [PASS]
python3 scripts/e2e_test.py        # 11/11 checks pass
```

Done. Brain dump processor runs tomorrow at 7AM CDT.

---

## Development

```bash
# Unit tests (no network required)
pytest tests/ -v

# With coverage
pytest --cov=tools tests/ --cov-report=term-missing

# Integration tests (requires live MinIO + OpenRouter)
RUN_INTEGRATION_TESTS=1 pytest tests/ -v -m integration

# Manual brain dump run
set -a && source .env && set +a
python3 tools/process_brain_dump.py --dry-run --verbose
```

---

## Project Layout

```
ObsidianHomeOrchestrator/
├── tools/
│   └── process_brain_dump.py       # Main pipeline (regex-first + OpenRouter cascade)
├── scripts/
│   ├── setup-n8n.sh                # Idempotent deploy: credentials + workflow import
│   ├── validate_env.py             # Fail-fast env checker (run before any deploy)
│   ├── e2e_test.py                 # Full pipeline test against live MinIO
│   └── health_check.py             # Stack health: MinIO + n8n + vault files
├── tests/
│   ├── conftest.py                 # Shared fixtures: moto MinIO, OpenRouter mock
│   ├── test_brain_dump.py          # Unit tests for parsing + extraction functions
│   ├── test_openrouter_cascade.py  # Model fallback chain tests
│   ├── test_s3_roundtrip.py        # Verified-write tests (mocked S3)
│   └── test_process_brain_dump_e2e.py  # Full pipeline integration tests
├── workflows/
│   ├── n8n/                        # v2 workflow JSONs (templates with __PLACEHOLDERS__)
│   └── archive/v1/                 # Superseded v1 workflows (kept for rollback)
├── docs/
│   ├── RUNBOOK.md                  # Operations playbook: credentials, failures, deploy
│   ├── adr/                        # Architecture Decision Records
│   │   ├── 0001-regex-first-extraction.md
│   │   ├── 0002-openrouter-free-tier-cascade.md
│   │   ├── 0003-bucket-root-no-prefix.md
│   │   └── 0004-v2-section-aware-extraction.md
│   └── superpowers/specs/          # Design specifications
├── .env.example                    # Environment variable template
├── CLAUDE.md                       # Claude Code project instructions
└── Makefile                        # make setup / test / e2e / health / deploy
```

---

## Key Rules

- **NO `Homelab/` prefix** — vault files are at MinIO bucket root (ADR-0003)
- **Canonical task format** — all Dataview queries depend on `[area:: X] [priority:: X]`
- **Never commit secrets** — `.env` is gitignored; use `.env.example` as the template
- **Verified writes** — every S3 put calls `head_object` to confirm write succeeded

## Docs

- [RUNBOOK.md](docs/RUNBOOK.md) — operations playbook
- [ADR-0001](docs/adr/0001-regex-first-extraction.md) — regex-first extraction
- [ADR-0002](docs/adr/0002-openrouter-free-tier-cascade.md) — OpenRouter cascade
- [ADR-0003](docs/adr/0003-bucket-root-no-prefix.md) — bucket root (no prefix)
- [ADR-0004](docs/adr/0004-v2-section-aware-extraction.md) — v2 section-aware extraction

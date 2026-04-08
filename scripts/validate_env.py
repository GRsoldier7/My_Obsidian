#!/usr/bin/env python3
"""
scripts/validate_env.py

Loud, fail-fast checker for the environment variables ObsidianHomeOrchestrator
needs. Run this before any deploy or pipeline operation. Exits 0 on success,
1 on missing/empty required vars, 2 on warnings only.

Usage:
    set -a && source .env && set +a && python3 scripts/validate_env.py
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Var:
    name: str
    consumers: str
    required: bool
    notes: str = ""


# Each var documents who reads it. Keep this in sync with .env.example.
REQUIRED_VARS: list[Var] = [
    # ── MinIO S3 ─────────────────────────────────────────────────
    Var("MINIO_ENDPOINT", "process_brain_dump, e2e_test, health_check, n8n", True,
        "default http://192.168.1.240:9000"),
    Var("MINIO_ACCESS_KEY", "process_brain_dump, e2e_test, health_check, setup-n8n", True,
        "MinIO service account access key"),
    Var("MINIO_SECRET_KEY", "process_brain_dump, e2e_test, health_check, setup-n8n", True,
        "MinIO service account secret key"),
    Var("MINIO_BUCKET", "process_brain_dump, e2e_test, health_check", True,
        "default obsidian-vault"),

    # ── OpenRouter ───────────────────────────────────────────────
    Var("OPENROUTER_API_KEY", "process_brain_dump, setup-n8n", True,
        "free tier ok — get one at https://openrouter.ai"),

    # ── n8n ─────────────────────────────────────────────────────
    Var("N8N_HOST", "setup-n8n, e2e_test, health_check", True,
        "default http://192.168.1.121:5678"),
    Var("N8N_API_KEY", "setup-n8n", True,
        "n8n > Settings > API > Create API Key"),

    # ── SMTP ────────────────────────────────────────────────────
    Var("SMTP_HOST", "setup-n8n", True, "default smtp.gmail.com"),
    Var("SMTP_PORT", "setup-n8n", True, "default 587"),
    Var("SMTP_USER", "setup-n8n", True, "your gmail address"),
    Var("SMTP_PASS", "setup-n8n", True,
        "Gmail App Password, NOT account password — required for setup-n8n.sh"),
    Var("NOTIFICATION_EMAIL", "setup-n8n", True,
        "alert destination — usually same as SMTP_USER"),
]

# Optional vars: only warn, never fail.
OPTIONAL_VARS: list[Var] = [
    Var("TELEGRAM_BOT_TOKEN", "telegram-capture workflow", False,
        "create bot via @BotFather; only needed if Telegram capture is in use"),
    Var("TELEGRAM_WEBHOOK_SECRET", "telegram-capture workflow", False,
        "shared secret for X-Telegram-Bot-Api-Secret-Token header"),
    Var("WEBHOOK_URL", "n8n env var, not script env", False,
        "set on Proxmox LXC for webhook URL resolution"),
    Var("N8N_ENCRYPTION_KEY", "n8n env var, not script env", False,
        "32-char random — openssl rand -hex 16"),
    Var("POSTGRES_USER", "external docker-compose", False, ""),
    Var("POSTGRES_PASSWORD", "external docker-compose", False, ""),
    Var("POSTGRES_DB", "external docker-compose", False, ""),
]

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def check(var: Var) -> tuple[bool, str]:
    """Return (is_set, value_preview)."""
    val = os.environ.get(var.name, "")
    if not val:
        return False, ""
    # Mask anything that looks like a secret
    if any(s in var.name.upper() for s in ("KEY", "SECRET", "PASS", "TOKEN")):
        preview = f"{val[:4]}…{val[-2:]}" if len(val) > 6 else "set"
    else:
        preview = val if len(val) <= 60 else val[:57] + "..."
    return True, preview


def main() -> int:
    print(f"{DIM}ObsidianHomeOrchestrator — env validation{RESET}\n")

    missing_required: list[Var] = []
    missing_optional: list[Var] = []

    print(f"{DIM}── Required ──────────────────────────────────────{RESET}")
    for var in REQUIRED_VARS:
        ok, preview = check(var)
        if ok:
            print(f"  {GREEN}✓{RESET} {var.name:24} = {preview}")
        else:
            print(f"  {RED}✗{RESET} {var.name:24} MISSING — {var.notes}")
            missing_required.append(var)

    print(f"\n{DIM}── Optional ──────────────────────────────────────{RESET}")
    for var in OPTIONAL_VARS:
        ok, preview = check(var)
        if ok:
            print(f"  {GREEN}✓{RESET} {var.name:24} = {preview}")
        else:
            print(f"  {YELLOW}·{RESET} {var.name:24} unset — {var.notes}")
            missing_optional.append(var)

    print()
    if missing_required:
        print(f"{RED}FAIL — {len(missing_required)} required var(s) missing:{RESET}")
        for v in missing_required:
            print(f"  • {v.name} (used by: {v.consumers})")
        print(f"\nFix by editing {YELLOW}.env{RESET} (copy from .env.example if needed),")
        print(f"then re-run with:  set -a && source .env && set +a && python3 scripts/validate_env.py")
        return 1

    if missing_optional:
        print(f"{GREEN}OK{RESET} — all required vars set. "
              f"{YELLOW}{len(missing_optional)} optional var(s) unset{RESET} (warnings only).")
        return 2

    print(f"{GREEN}OK — all required and optional vars set.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

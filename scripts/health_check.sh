#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# scripts/health_check.sh
# Thin shell wrapper for 'make health' — calls Python health_check.py
# with a guaranteed source of .env if present.
#
# Usage:
#   bash scripts/health_check.sh              # auto-sources .env
#   bash scripts/health_check.sh --json       # machine-readable JSON
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/.."

# Source .env if present (without exporting — health_check.py uses load_dotenv)
if [[ -f "$REPO_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

exec python3 "$SCRIPT_DIR/health_check.py" "$@"

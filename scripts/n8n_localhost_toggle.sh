#!/usr/bin/env bash
# scripts/n8n_localhost_toggle.sh — toggle N8N_EDITOR_BASE_URL between LAN and localhost.
#
# Why: Google's OAuth client validator rejects raw RFC1918 IPs as redirect URIs.
# To complete a Google OAuth flow against n8n, we register http://localhost:5678/...
# as the redirect URI. n8n must ALSO generate that same callback URL, so we
# temporarily add N8N_EDITOR_BASE_URL=http://localhost:5678 to n8n's env_file,
# restart n8n, complete the consent, then revert.
#
# Designed for the standard n8n compose layout where the compose service uses
# `env_file: .env` (which is Aaron's setup at /opt/n8n/.env on CT-202).
#
# RUN ON THE PVE HOST. Internally pct exec's into CT-202.
#
# Usage:
#   bash n8n_localhost_toggle.sh status         # current state, no changes
#   bash n8n_localhost_toggle.sh dry-run-on     # show what `on` would do; no changes
#   bash n8n_localhost_toggle.sh dry-run-off    # show what `off` would do; no changes
#   bash n8n_localhost_toggle.sh on             # apply override + restart
#   bash n8n_localhost_toggle.sh off            # revert override + restart
#
# Safety properties:
#   - set -euo pipefail throughout
#   - backs up .env to .env.gcal-backup before any mutation
#   - marker comment ' OHO-GCAL-OAUTH-TOGGLE' tags the line so off mode strips
#     exactly that line — never anything else
#   - probes /healthz after restart; fails loud if n8n doesn't return 200
#   - idempotent: `on` when already-on is a no-op; same for `off`
#   - dry-run modes apply ZERO mutation

set -euo pipefail

readonly LXC_ID="${LXC_PCT_CTID:-202}"
readonly MARKER=" # OHO-GCAL-OAUTH-TOGGLE"
readonly OVERRIDE_LINE="N8N_EDITOR_BASE_URL=http://localhost:5678${MARKER}"
readonly COMPOSE_PATH_DEFAULT="/opt/n8n/docker-compose.yml"
readonly ENV_PATH_DEFAULT="/opt/n8n/.env"

mode="${1:-status}"
case "$mode" in
  status|dry-run-on|dry-run-off|on|off) ;;
  *)
    echo "ERROR: unknown mode '$mode'. Use: status | dry-run-on | dry-run-off | on | off" >&2
    exit 2
    ;;
esac

# Run inside CT-202 and return stdout.
in_lxc() {
  pct exec "$LXC_ID" -- bash -lc "$1"
}

readonly COMPOSE_PATH="${N8N_COMPOSE_PATH:-$COMPOSE_PATH_DEFAULT}"
readonly ENV_PATH="${N8N_ENV_PATH:-$ENV_PATH_DEFAULT}"

# Validate paths exist inside CT-202.
if ! in_lxc "[ -f '$COMPOSE_PATH' ]"; then
  echo "ERROR: compose file not found at $COMPOSE_PATH inside CT-${LXC_ID}." >&2
  echo "Override with N8N_COMPOSE_PATH=<path> if non-standard." >&2
  exit 3
fi
if ! in_lxc "[ -f '$ENV_PATH' ]"; then
  echo "ERROR: env file not found at $ENV_PATH inside CT-${LXC_ID}." >&2
  echo "Override with N8N_ENV_PATH=<path> if non-standard." >&2
  exit 3
fi
readonly COMPOSE_DIR="$(dirname "$COMPOSE_PATH")"

echo "  CT:           ${LXC_ID}"
echo "  compose:      ${COMPOSE_PATH}"
echo "  env_file:     ${ENV_PATH}"

is_on() {
  in_lxc "grep -qF '$MARKER' '$ENV_PATH'"
}

status() {
  if is_on; then
    echo "  state:        ON (N8N_EDITOR_BASE_URL override active)"
  else
    echo "  state:        OFF (no OHO-GCAL-OAUTH-TOGGLE marker)"
  fi
}

restart_n8n() {
  echo "  -> docker compose up -d --force-recreate n8n (~10s)..."
  in_lxc "cd '$COMPOSE_DIR' && docker compose up -d --force-recreate n8n" >&2
  echo "  -> health probe..."
  for i in 1 2 3 4 5 6; do
    if in_lxc "curl -s -o /dev/null -w '%{http_code}' http://localhost:5678/healthz" 2>/dev/null | grep -q '^200$'; then
      echo "  OK n8n responded 200 on /healthz."
      return 0
    fi
    sleep 2
  done
  echo "ERROR: n8n did not return 200 after restart; investigate manually." >&2
  echo "       Last 30 log lines:" >&2
  in_lxc "cd '$COMPOSE_DIR' && docker compose logs --tail 30 n8n" >&2 || true
  exit 4
}

case "$mode" in

  status)
    status
    ;;

  dry-run-on)
    echo "  mode:         DRY-RUN (no changes applied)"
    if is_on; then
      echo "  -> override ALREADY present; 'on' would be a no-op."
      status
      exit 0
    fi
    echo "  -> 'on' would append exactly this line to ${ENV_PATH}:"
    echo
    echo "      ${OVERRIDE_LINE}"
    echo
    echo "  -> would back up ${ENV_PATH} to ${ENV_PATH}.gcal-backup first."
    echo "  -> would then run: docker compose up -d --force-recreate n8n"
    echo "  -> would then probe http://localhost:5678/healthz until 200 (max 12s)."
    echo
    echo "  Inspect current env_file size + tail:"
    in_lxc "wc -l '$ENV_PATH' && echo '--- last 5 lines ---' && tail -5 '$ENV_PATH'"
    echo
    echo "  Run with 'on' (not 'dry-run-on') to actually apply."
    ;;

  dry-run-off)
    echo "  mode:         DRY-RUN (no changes applied)"
    if ! is_on; then
      echo "  -> no override marker found; 'off' would be a no-op."
      exit 0
    fi
    echo "  -> 'off' would strip this line from ${ENV_PATH}:"
    in_lxc "grep -nF '$MARKER' '$ENV_PATH'" || true
    echo
    echo "  -> would back up ${ENV_PATH} to ${ENV_PATH}.gcal-backup first."
    echo "  -> would then run: docker compose up -d --force-recreate n8n"
    echo "  -> would then probe http://localhost:5678/healthz until 200."
    echo
    echo "  Run with 'off' (not 'dry-run-off') to actually apply."
    ;;

  on)
    if is_on; then
      echo "  OK override already present; nothing to do."
      status
      exit 0
    fi
    echo "  -> backup: ${ENV_PATH} -> ${ENV_PATH}.gcal-backup"
    in_lxc "cp -a '$ENV_PATH' '${ENV_PATH}.gcal-backup'"
    echo "  -> append: ${OVERRIDE_LINE}"
    # Use printf via base64 to avoid shell-escaping the marker comment
    local_line_b64="$(printf '%s\n' "$OVERRIDE_LINE" | base64 -w0)"
    in_lxc "echo '$local_line_b64' | base64 -d >> '$ENV_PATH'"
    restart_n8n
    status
    echo
    echo "  Next: bash scripts/laptop_oauth_tunnel.sh (on your laptop)"
    ;;

  off)
    if ! is_on; then
      echo "  OK no override marker found; nothing to revert."
      exit 0
    fi
    echo "  -> backup: ${ENV_PATH} -> ${ENV_PATH}.gcal-backup"
    in_lxc "cp -a '$ENV_PATH' '${ENV_PATH}.gcal-backup'"
    echo "  -> strip override line"
    in_lxc "grep -vF '$MARKER' '$ENV_PATH' > '${ENV_PATH}.tmp' && mv '${ENV_PATH}.tmp' '$ENV_PATH'"
    restart_n8n
    status
    echo
    echo "  Override reverted. n8n back to normal base URL."
    ;;

esac

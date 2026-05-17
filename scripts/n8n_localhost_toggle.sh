#!/usr/bin/env bash
# scripts/n8n_localhost_toggle.sh — temporarily toggle n8n's editor base URL
# between LAN IP and localhost.
#
# Why: Google's OAuth client validator rejects raw RFC1918 IPs as redirect URIs.
# To complete a Google OAuth flow against n8n, we register `http://localhost:5678/...`
# as the redirect URI. n8n must ALSO generate that same callback URL, so we
# temporarily set N8N_EDITOR_BASE_URL=http://localhost:5678 + restart n8n.
# After the OAuth dance captures the refresh token, we revert.
#
# RUN ON THE PVE HOST (the LXC host). Internally pct exec's into CT-202.
#
# Usage:
#   bash n8n_localhost_toggle.sh on        # set N8N_EDITOR_BASE_URL=localhost + restart
#   bash n8n_localhost_toggle.sh off       # remove the override + restart
#   bash n8n_localhost_toggle.sh status    # show current state
#
# Safety:
#   - set -euo pipefail throughout
#   - confirms n8n is reachable on http://localhost:5678/healthz after restart
#   - aborts if compose file can't be located

set -euo pipefail

readonly LXC_ID="${LXC_PCT_CTID:-202}"
readonly MARKER="# OHO-GCAL-OAUTH-TOGGLE"      # sentinel comment so off-mode can find the line
readonly OVERRIDE_LINE='      - N8N_EDITOR_BASE_URL=http://localhost:5678  # OHO-GCAL-OAUTH-TOGGLE'

mode="${1:-status}"

case "$mode" in
  on|off|status) ;;
  *)
    echo "ERROR: unknown mode '$mode'. Use one of: on | off | status" >&2
    exit 2
    ;;
esac

# Run a bash snippet inside CT-202 and return its output verbatim.
in_lxc() {
  pct exec "$LXC_ID" -- bash -lc "$1"
}

# Locate n8n's docker-compose.yml inside CT-202. Cached on first call.
locate_compose() {
  local found
  found="$(in_lxc 'find / -name "docker-compose*.y*ml" -path "*n8n*" 2>/dev/null | head -1' || true)"
  if [[ -z "$found" ]]; then
    found="$(in_lxc 'find / -name "compose*.y*ml" -path "*n8n*" 2>/dev/null | head -1' || true)"
  fi
  if [[ -z "$found" ]]; then
    echo "ERROR: could not locate n8n's docker-compose file inside CT-${LXC_ID}." >&2
    echo "Set N8N_COMPOSE_PATH in your env or pass it as the second arg." >&2
    exit 3
  fi
  echo "$found"
}

readonly COMPOSE_PATH="${N8N_COMPOSE_PATH:-$(locate_compose)}"
readonly COMPOSE_DIR="$(dirname "$COMPOSE_PATH")"

echo "  CT:           ${LXC_ID}"
echo "  compose:      ${COMPOSE_PATH}"

restart_n8n() {
  echo "  → docker compose up -d --force-recreate n8n (~10s)…"
  in_lxc "cd '$COMPOSE_DIR' && docker compose up -d --force-recreate n8n" >&2
  echo "  → health probe…"
  for i in 1 2 3 4 5 6; do
    if in_lxc "curl -s -o /dev/null -w '%{http_code}' http://localhost:5678/healthz" 2>/dev/null | grep -q '^200$'; then
      echo "  ✓ n8n responded 200 on /healthz."
      return 0
    fi
    sleep 2
  done
  echo "ERROR: n8n did not return 200 after restart; investigate manually." >&2
  exit 4
}

status() {
  if in_lxc "grep -F '$MARKER' '$COMPOSE_PATH'" >/dev/null 2>&1; then
    echo "  state:        ON (N8N_EDITOR_BASE_URL override is active)"
  else
    echo "  state:        OFF (no OHO-GCAL-OAUTH-TOGGLE marker in compose)"
  fi
}

case "$mode" in
  status)
    status
    ;;

  on)
    if in_lxc "grep -F '$MARKER' '$COMPOSE_PATH'" >/dev/null 2>&1; then
      echo "  ✓ override already present — nothing to do."
      status
      exit 0
    fi
    echo "  → inserting override line under the n8n service environment…"
    # Insert the override after the first line containing `environment:` under the n8n service.
    # We use a conservative awk: append after the first `environment:` line that follows a
    # line starting with `n8n:` (allowing any indent).
    in_lxc "awk -v line='$OVERRIDE_LINE' '
      /^[[:space:]]*n8n:[[:space:]]*$/ { in_n8n = 1 }
      in_n8n && /environment:/ && !inserted { print; print line; inserted = 1; next }
      { print }
    ' '$COMPOSE_PATH' > '${COMPOSE_PATH}.toggle.tmp' && mv '${COMPOSE_PATH}.toggle.tmp' '$COMPOSE_PATH'"
    restart_n8n
    status
    echo
    echo "Next: SSH-tunnel from your laptop, then `make gcal-create`."
    ;;

  off)
    if ! in_lxc "grep -F '$MARKER' '$COMPOSE_PATH'" >/dev/null 2>&1; then
      echo "  ✓ no override marker found — nothing to revert."
      exit 0
    fi
    echo "  → stripping override line…"
    in_lxc "grep -vF '$MARKER' '$COMPOSE_PATH' > '${COMPOSE_PATH}.toggle.tmp' && mv '${COMPOSE_PATH}.toggle.tmp' '$COMPOSE_PATH'"
    restart_n8n
    status
    echo
    echo "Override reverted. n8n is back to its normal base URL."
    ;;
esac

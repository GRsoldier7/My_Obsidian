#!/usr/bin/env bash
# scripts/laptop_oauth_tunnel.sh — one-shot SSH local port-forward for the
# GCAL OAuth flow.
#
# Run on Aaron's LAPTOP (not the homelab). Sets up:
#   localhost:5678  →  SSH tunnel  →  CT-202 (192.168.1.121):5678
#
# Keep the terminal open during the OAuth dance. Ctrl-C tears down the tunnel.
#
# Usage:
#   bash laptop_oauth_tunnel.sh                  # default: ssh to 192.168.1.121:22
#   OAUTH_SSH_HOST=root@pve.lan bash …          # via a different jump host
#   OAUTH_SSH_PORT=2222 bash …                  # different ssh port
#
# Once tunnel is up, opens http://localhost:5678 in your default browser
# (you can also open it manually).

set -euo pipefail

readonly SSH_HOST="${OAUTH_SSH_HOST:-root@192.168.1.121}"
readonly SSH_PORT="${OAUTH_SSH_PORT:-22}"
readonly LOCAL_PORT="${OAUTH_LOCAL_PORT:-5678}"
readonly REMOTE_PORT="${OAUTH_REMOTE_PORT:-5678}"

# Adjust the destination as appropriate. If SSH'ing directly to CT-202 (n8n
# host), use `localhost:5678` (the tunnel's "other end" resolves on the SSH
# server). If SSH'ing to a jump host (PVE), use `192.168.1.121:5678`.
readonly TUNNEL_DEST="${OAUTH_TUNNEL_DEST:-localhost:${REMOTE_PORT}}"

echo "  laptop tunnel:  localhost:${LOCAL_PORT} → ${SSH_HOST}:${TUNNEL_DEST}"
echo

# Probe local port — fail fast if already in use
if command -v lsof >/dev/null 2>&1; then
  if lsof -i ":${LOCAL_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: localhost:${LOCAL_PORT} is already in use on this laptop." >&2
    echo "Free the port or set OAUTH_LOCAL_PORT to something else." >&2
    exit 2
  fi
fi

# Open SSH tunnel in the foreground; the user keeps this terminal open during
# the dance. -N = no remote command. -T = no PTY. -o ServerAliveInterval keeps
# the tunnel alive during the consent screen.
echo "  Opening tunnel — keep this terminal open through STEP 6."
echo "  → ssh -p ${SSH_PORT} -L ${LOCAL_PORT}:${TUNNEL_DEST} -N -T ${SSH_HOST}"
echo "  → After 'tunnel up' below appears, open http://localhost:${LOCAL_PORT} in your browser."
echo

# Open the URL in default browser after a short delay (best-effort).
(
  sleep 3
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:${LOCAL_PORT}" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "http://localhost:${LOCAL_PORT}" >/dev/null 2>&1 || true
  fi
) &

# Foreground tunnel
exec ssh -p "${SSH_PORT}" \
  -L "${LOCAL_PORT}:${TUNNEL_DEST}" \
  -N -T \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=4 \
  "${SSH_HOST}"

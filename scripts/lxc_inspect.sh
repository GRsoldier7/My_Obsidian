#!/usr/bin/env bash
# =============================================================================
# scripts/lxc_inspect.sh — Read-only LXC readiness inspection
# =============================================================================
#
# Run this FROM INSIDE n8n LXC CT-202. It tells you exactly what's missing
# for the brain-dump-processor.py shell-out (ADR-0005) to work.
#
# To get inside the container (from the Proxmox host `pve`):
#   pct enter 202
#
# Then run this script. It makes NO changes — purely diagnostic.
#
# Pipe-paste version (if the script isn't yet on the LXC):
#   set +H && bash <(curl -sS https://raw.githubusercontent.com/.../lxc_inspect.sh)
# OR copy-paste the body directly into the LXC shell after `set +H`.
#
# Why `set +H`: bash's history expansion treats `!!` literally inside paths,
# so paths containing `!!` (the Mac's repo location) blow up an interactive
# shell. set +H disables history expansion for this session.
# =============================================================================

set +H
set -uo pipefail

echo "=== Inside container ===" && hostname && uname -a
echo
echo "=== Python ===" && python3 --version 2>&1
echo
echo "=== pip3 ===" && (pip3 --version 2>&1 || echo "pip3 missing")
echo
echo "=== Required Python packages ===" && \
  python3 -c "import boto3,openai,dotenv; print('boto3',boto3.__version__,'openai',openai.__version__,'dotenv ok')" 2>&1 \
  || echo "missing one or more of: boto3 / openai / python-dotenv"
echo
echo "=== Repo path candidates (literal) ===" && \
  for p in /opt/oho /mnt/oho /home/oho /root/oho /var/lib/n8n/oho; do
    if [ -d "$p" ]; then echo "FOUND $p"; else echo "absent $p"; fi
  done
echo
echo "=== Repo search (by marker) ===" && \
  find / -xdev -maxdepth 6 -type f -name "process_brain_dump.py" 2>/dev/null | head -5
echo
echo "=== Bind mounts visible from inside ===" && \
  mount | grep -E '/mnt|/oho|home' | head -10
echo
echo "=== MinIO reachable from container? ===" && \
  curl -sS -m 3 -o /dev/null -w "minio: HTTP %{http_code}\n" http://192.168.1.240:9000/minio/health/live
echo
echo "=== OpenRouter reachable from container? ===" && \
  curl -sS -m 3 -o /dev/null -w "openrouter: HTTP %{http_code}\n" https://openrouter.ai/
echo
echo "=== n8n process inside ===" && pgrep -af n8n | head -3
echo
echo "=== n8n version ===" && (which n8n && n8n --version) 2>&1 | head -3
echo
echo "=== Distro ===" && (cat /etc/os-release 2>/dev/null | head -3 || lsb_release -a 2>/dev/null)
echo
echo "=== Disk free ===" && df -h / | tail -1
echo
echo "=== Network interfaces ===" && ip -4 addr show | grep -E 'inet ' | head -5
echo
echo "=== Done — paste the full output back to the AI assistant ==="

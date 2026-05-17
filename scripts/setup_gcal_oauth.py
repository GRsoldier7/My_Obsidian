#!/usr/bin/env python3
"""
scripts/setup_gcal_oauth.py — interactive GCAL OAuth2 setup helper.

End state: a working `Google Calendar OAuth2` credential in n8n + the
credential's ID written to `.env` as `GCAL_CRED_ID` so `setup-n8n.sh`
can hydrate `__GCAL_CRED_ID__` placeholders into the Weekend Planner
workflow.

The script handles two paths automatically:

  PATH A — .env already has `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`:
    1. POST n8n `/credentials` with type=googleCalendarOAuth2Api.
    2. Print the deep-link operator must open in their browser to
       complete the Google consent flow (this is the ONE thing the
       script cannot automate — Google requires a live browser session
       bound to the operator's Google account).
    3. After consent, n8n stores the refresh token + the credential is
       usable. Operator then runs this script again with `--finalize`
       to write `GCAL_CRED_ID` to `.env`.

  PATH B — `.env` missing Google OAuth client creds:
    Prints exact Google Cloud Console steps (project create → OAuth
    consent screen → OAuth client ID for Web Application → authorized
    redirect URI matching n8n's callback) + the `.env` lines to add
    after.

Run:
    set -a && source .env && set +a
    python3 scripts/setup_gcal_oauth.py             # prints state + next action
    python3 scripts/setup_gcal_oauth.py --create    # PATH A: create cred shell in n8n
    python3 scripts/setup_gcal_oauth.py --finalize  # write GCAL_CRED_ID after operator consent

Exit codes:
  0 — success or guidance printed
  1 — missing required env or n8n API failure
  2 — operator action needed (printed to stdout)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"
CRED_NAME = "Google Calendar OAuth2 (Aaron)"


def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_PATH.exists():
        return out
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def write_env_var(key: str, value: str) -> None:
    """Idempotently set / replace a key=value line in .env. Never echoes value."""
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n")
    print(f"  ✓ wrote {key} to .env (value redacted, len={len(value)})")


def n8n_api(method: str, path: str, env: dict[str, str], body: dict | None = None) -> dict:
    host = env.get("N8N_HOST", "http://192.168.1.121:5678").rstrip("/")
    key = env["N8N_API_KEY"]
    url = f"{host}/api/v1{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url=url,
        data=data,
        method=method,
        headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode()
        except Exception:
            err_body = ""
        raise RuntimeError(f"n8n {method} {path} → HTTP {e.code}: {err_body}") from e


def find_existing_cred(env: dict[str, str]) -> str | None:
    """Scan existing workflows for a googleCalendarOAuth2Api cred reference."""
    try:
        data = n8n_api("GET", "/workflows", env)
    except RuntimeError:
        return None
    for wf in data.get("data", []):
        wf_id = wf.get("id")
        if not wf_id:
            continue
        try:
            detail = n8n_api("GET", f"/workflows/{wf_id}", env)
        except RuntimeError:
            continue
        for node in detail.get("nodes", []):
            creds = node.get("credentials", {}) or {}
            entry = creds.get("googleCalendarOAuth2Api")
            if isinstance(entry, dict) and entry.get("id") and not str(entry["id"]).startswith("__"):
                return str(entry["id"])
    return None


def print_state(env: dict[str, str]) -> None:
    print("=== GCAL OAuth state ===")
    have_client_id = bool(env.get("GOOGLE_CLIENT_ID") or env.get("GCAL_CLIENT_ID"))
    have_secret = bool(env.get("GOOGLE_CLIENT_SECRET") or env.get("GCAL_CLIENT_SECRET"))
    print(f"  .env GOOGLE_CLIENT_ID:     {'PRESENT' if have_client_id else 'MISSING'}")
    print(f"  .env GOOGLE_CLIENT_SECRET: {'PRESENT' if have_secret else 'MISSING'}")
    print(f"  .env GCAL_CRED_ID:         {'PRESENT (' + env['GCAL_CRED_ID'] + ')' if env.get('GCAL_CRED_ID') else 'MISSING'}")
    host = env.get("N8N_HOST", "http://192.168.1.121:5678").rstrip("/")
    print(f"  n8n host:                  {host}")
    print(f"  expected redirect URI:     {host}/rest/oauth2-credential/callback")
    print()


def print_path_b_instructions(env: dict[str, str]) -> None:
    """One-time Google Cloud Console setup. Verified against the 2025 Google Auth
    Platform UI per Context7 lookup of developers.google.com/calendar/auth and
    developers.google.com/meet/api/guides/tutorial-events-python (2025-Q2).

    The legacy 'OAuth consent screen' wizard is gone; config now lives under
    the Google Auth Platform with 4 separate panels: Branding, Audience, Data
    Access (scopes), Clients (OAuth client IDs).
    """
    host = env.get("N8N_HOST", "http://192.168.1.121:5678").rstrip("/")
    redirect = f"{host}/rest/oauth2-credential/callback"
    print("─" * 70)
    print("PATH B — Google Cloud Console setup (one-time, ~5 min)")
    print("Verified against the 2025 Google Auth Platform UI.")
    print("─" * 70)
    print()
    print("STEP 1 — Pick / create a Google Cloud project")
    print()
    print("   Open: https://console.cloud.google.com/projectcreate")
    print("   Project name: 'OHO Life OS'  (or pick an existing project)")
    print("   Note the project ID after creation; the URLs below auto-scope to it.")
    print()
    print("STEP 2 — Enable the Google Calendar API")
    print()
    print("   Open: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com")
    print("   Verify the project picker (top of page) shows the right project, then")
    print("   click ENABLE. Wait for the green check.")
    print()
    print("STEP 3 — Google Auth Platform → Branding")
    print()
    print("   Open: https://console.cloud.google.com/auth/branding")
    print()
    print("   First visit: Google prompts you to 'Get started' — accept that.")
    print("   Fill in:")
    print("     App name:               OHO Weekend Planner")
    print("     User support email:     <your Google account email>")
    print("     Audience (next panel — see step 4 — needs External for a personal Google account)")
    print("     Developer contact info: <your Google account email>")
    print("     App logo (optional):    skip")
    print("   Accept the 'Google API Services User Data Policy'. SAVE.")
    print()
    print("STEP 4 — Google Auth Platform → Audience")
    print()
    print("   Open: https://console.cloud.google.com/auth/audience")
    print()
    print("   User type: 'External' (only choice unless you're on Workspace).")
    print("   Publishing status: leave as 'Testing'. (Don't publish — refresh tokens")
    print("   expire after 7 days for unverified apps in production, but Testing has")
    print("   no such limit for added test users.)")
    print("   Test users → ADD USERS → enter your own Google email. SAVE.")
    print()
    print("STEP 5 — Google Auth Platform → Data Access (scopes)")
    print()
    print("   Open: https://console.cloud.google.com/auth/scopes")
    print()
    print("   ADD OR REMOVE SCOPES → in the right panel, search for: calendar.readonly")
    print("   Tick:  .../auth/calendar.readonly")
    print("   (Calendar.readonly is NON-sensitive — no verification needed.)")
    print("   UPDATE → SAVE.")
    print()
    print("STEP 6 — Google Auth Platform → Clients (create OAuth client ID)")
    print()
    print("   Open: https://console.cloud.google.com/auth/clients")
    print()
    print("   + CREATE CLIENT")
    print("     Application type:      Web application")
    print("     Name:                  OHO n8n")
    print("     Authorized JavaScript origins: (leave blank)")
    print("     Authorized redirect URIs → + ADD URI → paste EXACTLY:")
    print()
    print(f"        http://localhost:5678/rest/oauth2-credential/callback")
    print()
    print("   ⚠️  IMPORTANT — DO NOT use the n8n LAN IP here. Google rejects")
    print(f"       raw RFC1918 IPs ({host} would fail validation with")
    print("       'Invalid Redirect: must end with a public top-level domain').")
    print("       Use `http://localhost:5678` instead — Google accepts localhost")
    print("       and 127.0.0.1 as redirect URI exemptions to the public-TLD rule.")
    print()
    print("       This means n8n must ALSO advertise itself as localhost during")
    print("       the OAuth flow. See STEP 8b for the temporary config change +")
    print("       SSH tunnel from your laptop.")
    print()
    print("   CREATE → a modal shows the Client ID + Client Secret.")
    print("   Click DOWNLOAD JSON if you want a backup; otherwise click each")
    print("   field's clipboard icon. Keep this modal open until step 7.")
    print()
    print("STEP 7 — Paste into .env (terminal or IDE, NOT into chat)")
    print()
    print("   Append (replacing the placeholders):")
    print()
    print("     GOOGLE_CLIENT_ID=<paste Client ID>")
    print("     GOOGLE_CLIENT_SECRET=<paste Client Secret>")
    print()
    print("STEP 8a — Temporarily tell n8n its base URL is `localhost`")
    print()
    print("   Because Google's redirect URI is localhost (step 6), n8n MUST")
    print("   generate the SAME callback URL or you'll hit redirect_uri_mismatch.")
    print()
    print("   On the PVE host:")
    print("     pct exec 202 -- bash")
    print("     # find n8n's docker-compose.yml:")
    print("     find / -name 'docker-compose*.y*ml' -path '*n8n*' 2>/dev/null")
    print("     # edit it, add under the n8n service's environment:")
    print("     #   - N8N_EDITOR_BASE_URL=http://localhost:5678")
    print("     cd <path>")
    print("     docker compose up -d --force-recreate n8n")
    print("     curl -s -o /dev/null -w '%{http_code}\\n' http://localhost:5678/healthz")
    print("     # Expect 200. Exit the LXC.")
    print()
    print("STEP 8b — SSH port-forward from your laptop")
    print()
    print("   In a NEW terminal on your laptop (keep open during step 8c):")
    print("     ssh -L 5678:192.168.1.121:5678 <user>@<jump-host>")
    print("   (Or any host that can reach 192.168.1.121:5678. Once connected,")
    print("    `http://localhost:5678` on your laptop reaches n8n via the tunnel.)")
    print()
    print("STEP 8c — Complete the OAuth dance")
    print()
    print("   set -a && source .env && set +a")
    print("   make gcal-create")
    print()
    print("   The script POSTs the n8n credential shell + prints a deep-link URL")
    print("   (`http://localhost:5678/credentials/<id>`). Open it IN YOUR LAPTOP'S")
    print("   BROWSER (must be `localhost`, NOT `192.168.1.121`, so the URI matches).")
    print("   Click 'Sign in with Google' → Google consent → Allow.")
    print()
    print("STEP 8d — Capture cred ID + revert n8n config")
    print()
    print("   make gcal-finalize    # writes GCAL_CRED_ID to .env")
    print()
    print("   Then on PVE, remove the N8N_EDITOR_BASE_URL line from the n8n")
    print("   compose file and `docker compose up -d --force-recreate n8n` again.")
    print()
    print("STEP 9 — Re-deploy Weekend Planner")
    print()
    print("   bash scripts/setup-n8n.sh")
    print("   # Hydrates __GCAL_CRED_ID__ placeholder, re-imports Weekend Planner.")
    print()
    print("─" * 70)
    print("Troubleshooting:")
    print("  - 'Invalid Redirect: must end with a public top-level domain':")
    print("      You pasted the raw LAN IP. Use `http://localhost:5678/...`")
    print("      instead. See STEP 6 + STEP 8a-c for the localhost flow.")
    print("  - 'redirect_uri_mismatch' error during consent:")
    print("      n8n is sending a different redirect URI than Google has registered.")
    print("      Confirm STEP 8a worked (N8N_EDITOR_BASE_URL=http://localhost:5678)")
    print("      and that you opened the cred via `http://localhost:5678/...`, not")
    print("      via the LAN IP.")
    print("  - 'access_denied' error:")
    print("      You forgot to add yourself as a Test user in step 4.")
    print("  - 'invalid_client' error:")
    print("      .env values mis-pasted (newline / quote stripped). Re-check step 7.")
    print("─" * 70)


def print_path_a_create(env: dict[str, str], existing: str | None) -> int:
    host = env.get("N8N_HOST", "http://192.168.1.121:5678").rstrip("/")
    client_id = env.get("GOOGLE_CLIENT_ID") or env.get("GCAL_CLIENT_ID")
    client_secret = env.get("GOOGLE_CLIENT_SECRET") or env.get("GCAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing — re-read PATH B above.", file=sys.stderr)
        return 1

    if existing:
        print(f"FOUND existing googleCalendarOAuth2Api credential in n8n (ID: {existing}).")
        print("If you want to recreate, delete it in the n8n UI first.")
        print("Otherwise: complete the consent in the n8n UI then run --finalize.")
        return 0

    # n8n's `googleCalendarOAuth2Api` credential schema has conditional `allOf`
    # branches that all match when their gate properties are absent. The
    # validator therefore requires all 5 of these fields together — empirically
    # discovered 2026-05-16 via the schema endpoint + probe matrix.
    payload = {
        "name": CRED_NAME,
        "type": "googleCalendarOAuth2Api",
        "data": {
            "serverUrl": "",
            "clientId": client_id,
            "clientSecret": client_secret,
            "sendAdditionalBodyProperties": False,
            "additionalBodyProperties": "{}",
        },
    }
    print("POST /credentials → creating Google Calendar OAuth2 credential …")
    try:
        result = n8n_api("POST", "/credentials", env, payload)
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    new_id = result.get("id")
    if not new_id:
        print(f"FAIL: n8n didn't return an id in response: {result}", file=sys.stderr)
        return 1

    print(f"  ✓ credential shell created (ID: {new_id})")
    print()
    print("─" * 70)
    print("NEXT — complete the OAuth consent (browser via SSH tunnel)")
    print("─" * 70)
    print()
    print("Google's redirect URI is registered as `http://localhost:5678/...`,")
    print("so the OAuth flow MUST go through localhost — NOT the LAN IP.")
    print()
    print("On the PVE host (one-shot, sets N8N_EDITOR_BASE_URL + restarts n8n):")
    print()
    print("  bash scripts/n8n_localhost_toggle.sh on")
    print()
    print("On your LAPTOP (separate terminal — keep open during the OAuth dance):")
    print()
    print("  bash scripts/laptop_oauth_tunnel.sh")
    print()
    print("Then open in your laptop's browser (logged into your Google account):")
    print()
    print(f"  http://localhost:5678/credentials/{new_id}")
    print()
    print("→ Click 'Sign in with Google' / 'Connect my account'.")
    print("→ Complete the Google consent screen (allow calendar read).")
    print("→ n8n stores the refresh token automatically.")
    print()
    print("Then on your laptop:")
    print()
    print("  make gcal-finalize         # writes GCAL_CRED_ID to .env")
    print()
    print("Finally, on the PVE host (revert the localhost override):")
    print()
    print("  bash scripts/n8n_localhost_toggle.sh off")
    print()
    print("And re-deploy Weekend Planner from your laptop:")
    print()
    print("  bash scripts/setup-n8n.sh")
    print("─" * 70)
    return 0


def finalize(env: dict[str, str]) -> int:
    existing = find_existing_cred(env)
    if not existing:
        print("ERROR: no googleCalendarOAuth2Api credential found in n8n yet.", file=sys.stderr)
        print("Run --create first, then complete the consent in the n8n UI.", file=sys.stderr)
        return 1
    if env.get("GCAL_CRED_ID") == existing:
        print(f"  ✓ .env already has GCAL_CRED_ID={existing} — nothing to do.")
        return 0
    write_env_var("GCAL_CRED_ID", existing)
    print()
    print("Re-deploy Weekend Planner so the workflow picks up the new credential ID:")
    print()
    print("  set -a && source .env && set +a")
    print("  bash scripts/setup-n8n.sh")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GCAL OAuth2 setup helper")
    parser.add_argument("--create", action="store_true",
                        help="PATH A: POST the n8n credential shell (requires GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET in .env)")
    parser.add_argument("--finalize", action="store_true",
                        help="After operator completes Google consent in n8n UI, find the cred ID + write it to .env")
    args = parser.parse_args()

    env = read_env()
    # Layer in os.environ so --create works straight after `source .env`
    for k in ("N8N_HOST", "N8N_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
              "GCAL_CLIENT_ID", "GCAL_CLIENT_SECRET", "GCAL_CRED_ID"):
        if k not in env and k in os.environ:
            env[k] = os.environ[k]

    if "N8N_API_KEY" not in env:
        print("ERROR: N8N_API_KEY missing — set in .env or shell.", file=sys.stderr)
        return 1

    print_state(env)

    if args.finalize:
        return finalize(env)

    have_client_id = bool(env.get("GOOGLE_CLIENT_ID") or env.get("GCAL_CLIENT_ID"))
    have_secret = bool(env.get("GOOGLE_CLIENT_SECRET") or env.get("GCAL_CLIENT_SECRET"))

    if args.create:
        existing = find_existing_cred(env)
        return print_path_a_create(env, existing)

    # No flag — print state + recommended next step
    existing = find_existing_cred(env)
    if existing and not env.get("GCAL_CRED_ID"):
        print(f"n8n already has a googleCalendarOAuth2Api credential (ID: {existing}).")
        print("Run: python3 scripts/setup_gcal_oauth.py --finalize")
        return 0
    if have_client_id and have_secret:
        print("Ready for PATH A. Run:")
        print("  python3 scripts/setup_gcal_oauth.py --create")
        return 0
    # Otherwise: PATH B (guidance is informational, not a failure)
    print_path_b_instructions(env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

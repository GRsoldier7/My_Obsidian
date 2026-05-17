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
    host = env.get("N8N_HOST", "http://192.168.1.121:5678").rstrip("/")
    redirect = f"{host}/rest/oauth2-credential/callback"
    print("─" * 70)
    print("PATH B — Google Cloud Console setup (one-time, ~5 minutes)")
    print("─" * 70)
    print()
    print("1. Open https://console.cloud.google.com/")
    print("   - Create a new project (e.g. 'OHO Life OS') or pick an existing one.")
    print()
    print("2. Enable the Google Calendar API:")
    print("   https://console.cloud.google.com/apis/library/calendar-json.googleapis.com")
    print("   → click ENABLE.")
    print()
    print("3. Configure the OAuth consent screen:")
    print("   https://console.cloud.google.com/apis/credentials/consent")
    print("   → User Type: External (unless you have Workspace)")
    print("   → App name: OHO Weekend Planner")
    print("   → User support email: your email")
    print("   → Developer contact: your email")
    print("   → Scopes: add `.../auth/calendar.readonly` (read-only is enough for the planner).")
    print("   → Test users: add your Google account (the one with the calendar).")
    print()
    print("4. Create OAuth client ID:")
    print("   https://console.cloud.google.com/apis/credentials")
    print("   → CREATE CREDENTIALS → OAuth client ID")
    print("   → Application type: Web application")
    print("   → Name: OHO n8n")
    print(f"   → Authorized redirect URI (EXACT — paste this in):")
    print(f"       {redirect}")
    print("   → CREATE → copy the Client ID + Client Secret.")
    print()
    print("5. Append to .env (DO NOT paste them in chat):")
    print()
    print("   GOOGLE_CLIENT_ID=<paste your client ID>")
    print("   GOOGLE_CLIENT_SECRET=<paste your client secret>")
    print()
    print("6. Re-run this script with --create:")
    print()
    print("   set -a && source .env && set +a")
    print("   python3 scripts/setup_gcal_oauth.py --create")
    print()
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

    payload = {
        "name": CRED_NAME,
        "type": "googleCalendarOAuth2Api",
        "data": {
            "clientId": client_id,
            "clientSecret": client_secret,
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
    print("NEXT — complete the OAuth consent (browser, ~30 seconds)")
    print("─" * 70)
    print()
    print("Open this URL in your browser (logged into the Google account whose")
    print("calendar you want OHO to read):")
    print()
    print(f"  {host}/credentials/{new_id}")
    print()
    print("→ Click 'Sign in with Google' / 'Connect my account'.")
    print("→ Complete the Google consent screen (allow calendar read access).")
    print("→ n8n stores the refresh token automatically.")
    print()
    print("Then run:")
    print()
    print("  python3 scripts/setup_gcal_oauth.py --finalize")
    print()
    print("That writes GCAL_CRED_ID to .env and tells you to re-deploy")
    print("Weekend Planner via `make setup`.")
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
    # Otherwise: PATH B
    print_path_b_instructions(env)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

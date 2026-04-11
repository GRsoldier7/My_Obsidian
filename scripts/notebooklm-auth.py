"""
Build notebooklm storage_state.json from Chrome cookies via browser_cookie3.
This handles macOS Keychain decryption so we get the real SID / auth cookies.
"""
import json, time
from pathlib import Path

try:
    import browser_cookie3
except ImportError:
    print("Run: ~/.notebooklm-venv/bin/pip install browser_cookie3")
    raise

STORAGE_FILE = Path.home() / ".notebooklm" / "storage_state.json"
STORAGE_FILE.parent.mkdir(exist_ok=True)

# Domains to capture for NotebookLM auth
DOMAINS = [".google.com", "accounts.google.com", "notebooklm.google.com", ".notebooklm.google.com"]

print("Reading Chrome cookies (may prompt for Keychain access)...")
jar = browser_cookie3.chrome(domain_name=".google.com")

cookies = []
for c in jar:
    cookies.append({
        "name": c.name,
        "value": c.value,
        "domain": c.domain,
        "path": c.path if c.path else "/",
        "expires": int(c.expires) if c.expires else -1,
        "httpOnly": bool(c.has_nonstandard_attr("HttpOnly")),
        "secure": bool(c.secure),
        "sameSite": "Lax",
    })

# Filter to Google-related cookies only
google_cookies = [c for c in cookies if "google" in c["domain"]]

sid_cookies = [c for c in google_cookies if c["name"] == "SID"]
print(f"Total Google cookies: {len(google_cookies)}")
print(f"SID cookies: {len(sid_cookies)}")

if not sid_cookies:
    print("\nWARNING: No SID cookies found. Make sure you're signed in to Google in Chrome.")
    print("Cookies found:", sorted(set(c['name'] for c in google_cookies)))
else:
    print("SID domains:", [c['domain'] for c in sid_cookies])

storage_state = {
    "cookies": google_cookies,
    "origins": []
}

STORAGE_FILE.write_text(json.dumps(storage_state, indent=2))
print(f"\nSaved {len(google_cookies)} cookies to {STORAGE_FILE}")

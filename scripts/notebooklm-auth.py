"""
Build notebooklm storage_state.json from Chrome cookies via browser_cookie3.
Works cross-platform: macOS Keychain, Windows DPAPI, Linux Secret Service.
Chrome must be signed in to Google before running.

Linux extra deps (if needed): pip install secretstorage jeepney
"""
import json
from pathlib import Path

try:
    import browser_cookie3
except ImportError:
    print("Run: python3 -m pip install browser_cookie3")
    raise

STORAGE_FILE = Path.home() / ".notebooklm" / "storage_state.json"
STORAGE_FILE.parent.mkdir(exist_ok=True)

print("Reading Chrome cookies from OS credential store...")
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

google_cookies = [c for c in cookies if "google" in c["domain"]]
sid_cookies = [c for c in google_cookies if c["name"] == "SID"]

print(f"Total Google cookies: {len(google_cookies)}")
print(f"SID cookies: {len(sid_cookies)}")

if not sid_cookies:
    print("\nWARNING: No SID cookies found. Make sure Chrome is signed in to Google.")
    print("Cookies found:", sorted(set(c['name'] for c in google_cookies)))
else:
    print("SID domains:", [c['domain'] for c in sid_cookies])

STORAGE_FILE.write_text(json.dumps({"cookies": google_cookies, "origins": []}, indent=2))
print(f"\nSaved {len(google_cookies)} cookies to {STORAGE_FILE}")

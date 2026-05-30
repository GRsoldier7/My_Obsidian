# Claude in Chrome — OHO usage guide

> Verified against official docs 2026-05-30: <https://code.claude.com/docs/en/chrome> and <https://support.claude.com/en/articles/12012173-getting-started-with-claude-in-chrome>.
> **Operator-manual install** — the extension comes from the Chrome Web Store; Claude Code cannot install it for you.

## Why for OHO

Best fit = **Claude Code's browser backend** (`claude --chrome`), not the standalone side-panel agent.

Your current browser stack (Playwright MCP, `connect-chrome` skill, `browse` skill) is **headless + unauthenticated**. Claude in Chrome's one differentiator: it drives your **real logged-in Chrome window**, sharing existing session state, pausing for you on login/CAPTCHA. That fills the gap of testing anything behind a login:

- live n8n UI at `http://192.168.1.121:5678` (workflow state, execution logs)
- MinIO console at `http://192.168.1.240:9001`
- any authenticated dashboard — without scripting auth or storing creds

It does **not** replace n8n/MinIO/NotebookLM automation (server-side, scheduled, auditable). Dev/QA tool only.

## Requirements (all verified)

- Google Chrome or Microsoft Edge (NOT Brave/Arc/other Chromium; WSL unsupported)
- "Claude in Chrome" extension **≥ 1.0.36** (Web Store ID `fcoeoabgfenejglbffodgkkbkcdhcgfn`)
- Claude Code **≥ 2.0.73** (`claude --version`)
- A **direct Anthropic plan** (Pro/Max/Team/Enterprise). Not available via Bedrock/Vertex/Foundry — those need a separate claude.ai account.

## Setup (Linux desktop — aaron-inspiron-3030)

1. Chrome → Web Store → add the **Claude** extension (`fcoeoabgfenejglbffodgkkbkcdhcgfn`), sign in.
2. Pin it (puzzle-piece → thumbtack).
3. Confirm Claude Code current: `claude --version` (need ≥ 2.0.73).
4. Launch with the flag, or `/chrome` inside a session:
   ```bash
   claude --chrome
   ```
5. First run installs the native-messaging host. On Linux/Chrome it lands at:
   ```
   ~/.config/google-chrome/NativeMessagingHosts/com.anthropic.claude_code_browser_extension.json
   ```
   (Edge: `~/.config/microsoft-edge/NativeMessagingHosts/…`.) If "extension not detected" on first try → **restart Chrome** so it reads the new config.
6. `/chrome` any time = status / reconnect / pick browser / manage permissions.
7. Site permissions are inherited from the **extension settings** — grant only specific trusted domains there.

> Do **not** "Enable by default" in the CLI — official note: it always loads browser tools and raises context usage, which fights OHO's 69% context-discipline rule. Use per-session `--chrome`.

There is a `connect-chrome` skill in this workspace that wraps the connection flow — invoke it if you want guided reconnect steps.

## Security — read before pointing it anywhere

Claude in Chrome acts on a **real logged-in browser**: it can see and act on cookies, auth tokens, stored site data, and screenshots of the active tab.

- **Prompt injection is the dominant threat.** Anthropic's own research reports a **~1% attack-success-rate** under an adaptive attacker and states plainly that "a 1% attack success rate still represents meaningful risk" and "no browser agent is immune." Hidden page text, adversarial images, injected scripts can hijack the agent.
- **OHO privacy invariant (ADR-0008):** `faith` / family-named / kid-named / health-biomarker data must NEVER egress without explicit allow-list. An injection-hijacked browser agent with access to your logged-in Gmail/vault/health tabs is exactly the uncontrolled egress channel the privacy classifier exists to block.
- **Therefore:** treat it as a **clean-room dev/QA tool only**. Point it at the n8n UI, MinIO console, localhost apps, and public docs. **Never** at a tab holding faith/family/kid/health data, and **never** at banking/financial tabs (Anthropic hard-blocks those categories anyway).
- Keep the extension on **"Ask before acting,"** not "Act without asking" (the latter materially raises injection risk and may not pause for sensitive actions).
- Not Linux-headless-friendly: it drives a **visible** window and pauses for login/CAPTCHA → not a fit for OHO's scheduled/cron lane. n8n/MinIO stay canonical there.

## Verify the data-usage / retention terms

Before any sensitive-adjacent use, read <https://code.claude.com/docs/en/data-usage> for how screenshots/session captures are retained. (UNKNOWN at time of writing — verify against current docs.)

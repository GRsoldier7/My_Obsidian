---
name: notebooklm
description: |
  Complete programmatic access to Google NotebookLM via the notebooklm-py CLI.
  Creates notebooks, adds sources (URLs, YouTube, PDFs, audio, video, images), generates
  all artifact types (podcast, video, quiz, flashcards, slide deck, infographic, mind map,
  report), downloads results, and supports web research and chat.

  EXPLICIT TRIGGER on: "/notebooklm", "create a podcast about", "audio overview", "generate
  a quiz from", "summarize these URLs", "NotebookLM", "add to notebooklm", "flashcards for
  studying", "turn this into a podcast", "create flashcards", "generate a slide deck",
  "make an infographic", "create a mind map", "install notebooklm", "add notebooklm to cowork",
  "briefing doc", "study guide from", "deep dive podcast".

  Also activates on: "create a podcast about X", "I want to study this material", "can you
  summarize these documents into something I can listen to", "make this into audio content".
compatibility: Requires notebooklm-py CLI installed; Google account authenticated; Python 3.10+
metadata:
  author: aaron-deyoung
  version: "2.0"
  domain-category: core
  adjacent-skills: wrapup, knowledge-management, obsidian-automation-architect
  last-reviewed: "2026-04-03"
  review-trigger: "notebooklm-py version bump, Google NotebookLM UI changes that break auth, new artifact type added"
allowed-tools: Bash
---

## Purpose and Scope

Full automation of Google NotebookLM via `notebooklm-py` CLI — create notebooks, add sources,
generate AI artifacts (podcast, quiz, slides, etc.), and download outputs. Covers setup,
authentication, Co-work embedding, and all generation workflows.

Does NOT: edit or delete individual source content, access NotebookLM's internal chat history
without `--json`, or operate without a valid authenticated session.

---

## Section 1 — Core Knowledge

### Key Principles

1. **Auth state is fragile** — Google session cookies expire (7–30 days). Always run
   `notebooklm auth check` before any workflow. SID cookie must be present.
2. **Context must be set** — Every command except `list` and `create` requires an active
   notebook context. Use `notebooklm use <id>` before any source or generate command.
3. **Sources must be READY** — Generation uses whatever is READY. Adding a source and
   immediately generating will silently exclude it. Always wait: `notebooklm source wait <id>`.
4. **Generation is async and rate-limited** — Audio takes 10–20 min, video 15–45 min. Google
   throttles aggressively. Use `--no-wait` + `notebooklm artifact wait` to check status.
5. **Interactive login won't work in Claude Code** — `notebooklm login` opens a browser but
   needs interactive terminal input. Use the custom `nlm_login.py` script instead.
6. **Parallel generation fails** — Do not trigger two generations simultaneously on the same
   notebook. Google rate-limits at the notebook level.

### Decision Framework

| Goal | Command |
|------|---------|
| Check if auth is valid | `notebooklm auth check` |
| List all notebooks | `notebooklm list` |
| Start fresh | `notebooklm create "Title"` → `notebooklm use <id>` |
| Add web content | `notebooklm source add "https://..."` |
| Add local file | `notebooklm source add ./file.pdf` |
| Research a topic | `notebooklm source add-research "query" --mode deep --no-wait` |
| Chat with sources | `notebooklm ask "question"` |
| Generate listenable content | `notebooklm generate audio "instructions"` |
| Generate studyable content | `notebooklm generate quiz` or `flashcards` |
| Download completed artifact | `notebooklm download <type> ./output.<ext>` |

---

## Section 2 — Advanced Patterns

### Pattern 1: Stripped Cookie Auth for Co-work Embedding
When embedding auth in a Co-work skill, the full `storage_state.json` contains ~55% redundant
cookies (`.google.ae`, `.youtube.com`, etc.). Strip to only `.google.com`, `notebooklm.google.com`,
and `accounts.google.com`, minus analytics cookies (`_gcl_au`, `_ga_*`, `OTZ`). This reduces
embedded auth from ~3,100 to ~1,400 tokens while maintaining full session validity.

### Pattern 2: Source Wait → Gate Before Generate
Never call `notebooklm generate` without first confirming all sources are `READY`:
```bash
# Poll until ready (don't skip this)
notebooklm source list --json  # check all status=ready
notebooklm source wait <id>    # wait for specific source
notebooklm generate audio "Focus on key decisions"
```
Generating before sources are ready silently produces output from incomplete knowledge.

### Pattern 3: Research Mode for Unknown Topics
For broad topic synthesis where you don't have source URLs:
```bash
notebooklm source add-research "query" --mode deep --no-wait
notebooklm research wait --import-all   # waits and imports all results
notebooklm generate report --format briefing-doc
```
Fast mode (`--mode fast`) is good for well-documented topics; deep mode for emerging topics.

### Pattern 4: Multi-Format Generation from One Notebook
One notebook → multiple artifacts for different use cases:
```bash
notebooklm generate audio "Executive summary format"    # listen on commute
notebooklm generate quiz --difficulty hard              # retention testing
notebooklm generate slide-deck --format presenter       # presentation ready
```
Each runs independently. Check `artifact list` between generations.

---

## Section 3 — Standard Workflow

### First-Time Setup
1. Check Python version: `python3 --version` (must be 3.10+)
2. Create venv: `python3 -m venv ~/.notebooklm-venv`
3. Install: `pip install "notebooklm-py[browser]" && playwright install chromium`
4. Create `~/bin` dir and symlink (Windows: copy the .exe):
   ```bash
   mkdir -p "$HOME/bin"
   ln -sf "$HOME/.notebooklm-venv/Scripts/notebooklm" "$HOME/bin/notebooklm" 2>/dev/null \
     || cp "$HOME/.notebooklm-venv/Scripts/notebooklm.exe" "$HOME/bin/notebooklm.exe" 2>/dev/null \
     || true
   ```
5. **Write the nlm_login.py script** (Claude writes this file automatically):
   ```python
   # nlm_login.py — auto-detects login completion, no signal file needed
   import asyncio, json, os
   from pathlib import Path
   from playwright.async_api import async_playwright

   STORAGE_DIR = Path.home() / ".notebooklm"
   STORAGE_FILE = STORAGE_DIR / "storage_state.json"
   NLM_READY_SELECTOR = "mat-sidenav-container, notebook-list, [data-test='notebook-list'], .notebooks-container"

   async def main():
       STORAGE_DIR.mkdir(exist_ok=True)
       async with async_playwright() as p:
           browser = await p.chromium.launch(headless=False)
           context = await browser.new_context()
           page = await context.new_page()
           await page.goto("https://notebooklm.google.com/")
           print("Sign in to Google in the Chrome window. Will auto-detect when done.")
           try:
               await page.wait_for_selector(NLM_READY_SELECTOR, timeout=300_000)
           except Exception:
               for _ in range(150):
                   if "notebooklm.google.com" in page.url and "accounts.google.com" not in page.url:
                       break
                   await asyncio.sleep(2)
           await asyncio.sleep(3)
           storage = await context.storage_state()
           STORAGE_FILE.write_text(json.dumps(storage, indent=2))
           print(f"Session saved to {STORAGE_FILE}")
           await browser.close()

   asyncio.run(main())
   ```
6. **Run the login flow** (Claude does ALL of this — user only signs in to Google):
   - Claude writes `nlm_login.py` to `$TMPDIR/nlm_login.py` (Windows: `C:/Users/<name>/AppData/Local/Temp/`)
   - Claude runs it in the **foreground** (not background — we need to wait for completion):
     `python3 "C:/Users/$USERNAME/AppData/Local/Temp/nlm_login.py"`
   - Claude tells user: "Chrome is opening — sign in to Google. I'll detect when you're done automatically."
   - User signs in to Google. Script auto-detects NotebookLM load, saves cookies, exits.
   - Claude verifies: `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 notebooklm auth check`
7. If auth check shows SID present → proceed. If not → retry from step 6.

### Authentication Re-check / Re-login (session expired)
When `notebooklm list` or any command returns "Authentication expired":
1. Claude writes `nlm_login.py` (same auto-detect script above)
2. Claude runs it: `python3 "C:/Users/$USERNAME/AppData/Local/Temp/nlm_login.py"`
3. Claude tells user: "Chrome is open — sign in to Google. Auto-detects when done."
4. User signs in — script auto-saves, browser closes
5. Claude verifies: `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 notebooklm auth check`

**IMPORTANT:** `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` must prefix ALL notebooklm commands on Windows to prevent Unicode rendering errors with Rich terminal output.

### Research-to-Podcast Workflow
1. `notebooklm auth check` — stop if SID missing
2. `notebooklm create "Research: [topic]" --json` → capture `id`
3. `notebooklm use <id>`
4. `notebooklm source add "https://..."` for each source
5. `notebooklm source list --json` — confirm all `status=ready`
6. `notebooklm generate audio "Deep dive on [angle]"`
7. `notebooklm artifact wait <artifact_id>` — wait for completion
8. `notebooklm download audio ./podcast.mp3`

### Co-work Embedding Workflow
1. Verify auth: `cat ~/.notebooklm/storage_state.json`
2. Run strip script to generate minimal auth JSON
3. Read this skill file; replace Step 0 with Auto-Authentication block
4. Save as `NotebookLMSkill-Cowork.md` on Desktop
5. Tell user to upload as skill in Claude Co-work

---

## Section 4 — Edge Cases

**Edge Case 1: `notebooklm login` exits immediately / session expired**
Interactive terminal input is required but unavailable in Claude Code. The browser opens and
closes instantly. Mitigation: Claude writes and runs `nlm_login.py` — a Playwright script that
auto-detects login completion by waiting for the NotebookLM app shell selector. No signal file,
no "tell me when done" — the script saves cookies and exits automatically once the user signs in.
The user's only action is signing in to Google in the browser that appears.

**Edge Case 2: Generation fails with 429 / rate limit**
Google rate-limits at the account level across all notebooks. Mitigation: Wait 10–20 minutes,
use `--retry 3` flag, or switch to a different generation type (e.g., quiz before audio).
Never retry within 2 minutes — it burns quota without success.

**Edge Case 3: Source stuck in PROCESSING for >10 minutes**
YouTube sources take longer. PDFs with DRM fail silently. Mitigation: Check
`notebooklm source list --json` — if `status=error`, remove and re-add. For YouTube,
try a direct video URL vs. playlist URL.

**Edge Case 4: Co-work cookies expired**
Embedded cookies have a fixed expiry. Mitigation: Tell user to re-run `notebooklm login`
in Claude Code and regenerate the Co-work skill file with fresh cookies.

**Edge Case 5: Slide revision requires artifact ID**
`generate revise-slide` requires `--artifact <id>` and `--slide N` (0-indexed).
Get artifact ID from `notebooklm artifact list --json`. Omitting these causes a silent no-op.

---

## Section 5 — Anti-Patterns

**Anti-Pattern 1: Running `notebooklm login` directly**
Temptation: It's the documented login command, seems obvious.
Failure: Requires interactive Enter keypress that Claude Code's bash tool cannot send.
Browser opens, closes in <1s, no session saved.
Instead: Claude writes and runs `nlm_login.py` automatically — user only signs in to Google.
Claude sends the signal file when user confirms, then verifies auth. No manual script running required.

**Anti-Pattern 2b: Asking user to run the login script manually or say "auth done"**
Temptation: "Please run this script in a terminal" or "tell me when you're done signing in."
Failure: Breaks the skill contract — the skill must be fully automated. User frustration.
Instead: Claude runs ALL commands. The ONLY thing the user does is sign in to Google in the browser
that Claude opens. The script auto-detects NotebookLM load and saves cookies — no user action needed
beyond the Google sign-in itself.

**Anti-Pattern 2c: Missing PYTHONIOENCODING on Windows**
Temptation: Run `notebooklm auth check` directly.
Failure: UnicodeEncodeError on Windows (CP1252 can't encode checkmark ✓). Command crashes.
Instead: Prefix ALL notebooklm commands with `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` on Windows.

**Anti-Pattern 2: Generating before sources are READY**
Temptation: Source add commands return quickly — assuming they're processed.
Failure: Generation silently uses only partially-processed knowledge. Audio covers only half
the material with no warning. Quality is unpredictably degraded.
Instead: Always call `notebooklm source list --json` or `source wait` before generating.

**Anti-Pattern 3: Embedding full storage_state.json in Co-work**
Temptation: Copy the whole file for simplicity.
Failure: ~3,100 tokens of cookies per activation, most for Google domains irrelevant to
NotebookLM. Burns context window on every Co-work session.
Instead: Strip to 3 essential domains + skip analytics cookies. Produces identical auth.

**Anti-Pattern 4: Triggering parallel generations**
Temptation: Start audio and quiz at the same time to save time.
Failure: Google rate-limits at notebook level. Both fail with 429, wasting the generation
attempt. Each generation type counts against daily quota independently.
Instead: Sequential — wait for first artifact completion, then start next.

---

## Section 6 — Quality Gates

- [ ] `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 notebooklm auth check` passes with SID cookie present before any workflow (Windows: always include the env prefix)
- [ ] Notebook context set (`notebooklm status` shows a notebook) before source/generate commands
- [ ] All sources confirmed `status=ready` in `source list --json` before generating
- [ ] Artifact status confirmed `completed` in `artifact list --json` before downloading
- [ ] For Co-work: auth JSON contains cookies for exactly the 3 essential domains
- [ ] Download file exists and is non-zero bytes after `notebooklm download`
- [ ] Auth flow was fully automated — user only signed in to Google, ran no commands manually

---

## Section 7 — Failure Modes and Fallbacks

**Failure 1: Auth/Cookie Error on any command**
Detection: `notebooklm auth check` shows SID cookie missing, or any command returns auth error.
Fallback: Delete profile and re-authenticate:
```bash
rm -rf ~/.notebooklm/browser_profile ~/.notebooklm/storage_state.json
# Re-run nlm_login.py script
```

**Failure 2: "No notebook context" on source/generate**
Detection: Error message contains "No notebook context" or "no active notebook".
Fallback: `notebooklm list` to find the notebook ID, then `notebooklm use <id>`.

**Failure 3: Generation completes but download fails**
Detection: `artifact list` shows `status=completed` but download errors.
Fallback: Check artifact type matches download command. Audio→`.mp3`, video→`.mp4`,
slide-deck→`.pdf`/`.pptx`. Wrong extension causes silent failure.

**Failure 4: CLI not found**
Detection: `command not found: notebooklm`
Fallback: `source ~/.notebooklm-venv/bin/activate && notebooklm ...` or use full path
`~/.notebooklm-venv/bin/notebooklm`. Re-run symlink step if needed.

---

## Section 8 — Composability

**Hands off to:**
- `wrapup` — after a research session, push session summary to AI Brain notebook
- `knowledge-management` — when organizing outputs into vault structure
- `obsidian-automation-architect` — when routing NotebookLM outputs to Obsidian vault

**Receives from:**
- `wrapup` — when pushing session summaries to the AI Brain notebook
- Any skill — when the user needs to transform research into audio/visual/study content

---

## Section 9 — Improvement Candidates

- Auto-refresh cookies: detect expiry from `auth check` and prompt re-login before workflow fails mid-run
- Batch source addition: accept a list of URLs from a file and add sequentially with individual wait
- Artifact polling loop: replace manual `artifact wait` with a progress-reporting polling loop that shows estimated time remaining

---

## Quick Reference

> **Windows note:** Prefix ALL commands with `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` to prevent Unicode errors.
> **Auth note:** Claude runs ALL login commands. User only signs in to Google in the Chrome window.

| Task | Command |
|------|---------|
| Auth check | `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 notebooklm auth check` |
| List notebooks | `notebooklm list` |
| Create + use | `notebooklm create "Title" && notebooklm use <id>` |
| Add URL | `notebooklm source add "https://..."` |
| Add file | `notebooklm source add ./file.pdf` |
| Web research | `notebooklm source add-research "query" --mode deep --no-wait` |
| Wait research | `notebooklm research wait --import-all` |
| Chat | `notebooklm ask "question"` |
| Podcast | `notebooklm generate audio "instructions"` |
| Quiz | `notebooklm generate quiz --difficulty medium` |
| Flashcards | `notebooklm generate flashcards` |
| Slide deck | `notebooklm generate slide-deck --format detailed` |
| Report | `notebooklm generate report --format briefing-doc` |
| Mind map | `notebooklm generate mind-map` |
| Infographic | `notebooklm generate infographic` |
| Check artifact | `notebooklm artifact list` |
| Wait artifact | `notebooklm artifact wait <id>` |
| Download audio | `notebooklm download audio ./out.mp3` |
| Download quiz | `notebooklm download quiz quiz.json` |
| Download slides | `notebooklm download slide-deck ./slides.pdf` |
| Set language | `notebooklm language set zh_Hans` |

# Runbook — Rotate Telegram Bot Token (HYG-A)

**Status:** Operator-only · **Urgency:** Highest in Hygiene wave · **Why:** the token leaked in `agent-orch-lxc` `.planning/ROADMAP.md` is the **same token** live in OHO's `telegram-capture` workflow. Rotation unblocks both repos.

**Time budget:** ~5 min @BotFather + ~5 min OHO updates + ~2 min agent-orch-lxc updates = **~15 min total**.

---

## 1. @BotFather — issue new token

In Telegram:

1. Open chat with `@BotFather`.
2. `/mybots` → select `aarondy3777-bot` (or your bot's name).
3. `API Token` → `Revoke current token`.
4. BotFather issues a new token: `7XXXXXXXXXX:AAH...new...`.
5. **Copy the new token. Do not paste it in chat with anyone, including me.**

---

## 2. OHO updates (3 spots)

### 2.a — `.env` on this repo

Edit `.env` directly (never via chat). Replace the line:

```dotenv
TELEGRAM_BOT_TOKEN=<NEW_TOKEN>
```

(File-local only. `.env` is git-ignored.)

### 2.b — n8n credential

Visit `http://192.168.1.121:5678` → Credentials → `Telegram: aarondy3777-bot` → paste new token in the `accessToken` field → Save.

### 2.c — Verify

```bash
set -a && source .env && set +a
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | python3 -m json.tool
```

Expected: `{"ok": true, "result": {...your bot identity...}}`. If `ok: false` → token wrong; re-paste from BotFather.

Then send a test message via the bot's username from your own Telegram. Within ~60s, watch the n8n execution log for `telegram-capture` to confirm webhook fires.

---

## 3. `agent-orch-lxc` updates (sister repo)

Per recon doc, the token is referenced in:

- `agent-orch-lxc/.env` (or `.env.example` — verify which holds the live value)
- `agent-orch-lxc/scripts/setup-n8n.sh`
- `agent-orch-lxc/scripts/validate_env.py`
- `agent-orch-lxc/n8n/workflows/telegram-capture.json` (or wherever Phase 4 stores it)
- `agent-orch-lxc/docs/RUNBOOK.md`
- `agent-orch-lxc/DT_AgentTeam.txt` lines 477, 534, 722

For each: edit + replace. **NEVER `git add -A`** after — explicitly add files. The leaked token in commit history is already public; the rotation just makes the leaked one inert.

Commit on agent-orch-lxc:

```bash
git add <changed files>
git commit -m "chore(security): rotate Telegram bot token (HYG-A from OHO ADR-0007)"
git push
```

---

## 4. Scrub the old token from any unfortunate places

```bash
# In each repo:
grep -rn "7820977825:AAH40" . --exclude-dir=.git --exclude-dir=node_modules \
  --exclude='*.lock'
# Any hit that isn't a historical commit log → fix it.
```

If the old token survived in any *.json or *.md file: replace with the placeholder `__TELEGRAM_BOT_TOKEN__` and re-run `setup-n8n.sh` so the n8n hydration path is the only place the real token lives at rest.

---

## 5. Update the secrets-rotation table

Open `docs/security/secrets-rotation.md` and update the Telegram row:

- `last_rotated`: today's date
- `next_due`: today + 90 days

---

## 6. Confirm done

- [ ] BotFather shows ONE active token (the new one).
- [ ] `curl getMe` returns `ok: true` for the new token.
- [ ] Test message round-trips through `telegram-capture` workflow.
- [ ] OHO repo `grep -r "7820977825" .` returns zero hits outside `.git/`.
- [ ] agent-orch-lxc repo same.
- [ ] Secrets-rotation table updated.

---

## Failure modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| `getMe` returns `ok: false, error_code: 401` | Token mismatch | Re-copy from BotFather; paste exact value |
| n8n workflow doesn't fire on test message | n8n credential not saved | Reload `http://192.168.1.121:5678`; verify credential was committed |
| Old token still works in `getMe` | BotFather revoke didn't apply | `/mybots` → `API Token` → `Revoke` again |
| `setup-n8n.sh` reports `__TELEGRAM_BOT_TOKEN__` unresolved | env not sourced | `set -a && source .env && set +a` first |

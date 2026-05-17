# Secrets Rotation — OHO + Cross-Host Fleet

**Cadence default:** every secret rotates **every 90 days** unless its row says otherwise. The default is calendar-driven, not incident-driven — incident-driven rotation is always allowed and never waits for the cadence.

**Secret store of record:** Bitwarden self-hosted at `https://vault.tailfab8a7.ts.net:8443`. `.env` files on individual hosts are derived state; they are NEVER the source of truth.

**Rotation rule:** if a secret appears in any committed file in any repo, it is *already burned* — rotate immediately, then scrub. Git history is forever; the leaked secret in history is harmless ONLY because the live secret is different.

---

## Rotation cadence table

| Edge / secret                       | Type            | Where it lives                                 | Rotation cadence | Last rotated | Next due   | Runbook                                         |
|-------------------------------------|-----------------|------------------------------------------------|------------------|--------------|------------|-------------------------------------------------|
| Telegram bot (`aarondy3777-bot`)    | bot token       | n8n cred (operator preference — not `.env`)    | 90d              | 2026-05-16 ✅ | 2026-08-14 | `docs/runbooks/rotate-telegram-token.md`        |
| OpenRouter API                      | API key         | `.env` `OPENROUTER_API_KEY`; n8n httpHeaderAuth cred | 90d              | 2026-05-16 ✅ | 2026-08-14 | `docs/security/2026-05-16-INCIDENT-job-search-leak.md` |
| MinIO S3                            | access+secret   | `.env` `MINIO_*`; n8n s3 cred                  | 180d             | 2026-04-08*  | 2026-10-05 | (TBD)                                           |
| Gmail SMTP (Aaron)                  | app password    | n8n smtp cred only                             | 90d              | TBD          | TBD        | Google account → 2SV → app passwords → revoke + reissue |
| Google Calendar OAuth (GCAL)        | OAuth2 token    | n8n cred `GCAL_CRED_ID`                        | n/a — refresh    | not-issued (HYG-B3) | n/a   | n8n → Credentials → Google Calendar OAuth2      |
| `OHO_RUNNER_TOKEN`                  | bearer (FastAPI)| `.env` on dev + `/opt/oho/.env` on CT-202; n8n cred `OHO Runner Auth` | 90d | 2026-05-09  | 2026-08-07 | `openssl rand -hex 32` → `.env` → `make deploy-runner` |
| Bitwarden master                    | account passwd  | Aaron's head + 2SV                             | rotate on suspicion only | — | — | Bitwarden self-hosted → account settings        |
| Tailscale auth keys                 | one-time tokens | issued at host enroll                          | rotate per-host on rebuild | — | — | Tailscale admin console                         |
| **(P3.5 — Phase F)** `comms_token_desktop_to_lxc` | per-edge bearer | Desktop `~/.oho/comms/.env`; LXC `/opt/oho/.env`     | 90d (staged)     | not-issued   | n/a        | `make rotate-comms-token EDGE=desktop->lxc` (TBD) |
| **(P3.5 — Phase F)** `comms_token_lxc_to_desktop` | per-edge bearer | LXC `/opt/oho/.env`; Desktop `~/.oho/comms/.env`     | 90d              | not-issued   | n/a        | same                                            |
| **(P3.5 — Phase F)** `comms_token_lxc_to_vps`     | per-edge bearer | LXC `/opt/oho/.env`; VPS `/etc/oho/comms.env`        | 90d              | not-issued   | n/a        | same                                            |
| **(P3.5 — Phase F)** `comms_token_vps_to_lxc`     | per-edge bearer | VPS `/etc/oho/comms.env`; LXC `/opt/oho/.env`        | 90d              | not-issued   | n/a        | same                                            |
| **(P3.5 — Phase F)** `oho_to_broker` (CT 215)     | per-worker bearer | CT 215 `/etc/agent-control-plane/worker-tokens.yaml`; OHO `/opt/oho/.env`  | 90d | not-issued | n/a | sister repo                                     |
| **(P3.5 — Phase F)** `broker_audit_read`          | bearer          | LXC `/opt/oho/.env`; operator CLI                    | 180d             | not-issued   | n/a        | TBD                                             |

\* MinIO last rotation date approximate; verify on first scheduled rotation.

---

## Universal rotation procedure

1. **Generate** new secret. `openssl rand -hex 32` for bearers; provider portal for OAuth/API keys.
2. **Stage** the new secret receiver-side first (`COMMS_TOKENS_ACCEPTED=old,new` pattern for bearers; n8n cred edits for API keys).
3. **Update** sender-side `.env` + reload sender.
4. **Wait** 5 minutes for in-flight retries.
5. **Remove** old secret from receiver. Reload.
6. **Smoke test** the path end-to-end.
7. **Update** this table: bump `last_rotated`, recompute `next_due`.
8. **Update** Bitwarden vault entry.
9. **Commit** the table update (NOT the secrets themselves).

Zero-downtime is the discipline; receiver-accepts-both window is how we achieve it.

---

## Incident-driven rotation triggers

Rotate immediately, regardless of cadence, if any of:

- Secret appears in a `git grep` of any repo outside `.git/`.
- Secret appears in a log file outside the configured allow-list.
- A team member leaves who had access.
- An n8n workflow JSON gets shared externally (workflow exports contain credentials references but not secrets — verify before sharing).
- Bitwarden vault shows a session anomaly (login from unrecognized IP/UA).
- Tailscale admin console shows a node compromise.
- A bearer-auth failure rate exceeds 3 in 5 minutes from a single source (possible brute-force).

---

## Audit + reminder mechanism

A weekly cron (proposed; not yet implemented) reads this table and:
- Surfaces every row where `next_due` is within 14 days as a `[priority:: A] [area:: home]` task in the MTL.
- Surfaces every row where `next_due` is in the past as a PAGE-level alert via error-handler.
- Compares the table against actual `.env` ages where possible (mtime of host `.env` files via the deploy_oho_runner inspection step).

Filed under Wave-X observability when promoted.

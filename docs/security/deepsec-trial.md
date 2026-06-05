# deepsec — gated trial procedure (NOT yet run)

> Status: **scaffold only, never executed against OHO code as of 2026-05-30.**
> Tool: [vercel-labs/deepsec](https://github.com/vercel-labs/deepsec) — AI-powered vulnerability scanner. Apache-2.0, `vercel-labs` (experimental org). Node ≥22, pnpm.
> Vendor-reviewed at commit on `main` 2026-05-30. Re-review before each use (fast-moving agent SDKs).

## What it is

Two-stage scanner: (1) fast regex pass finds candidate sites, (2) drives an autonomous AI coding agent (Anthropic Claude Agent SDK and/or OpenAI Codex SDK) to investigate/triage/revalidate, exports JSON or a markdown findings dir. It **reads** source; it does not run the scanned app — but the *agent itself* has tools.

It **complements**, does not replace, OHO's rule-based audits (`audit_workflow_credentials.py`, `audit_workflow_connections.py`, `audit_extraction_receipts.py`). Those are deterministic invariant checks on n8n JSON + Python. deepsec is open-ended AI vuln discovery, strongest on app code (`services/oho_runner/`, `tools/*.py`, `clients/agent_orch_client.py`). It is a **manual, supervised tool** — never a cron/n8n job.

## Security facts (verified by source read, not README)

- The triage/enrich agent runs with `allowedTools: ["Read","Glob","Grep","Bash"]` and `permissionMode: "dontAsk"` (`packages/processor/src/agents/claude-agent-sdk.ts:226,469`). **Bash runs with no approval prompt.**
- **Local mitigation:** on Linux, the Agent SDK wraps the spawned `claude` CLI in a **bubblewrap** OS sandbox (`buildSandbox()`, same file). But the code comment is explicit: "No filesystem or network restrictions are layered on top." So the agent can read any file it can reach and make network calls within bubblewrap. Only **Vercel Sandbox microVM mode** restricts egress to AI-provider hosts.
- **Source egress is by design:** repository source is sent to an external LLM (Anthropic / OpenAI, or via Vercel AI Gateway). Anything in scanned files — including embedded secrets/PII — leaves the homelab.
- **Creds deepsec consumes:** `AI_GATEWAY_API_KEY`, `ANTHROPIC_AUTH_TOKEN` (or `ANTHROPIC_BASE_URL` proxy), `OPENAI_API_KEY`. The long list of `DB_PASSWORD`/`STRIPE_KEY`/`JWT_SECRET`/`COSMOSDB_MASTER_KEY` strings in the source are **secret-detection regex signatures** (what it hunts in *target* code), NOT keys it reads from your env.
- **Supply chain:** deps include `@anthropic-ai/claude-agent-sdk@^0.3.158`, `@openai/codex` + `@openai/codex-sdk@^0.125.0`, `@vercel/sandbox`, `jiti` (runtime TS loader), `tar`, `minimatch`. `jiti` executes TS at runtime — re-pin/review before each use.

## Hard rules for any OHO trial

1. **Never** the OHO production creds. No OpenRouter key, no n8n creds, no MinIO creds. Provision a **dedicated throwaway** Anthropic or Vercel AI-Gateway key, used nowhere else, revoked after the trial.
2. The scoped key goes in a **throwaway env file outside this repo** (e.g. `~/.deepsec-trial.env`), **never** OHO `.env`.
3. Point it at a **copy** of `services/oho_runner/` + `tools/` only. **Exclude** `.env`, the Obsidian vault, `workflows/` (placeholder creds), `docs/security/`, anything secret-bearing.
4. Prefer **`--sandbox` (Vercel Sandbox)** mode so egress is restricted to AI hosts. If running local, accept that bubblewrap does NOT restrict network.
5. Treat all output as **leads, not verified vulns** — human-triage every finding (OHO anti-hallucination discipline).
6. Per OHO CLAUDE.md: external tools are scanned before use. This doc is that review. Do not skip the re-review on version bumps.

## Procedure (operator runs manually — do NOT automate)

```bash
# 0. Re-review the pinned agent-SDK versions in packages/deepsec/package.json first.

# 1. Throwaway scoped key (NEVER reuse an OHO key). Put in a file OUTSIDE this repo:
echo "ANTHROPIC_AUTH_TOKEN=sk-ant-THROWAWAY"  > ~/.deepsec-trial.env   # or AI_GATEWAY_API_KEY

# 2. Stage a SCOPED COPY — only the app code, never secrets/vault/workflows:
rm -rf /tmp/deepsec-target && mkdir -p /tmp/deepsec-target
cp -r services/oho_runner tools /tmp/deepsec-target/
# sanity: confirm no secrets came along
grep -rIl -e 'sk-' -e 'AKIA' -e 'PASSWORD=' /tmp/deepsec-target && echo "ABORT: secret in target" || echo "target clean"

# 3. Init deepsec in an isolated workspace + install:
cd /tmp && npx deepsec init && cd .deepsec && pnpm install

# 4. Run against the COPY, sandbox mode preferred. Load the throwaway env only for this shell:
set -a && source ~/.deepsec-trial.env && set +a
pnpm deepsec scan    --target /tmp/deepsec-target --sandbox
pnpm deepsec process --sandbox
pnpm deepsec export  --format md-dir --out /tmp/deepsec-findings

# 5. Review /tmp/deepsec-findings/ by hand. Cross-check each before acting.

# 6. Teardown: revoke the throwaway key, rm -rf /tmp/deepsec-target /tmp/deepsec-findings ~/.deepsec-trial.env
```

## Decision gate

If the trial surfaces real bugs the rule-based audits miss → consider a recurring **manual** quarterly pass over the app code. Do **not** wire into `audit-all`/cron (interactive, paid, nondeterministic, code egresses). Revisit if OHO ever needs air-gapped scanning (deepsec can't do that — it needs an external LLM).

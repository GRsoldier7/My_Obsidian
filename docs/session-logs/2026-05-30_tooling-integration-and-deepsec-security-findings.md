# 2026-05-30 — External Tooling Integration + deepsec Security Findings

**Session goal:** Evaluate 5 external repos/tools for the OHO workflow, adopt the ones that fit, and run the adopted security scanner (deepsec) against OHO code.

**Branch:** work done on `polish/prod-ready`; the one code fix is on `fix/runner-health-info-disclosure` (off `polish/prod-ready`).

---

## 1. Five-tool evaluation — verdicts & decisions

Researched in parallel (5 agents), then decided with the operator.

| # | Tool | License | Verdict | Operator decision |
|---|------|---------|---------|-------------------|
| 1 | [crafter-station intent-layer](https://github.com/crafter-station/skills/tree/main/context-engineering/intent-layer) | MIT | trial | **Adopted** (scanned + installed) |
| 2 | [vercel-labs/deepsec](https://github.com/vercel-labs/deepsec) | Apache-2.0 | trial (gated) | **Adopted + run** (findings below) |
| 3 | [vercel-labs react-best-practices](https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices) | MIT | **skip** | Skipped — zero React surface in OHO |
| 4 | [rohitg00/agentmemory](https://github.com/rohitg00/agentmemory) | Apache-2.0 | needs-decision | **Skipped** — stay NotebookLM + files |
| 5 | Claude in Chrome (Anthropic extension) | proprietary | trial (dev/QA) | **Adopted** (guide written; operator-manual install) |

**Memory-backend decision (agentmemory):** rejected for now. It's Node + the `iii-engine` runtime (an island in a Python homelab), brings its own SQLite (ignores existing Postgres/MinIO), and pins an old `iii v0.11.2`. If a DB-backed memory is ever wanted, the cleaner path is **pgvector on the existing Postgres** or `mem0`, not agentmemory. Current memory layer (NotebookLM + markdown/frontmatter files) stays canonical.

---

## 2. What landed in the repo

- **intent-layer skill** → `.claude/skills/intent-layer/` (copied, NOT symlinked, so it stays out of `scripts/sync_foundation_skills.sh`).
  - skill-sentinel scan: **SAFE TO DEPLOY / LOW** — 8/8 threat categories clear. Scripts are read-only (`find`/`cat`/`grep`/`wc`); no network, no credential reads, no eval.
  - Design caveat: its "ONE root file" rule conflicts with OHO's deliberate dual `CLAUDE.md` + `AGENTS.md` (audit-enforced by `scripts/audit_ai_tooling.py`). **Never let it rewrite root files.** Value = the child-`AGENTS.md` node idea + token-estimate diagnostics.
  - Its diagnostics flagged `scripts/` (~72k tokens) and `workflows/` (~76k) as candidates for child `AGENTS.md` nodes. (Not generated — optional future work.)
- **deepsec trial doc** → [docs/security/deepsec-trial.md](../security/deepsec-trial.md) (vendor review + gated procedure).
- **Claude-in-Chrome guide** → [docs/claude-in-chrome-guide.md](../claude-in-chrome-guide.md).
- **`.gitignore`** → added `.deepsec/` + `.deepsec-trial.env` guards.
- **/health fix** (branch `fix/runner-health-info-disclosure`):
  - [services/oho_runner/app.py](../../services/oho_runner/app.py) — unauth `/health` reduced to minimal liveness; verbose diagnostics moved behind bearer auth at new `GET /health/jobs`.
  - [tests/test_runner_health_info_disclosure.py](../../tests/test_runner_health_info_disclosure.py) — 4 regression tests. **Not yet committed.**

---

## 3. deepsec engagement — the security scan

**What deepsec is:** Apache-2.0 AI vulnerability scanner. Two stages: (1) fast regex matchers find candidate sites; (2) an autonomous AI coding agent (Claude Agent SDK *or* OpenAI Codex SDK) investigates/triages. It has no model of its own — it drives a logged-in `claude`/`codex` CLI or a metered API key.

**Auth/cost behavior (verified by source read):**
- `preflight.ts:180-181`: in **local mode**, if a logged-in `claude` CLI is on PATH, it uses `~/.claude/.credentials.json` → the Claude **subscription**, no metered key.
- The agent runs `allowedTools: ["Read","Glob","Grep","Bash"]` + `permissionMode: "dontAsk"` (Bash with no approval prompt). On Linux it's bubblewrap-sandboxed (FS-escape blocked) but **network is not restricted** in local mode.
- deepsec **auto-selects** the agent from whatever CLI is logged in. With both `claude` and `codex` logged in, **it chose `codex`/`gpt-5.5`** for the `tools/` run → that one **billed the OpenAI account ($0.86)**, not the free subscription. Pass `--agent claude-agent-sdk` to force the subscription.

**Harness guardrails hit:** the Claude Code auto-mode classifier **blocked** `pnpm install` and `deepsec process` as untrusted-code-execution / unsandboxed-agent-egress. Operator ran those steps manually. (Correct behavior — those need deliberate human sign-off.)

**Scope discipline:** scanned only **copies** of `services/oho_runner/` and `tools/`, secret-scanned first; `.env`/vault/`workflows/` excluded. Per-target `INFO.md` written grounded in the real source (incl. pre-marking sha256 content-hashing + the intentional `SKELETON_MODE` privacy classifier as known false-positives).

### Findings

| Target | Files | Regex candidates | Confirmed findings |
|--------|-------|------------------|--------------------|
| `oho_runner` (sidecar) | 4 | 1 (`crypto-usage`) | **1 MEDIUM** (real) |
| `tools/` | 11 | 2 (`crypto-usage`) | **0** (both candidates confirmed benign) |

`tools/` run stats: filesProcessed 2 · findingsCount 0 · cost **$0.86** (codex/gpt-5.5) · 164s.

### The one real finding — [MEDIUM] `/health` info-disclosure

- **What:** unauthenticated `GET /health` returned recon-useful internals — `workdir` (`/opt/oho`), `python` executable path, and the **full `command` argv tuples + script-presence for every privileged job**.
- **Why it's valid:** not a secret leak (token/env were booleans, correct) but **layout/job recon** that aids attacking the authenticated POST endpoints. Class of bug the rule-based `audit_workflow_*` scripts structurally cannot see.
- **Real-world severity in OHO:** LOW→MEDIUM. Sidecar is LAN/Tailscale-only on a private LXC, called by n8n — attacker-on-network precondition. Defense-in-depth fix still cheap.
- **Fix:** minimal unauth `/health` (liveness booleans + aggregate `all_scripts_present`, no paths/commands/job-names); verbose detail moved to bearer-auth `GET /health/jobs`.
- **Consumer check before changing shape:** the only programmatic consumer is the deploy smoke probe ([scripts/deploy_oho_runner.py](../../scripts/deploy_oho_runner.py) ~L621-649) which just needs HTTP 200 — confirmed unaffected. No test asserted the old shape.
- **Verification:** new tests 4/4 pass · existing runner tests 45/45 pass · live JSON confirmed (unauth body carries no path/command; `/health/jobs` → 401 without token, full detail with valid bearer).

---

## 4. deepsec — keep or drop?

**Keep, as a manual supervised pass.** It found 1 true positive across the scan that the deterministic audits couldn't. But:
- **Not for cron/`audit-all`** — agentic, slow, nondeterministic, code egresses to an external LLM.
- **Force the free agent:** always pass `--agent claude-agent-sdk` (else it may pick metered codex).
- **Scope inputs every time:** copies only, secret-scan first, never `.env`/vault.
- Re-review the pinned agent-SDK versions before each use (`jiti` runtime-TS loader = supply-chain surface).

---

## 5. Open items / next steps

- [ ] **Commit** the `/health` fix on `fix/runner-health-info-disclosure` (1 source + 1 test), then merge to `polish/prod-ready`.
- [ ] When deployed, the fix changes `/health` shape — confirm the n8n `system-health-monitor` workflow (if it reads runner `/health`) still works; it only needs reachability/`status`.
- [ ] Optional: add `--agent claude-agent-sdk` note to [docs/security/deepsec-trial.md](../security/deepsec-trial.md) so future runs default to the free subscription.
- [ ] Optional: generate child `AGENTS.md` nodes for `scripts/` + `workflows/` (intent-layer flagged them).
- [ ] Scratch staged at `/tmp/deepsec-target` + `/tmp/deepsec-tools` (ephemeral; `.deepsec` workspace holds both registered projects).

**Operator-manual (not automatable by Claude):** Claude-in-Chrome extension install; any further `pnpm deepsec process` runs (classifier-gated).

---

## Addendum — 2026-05-31: n8n disk-full (ENOSPC) incident

Separate from the tooling work, error emails arrived: "🚨 n8n Error: 📚 Article
Processor — Parse URLs". Real error was **`ENOSPC: no space left on device`** on
the CT-202 LXC — n8n could not `mkdir` an execution's binaryData dir. Not a code
bug; the disk was full from ~860 unpruned execution binaryData artifacts (oldest
2026-05-17, no pruning configured).

**Fix applied (this session):**
- Deleted 685 executions older than 3 days via the n8n API (0 failures) → freed
  their on-disk binaryData → newest execution then returned `status: success`.
- Added an early-warning canary `check_n8n_execution_backlog()` to
  `scripts/health_check.py` (PASS <1200, WARN ≥1200, FAIL ≥2500 retained) + 5 tests.
- Documented the full playbook in `docs/RUNBOOK.md` § Disk-Full / Execution Pruning.

**Operator action still required:** enable pruning on CT-202 —
`EXECUTIONS_DATA_PRUNE=true`, `EXECUTIONS_DATA_MAX_AGE=168`,
`EXECUTIONS_DATA_PRUNE_MAX_COUNT=500`, then recreate the n8n container. Until
then the backlog will slowly regrow (canary will WARN first).

# ADR-0003: Vault Files at MinIO Bucket Root (No Prefix)

**Date:** 2026-03-29  
**Status:** Accepted  
**Deciders:** Aaron DeYoung

---

## Context

The Obsidian vault is synced to a MinIO S3 bucket (`obsidian-vault`) by the **Remotely-Save** plugin. When the plugin was configured, it was set to store files at the bucket root — meaning a vault file like `00_Inbox/brain-dumps/BrainDump.md` lives at the MinIO key `00_Inbox/brain-dumps/BrainDump.md`, not `Homelab/00_Inbox/brain-dumps/BrainDump.md`.

An early assumption in several n8n workflow configurations used a `Homelab/` prefix for all S3 paths, causing workflows to look for files that didn't exist at the expected keys.

This was discovered during the 2026-03-29 n8n audit. See `docs/2026-03-29-n8n-audit-and-fix.md` for the full incident report.

---

## Decision

**Vault files are at the bucket root. No prefix. This is canonical.**

All code, scripts, and workflow configurations use bare vault-relative paths:
- `00_Inbox/brain-dumps/` ✓
- `10_Active Projects/Active Personal/!!! MASTER TASK LIST.md` ✓

Any path with a leading `Homelab/` prefix is **wrong**:
- `Homelab/00_Inbox/brain-dumps/` ✗

The CLAUDE.md `CRITICAL RULES` section states this explicitly. This ADR provides the full history.

---

## What Caused the Incident

The n8n workflows were originally written with a `Homelab/` prefix assumption inherited from an earlier vault configuration draft. When the Remotely-Save plugin was actually installed and configured (months later), it defaulted to bucket root — but the workflows weren't updated to match.

Result: workflows ran daily, appeared to succeed (n8n showed green), but silently processed nothing. Brain dump files existed at `00_Inbox/...` but workflows were looking at `Homelab/00_Inbox/...`. Zero-length file lists → zero tasks extracted.

Root cause: No end-to-end test verified that S3 put + list + get all used the same key format.

---

## Fix Applied (2026-03-29)

1. Audited all 11 v2 workflow JSONs — updated every `Prefix`, `Key`, and path reference to remove `Homelab/`
2. Audited all Python scripts — `process_brain_dump.py`, `e2e_test.py`, `health_check.py` all confirmed using bare paths
3. Added `BRAIN_DUMPS_PREFIX = "00_Inbox/brain-dumps/"` as a named constant in `process_brain_dump.py` to prevent future drift
4. Added vault file checks in `health_check.py` that verify specific known keys exist at bucket root

---

## Consequences

**Rule:** Never add a prefix to vault S3 paths. The bucket IS the vault.

**Exception:** If a future Remotely-Save reconfiguration adds a prefix (e.g., the plugin is reinstalled), ALL paths across all workflows and scripts must be updated simultaneously, and e2e tests re-run.

**Detection:** The e2e test (`scripts/e2e_test.py`) writes to `00_Inbox/brain-dumps/E2E-Test-BrainDump.md` and reads back from `00_Inbox/processed/`. If this test passes, the path mapping is correct.

---

## Related

- `docs/2026-03-29-n8n-audit-and-fix.md` — full incident report and audit details
- `tools/process_brain_dump.py` — `BRAIN_DUMPS_PREFIX`, `PROCESSED_PREFIX` constants
- `scripts/e2e_test.py` — integration test that catches prefix drift
- CLAUDE.md `CRITICAL RULES` — enforces this in all future AI-assisted code generation

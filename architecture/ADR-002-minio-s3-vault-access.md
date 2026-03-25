# ADR-002: MinIO S3 as the Canonical Vault Access Layer

**Status:** Accepted
**Date:** 2026-03-24
**Decision Maker:** Aaron (system owner)
**Supersedes:** The filesystem (`fs.readFileSync`) approach used in all workflows prior to this date.

---

## Context

The n8n automation instance runs inside a Proxmox LXC container at `192.168.1.121:5678`. It has no filesystem access to Aaron's Mac, where the Obsidian vault lives. The original three workflows (`brain-dump-processor.json`, `daily-note-creator.json`, `overdue-task-alert.json`) used `fs.readFileSync()` and `fs.writeFileSync()` inside n8n Code nodes — these calls target the container's local filesystem, which does not contain the vault. **All three workflows were silently broken in production.**

MinIO (`192.168.1.240:9000`) is the correct intermediary: the Obsidian vault on Mac syncs to MinIO via the Remotely Save plugin, and n8n reads/writes through the S3 API. This is the architecture already described in the Mission Control reference document.

---

## Decision

All n8n workflows use n8n's native **AWS S3 node** (`n8n-nodes-base.awsS3`) to read and write vault files from MinIO bucket `obsidian-vault` with vault root prefix `Homelab/`.

---

## Rationale

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| `fs` module in Code nodes | Simple JS | Only works if n8n is on same machine as vault | ❌ Rejected |
| Obsidian Local REST API | Direct live reads | Obsidian must be open; Mac IP changes | ❌ Backup only |
| HTTP Request + AWS Sig V4 | No credential setup | ~80 lines of crypto boilerplate per node | ❌ Too complex |
| **n8n AWS S3 node + MinIO credential** | Clean, maintainable, native n8n | One-time credential setup | ✅ **Accepted** |

---

## Implementation

### n8n Credential Setup (one-time)

In n8n → Settings → Credentials → New → AWS:

| Field | Value |
|-------|-------|
| Credential name | `MinIO — obsidian-vault` |
| Region | `us-east-1` *(ignored by MinIO but required by n8n)* |
| Access Key ID | *(from .env MINIO_ACCESS_KEY — Claude_Cowork service account)* |
| Secret Access Key | *(from .env MINIO_SECRET_KEY)* |
| Custom Endpoint | `http://192.168.1.240:9000` |
| Force path style | ✅ Enabled *(required for MinIO)* |

All workflows reference this credential by name: `"name": "MinIO — obsidian-vault"`. When a workflow is imported and a credential with that name already exists in n8n, it auto-links.

### File Path Convention

```
MinIO bucket:   obsidian-vault
Vault prefix:   Homelab/
Brain dumps:    Homelab/00_Inbox/brain-dumps/BrainDump — {Domain}.md
Master tasklist: Homelab/10_Active Projects/Active Personal/!!! MASTER TASK LIST.md
North Star:     Homelab/000_Master Dashboard/North Star.md
Daily notes:    Homelab/40_Timeline_Weekly/Daily/YYYY-MM-DD.md
```

### Sync Dependency

Vault files must be synced to MinIO via the Remotely Save plugin (already installed). If sync is delayed, n8n will read/write a slightly stale version. This is acceptable for a daily-cadence system.

---

## Consequences

- n8n workflows now work correctly from the LXC container.
- One-time credential setup required in n8n UI before importing any workflow.
- Vault must be actively syncing to MinIO via Remotely Save (verify in Obsidian Settings → Remotely Save → endpoint: `http://192.168.1.240:9000`, bucket: `obsidian-vault`).
- The Python fallback script (`scripts/process_brain_dump.py`) continues to use direct filesystem access for local/manual runs.

---

## Area → Vault Folder Mapping (Canonical)

| Area | MinIO Write Path |
|------|-----------------|
| `faith` | `Homelab/30_Knowledge Library/Bible Studies & Notes/` |
| `family` | `Homelab/20_Domains (Life and Work)/Personal/Family/` |
| `business` | `Homelab/20_Domains (Life and Work)/Personal/Business Ideas & Projects/` |
| `consulting` | `Homelab/20_Domains (Life and Work)/Career/Consulting/` |
| `work` | `Homelab/20_Domains (Life and Work)/Career/Parallon/` |
| `health` | `Homelab/30_Knowledge Library/Biohacking/` |
| `home` | `Homelab/20_Domains (Life and Work)/Personal/Home/` |
| `personal` | `Homelab/20_Domains (Life and Work)/Personal/` |

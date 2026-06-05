# Session Log — 2026-06-05 — ENOSPC was host-root, not n8n

**One line:** An n8n `ENOSPC` error that looked like a code bug (and looked like the
2026-05-31 incident) was neither — the Proxmox **host root LV was 100% full** from a
stale 48G photo-sync copy, not from n8n. Fixed at the foundation and made self-healing.

---

## What We Did

- **Diagnosed the true root cause by verifying the filesystem, not trusting the app.**
  `ENOSPC ... mkdir /home/node/.n8n/binaryData/.../executions/9621` (Article Processor,
  wf `4HAStrQY`). `/home/node/.n8n` is a bind mount onto the **Proxmox host root LV
  `pve-root`** (96G), which was **100% full — 0 bytes free**. n8n was the victim, not the
  cause (its binaryData was only 1.2G).
- **Found the real hogs:** a **48G photo-library copy** at `/mnt/ssd-storage/immich-library`
  + ~21G unrotated backups + ~9G dev caches — all dumped onto the OS disk.
- **Found the recurrence mechanism:** cron `0 3 * * 3,6 /root/homelab/scripts/sync-photos-nas-to-ssd.sh`
  rsyncs the NAS photo library to a "local SSD" that **does not exist** (no SSD; the
  `ssd-fast` Proxmox storage is `disable`d), for an **Immich instance that isn't running**.
  It re-dumped 48G onto `pve-root` every Wed/Sat.
- **Recovered the disk safely:**
  - n8n: deleted executions >3d via API (462 → 175).
  - Caches + old backups rotated (~9G).
  - Verified the 48G copy was a **complete subset of the NAS** (rsync `-rni --size-only`
    dry-run empty; byte-identical sample; NAS = 129G superset) → deleted it.
  - **Result: pve-root 100% → 43% (52G free).**
- **Made it self-healing:**
  - Disabled the photo-sync cron (commented in `root@pve` crontab; backup at
    `/root/crontab.bak.20260605-ohofix`).
  - Enabled n8n built-in pruning (`EXECUTIONS_DATA_PRUNE=true`, `MAX_AGE=168`,
    `PRUNE_MAX_COUNT=500`) in `/opt/n8n/.env`; recreated `n8n-n8n-1`.
  - Added `check_n8n_disk_errors` to `scripts/health_check.py` — scans recent executions
    for ENOSPC, FAILs if any in last 24h (+5 tests; 22/22 pass).
- **Verified end-to-end:** reproduced the failing `mkdir` → `WRITE_OK`; `df -h /data` 52G
  free; health check green (disk canary shows expected 24h-lagging FAIL that auto-clears).

## Decisions Made

- **Delete the 48G photo copy, not relocate it** — proven a complete duplicate of the
  authoritative NAS library (Aaron confirmed; rsync dry-run empty). No data at risk.
- **Retire the photo-sync cron, don't re-point it** — no SSD, no Immich; the NAS is the
  proper photo home. Reversible (commented). Re-enable only after carving a real LV.
- **Symptom-canary over proxy-canary** — the existing execution-count canary was
  structurally blind to non-n8n host-disk fills (stayed green at ~220). The new canary
  watches the actual ENOSPC symptom, catching a full disk regardless of which FS fills.
- **n8n pruning ON** — hygiene/future-proofing even though n8n wasn't the cause.

## Key Learnings

- **`pct exec 202 -- df -h /data` (== `df -h /` on pve) is the FIRST diagnostic** for any
  n8n ENOSPC. The n8n data dir lives on `pve-root`; the disk can fill for reasons that
  have nothing to do with n8n. A green count-canary does not mean the disk is healthy.
- **A "self-healing" safeguard that monitors a proxy can be silently blind.** The 05-31
  fix added a count-canary; it could not see this fill. Monitor the symptom, not a stand-in.
- **A deferred permanent fix is a scheduled recurrence.** (05-31 deferred pruning → it
  regrew. This time the photo-sync cron would have re-filled tomorrow.) Neutralize the
  *mechanism*, not just the *state*.
- **Verify duplicates before deleting irreplaceable data** — superset size + byte-identical
  sample + empty rsync dry-run = provably safe. Applied to 48G of family photos.

## Open Threads

- **Optional:** if Immich is ever wanted, carve a dedicated LV from the 816G `pve-data`
  pool, mount at `/mnt/ssd-storage`, enable the `ssd-fast` storage, then re-enable the
  photo-sync cron. Until then it stays disabled. (Tracked in NEXT-STEPS + RUNBOOK.)
- Disk canary will read FAIL for <24h post-fix (lagging signal), then auto-PASS.

## Tools & Systems Touched

Proxmox `pve` (root LV, crontab, LVM/`pve-data` pool) · CT-202 LXC (`pct exec`) ·
n8n container `n8n-n8n-1` at `/opt/n8n` · n8n REST API (execution prune) · Synology NAS
(NFS photo share, duplicate verification) · `scripts/health_check.py` +
`tests/test_health_check.py` · `docs/RUNBOOK.md` § Disk-Full.

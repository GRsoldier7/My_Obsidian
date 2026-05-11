# ADR-0006: Life OS Home Consolidation — Single Daily Command Center

**Date:** 2026-05-06
**Status:** Accepted — Phase 1–3 implemented in this commit; Phase 4 (workflow wire-in) and Phase 5 (Bases) deferred
**Deciders:** Aaron DeYoung
**Supersedes:** the implicit "many dashboards, hand-curated" pattern that produced 12 dashboard files in `000_Master Dashboard/` of which only `Live Dashboard.md` and `Needle Movers.md` auto-update

---

## Context

P1 closed the integrity layer (ADR-0005). The next blocker is **operator UX**: brain-dump outputs are produced cleanly, but the human-facing surface is broken.

Verified state on 2026-05-06:

- 12 dashboards in `000_Master Dashboard/`. Only `Live Dashboard.md` (4038B) and `Needle Movers.md` (5916B) are auto-rebuilt hourly by `live-dashboard-updater`.
- `Home.md` (4258B) was last written 2026-04-26 — 10 days stale. `tools/build_home_view.py` exists but is not on a schedule.
- Six March-vintage dashboards (Mission Control, North Star, Personal & Life, The Catch All, Faith & Spirit, Health & Biohacking, Work — *) are 6+ weeks stale.
- `00_Inbox/processed/` accumulates one file per source per processed-day. 12 files and growing. The expectation that a human reads these is the wrong model.
- Result: when Aaron opens the vault to act on the day, the file tree presents 12 plausible landing pages, only one of which is current, and none of which is named to float to the top. The system pulls toward the wrong surface.

This is a UX failure, not a pipeline failure. The pipeline is healthy — receipts on 2026-05-03 / 04 / 05 all match logs.

---

## Decision

**One auto-rebuilt landing page replaces the dashboard sprawl.**

- Path: `000_Master Dashboard/!!! DAILY COMMAND CENTER.md`
- Generator: [tools/build_command_center.py](../../tools/build_command_center.py)
- Filename floats to the top of the file tree on alphabetical sort (leading `!!!`).
- Pinned/bookmarked as the operator's single entry point. `Live Dashboard.md` and `Needle Movers.md` survive as drill-down metric views, cross-linked from the command center's `🧾 System/Audit Links` section.
- Old `Home.md` is replaced with a one-paragraph redirect stub pointing at the new file.
- `00_Inbox/processed/` gets a `! README.md` declaring it audit-only — humans don't browse it, the command center surfaces what they need.

### Section structure (locked by user, 2026-05-06)

```
# !!! DAILY COMMAND CENTER
## 🔥 Do This First
## 🧠 New From Brain Dumps
## ✅ Ready-To-Act Tasks
## ❓ Needs Review
## 📚 Articles / References
## 🗂 By Life Area
## 🧾 System/Audit Links
```

Each H2 is a stable navigation anchor. Inside each section, content uses Obsidian callouts (`> [!important]+`, `> [!warning]+`, `> [!info]-` etc.) for visual hierarchy and collapsibility on mobile. Tasks render via Dataview `TASK` queries so checking off the rendered task checks the original line in MTL.

### Content sources per section

| Section | Source |
|---------|--------|
| 🔥 Do This First | Computed top open task from MTL (priority A first, then earliest overdue, then earliest due); overdue grouped by criticality (Critical 8d+, High 4-7d, Recent 1-3d); Q2 Rocks alignment hint |
| 🧠 New From Brain Dumps | `99_System/state/last-brain-dump-summary.json` (new file emitted by `process_brain_dump.py`); top 10 newly-added tasks; 7-day rollup of processed file count |
| ✅ Ready-To-Act Tasks | Dataview TASK from MTL (due today + priority A; Quick Wins) |
| ❓ Needs Review | Inline list parsed from `00_Inbox/review-queue.md` if present |
| 📚 Articles / References | Dataviewjs from `00_Inbox/articles-to-process.md`; inline `[explore:: true]` items |
| 🗂 By Life Area | Dataview TASK GROUP BY area, sorted priority/due |
| 🧾 System/Audit Links | Drill-down nav (Live Dashboard, Needle Movers, Pipeline Health, MTL, processed/, receipts, run logs); last receipt audit + last brain-dump run timestamp |

### Operator-summary state file (new contract)

`tools/process_brain_dump.py` writes a small `99_System/state/last-brain-dump-summary.json` at the end of every successful run. The command-center generator reads this — *not* the run log — so the summary stays decoupled from log schema churn. Shape:

```json
{
  "run_finished_at": "2026-05-06T11:18:42+00:00",
  "status": "success",
  "tasks_written": 5,
  "review_added": 0,
  "articles_queued": 2,
  "files_extracted": ["BrainDump — Personal.md"],
  "files_partial": [],
  "files_error": [],
  "top_added_tasks": [
    {"area": "business", "priority": "A", "desc": "..."},
    ...
  ]
}
```

If the file is missing or older than 36h, the command-center renders a `> [!warning]+` calling that out.

---

## Phased rollout

| Phase | Scope | Status |
|---|---|---|
| 1 | Create `tools/build_command_center.py`. Add `! README.md` writer for `00_Inbox/processed/`. | ✅ this commit |
| 2 | Emit `99_System/state/last-brain-dump-summary.json` from `process_brain_dump.py`. | ✅ this commit |
| 3 | Replace `Home.md` content with a redirect stub when the new file is verified. | ✅ this commit (idempotent — re-runnable) |
| 4 | Wire into `live-dashboard-updater` workflow at the existing `:03` slot via an HTTP follow-on to the OHO runner sidecar. | ✅ this commit (code-complete; needs operator deploy of new runner image) |
| 5 | Migrate Q2 Rocks content out of `North Star.md` into the command center; archive remaining stale dashboards to `09_Archives/dashboards/`. | ⏳ deferred — needs operator-with-creds audit pass |
| 6 | Convert MTL filterable view to Obsidian Bases (1.9+) once it stabilises. | ⏳ explicitly deferred until P2 threaded tasks land |

Phase 4 wire-in note: the existing `live-dashboard-updater` already runs hourly at `:03` with internal Code → S3 nodes. Adding `tools/build_command_center.py` to that workflow is one `executeCommand` node call after the Code+S3 step. No new cron slot required → no contention with the `:43` / `:53` open slots → no test_workflow_templates.py changes needed for slot allocation. Test will need updating only if the workflow gains a Code node that's heavy enough to count as Code-heavy in the cron-collision rule.

---

## Why one home, not two surfaces

An earlier draft proposed two files: `!!! DAILY COMMAND CENTER.md` (action) + `!!! BRAIN DUMP REVIEW.md` (review). Rejected after user feedback. Two surfaces means two things to babysit, two things to forget, two ways to drift. One home with a `🧠 New From Brain Dumps` section and a `❓ Needs Review` section folds the review surface in without doubling the discoverability cost. Audit data (processed files, receipts, logs) stays one click away in `🧾 System/Audit Links` for when investigation is actually needed.

---

## Why callouts over plain markdown

Obsidian callouts (`> [!type]+/-` syntax) give visual hierarchy, color, and collapsibility for free, render on mobile, and don't require a plugin. Plain markdown headers leave the page as a wall of bullets. The `+`/`-` modifier means high-frequency content stays expanded (`Do This First`) while low-frequency rollups stay folded (`This week's captures`).

---

## Anti-patterns this ADR closes

- **Hand-curated dashboards.** If a file isn't auto-rebuilt, it goes stale. Every section in the command center has a code-driven source.
- **Multi-surface review.** The codex draft of two surfaces is rejected; one home, one review section inside it.
- **`processed/` as operator output.** It's audit-trail. The README marks it as such.
- **Dashboard sprawl.** Six stale March files cluttering the tree. Phase 5 archives them.

---

## Open questions

- **Filename punctuation.** `!!! DAILY COMMAND CENTER` confirmed by user. Em-dash variants (`Life OS — Home`) rejected to avoid the em-dash slug class that bit the receipt audit on 2026-05-04.
- **Bases vs Dataview for MTL view.** Phase 6. Bases is faster and native but newer; Dataview's task-level checkboxes are still the only way to tick off the rendered task to also tick off the source row.
- **Q2 Rocks as inline metadata.** Currently a static prose block in `process_brain_dump.py`. Future work: extract to a config file the command center can render in `🔥 Do This First`.

---

## Test surface

- Unit tests for `build_command_center.py` renderers cover: empty MTL, MTL with no priority A, missing `last-brain-dump-summary.json`, stale summary (>36h), summary with files_error, summary with files_partial, no review queue file, empty articles list.
- `process_brain_dump.py` summary emission has a regression test: every successful run must produce `last-brain-dump-summary.json` whose fields match the run log's totals.

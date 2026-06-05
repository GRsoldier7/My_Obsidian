# Obsidian Life Mission Control — Strategic Overhaul Plan

**For:** Aaron DeYoung
**Date:** March 22, 2026
**Status:** IMPLEMENTED — Changes applied to vault on this date.

---

## What Was Done (Change Log)

### Files Created
- **`000_Master Dashboard/North Star.md`** — New top-level note defining 5 Life Pillars, Q2 2026 Quarterly Rocks (one needle-mover per pillar), the Decision Filter, and the review cadence. Includes live Dataview queries that pull Priority A tasks by area.
- **`10_Active Projects/Active Personal/Task Archive.md`** — New archive for completed tasks, organized by month. Keeps the Master Task List clean.

### Files Restructured
- **`10_Active Projects/Active Personal/!!! MASTER TASK LIST.md`** — Complete rewrite. All tasks migrated from old `! TO DO` files. Tasks re-tagged with expanded area taxonomy (faith, family, health, home instead of overloaded "personal"). Completed tasks moved to Task Archive. New needle-mover tasks added for Q2 2026.
- **`000_Master Dashboard/Mission Control.md`** — Updated with 8 area sections (faith, family, business, consulting, work, health, home, personal), plus an "Untagged/Unsorted" catch-all. North Star link added to navigation. Renamed "Priority A" section to "Needle Movers."
- **`000_Master Dashboard/Personal & Life.md`** — Expanded to query all 5 personal-life areas (faith, family, health, home, personal) instead of just "personal."
- **`40_Timeline_Weekly/Weekly_Review.md`** — Redesigned as a guided 7-step weekly review process (Christ-first check, overdue review, task load by area, completions this week, scorecard, reflection, next week's Top 3). No longer duplicates Mission Control queries.
- **`20_Domains/Personal/! Home Projects/House Projects.md`** — Added Dataview inline fields to all tasks so they appear in dashboards.

### Files Archived
- **`! TO DO/Personal & Work.md`** — Marked ARCHIVED. All open tasks migrated to Master Task List.
- **`! TO DO/Personal.md`** — Marked ARCHIVED. All open tasks migrated.
- **`99_System/! Obsidian Organizer.md`** — Marked SUPERSEDED. Described a Tasks Plugin + hashtag system that was never fully implemented. Vault now uses Dataview inline fields as the canonical standard.

### Files Updated (Minor)
- **`000_Master Dashboard/The Catch All.md`** — Added North Star and Master List links to navigation.

---

## Area Taxonomy (Canonical)

| Area Tag | Pillar | What It Covers |
|----------|--------|---------------|
| `[area:: faith]` | 🙏 Faith & Spiritual Growth | Bible study, prayer, outreach, social media ministry, church |
| `[area:: family]` | 💒 Marriage & Family | Christy, kids, parenting, family decisions |
| `[area:: business]` | 🚀 Business & Consulting | Echelon Seven startup, offer development, client acquisition |
| `[area:: consulting]` | 🚀 Business & Consulting | Active consulting engagements, billable work |
| `[area:: work]` | 🏥 Career (Parallon) | Day job, BAM role, Parallon projects |
| `[area:: health]` | 💪 Health & Home | Gym, nutrition, sleep, hip decision, biohacking |
| `[area:: home]` | 💪 Health & Home | House projects, UPS/generator, photo cleanup, MI property |
| `[area:: personal]` | (General) | AI hobby projects, tech tinkering, miscellaneous |

### Canonical Task Format
```
- [ ] Task description [area:: work] [priority:: A] [due:: 2026-XX-XX]
```
Priority values: A (critical/needle-mover), B (important), C (nice-to-have)

---

## Q2 2026 Quarterly Rocks (Needle Movers)

1. **🙏 Faith:** Launch the social media Bible study (4 sessions delivered)
2. **💒 Family:** Complete Marriage Alignment Questionnaire with Christy + establish bi-weekly check-in
3. **🚀 Business:** Ship the MVP (website live, offer defined, 3 outreach conversations)
4. **🏥 Career:** Deliver Union project
5. **💪 Health:** Make hip decision + 3x/week gym for 8 weeks

---

## Operating Rhythm

| Cadence | When | Action |
|---------|------|--------|
| Daily | Every morning | Open Mission Control → set Top 3 priorities |
| Weekly | Sunday evening | Open Weekly Review Hub → complete 7-step process |
| Quarterly | End of quarter | Review North Star → set next 5 rocks |

---

## What Still Needs Attention

1. **Activate Daily Notes** — The template is ready in `05_Templates/Daily Note.md`. Configure Templater to auto-create in `40_Timeline_Weekly/Daily/`.
2. **First Weekly Review** — Open the Weekly Review Hub this Sunday and complete it.
3. **Startup Kanban** — Create a kanban board for the business startup pipeline when you're ready to track project phases visually.
4. **2026 Goals Integration** — The 10-domain goals doc is thorough but not yet wired to the task system. The North Star covers the top 5 priorities; deeper domain-level planning can be connected over time.
5. **Plugin optimization** — Calendar plugin should be linked to Daily Notes folder. Tasks plugin is installed but unused (Dataview handles queries currently).



---

## What We've Built and What's Left

### ✅ Done This Session

Everything in the vault has been set up correctly. The North Star and Needle Movers documents are accurate (Faith at 35%/In Progress, Business at 25%/In Progress). The brain dump workflow (18 nodes, 7AM daily) has been built and is ready to deploy. The transfer to your Mac is currently mid-flight — Part 0 of 6 was just sent successfully when you paused me.

---

## The 4-Phase Roadmap to Full Completion

---

### Phase 1 — Finish the Brain Dump Workflow Deployment (30 min, mostly waiting)

This is what we were mid-stream on. Steps in order:

**1a. Complete the file transfer (Parts 1–5 of 6)** — each is ~2,220 characters of compressed base64, sent via osascript Python writes to `/tmp/poster.b64` on your Mac. Part 0 is already there.

**1b. Decompress on Mac** — run one Python command that turns `/tmp/poster.b64` → `/tmp/poster.py` (59,472 bytes). We verify the byte count before doing anything else.

**1c. Run poster.py** — this script POSTs the 18-node workflow JSON to your n8n instance at `192.168.1.121:5678` and returns the workflow ID. You need n8n to be running and reachable at that moment.

**1d. Activate the workflow in n8n** — either poster.py does it directly, or you flip the Active toggle in the UI. The workflow fires at 7AM daily.

---

### Phase 2 — Wire the Brain Dump Infrastructure (1–2 hours, requires hands-on config)

The workflow is built to read brain dump files from MinIO. That means two things need to exist before it can actually do anything useful:

**2a. MinIO bucket for brain dumps** — your Synology is at `192.168.1.240:9000`. You need a bucket (e.g., `brain-dumps`). You also need an access key/secret key pair scoped to that bucket. Create both in the MinIO console. Then add an n8n S3 credential using those keys.

**2b. A mechanism to get brain dump content into MinIO** — this is the key open question. The 7 brain dump files live in your Obsidian vault at `00_Inbox/brain-dumps/`. The workflow is MinIO-native, meaning it expects to find files in a MinIO bucket. You have two clean options:

- **Option A (simpler):** Add a step to the workflow that reads the brain dumps directly via the Obsidian Local REST API (same way the weekly digest reads North Star.md), processes them, and clears them. This removes MinIO from the loop for brain dumps entirely.
- **Option B (as designed):** A companion script or Obsidian automation uploads filled brain dump files to MinIO, the n8n workflow picks them up, processes them, then writes results back to Obsidian and clears the MinIO file.

Option A is faster to get working. Option B matches the original MinIO-native design intent. You'll need to decide.

**2c. Configure n8n credentials the workflow needs** — at minimum: MinIO/S3 credentials, and whatever AI model the workflow uses (likely an OpenAI or Anthropic API key credential in n8n). These are added in n8n under Settings → Credentials.

**2d. Confirm what "processing" means for your brain dumps** — the workflow reads each brain dump file and does something with the content. Based on context, it likely: extracts tasks and adds them to the Master Task List, routes Needle Mover content back to the appropriate North Star rock, and clears the brain dump file. You should verify this matches your expectation before you start dumping real content into those templates.

---

### Phase 3 — Set Up the Weekly Digest Workflow (45 min, all manual steps in n8n/Obsidian)

The weekly digest workflow JSON exists (`n8n-weekly-digest-workflow.json` in your vault). It's not imported into n8n yet. This workflow emails you every Sunday at 6pm with your full rock status, Priority A tasks, and completions. Steps:

**3a. Confirm Obsidian Local REST API plugin is running** — it's installed (I can see it in your vault's plugins). Open Obsidian → Settings → Local REST API → confirm it's enabled and copy your API key. Note your Mac's local IP (`ipconfig getifaddr en0` in Terminal).

**3b. Import the workflow into n8n** — go to `http://192.168.1.121:5678`, click Import from File, select `n8n-weekly-digest-workflow.json`.

**3c. Configure the Config node** — fill in your Mac IP and Obsidian API key inside the workflow's Config node.

**3d. Set up Gmail OAuth2 credentials** — in n8n Settings → Credentials → New → Gmail OAuth2. Authenticate with Aaron.deyoung@gmail.com. Attach the credential to the Send Digest Email node.

**3e. Run a manual test** — hit Test Workflow. Each node should green-check. The final node sends an email to Aaron.deyoung@gmail.com.

**3f. Activate the schedule** — toggle Active. It will fire every Sunday at 6pm CT.

---

### Phase 4 — Full End-to-End Validation (30 min)

Once both workflows are deployed:

**4a.** Add a few real tasks or notes to one brain dump template (e.g., `BrainDump — Business`). Wait for the 7AM trigger (or manually test the brain dump workflow) and verify the tasks appear in your Master Task List with the right area and priority tags.

**4b.** Update a rock status in North Star.md, wait for Sunday 6pm (or manually trigger the weekly digest), and verify the email looks correct with current statuses.

**4c.** Confirm the brain dump file is cleared/reset after processing so it's ready for the next dump.

---

## Longer-Term Enhancements (When You're Ready)

These are from your own setup notes and the "Future Enhancements" section of the digest guide — not required for the core system to work, but worth having on your radar:

**Infrastructure hardening** — Reverse proxy (Caddy or Nginx Proxy Manager) + TLS for n8n so you can reach it over Tailscale securely. Your own N8N.md doc says this is the #1 improvement item. Flip `N8N_SECURE_COOKIE=true` when ready.

**Daily 7AM morning briefing email** — a second n8n workflow (simpler than the digest) that emails just today's Priority A tasks Mon–Fri. Your setup doc called this out as a future workflow.

**Stale rock alert** — if a rock stays at the same progress % for 2 consecutive weeks, n8n sends a nudge. This is entirely buildable once the digest workflow is live.

**Bible GPT integration** — you have `Bible GPT 2.0 — Connect Bible Study to Obsidian through n8n` as a Priority B task in your Master List. Once the brain dump pipeline is validated, this would be the natural next AI workflow to build.

**Off-host backup** — your N8N.md calls for a second restic remote (Backblaze B2 or second MinIO bucket) for 3-2-1 posture. Currently you have n8n backed up to MinIO only.

**Monitoring** — Uptime Kuma to ping `192.168.1.121:5678/healthz` and alert you if n8n goes down.

---

## Summary of What's Blocking You Right Now

The single blocker is **Phase 1** — deploying the brain dump workflow so it exists in n8n. Everything else (Phase 2–4) depends on that being live first. Phase 2 also has a design decision: do you keep the MinIO-native approach for brain dumps, or pivot to direct Obsidian REST API reads (which is simpler and already proven by the weekly digest)?

Want me to resume the transfer and finish Phase 1 now, or do you want to talk through the Phase 2 design decision first?


Let me read the actual workflow content from poster.py before writing this up — I want every detail accurate.Now I have everything. Let me write the comprehensive document to the vault.[View the reference doc in your vault](https://claude.ai/local_sessions/local_e77ca724-46c1-4923-99ca-535a3679b253)

"
# 🧠 Brain Dump Processor — Full Reference

> **Workflow name in n8n:** `🧠 Brain Dump Processor — Daily 7AM` **Node count:** 18 **Schedule:** `0 7 * * *` — every day at 7:00 AM **Source of truth for files:** MinIO bucket `obsidian-vault` at `192.168.1.240:9000` **Deployment script:** `poster.py` (59,472 bytes) — POSTs workflow JSON to `http://192.168.1.121:5678`

---

## ① Intent & Philosophy

The brain dump processor is the **intake engine** of your personal operating system. The fundamental problem it solves: most productivity systems fail not because of bad task management, but because the gap between _"I thought of something"_ and _"it's in the system"_ is too wide and too friction-ful.

The seven brain dump files in `00_Inbox/brain-dumps/` are zero-friction capture zones — one per life domain. You write anything, formatted or not, and the workflow handles the rest every morning at 7 AM. You never have to manually tag, file, or clean up a brain dump. You open it, dump your brain, close it. That's the contract.

The workflow does five things in sequence:

1. **Reads** all 7 brain dump files from MinIO in parallel
2. **Parses** every section of every file, classifying content by type and priority
3. **Writes** Priority A and B tasks into the correct sections of your Master Task List with proper Obsidian inline field tags
4. **Clears** each processed brain dump back to its clean empty template, ready for the next capture session
5. **Emails** you a structured digest confirming everything that was processed, flagging review items for human attention

The design is deliberately asymmetric: **tasks are auto-filed; everything else is flagged for review.** Notes, ideas, articles, and recurring rhythms go into the email digest only — never auto-inserted into any file — because they require your judgment to know where they belong.

---

## ② Infrastructure Architecture

```
Your Mac (Obsidian vault, Remotely Save plugin)
        ↕ sync
MinIO bucket: obsidian-vault @ 192.168.1.240:9000
        ↕ S3 API
n8n CT-202 @ 192.168.1.121:5678
        ↓ SMTP
Gmail → [USER_EMAIL]
```

The vault on your Mac and the MinIO bucket must stay in sync via the **Remotely Save** plugin (already installed). n8n reads from MinIO and writes back to MinIO. The next time Remotely Save syncs, your Mac picks up the updated files — meaning the Master Task List additions and the cleared brain dumps appear in Obsidian on your Mac automatically.

---

## ③ Complete Node-by-Node Breakdown

### Node 1 — Schedule — 7AM Daily

**Type:** `n8n-nodes-base.scheduleTrigger` **Cron:** `0 7 * * *`

The sole trigger. Fires every day at 7:00 AM regardless of whether any brain dumps contain content. The `IF Has Content` gate at Node 11 handles the clean no-op case when files are empty. This means the workflow is always safe to leave active — it will never corrupt anything on an empty run.

---

### Nodes 2–8 — Get BD — [Domain] (×7 in parallel)

**Type:** `n8n-nodes-base.awsS3`, operation: `getFile` **Bucket:** `obsidian-vault`

All 7 fire simultaneously from the schedule trigger. File keys:

|Node|File Key in MinIO|
|---|---|
|Get BD — Personal|`Homelab/00_Inbox/brain-dumps/BrainDump — Personal.md`|
|Get BD — Family|`Homelab/00_Inbox/brain-dumps/BrainDump — Family.md`|
|Get BD — Work|`Homelab/00_Inbox/brain-dumps/BrainDump — Work (Parallon).md`|
|Get BD — Business|`Homelab/00_Inbox/brain-dumps/BrainDump — Business (Echelon Seven).md`|
|Get BD — Faith|`Homelab/00_Inbox/brain-dumps/BrainDump — Faith.md`|
|Get BD — Health|`Homelab/00_Inbox/brain-dumps/BrainDump — Health.md`|
|Get BD — Home|`Homelab/00_Inbox/brain-dumps/BrainDump — Home.md`|

**Credential required:** AWS S3-compatible credential pointed at `http://192.168.1.240:9000`.

---

### Node 9 — Merge Brain Dumps

**Type:** `n8n-nodes-base.merge`, mode: `append`

Gathers all 7 parallel file reads into a single array. Downstream nodes see all 7 files as a sequential list of items. This is the fan-in point after the fan-out from the schedule trigger.

---

### Node 10 — Parse & Analyze ⭐ (main logic node)

**Type:** `n8n-nodes-base.code` (JavaScript)

This is the brain of the system. It processes all 7 files in a single pass and produces all the data the rest of the workflow needs.

#### Configuration Constants (hardcoded in the node)

**ROCKS** — maps each domain area to its current Q2 quarterly rock:

```
faith    → "Launch the Social Media Bible Study"
family   → "Marriage Alignment with Christy"
business → "Ship the MVP"
work     → "Deliver Union Project + Position for Exit"
health   → "Hip Decision + 3x/week Gym"
personal → null  (no rock — tasks still filed)
home     → null  (no rock — tasks still filed)
```

**AREA_MAP** — maps the `domain:` YAML frontmatter value to the internal area key:

```
"Personal"                 → "personal"
"Family"                   → "family"
"Work (Parallon)"          → "work"
"Business (Echelon Seven)" → "business"
"Faith"                    → "faith"
"Health"                   → "health"
"Home"                     → "home"
```

**FILE_KEYS** — maps domain names back to their MinIO paths (used when building the cleared-file write-back array).

#### Per-File Processing Logic

For each of the 7 files:

1. **Read binary** — extracts file content from the S3 binary item
2. **Extract domain** — reads `domain:` from YAML frontmatter to identify which life area this is
3. **Extract 7 sections** by heading keyword using regex:
    - `Needle Movers`
    - `To Do`
    - `Quick Notes`
    - `Articles & Resources`
    - `Things to Organize`
    - `Ideas & Possibilities`
    - `Recurring / Rhythms`
4. **Content check** — if none of the 7 sections have real content (headers, dashes, empty HTML comments, and `*` lines don't count), the file is skipped entirely. No cleared version is generated. No tasks are filed. Zero noise.
5. **Needle Movers section** → every item becomes a **Priority A task**. The domain's Q2 quarterly rock is attached as `rock:` metadata. Priority A means it feeds the quarterly rocks directly.
6. **To Do's section** → items respect inline `[priority:: A/B/C]` tags you've already written. Defaults to Priority B if no tag is present. Any A-tagged To Do also receives the rock attachment.
7. **Notes, Articles, Ideas, Organize, Recurring** → collected as _review items_ only. They appear in the digest email but are **never auto-filed**. This is intentional — these require human judgment about where they belong.
8. **Generate cleared file** — builds the full empty template for this domain using `buildClearedContent()`, which:
    - Preserves and updates YAML frontmatter (`last_processed: YYYY-MM-DD`, `status: empty`)
    - Restores all section headings
    - Restores all HTML comment prompts (`<!-- Add notes here -->`)
    - Strips all actual content

#### Task Line Format Output

Every task is written in the Obsidian Tasks + Dataview inline field format that your entire dashboard already queries:

```
- [ ] <task text> [area:: faith] [priority:: A] [due:: 2026-04-15]
```

This format makes every task immediately visible in Mission Control's Dataview queries, Needle Movers' per-pillar task lists, and the weekly digest email — without any manual tagging.

#### Output JSON Structure

```json
{
  "has_content": true,
  "processed_domains": [{ "domain": "Faith", "area": "faith", "emoji": "🙏" }, ...],
  "priority_a_tasks": [{
    "domain": "Faith",
    "area": "faith",
    "raw": "original task text",
    "due": "2026-04-15",
    "rock": "Launch the Social Media Bible Study",
    "line": "- [ ] original task text [area:: faith] [priority:: A] [due:: 2026-04-15]"
  }, ...],
  "priority_b_tasks": [{ ... same shape plus "priority": "B" }],
  "review_notes":     [{ "domain", "area", "text" }],
  "review_articles":  [{ "domain", "area", "text" }],
  "review_ideas":     [{ "domain", "area", "text" }],
  "review_organize":  [{ "domain", "area", "text" }],
  "review_recurring": [{ "domain", "area", "text" }],
  "cleared_dumps":    [{ "fileKey", "domain", "area", "content" }],
  "rocks": { "faith": "...", "family": "...", ... },
  "today": "2026-03-24"
}
```

---

### Node 11 — IF Has Content

**Type:** `n8n-nodes-base.if` **Condition:** `$json.has_content === true`

**True (main:0)** → continues to Get Master Task List → full write + email pipeline. **False (implicit stop)** → workflow ends. Nothing is written. No email is sent. No noise.

This gate means you can have a day where you didn't brain dump anything and the workflow exits cleanly in under 2 seconds without touching any files.

---

### Node 12 — Get Master Task List

**Type:** `n8n-nodes-base.awsS3`, operation: `getFile` **Key:** `Homelab/10_Active Projects/Active Personal/!!! MASTER TASK LIST.md`

Fetches the current state of your master task list so the next node can append to it safely rather than overwrite it. This is a read-before-write pattern.

---

### Node 13 — Build All Updates ⭐ (write assembly node)

**Type:** `n8n-nodes-base.code` (JavaScript)

**Inputs:** Master Task List content (from Node 12) + all parsed data (from Node 10 via `$('Parse & Analyze').first().json`)

#### Master Task List Update Logic

Priority A tasks are grouped by area, then each area's tasks are inserted into the correct `### [Area]` subsection under `## 🔴 Priority A` in the master list. The node finds the header using string search, then finds the next section break, and splices the new task lines in just before it.

Priority B tasks are similarly inserted under `## 🟡 Priority B`. If a section header isn't found (e.g., the master list doesn't have a matching subsection), the tasks are appended to the end of the file rather than silently dropped.

#### Output Array

Returns an array of file objects, one per file to write back to MinIO:

```
[
  { fileKey: "...MASTER TASK LIST.md", content: "...", label: "Master Task List" },
  { fileKey: "...BrainDump — Faith.md", content: "...", label: "Brain Dump — Faith" },
  { fileKey: "...BrainDump — Business.md", content: "...", label: "Brain Dump — Business" },
  ...
]
```

The first item is always the master task list. Remaining items are one cleared brain dump per domain that had real content.

---

### Node 14 — Split Files Loop

**Type:** `n8n-nodes-base.splitInBatches`, batch size: 1

Iterates through the file array one at a time, feeding each item through Set Binary Content → Upload to MinIO, then looping back. When all items are exhausted:

- `main:0` = next item (loops to Set Binary Content)
- `main:1` = all done (triggers Build Summary Email)

This is n8n's loop construct. The loop safely handles any number of files without knowing in advance how many domains had content.

---

### Node 15 — Set Binary Content

**Type:** `n8n-nodes-base.code` (JavaScript)

Adapter node. Converts `item.json.content` (a string) into a base64-encoded binary object that the S3 upload node requires. Sets MIME type to `text/markdown`. This is boilerplate bridge code required by n8n's S3 node interface.

---

### Node 16 — Upload to MinIO

**Type:** `n8n-nodes-base.awsS3`, operation: `upload` **Bucket:** `obsidian-vault` **Key:** `{{ $json.fileKey }}` (dynamic)

Writes each file back to MinIO. For brain dumps this is the "clear" write. For the Master Task List this is the "append" write. After each upload, loops back to Split Files Loop for the next file.

---

### Node 17 — Build Summary Email ⭐ (digest builder)

**Type:** `n8n-nodes-base.code` (JavaScript) **Triggered by:** Split Files Loop `main:1` (all writes complete)

Builds a full HTML digest email. Structure:

|Section|Content|
|---|---|
|Gradient header|"🧠 Brain Dump Processed" + today's date|
|Stats row|Domains processed · Priority A count · Priority B count · Review items count|
|Priority A tasks|Card per task: domain emoji, task text, linked rock name (yellow badge), due date if set|
|Priority B tasks|Same card layout in amber|
|Review — Notes|Bulleted list, domain labeled. Human review only.|
|Review — Articles|Same|
|Review — Ideas|Same|
|Review — Organize|Same|
|Footer|"Brain dumps cleared and ready for tomorrow" + timestamp|

**Subject line:** `🧠 Brain Dump Processed — X new tasks · YYYY-MM-DD` **To:** `[USER_EMAIL]`

---

### Node 18 — Send Brain Dump Digest

**Type:** `n8n-nodes-base.emailSend` **From:** `[USER_EMAIL]` **SMTP:** Gmail (`smtp.gmail.com:587`) using an App Password

Sends the HTML digest. Uses the standard `emailSend` node (SMTP) rather than Gmail OAuth2 — simpler to configure and more stable for automation.

---

## ④ Data Flow Summary

```
Schedule (7AM)
    ↓ (fan-out, parallel)
    ├── Get BD — Personal ──┐
    ├── Get BD — Family ────┤
    ├── Get BD — Work ──────┤
    ├── Get BD — Business ──┤──→ Merge Brain Dumps
    ├── Get BD — Faith ─────┤
    ├── Get BD — Health ────┤
    └── Get BD — Home ──────┘
                            ↓
                    Parse & Analyze
                    (classify, build cleared content)
                            ↓
                    IF Has Content?
                      ↓ (yes)
                 Get Master Task List
                            ↓
                    Build All Updates
                    (append tasks + package cleared files)
                            ↓
                    Split Files Loop ←──────────────┐
                      ↓ (each item)                  │
                  Set Binary Content                  │
                            ↓                        │
                    Upload to MinIO ─────────────────┘
                      ↓ (all done)
                Build Summary Email
                            ↓
               Send Brain Dump Digest
```

---

## ⑤ What Still Needs to Be Addressed

### 🔴 Blocking: Deployment (poster.py)

The workflow JSON has been built and compressed for transfer. The transfer is mid-flight — Part 0 of 6 is on your Mac at `/tmp/poster.b64`. Parts 1–5 still need to be sent, then the file decompressed and run. The Mac needs n8n reachable at `192.168.1.121:5678` when poster.py runs.

**Remaining steps:**

1. Send Parts 1–5 via osascript Python write/append calls
2. Decompress: `python3 -c "import base64,zlib; open('/tmp/poster.py','wb').write(zlib.decompress(base64.b64decode(open('/tmp/poster.b64').read())))"`
3. Verify: `wc -c /tmp/poster.py` must equal `59472`
4. Deploy: `python3 /tmp/poster.py`
5. Activate: flip the Active toggle in n8n UI

---

### 🔴 Blocking: MinIO Bucket & Vault Sync

The workflow reads from and writes to MinIO bucket `obsidian-vault`. Two things must be true before it works:

**1. The bucket must exist and be populated.** Open MinIO at `http://192.168.1.240:9000` (or `http://192.168.1.240:9001` for the console). Create bucket `obsidian-vault` if it doesn't exist. Create an access key/secret key pair scoped to it.

**2. The bucket must stay in sync with your Mac vault.** Your vault uses the **Remotely Save** plugin (already installed). Check: Obsidian → Settings → Remotely Save → see what remote it's configured for.

- If it's already pointed at MinIO with bucket `obsidian-vault` → you're done.
- If it's pointed at a different bucket name → change the `bucketName` field in all 8 S3 nodes in the n8n workflow to match.
- If it's pointed at iCloud, Syncthing, or another sync mechanism → you have a choice: reconfigure Remotely Save to use MinIO, or redesign the workflow to use the Obsidian Local REST API instead (same pattern as the weekly digest workflow — simpler but loses the MinIO-native architecture).

---

### 🔴 Blocking: n8n Credentials

The workflow needs two credentials configured in n8n before it can run:

**S3 / MinIO credential:**

|Field|Value|
|---|---|
|Credential name|`MinIO — obsidian-vault` (or anything)|
|Type|AWS S3|
|Access Key ID|From MinIO console|
|Secret Access Key|From MinIO console|
|Region|`us-east-1` (ignored by MinIO, required by n8n)|
|Endpoint URL|`http://192.168.1.240:9000`|
|Force path style|✅ Enabled (required for MinIO)|

After creating this credential, open the deployed workflow in n8n and assign it to all 8 S3 nodes (7 Get BD nodes + Upload to MinIO node).

**SMTP credential (for Node 18 emailSend):**

|Field|Value|
|---|---|
|Credential name|`Gmail SMTP`|
|Type|SMTP|
|Host|`smtp.gmail.com`|
|Port|`587`|
|User|`[USER_EMAIL]`|
|Password|Gmail App Password (Google Account → Security → 2-Step Verification → App Passwords → generate for "Mail")|
|SSL/TLS|STARTTLS|

After creating, assign to Node 18 (Send Brain Dump Digest).

---

### 🟡 Important: Brain Dump Frontmatter

Each brain dump file must have a `domain:` field in its YAML frontmatter that exactly matches one of the values in AREA_MAP. The parser uses this to identify which domain the file belongs to. Current brain dump files have:

```yaml
---
domain: Faith
status: empty
last_processed: null
---
```

If a file is missing the `domain:` frontmatter key, the parser silently skips it. No error, no task filing. Make sure all 7 files have this field.

---

### 🟡 Important: Activate the Workflow After Deployment

poster.py creates the workflow in n8n in **inactive** state (by design — you review before activating). After deploying, go to n8n → your workflow → toggle **Active** in the top-right. Without this step, the 7AM schedule never fires.

---

### 🟡 Important: Master Task List Section Headers

The task insertion logic in Build All Updates searches for exact section headers. Your master task list must contain these headers for the insertion to land in the right places rather than appending to the end:

**For Priority A tasks (one per area):**

- `### 🙏 Faith`
- `### 💒 Marriage & Family`
- `### 🚀 Business`
- `### 🏥 Work (Parallon)`
- `### 💪 Health`
- `### 🤖 Personal`
- `### 🏠 Home`

**For Priority B tasks:** `## 🟡 Priority B`

If your master list uses different header text, either update the headers in the list to match, or update the `sectionHeaders` maps in Build All Updates node to match your actual headers.

---

## ⑥ Future Iterations — Where This Can Go

### Iteration 1: Claude AI Classification Layer

**Effort:** Medium | **Value:** High

Currently the parser is rule-based: section heading determines category, inline field determines priority. An AI layer (Claude via the Anthropic API node or a self-hosted Ollama node) could:

- Infer priority from the content of the task text, not just inline tags. "Schedule hip surgery consult" with no priority tag would auto-classify as A.
- Detect if a note in Quick Notes is actually a task in disguise and promote it to the To Do's list.
- Auto-classify ideas as "worth exploring now" vs "backlog" based on whether they map to an active quarterly rock.
- Extract follow-up tasks from article URLs — paste in a link, the AI reads the article and extracts the actionable takeaways as tasks.

This would require adding one HTTP Request node (to call Claude's API) in the Parse & Analyze stage, replacing or augmenting the rule-based extractors.

---

### Iteration 2: North Star Progress Auto-Update

**Effort:** Low | **Value:** High

When a task tagged as Priority A is filed, the workflow could also check if it indicates progress on the linked quarterly rock and increment the `nm-progress-[area]::` inline field in North Star.md. Example: if 3 Priority A tasks for `faith` are filed and the current progress is 35%, nudge it to 40%.

This is conservative by design — nudges only, never sets a high number automatically. The human still does the Sunday review. But it reduces the chance that North Star.md drifts stale.

Implementation: one additional S3 read of North Star.md at the end of Build All Updates, regex replacement of the progress field, added to the files-to-write array.

---

### Iteration 3: Smart Duplicate Detection

**Effort:** Low | **Value:** Medium

The current system will happily file the same task twice if you dump "Record Bible study session 1" two days in a row without completing or clearing it. A deduplication step in Build All Updates could read the existing tasks in the master list and skip any new task whose text fuzzy-matches an existing open task (normalized, trimmed comparison with ~85% threshold).

---

### Iteration 4: Recurring Rhythms Auto-Create

**Effort:** Medium | **Value:** Medium

Items in the `Recurring / Rhythms` section currently go to the email only. A future version could detect recurring patterns (text containing "every week", "weekly", "monthly") and automatically create recurring tasks in the master list with appropriate RRULE-style metadata, or just create the next instance with a calculated due date.

---

### Iteration 5: Read Directly from Obsidian REST API (drop MinIO dependency for brain dumps)

**Effort:** Low | **Value:** High if MinIO sync is problematic

Replace all 7 `awsS3 getFile` nodes with `HTTP Request` nodes calling the Obsidian Local REST API at `http://[MAC_IP]:27123/vault/Homelab/00_Inbox/brain-dumps/[filename]`. This is the exact same pattern the weekly digest workflow already uses.

Advantages: no MinIO dependency, no sync lag, reads the live vault directly. Disadvantages: Obsidian must be open and the REST API plugin running whenever the workflow fires.

The write-back (clearing brain dumps + updating master list) would similarly shift to HTTP PUT calls to the REST API.

---

### Iteration 6: Multi-Vault / Multi-Person Support

**Effort:** High | **Value:** Low now, High later

If you ever want Christy to have her own brain dump feeds processed into a shared family task list, the workflow architecture supports this: duplicate the 7 Get BD nodes pointing to a different MinIO path prefix, pipe through the same parser with a different AREA_MAP, and route output to a shared "Family" section of the master list.

---

### Iteration 7: Daily Digest Enrichment

**Effort:** Low | **Value:** Medium

The digest email currently shows what was processed. A future version could also:

- Show how many open Priority A tasks exist per domain (from a quick scan of the master list)
- Highlight any task that's overdue (due date < today)
- Include a one-line "today's focus" recommendation based on the most time-sensitive Priority A task
- Embed a direct Obsidian URL link to each task (using the `obsidian://` protocol) so you can tap a task in the email and jump directly to the right note

---

### Iteration 8: Brain Dump → Notion / Linear / Todoist Bridge

**Effort:** Medium | **Value:** Depends on your tools

If you ever move parts of your system to external tools, the Build All Updates node can be extended to output tasks to multiple destinations via n8n's existing integrations — Notion databases, Linear issues, Todoist tasks, or a webhook. The data structure is already normalized; it just needs a second output path.

---

## ⑦ Companion Workflows in This System

This brain dump processor is one piece of a two-workflow personal OS running on n8n. The other:

### Weekly Needle Mover Digest (`n8n-weekly-digest-workflow.json`)

- **Schedule:** Every Sunday at 6:00 PM CT
- **Source:** Reads North Star.md and Master Task List directly via Obsidian Local REST API
- **Output:** Full HTML digest email showing all 5 rock statuses + progress bars, all open Priority A tasks, completions, and 14-day lookahead
- **Setup guide:** `n8n-weekly-digest-SETUP.md` (same folder as this file)
- **Status:** Workflow JSON exists in vault. Needs to be imported into n8n. Requires Obsidian Local REST API plugin running + Gmail OAuth2 credential.

---

## ⑧ Quick Reference — Credentials Needed in n8n

|Credential Name|Type|Used By|
|---|---|---|
|MinIO — obsidian-vault|AWS S3|Nodes 2–8 (reads) + Node 16 (upload)|
|Gmail SMTP|SMTP|Node 18 (send digest)|
|_(Weekly digest)_ Gmail OAuth2|Gmail OAuth2|Weekly digest "Send Digest Email" node|

---

## ⑨ File Map

|File|Location|Purpose|
|---|---|---|
|`poster.py`|`/tmp/poster.py` on Mac (after deploy)|Deploys workflow JSON to n8n|
|Brain Dump — Personal|`00_Inbox/brain-dumps/`|Capture zone|
|Brain Dump — Family|`00_Inbox/brain-dumps/`|Capture zone|
|Brain Dump — Work|`00_Inbox/brain-dumps/`|Capture zone|
|Brain Dump — Business|`00_Inbox/brain-dumps/`|Capture zone|
|Brain Dump — Faith|`00_Inbox/brain-dumps/`|Capture zone|
|Brain Dump — Health|`00_Inbox/brain-dumps/`|Capture zone|
|Brain Dump — Home|`00_Inbox/brain-dumps/`|Capture zone|
|Master Task List|`10_Active Projects/Active Personal/`|Task destination|
|North Star|`000_Master Dashboard/`|Rock status (read by weekly digest)|
|Needle Movers|`000_Master Dashboard/`|Rock definitions|
|`n8n-weekly-digest-workflow.json`|`20_Domains/.../Homelab/`|Weekly digest workflow JSON|
|`n8n-weekly-digest-SETUP.md`|`20_Domains/.../Homelab/`|Weekly digest setup guide|
|`n8n-brain-dump-processor-REFERENCE.md`|`20_Domains/.../Homelab/`|**This file**|

---

_Reference document for the Brain Dump Processor n8n workflow — March 2026_
"


Here's the full story, decoded from the actual workflow JSON:

---

## What This Workflow Actually Is

The brain dump processor is the **intake engine** of your personal OS. The core bet: most productivity systems die in the gap between "I thought of something" and "it's in the system." This closes that gap. You dump anywhere, the 7AM trigger handles everything else, and you never touch it again.

---

## The 18 Nodes — What Each One Does

**Node 1 (Schedule)** — fires `0 7 * * *`. Runs daily, no exceptions. The no-content gate downstream makes it safe to leave always-active.

**Nodes 2–8 (7× S3 GetFile)** — all fire in parallel, reading one brain dump each from MinIO bucket `obsidian-vault`. File keys are hardcoded to the exact paths in your Obsidian vault.

**Node 9 (Merge)** — fan-in. Gathers the 7 parallel reads into one sequential array.

**Node 10 (Parse & Analyze) — the brain.** One JavaScript code node processes all 7 files in a single pass. It knows all 5 quarterly rocks, maps every domain to its area key, reads 7 sections per file (Needle Movers, To Do's, Quick Notes, Articles, Organize, Ideas, Recurring), and applies a clean content check so files with nothing but headers and HTML comment prompts are silently skipped. Needle Mover items → Priority A with the rock attached. To Do items → respect inline `[priority:: A/B/C]` tags, default B. Notes, articles, ideas, organize items, and recurring rhythms go to the email only — never auto-filed, by design. The node also pre-builds each cleared brain dump (frontmatter updated with today's date and `status: empty`, all section structure restored, all content stripped).

**Node 11 (IF Has Content)** — `$json.has_content === true`. False path exits cleanly. No writes, no email, no noise.

**Node 12 (Get Master Task List)** — reads the current master list before writing to it. Read-before-write so nothing gets overwritten.

**Node 13 (Build All Updates) — the write assembler.** Takes the parser's output and the current master task list, inserts Priority A tasks into their exact `### [Area]` subsections under `## 🔴 Priority A`, inserts Priority B tasks under `## 🟡 Priority B`, then packages everything — updated master list plus all cleared brain dumps — into one array of `{fileKey, content}` objects.

**Node 14 (Split Files Loop)** — iterates through that array one item at a time. `main:0` = next file to upload (loops). `main:1` = all done (triggers email).

**Nodes 15–16 (Set Binary + Upload)** — adapter + S3 upload. Converts string content to base64 binary (n8n S3 nodes require binary), then uploads each file back to MinIO.

**Node 17 (Build Summary Email)** — triggered when the loop exhausts. Builds a full HTML digest: stats (domains processed, A/B counts, review item count), Priority A task cards (domain emoji, task text, rock name as yellow badge, due date if set), Priority B cards, four review sections as bulleted lists, footer confirming brain dumps are cleared.

**Node 18 (Send Brain Dump Digest)** — SMTP emailSend to `[USER_EMAIL]` via Gmail SMTP with an App Password.

---

## The 5 Open Blockers

**🔴 poster.py deployment** — mid-transfer, Part 0 of 6 is already on your Mac. Parts 1–5 still need to go.

**🔴 MinIO bucket `obsidian-vault`** — must exist and have the vault contents. The critical question is whether Remotely Save is already syncing to MinIO or to something else. Check Obsidian → Settings → Remotely Save → endpoint/bucket.

**🔴 n8n S3 credential** — needs to point to `http://192.168.1.240:9000` with path-style enabled. Assign to all 8 S3 nodes after deploying.

**🔴 n8n SMTP credential** — Gmail SMTP at port 587, App Password (not your account password). Assign to Node 18.

**🟡 Workflow activation** — poster.py deploys it inactive. You flip the toggle.

---

## The 8 Future Iterations (in the doc)

Claude AI classification layer → North Star progress auto-nudge → fuzzy duplicate detection → recurring rhythms auto-create → swap MinIO reads for Obsidian REST API → multi-person support → enriched daily digest (overdue highlights, obsidian:// deep links) → bridge to Notion/Linear/Todoist. All architecturally straightforward additions to what's already built.



Confirmed: zero AI or Agent nodes. The entire workflow is pure rule-based JavaScript. Let me write the full design for turning this into a genuinely intelligent system.[View the AI Enhancement Design doc](https://claude.ai/local_sessions/local_e77ca724-46c1-4923-99ca-535a3679b253)

---

## To Answer Your Question Directly

**Zero AI or Agent nodes exist in the current workflow.** It is 100% rule-based JavaScript — regex, string matching, and section headings. If you put content in the right place with the right format, it works perfectly. If you don't, it silently fails.

---

## Where Rule-Based Logic Breaks Down

The system has seven failure modes, all real-world:

**You write free-form prose.** A paragraph of stream-of-consciousness won't parse. The workflow needs you in section-sorting mode, which is cognitive work that defeats the purpose of a brain dump.

**You skip the priority tag.** Everything in To Do defaults to Priority B. Genuinely urgent tasks get miscategorized because you didn't write `[priority:: A]` at 11pm.

**You write natural language dates.** "Before the conference next Tuesday" drops silently. No due date gets set.

**Review items die in the email.** Notes, ideas, articles, and recurring rhythms get emailed to you and then live in your inbox until you manually act on them. There is no intelligence about whether they're worth pursuing or whether you've said the same thing six times.

**No deduplication.** Dump "need to schedule the hip consultation" three days in a row, get three identical tasks in the master list.

**No rock alignment inference.** If you don't tag something for faith/A, the workflow doesn't know it's your #1 quarterly rock action. It files it as a generic B task.

**Rocks are hardcoded.** When Q3 starts, someone has to manually update the JS code inside n8n.

---

## The Five Insertion Points for AI

The design is clean: the AI layer is a drop-in replacement at the **extraction layer only**. Everything from Build All Updates onward — the file writes, the loop, the MinIO uploads — is untouched. The AI must produce the same JSON schema the downstream nodes already consume. This is what makes it future-proof: you can upgrade the intelligence without touching the plumbing.

**Insertion Point 1 — LLM Extractor (replaces Parse & Analyze entirely)** The single highest-value change. A Claude Haiku call with a structured JSON output schema replaces 8,025 lines of regex JS. You send it the raw brain dump text — formatted, messy, prose, whatever — along with the context of your 5 quarterly rocks and today's date. It returns a typed array of extracted items with `item_type`, `area`, `priority`, `rock` alignment, natural-language-resolved `due_date`, the cleaned task text, a confidence score, and a one-sentence reasoning explanation. Free-form prose works. Natural dates resolve. Rock alignment is automatic. Low-confidence items get flagged in the email instead of silently dropped.

**Insertion Point 2 — Deduplication Check** After extraction, before filing. A code node normalizes task text and fuzzy-matches against all existing open tasks fetched from the Master Task List. ~80% threshold catches obvious duplicates. The vector store version (Phase 5, Qdrant running on CT-202) catches semantic paraphrases — "schedule hip consult" matches "call the orthopedic surgeon."

**Insertion Point 3 — Review Item Triage** A parallel branch off the extraction output. Each review item (notes, ideas, articles, recurring) gets classified into one of four buckets: `action_now` (it's actually a task — promote and file), `someday_maybe` (write to a Someday-Maybe.md file in your vault), `follow_up` (flag with a suggested date), or `discard` (too vague to act on). Notes and ideas stop dying in your email.

**Insertion Point 4 — Rock Stall Detection** Pure code logic, but only possible after AI classification gives you reliable rock-tagged tasks to count. If any rock at 0% has received zero Priority A input for 14+ consecutive days, the email generates a "⚠️ Rock Stall" callout: _"No Priority A tasks have been filed for Family in 14 days. Your quarterly rock 'Marriage Alignment with Christy' has no momentum."_

**Insertion Point 5 — Narrative Briefing** A 2–3 sentence LLM-generated paragraph injected at the top of the digest email. Instead of a mechanical task list, you get: _"Today's brain dump touched four areas. Your heaviest input was Business — four Priority A tasks filed, all feeding the MVP. One Health item is worth attention: you mentioned the hip consultation again — third time in 10 days. It's been promoted to Priority A."_ Costs less than a fraction of a cent. Makes the whole thing feel like a smart assistant rather than a cron job.

---

## The Full Vision — Phase 6 AI Agent

At the end of the roadmap, the extraction layer becomes a proper n8n AI Agent node with tool-calling. The agent gets tools: `get_quarterly_rocks` (reads North Star.md live — rocks are no longer hardcoded), `get_open_tasks` (reads the master list for deduplication), `get_recent_history` (queries Qdrant: "how many times has this topic appeared in the last 30 days?"), `create_task`, `flag_for_review`, and `file_someday`. Instead of a single-pass extraction, it can reason: _"I've seen this topic before — let me check whether this is a duplicate or a new angle before deciding."_

---

## Cost and Non-Negotiables

The entire daily run with all AI layers active costs under one cent. Claude Haiku handles all of it — it's fast, cheap, and reliable at following JSON schemas. The Anthropic API credential goes into n8n under Settings → Credentials.

Three guardrails that must hold regardless of how intelligent the system gets: high-confidence tasks auto-file, everything else flags for human review first; every decision writes its `reasoning` field alongside the task so you always know why it was classified that way; and if any LLM call fails, the workflow exits cleanly with an error notification and leaves the original brain dump files completely untouched in MinIO.

---

## The Immediate Move After Deployment

Once poster.py is deployed and the current workflow is live, the first upgrade is Phase 1 — the LLM Extractor. It's 2–3 hours of work to write the system prompt, test against real brain dump examples, and swap the extraction node. That single change eliminates six of the seven failure modes and turns this from a system that requires you to think in its format into one that thinks in yours.

# 🤖 Brain Dump Processor — AI Enhancement Design

> **Status:** Not yet implemented — design spec for the intelligent evolution of the brain dump pipeline **Companion doc:** `n8n-brain-dump-processor-REFERENCE.md` **Core question:** Where does rule-based logic break down, and exactly how do we replace it with intelligence?

---

## The Honest Problem With the Current System

The current workflow is 100% rule-based JavaScript. It will correctly classify and file _anything you put in the right place with the right format._ That's the whole dependency — **you** doing the cognitive work of pre-classifying your own brain dump before the system ever sees it.

Specifically, the current system breaks under these real conditions:

**Condition 1 — You don't use the sections correctly.** You open the brain dump and write a paragraph of stream-of-consciousness. Or you put a task under Notes because that's where your cursor landed. Or you paste five things in a row without separating them. The parser sees raw text it doesn't know how to route and silently skips it.

**Condition 2 — You don't add inline priority tags.** Everything that lands in To Do without a `[priority:: A]` tag defaults to Priority B. A legitimately urgent task that you didn't tag correctly gets filed in the wrong tier.

**Condition 3 — You write natural language dates.** "Before the conference next Tuesday" or "by end of month" or "ASAP" — none of these parse. The due date is silently dropped and the task has no deadline.

**Condition 4 — Review items die in the email.** Notes, ideas, articles, and recurring rhythms go into the digest email and live there until you act on them. There is no intelligence about whether they're worth pursuing, whether you've had the same idea six times, or whether one of them is actually a blocked quarterly rock action.

**Condition 5 — No context about what already exists.** The workflow doesn't know what tasks are already in your Master Task List. You can file the same thought three weeks in a row and it will quietly add three duplicate tasks.

**Condition 6 — No rock alignment inference.** You write "Post the first Bible study video" without tagging it as faith/A. The system has no way to know this is directly tied to your #1 quarterly rock.

**Condition 7 — Rigid sections, rigid format.** The template was designed to guide good capture, but real brain dumps are messy. The more friction the format adds, the less you use it. The ideal is: write anything, any way. The system figures out the rest.

---

## The Target Architecture

```
[Brain dump files from MinIO — raw, messy, free-form]
              ↓
    ┌─────────────────────────┐
    │   LLM Extraction Layer  │  ← Claude claude-haiku-4-5-20251001 (fast, structured JSON output)
    │   (replaces code parser)│    System prompt: your rocks, your areas, your schema
    └─────────────────────────┘
              ↓ structured JSON
    ┌─────────────────────────┐
    │   Context Enrichment    │  ← Fetches Master Task List + North Star live
    │   Agent (optional)      │    Deduplication, rock alignment scoring, priority arbitration
    └─────────────────────────┘
              ↓ enriched, deduplicated decisions
    ┌─────────────────────────┐
    │   Write + Clear         │  ← Existing build/upload nodes (unchanged)
    └─────────────────────────┘
              ↓
    ┌─────────────────────────┐
    │   Intelligent Digest    │  ← LLM-generated narrative summary, not just a task list
    └─────────────────────────┘
```

---

## Where to Add AI — Five Specific Insertion Points

---

### Insertion Point 1: LLM Extraction (replaces Parse & Analyze)

**Position in workflow:** Between Merge Brain Dumps and IF Has Content **n8n node:** OpenAI / Anthropic Chat Model → Structured Output Parser **Replaces:** Node 10 (Parse & Analyze code node, 8,025 chars of JS)

This is the highest-value change. Instead of regex and section matching, every brain dump file is sent to an LLM with a detailed system prompt and a JSON schema. The LLM reads free-form text — formatted, unformatted, stream-of-consciousness, whatever — and returns structured data.

#### System Prompt Design

```
You are a personal productivity assistant processing brain dumps for Aaron.

CONTEXT — Q2 2026 QUARTERLY ROCKS (the most important things this quarter):
- faith: "Launch the Social Media Bible Study" (In Progress, 35%)
- family: "Marriage Alignment with Christy" (Not Started, 0%)
- business: "Ship the MVP — Echelon Seven" (In Progress, 25%)
- work: "Deliver Union Project + Position for Exit" (Not Started, 0%)
- health: "Hip Decision + 3x/week Gym for 8 Weeks" (Not Started, 0%)

AREAS: faith, family, business, work, health, personal, home

YOUR JOB:
Read the brain dump content below. Extract every distinct item and classify it.

FOR EACH ITEM, determine:
1. item_type: "task" | "idea" | "note" | "article" | "recurring" | "question"
2. area: which life domain this belongs to (infer from context if not stated)
3. priority: "A" | "B" | "C"
   - A = directly advances a quarterly rock OR is time-sensitive/blocking
   - B = important but not urgent, not directly tied to a rock
   - C = low stakes, someday/maybe
4. rock: which quarterly rock this is connected to (null if none)
5. due_date: ISO date if you can infer one from natural language ("by end of April" → "2026-04-30", "next Tuesday" → calculate from today's date). null if not determinable.
6. task_text: clean, actionable phrasing (imperative voice, specific)
7. confidence: "high" | "medium" | "low" — how confident you are in this classification
8. reasoning: one sentence explaining the key classification decision (priority and rock especially)

Today's date: {{today}}
Domain of this brain dump: {{domain}}

RULES:
- Extract items even if they're buried in prose paragraphs
- If something is vague ("need to deal with the business stuff"), flag it as a note with low confidence
- If you see the same item stated twice, return it once
- Tasks that mention "weekly", "every", "recurring" → item_type: "recurring"
- Questions that need an answer before action can happen → item_type: "question"

Return ONLY a JSON array of extracted items. No explanation outside the JSON.
```

#### Output JSON Schema

```json
[
  {
    "item_type": "task",
    "area": "faith",
    "priority": "A",
    "rock": "Launch the Social Media Bible Study",
    "due_date": "2026-04-01",
    "task_text": "Record session 1 of the Bible study series",
    "confidence": "high",
    "reasoning": "Directly advances the Faith quarterly rock; no blocking dependencies identified"
  }
]
```

#### What This Unlocks

- **Free-form prose works.** "I really need to get around to calling that orthopedic surgeon about my hip before it gets worse" → task, area: health, priority: A, rock: "Hip Decision + 3x/week Gym", due: inferred.
- **Natural language dates resolve.** "Need this done by end of the month" → `2026-03-31`.
- **Rock alignment is automatic.** You don't need to know the rock names. The LLM knows them.
- **Low-confidence items are flagged** in the email with a "⚠️ Review needed" badge rather than silently skipped.

---

### Insertion Point 2: Deduplication Check

**Position:** After LLM Extraction, before Write **n8n node:** HTTP Request (read current Master Task List) → Code node (semantic match) OR LLM second pass **Optional enhancement:** Qdrant vector store for semantic similarity

The current workflow reads the Master Task List at Node 12, but only to append to it — it never checks whether a new task is semantically equivalent to something already open.

#### Simple version (no vector store required):

A code node normalizes task text (lowercase, strip punctuation, remove stop words) and does a fuzzy string match against all existing open tasks in the master list. Match threshold ~80%. Items that match an existing open task are suppressed from filing and flagged in the email: "⚠️ Already in system: 'Schedule hip surgery consult' (open, unfiled from 2 weeks ago)."

#### Vector store version (Qdrant on homelab):

When tasks are filed, their embeddings are stored in Qdrant. On each new run, new task embeddings are compared against stored ones (cosine similarity > 0.85 = duplicate). This handles paraphrases and synonyms that fuzzy text matching misses.

**Qdrant deployment:** `docker run -p 6333:6333 qdrant/qdrant` on CT-202 alongside n8n.

---

### Insertion Point 3: Priority Arbitration + Rock Alignment Scoring

**Position:** After Extraction, before Build All Updates **n8n node:** Code node using extraction output (no additional LLM call needed — the extraction already returned this data)

This is already handled by the LLM Extraction layer above — the LLM returns `priority`, `rock`, and `reasoning` for every item. The code node formerly doing this work in Parse & Analyze is replaced entirely.

However, one additional rule worth implementing in code (not LLM) after extraction:

**Rock stall detection:** If the two rocks currently at 0% (Family, Work, Health) receive zero Priority A tasks for 3+ consecutive days, the workflow generates a special "⚠️ Rock Stall" alert section in the email: "No Priority A tasks have been filed for Family in 14 days. Your quarterly rock 'Marriage Alignment with Christy' has no momentum."

This is pure code logic (track dates, count A tasks per rock per day) but is only possible _after_ AI classification gives you reliable rock-tagged tasks to count.

---

### Insertion Point 4: Review Item Triage

**Position:** Parallel branch off the main extraction output **n8n node:** Anthropic/OpenAI Chat → structured output

Currently Notes, Articles, Ideas, Organize, and Recurring items are emailed and forgotten. An AI triage pass on these would classify each review item into one of four buckets:

|Bucket|Meaning|Action|
|---|---|---|
|`action_now`|This is actually a task in disguise|Promote to task, file in master list|
|`someday_maybe`|Worth parking for later review|Write to a `Someday-Maybe.md` file in Obsidian|
|`follow_up`|Needs more info before acting|Flag in email with a suggested follow-up date|
|`discard`|Too vague to act on, no clear value|Include in email but label "Consider discarding"|

The prompt for this triage would be simpler and cheaper than the main extraction — it receives one item at a time and returns a single classification with one line of reasoning.

Over time, if you find you never act on the `someday_maybe` bucket, you can change the prompt to classify those as `discard` instead.

---

### Insertion Point 5: Intelligent Digest Narrative

**Position:** Replace or augment Build Summary Email (Node 17) **n8n node:** Anthropic/OpenAI Chat → HTML output injected into existing email template

Instead of (or alongside) the mechanical task-card list, add a brief AI-generated narrative paragraph at the top of the digest that reads like a smart morning briefing:

**Example output:**

> "Today's brain dump touched four areas. Your heaviest input was Business — four Priority A tasks filed, all directly feeding the MVP. Faith had two items: one task (recording session 1) and one article you'll want to follow up on. One item from Health is worth attention: you mentioned the hip consultation again — this is the third time in 10 days. It's been promoted to Priority A with a suggested due date of April 15."

This is a cheap, low-token prompt because all the data is already structured at this point. The LLM is just narrating what happened.

---

## n8n Node Map for the Enhanced Workflow

### New nodes to add (in order)

```
[After Merge Brain Dumps, before IF Has Content]

NEW: Prepare LLM Context
  Type: n8n-nodes-base.code
  Purpose: Assembles each brain dump's text + metadata into a clean string
  with the domain, today's date, and a preview of current quarterly rocks.

NEW: LLM Extractor — Claude
  Type: @n8n/n8n-nodes-langchain.lmChatAnthropic
  Model: claude-haiku-4-5-20251001 (fast + cheap, ~$0.001 per brain dump set)
  Output: structured JSON array of extracted items
  System prompt: full extraction prompt (see Insertion Point 1 above)

NEW: Parse LLM Output
  Type: n8n-nodes-base.code
  Purpose: Parses the JSON string returned by the LLM, validates schema,
  handles any malformed output gracefully (falls back to empty array + alert)

[Optional — after Parse LLM Output]

NEW: Deduplication Check
  Type: n8n-nodes-base.code (text fuzzy match) OR
        @n8n/n8n-nodes-langchain.vectorStoreSearch (Qdrant)
  Purpose: Compare new tasks against open tasks in master list

[Optional — parallel branch]

NEW: Review Item Triage
  Type: @n8n/n8n-nodes-langchain.lmChatAnthropic
  Model: claude-haiku-4-5-20251001
  Purpose: Classify review items into action_now / someday_maybe / follow_up / discard

[Before Build Summary Email]

NEW: Narrative Briefing Generator
  Type: @n8n/n8n-nodes-langchain.lmChatAnthropic
  Model: claude-haiku-4-5-20251001 (2–3 sentence output, very cheap)
  Purpose: Write a plain-English summary of the day's processing
```

### Nodes removed or simplified

- **Parse & Analyze (Node 10):** Replaced entirely by the LLM Extractor pipeline. The 8,025-char regex parser is deleted.
- **Build Summary Email (Node 17):** The task-card building logic remains, but the narrative intro paragraph is now generated rather than templated.

### Nodes unchanged

Everything from IF Has Content onward (Build All Updates, Split Files Loop, Set Binary Content, Upload to MinIO, Send Brain Dump Digest) is unchanged. The AI layer produces the same JSON schema that the downstream nodes already consume. This is the key design constraint: the AI is a drop-in upgrade at the parsing layer only.

---

## Model Selection & Cost

|Task|Model|Why|Est. cost per day|
|---|---|---|---|
|Main extraction|Claude Haiku|Fast, cheap, follows JSON schemas well|~$0.001|
|Review item triage|Claude Haiku|Same|~$0.0005|
|Narrative briefing|Claude Haiku|2–3 sentence output, trivial token cost|~$0.0002|
|Deduplication (optional LLM)|Embeddings API|One-time per task, stored in Qdrant|~$0.00001/task|
|**Total daily cost**|||**< $0.01**|

The entire daily processing run costs less than a penny. There's no reason to use anything other than Haiku here — the tasks are well-defined, the schemas are rigid, and Haiku follows structured JSON prompts reliably.

For the Anthropic API credential in n8n: Settings → Credentials → New → Anthropic → paste API key.

---

## Implementation Phases

### Phase 1 — Drop-in LLM Parser (highest ROI, lowest risk)

**Change:** Add Prepare LLM Context + LLM Extractor + Parse LLM Output between Merge and IF Has Content. Remove the Parse & Analyze code node.

**Effort:** 2–3 hours (write the prompt, test with 3–4 real brain dump examples, tune the schema)

**What you gain immediately:**

- Free-form prose brain dumps work
- Natural language dates resolve
- Rock alignment is automatic
- Low-confidence items flagged in email instead of silently dropped
- Priority inference from content rather than manual tagging

**Risk:** LLM can return malformed JSON. The Parse LLM Output node needs a try/catch that falls back to a `has_content: false` safe exit with an error alert email. This is 10 lines of code.

---

### Phase 2 — Deduplication + Rock Stall Detection

**Change:** Add text-fuzzy dedup code node after Parse LLM Output. Add rock stall counter to Build Summary Email.

**Effort:** 1–2 hours

**What you gain:**

- Duplicate suppression
- Rock momentum tracking
- Email alerts when a rock has had no A-task input for N days

---

### Phase 3 — Review Item Triage + Someday-Maybe File

**Change:** Add Review Item Triage parallel branch. Add Someday-Maybe.md file to the write-back array when items are classified `someday_maybe`.

**Effort:** 2–3 hours

**What you gain:**

- Notes and ideas stop dying in the email
- Someday-Maybe list builds up over time — becomes a genuine resource

---

### Phase 4 — Narrative Briefing + Tone-Aware Digest

**Change:** Add Narrative Briefing Generator node before Send Brain Dump Digest. Inject the output into the email HTML.

**Effort:** 1 hour

**What you gain:**

- Email reads like a morning briefing, not a task spreadsheet
- Contextual callouts ("you mentioned the hip thing again")
- Feels like a smart assistant instead of a cron job

---

### Phase 5 — Vector Memory (Qdrant)

**Change:** Deploy Qdrant on CT-202. Add embedding + upsert step after each task is filed. Replace text-fuzzy dedup with semantic vector search.

**Effort:** Half day (mostly Qdrant setup + n8n Qdrant node configuration)

**What you gain:**

- True semantic deduplication (catches paraphrases)
- Historical pattern queries: "How many times has this topic come up in the last 30 days?"
- Foundation for the full learning agent (Phase 6)

**Qdrant deployment:**

```bash
# On CT-202 alongside n8n
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v /opt/n8n/qdrant:/qdrant/storage \
  qdrant/qdrant
```

---

### Phase 6 — Full AI Agent with Tool Calling

**Change:** Replace the entire LLM Extractor + enrichment pipeline with a single n8n AI Agent node equipped with tools.

**n8n AI Agent node** + **tools** (implemented as sub-workflows or HTTP calls):

|Tool|What it does|When the agent uses it|
|---|---|---|
|`get_quarterly_rocks`|Returns current rocks + status + progress from North Star.md|At the start of every run to load context|
|`get_open_tasks`|Returns all open Priority A tasks from Master Task List|For deduplication + priority arbitration|
|`get_recent_history`|Queries Qdrant: "What tasks have been filed about [topic] in the last 30 days?"|When confidence is low or recurring pattern suspected|
|`classify_item`|LLM sub-call to classify a single ambiguous item with full reasoning|For items the main extraction flags as `confidence: low`|
|`create_task`|Adds a task to the output array|When agent decides an item should be filed|
|`flag_for_review`|Adds item to review section of email|When agent decides human should see it first|
|`file_someday`|Adds item to Someday-Maybe.md|When item is worth parking|

The agent's system prompt is the same extraction prompt from Phase 1, but now it can call tools to look things up before making decisions. It's no longer a single-pass extraction — it can reason: "I've seen this topic before, let me check the history before deciding if this is a duplicate or a new angle on the same problem."

This is the full vision. It's genuinely intelligent intake processing.

---

## Structural Guardrails (Non-Negotiables)

Regardless of how much AI is added, these design constraints must hold:

**1. Human always approves before filing.** Review items, low-confidence tasks, and anything the agent is uncertain about go to the email digest first, never auto-filed. High-confidence tasks above a threshold (say, 0.9) can auto-file. Everything else flags for review.

**2. Every decision is explainable.** The `reasoning` field from the LLM is stored with each task (as an Obsidian comment or metadata field). You should always be able to look at a filed task and see why it was classified the way it was.

**3. Fallback to safe state.** If the LLM call fails (API down, rate limit, malformed response), the workflow exits cleanly with an error notification rather than filing garbled data. The original brain dump content is preserved in MinIO untouched.

**4. The schema is the contract.** The downstream nodes (Build All Updates, file writes) don't change. The AI layer must produce the same `priority_a_tasks`, `priority_b_tasks`, `review_*` JSON structure. This means AI is swappable without touching the write layer.

**5. Cost transparency.** Every LLM call logs input and output token counts to a MinIO log file (`automation-logs/brain-dump-costs.jsonl`). You should be able to see what each run costs and catch any prompt that's accidentally inflating token usage.

---

## Quick Wins vs. Long Game

|Change|Effort|Impact|When|
|---|---|---|---|
|LLM extraction (Phase 1)|3 hrs|🔥🔥🔥🔥|Do after deployment|
|Rock stall detection|1 hr|🔥🔥🔥|Phase 2|
|Duplicate suppression|2 hrs|🔥🔥🔥|Phase 2|
|Review item triage|2 hrs|🔥🔥|Phase 3|
|Narrative briefing|1 hr|🔥🔥|Phase 4|
|Qdrant vector memory|4 hrs|🔥🔥🔥|Phase 5|
|Full AI Agent|1 day|🔥🔥🔥🔥🔥|Phase 6|

---

## What "Future-Proof" Actually Means Here

The workflow as designed is future-proof **structurally**: the extraction layer is isolated from the write layer by a clean JSON schema. Swapping rule-based JS for an LLM, or swapping Haiku for a better model, or adding an agent — none of these require touching the file write logic.

What it is **not** yet future-proof against is:

- Your quarterly rocks changing (currently hardcoded in the LLM system prompt — must be updated each quarter)
- Your brain dump template structure changing (LLM extraction is flexible here, but a major restructure would need a prompt update)
- n8n's Langchain node API changing (n8n updates Langchain nodes regularly)

**The rock hardcoding problem** is the one worth solving now: instead of hardcoding the rocks in the LLM prompt, the workflow should read them dynamically from North Star.md or Needle Movers.md at runtime (already fetched in the weekly digest workflow). This way when Q3 starts and your rocks rotate, you update North Star.md and the brain dump AI prompt updates automatically.

---

_AI Enhancement Design for the Brain Dump Processor — March 2026_
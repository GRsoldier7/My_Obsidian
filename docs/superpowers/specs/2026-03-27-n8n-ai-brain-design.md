# n8n AI Brain — Intelligent Workflow Agents

**Date:** 2026-03-27
**Status:** Design Approved
**Author:** Aaron + Claude

---

## Summary

Add a shared AI sub-workflow ("the Brain") to n8n that gives all 5 Life OS workflows intelligent content processing, needle-mover scoring, and strategic insight. Free-tier LLMs only (Groq primary, Gemini Flash fallback). Total daily token cost: ~2000-4000 tokens. Five workflows: 4 upgraded, 1 new.

---

## Design Mandate

Efficient. Effective. Concise. Lean. Extremely polished.

- Zero wasted tokens — gate checks before every AI call
- One shared Brain — no duplicate prompt logic
- Free tier first — paid only if free breaks
- Structured JSON output only — no prose from the LLM
- Needle-mover scoring on everything — tasks, notes, articles, decisions

---

## Architecture: Central Brain Pattern

### AI Brain Sub-Workflow

A single reusable n8n sub-workflow that all other workflows call via n8n's "Execute Sub-Workflow" node.

**Interface:**

```json
// Input
{
  "job": "classify | summarize | brief | triage | review",
  "content": "...",
  "context": { /* optional: north_star, overdue_tasks, weekly_completions */ }
}

// Output
{
  "success": true,
  "results": [ /* structured items — schema varies by job type */ ]
}
```

**Model Stack (free tier priority order):**

| Priority | Provider | Model | Free Tier | Speed | Best For |
|----------|----------|-------|-----------|-------|----------|
| 1 | Groq | Llama 3.3 70B | ~6000 req/day | Blazing | Classification, structured JSON |
| 2 | Google | Gemini 2.0 Flash | ~1500 req/day | Fast | Summarization, longer analysis |

Auto-fallback: If Groq returns a rate limit error (429), retry the same call with Gemini Flash. Zero downtime.

**System Prompt (~400 tokens, loaded once per call):**

```
You are the AI Brain for Aaron's Life Operating System. You process personal knowledge management content and return structured JSON only.

CONTEXT:
- 8 life domains: faith, family, business, consulting, work, health, home, personal
- Task format: - [ ] Description [area:: X] [priority:: A/B/C] [due:: YYYY-MM-DD]
- Priority A = needle-mover (advances North Star quarterly rocks or annual goals)
- Priority B = important but not a needle-mover
- Priority C = nice-to-have

NEEDLE-MOVER DEFINITION:
A needle-mover directly advances one of Aaron's quarterly rocks or annual goals. Urgent != important. "Reply to Slack" is not a needle-mover. "Draft Echelon Seven offer page" is.

RULES:
- Return valid JSON only. No markdown fences. No prose.
- Be concise. Summaries are 3-4 sentences max.
- Rewrite raw shorthand into clear, complete sentences that future-Aaron can understand in 2 weeks.
- When content crosses domains (e.g., "pray about consulting deal"), tag the primary area and list secondary in connections.
- If uncertain about area, default to personal. If uncertain about priority, default to B.
```

**Job-specific instruction appended per call (not duplicated in system prompt).**

---

## Workflow 1: Brain Dump Processor (7AM Daily)

### Changes from Current
- Remove: 200+ line JavaScript parser
- Add: Single call to AI Brain with `job: classify`
- Add: New item type routing (task, note, article, decision)

### Flow

```
Schedule (7AM)
  → Read 8 brain dump files from MinIO (S3)
  → Filter out empty files (no AI call for empty dumps)
  → Concatenate non-empty dumps with domain labels
  → Call AI Brain (job: classify)
  → Route by item type:
      tasks     → 00_Inbox/processed/YYYY-MM-DD-HHmm-slug.md
      notes     → Domain folder (area-to-folder mapping)
      articles  → Append URL to 00_Inbox/articles-to-process.md
      decisions → 00_Inbox/processed/YYYY-MM-DD-HHmm-slug.md (with pros/cons)
  → Clear brain dump files
  → Send smart digest email (grouped by domain, needle-movers at top)
```

### Classify Job Output Schema

```json
{
  "results": [
    {
      "type": "task | note | article | decision",
      "title": "Clean, actionable title",
      "content": "Polished body text rewritten for clarity",
      "area": "faith | family | business | consulting | work | health | home | personal",
      "priority": "A | B | C",
      "needle_mover": true,
      "due": "2026-04-01 | null",
      "connections": ["faith", "consulting"],
      "url": "https://... | null",
      "source_domain": "consulting"
    }
  ]
}
```

### Routing Rules
- `type: task` → Write individual file to `00_Inbox/processed/` with canonical task format in body. Needle-movers get Priority A automatically.
- `type: note` → Write to domain folder per area-to-folder mapping. Frontmatter includes `needle_mover` field.
- `type: article` → Append URL + context line to `00_Inbox/articles-to-process.md` for Article Processor.
- `type: decision` → Write to `00_Inbox/processed/` with `type: decision` frontmatter. AI provides initial pros/cons framing. Always Priority A.

### Area-to-Folder Mapping (Canonical)

| Area | Folder Path |
|------|-------------|
| faith | `30_Knowledge Library/Bible Studies & Notes/` |
| family | `20_Domains (Life and Work)/Personal/Family/` |
| business | `20_Domains (Life and Work)/Personal/Business Ideas & Projects/` |
| consulting | `20_Domains (Life and Work)/Career/Consulting/` |
| work | `20_Domains (Life and Work)/Career/Parallon/` |
| health | `30_Knowledge Library/Biohacking/` |
| home | `20_Domains (Life and Work)/Personal/Home/` |
| personal | `20_Domains (Life and Work)/Personal/` |

### Token Cost
~600-800 tokens per daily run (one batched call for all 8 dumps).

---

## Workflow 2: Daily Note Creator (6AM Daily)

### Changes from Current
- Add: Gate check — only call AI when there's signal
- Add: AI-generated briefing inserted into daily note template
- Keep: Existing template structure, day-of-week themes, idempotency check

### Flow

```
Schedule (6AM)
  → Check if daily note already exists (idempotent — same as today)
  → Read from MinIO (local parsing, no AI):
      - Overdue tasks (parse Master Task List for due < today)
      - Inbox count (S3 list of 00_Inbox/processed/)
      - This week's needle-mover tasks (parse for priority A / needle_mover: true)
  → GATE CHECK:
      0 overdue + 0 inbox + 0 needle-movers = SKIP AI, use static template
      ANY content = proceed to AI call
  → Call AI Brain (job: brief)
  → Insert briefing into daily note under ## Today's Focus
  → Write daily note to MinIO
```

### Brief Job Output Schema

```json
{
  "results": {
    "focus_items": [
      "Complete Echelon Seven offer draft (needle-mover, due Wednesday)",
      "Call electrician about generator (overdue 3 days)",
      "Review consulting proposal from inbox"
    ],
    "domain_nudge": "No health tasks completed in 8 days",
    "overdue_count": 2
  }
}
```

### Briefing Format in Daily Note

```markdown
## Today's Focus
> **3 items need attention today:**
> 1. Complete Echelon Seven offer draft *(needle-mover, due Wed)*
> 2. Call electrician about generator *(overdue 3 days)*
> 3. Review consulting proposal from inbox
>
> *No health tasks completed in 8 days.*
```

### Token Cost
0 tokens on quiet days. ~300 tokens on active days. Estimated 3-4 AI calls per week.

---

## Workflow 3: Overdue Task Alert — Smart Triage Email

### Changes from Current
- Remove: Flat list email
- Add: AI triage with act/reschedule/drop/escalate recommendations
- Add: Gate check — no overdue items = no email

### Flow

```
Schedule (existing cadence)
  → Read Master Task List + 00_Inbox/processed/ from MinIO
  → Parse overdue tasks locally (date comparison, no AI)
  → GATE CHECK: 0 overdue = stop, no email, no AI call
  → Read North Star.md (for needle-mover context)
  → Call AI Brain (job: triage, content: overdue task list, context: { north_star: "..." })
  → Send structured triage email
```

### Triage Job Output Schema

```json
{
  "results": [
    {
      "task": "Draft Echelon Seven offer page",
      "area": "business",
      "days_overdue": 5,
      "recommendation": "escalate",
      "reason": "Needle-mover aligned with Q2 rock. This is your #1 priority.",
      "suggested_date": null
    },
    {
      "task": "Research new lawn mower options",
      "area": "home",
      "days_overdue": 21,
      "recommendation": "drop",
      "reason": "C-priority, overdue 3 weeks. Not advancing any goal.",
      "suggested_date": null
    },
    {
      "task": "Review consulting contract terms",
      "area": "consulting",
      "days_overdue": 2,
      "recommendation": "reschedule",
      "reason": "Important but not this week. Push to Monday.",
      "suggested_date": "2026-03-30"
    }
  ]
}
```

### Email Structure

```
SUBJECT: [Triage] 2 needle-movers need action, 4 items to reschedule

🔴 DO TODAY (Needle-Movers)
  • Draft Echelon Seven offer page (business, 5 days overdue)
    → This is your #1 priority. Aligned with Q2 rock.

🟡 RESCHEDULE THESE
  • Review consulting contract terms → push to Monday 3/30
  • Update weekly report template → push to Friday 4/3
  • Schedule dentist appointment → push to next week
  • Order replacement filter for HVAC → push to Saturday

⚪ CONSIDER DROPPING
  • Research new lawn mower options (21 days overdue, C-priority)
```

### Token Cost
~400 tokens per call. Only fires when overdue items exist.

---

## Workflow 4: Weekly Digest (Sunday 6PM) — Strategic Review

### Changes from Current
- Remove: Simple file-read summary
- Add: Full strategic review comparing actions vs. North Star goals
- Add: Domain balance analysis, needle-mover scorecard, accountability question

### Flow

```
Schedule (Sunday 6PM)
  → Read from MinIO:
      - North Star.md (quarterly rocks + annual goals)
      - Master Task List (completed tasks this week — parse completion dates locally)
      - 00_Inbox/processed/ files created this week
      - Open needle-mover tasks
  → Call AI Brain (job: review, content: all above, context: { north_star: "..." })
  → Send strategic review email
```

### Review Job Output Schema

```json
{
  "results": {
    "needle_mover_scorecard": {
      "completed": [
        { "task": "Draft Echelon Seven offer page", "area": "business" }
      ],
      "still_open": [
        { "task": "Record 3 social media ministry videos", "area": "faith", "next_action": "Block 2 hours Tuesday morning" }
      ],
      "completed_count": 2,
      "total_count": 5
    },
    "domain_balance": {
      "faith": 1,
      "family": 3,
      "business": 2,
      "consulting": 4,
      "work": 14,
      "health": 0,
      "home": 2,
      "personal": 1
    },
    "domain_warning": "Business has zero activity but Q2 rock is 'Launch Echelon Seven offer'",
    "wins": [
      "Completed Echelon Seven offer draft — major needle-mover",
      "Resolved 4 consulting deliverables ahead of schedule"
    ],
    "next_week_focus": [
      "Record ministry videos (faith needle-mover, 2 weeks stale)",
      "Schedule hip consultation (health, keep slipping)",
      "Finalize Echelon Seven pricing page (business, builds on this week's win)"
    ],
    "honest_question": "You completed 14 work tasks but 0 health tasks. Your hip decision has been deferred for 3 weeks. Is Parallon consuming time that should go to your health?"
  }
}
```

### Email Structure

```
SUBJECT: Weekly Review — 2/5 Needle-Movers Done | ⚠️ Health Neglected

📊 NEEDLE-MOVER SCORECARD: 2 of 5
  ✅ Draft Echelon Seven offer page (business)
  ✅ Complete Q1 consulting retrospective (consulting)
  ⬜ Record 3 social media ministry videos (faith) → Block 2hrs Tuesday
  ⬜ Schedule hip consultation (health) → Call Monday AM
  ⬜ Finalize Echelon Seven pricing (business) → Builds on this week

⚖️ DOMAIN BALANCE
  work: ██████████████ 14
  consulting: ████ 4
  family: ███ 3
  business: ██ 2
  home: ██ 2
  faith: █ 1
  personal: █ 1
  health: 0 ⚠️

🏆 WINS
  • Completed Echelon Seven offer draft — major needle-mover
  • Resolved 4 consulting deliverables ahead of schedule

🎯 NEXT WEEK FOCUS
  1. Record ministry videos (faith needle-mover, 2 weeks stale)
  2. Schedule hip consultation (health, keeps slipping)
  3. Finalize Echelon Seven pricing page (builds on this week)

💬 ONE HONEST QUESTION
  "You completed 14 work tasks but 0 health tasks. Your hip decision
   has been deferred for 3 weeks. Is Parallon consuming time that
   should go to your health?"
```

### Token Cost
~800 tokens. Once per week. Highest value workflow.

---

## Workflow 5: Article/Link Processor (8AM + 7PM Daily)

### New Workflow

Picks up URLs from `00_Inbox/articles-to-process.md`, fetches content, summarizes, tags, and files as knowledge notes.

### Capture Mechanism

One file: `Homelab/00_Inbox/articles-to-process.md`

```markdown
---
type: article-queue
---

https://example.com/zone-2-cardio-longevity
https://example.com/ai-consulting-pricing — relevant for Echelon Seven pricing
```

URLs are added by:
- User pasting directly into the file in Obsidian
- Brain Dump Processor routing article-type items here automatically

### Flow

```
Schedule (8AM, 7PM)
  → Read articles-to-process.md from MinIO
  → GATE CHECK: empty or no URLs = stop
  → For each URL:
      → HTTP Request node (fetch page content)
      → HTML Extract node (strip to readable text)
      → Call AI Brain (job: summarize, content: extracted text + user context)
  → Write article note to domain folder:
      Frontmatter: source_url, date_captured, area, needle_mover
      Body: ## Summary + ## Key Takeaways + ## Action Items
  → Extract any action items as separate task files in 00_Inbox/processed/
  → Clear articles-to-process.md (leave frontmatter intact)
```

### Summarize Job Output Schema

```json
{
  "results": {
    "title": "Zone 2 Cardio: The Longevity Protocol",
    "summary": "Zone 2 cardio (60-70% max HR) improves mitochondrial function and is the single highest-ROI exercise for longevity. 3-4 sessions per week of 30-45 minutes.",
    "key_takeaways": [
      "Zone 2 = conversational pace, nose-breathing test",
      "3-4x per week, 30-45 min minimum effective dose",
      "Improves fat oxidation and mitochondrial density"
    ],
    "area": "health",
    "needle_mover": false,
    "action_items": [
      {
        "task": "Add 3x weekly zone 2 cardio sessions to gym routine",
        "area": "health",
        "priority": "B",
        "due": null
      }
    ]
  }
}
```

### Article Note Output

Written to domain folder (e.g., `30_Knowledge Library/Biohacking/`):

```markdown
---
type: article-note
source_url: https://example.com/zone-2-cardio-longevity
date_captured: 2026-03-27
area: health
needle_mover: false
---

# Zone 2 Cardio: The Longevity Protocol

## Summary
Zone 2 cardio (60-70% max HR) improves mitochondrial function and is the single
highest-ROI exercise for longevity. 3-4 sessions per week of 30-45 minutes.

## Key Takeaways
- Zone 2 = conversational pace, nose-breathing test
- 3-4x per week, 30-45 min minimum effective dose
- Improves fat oxidation and mitochondrial density

## Action Items
- [ ] Add 3x weekly zone 2 cardio sessions to gym routine [area:: health] [priority:: B]
```

### Token Cost
~400-500 tokens per article. Estimated 2-3 articles/day = ~1000-1500 tokens/day.

---

## Total Daily Token Budget

| Workflow | Frequency | Tokens/Call | Daily Estimate |
|----------|-----------|-------------|----------------|
| Brain Dump Processor | 1x/day | 600-800 | 800 |
| Daily Note Creator | 1x/day | 0-300 | 150 (avg) |
| Overdue Task Alert | 1x/day | 0-400 | 200 (avg) |
| Weekly Digest | 1x/week | 800 | 115 (daily avg) |
| Article Processor | 2x/day | 400-500 each | 1000 |

**Total: ~2,200 tokens/day average**

Groq free tier handles ~6,000 requests/day. This system uses 3-8 requests/day. Not even close to the limit.

---

## Error Handling

Every workflow follows the same pattern:

1. **Gate check fails** (empty content) → Stop gracefully, no AI call, no notification
2. **Groq rate limit (429)** → Auto-retry with Gemini Flash
3. **Gemini rate limit** → Skip AI processing, fall back to "dumb" mode (existing JS logic preserved as fallback), send email noting "AI processing unavailable today"
4. **Invalid JSON from LLM** → Retry once with "Return valid JSON only" appended. If still invalid, log error and skip.
5. **MinIO connection failure** → n8n's built-in retry (3 attempts, exponential backoff). If all fail, send error notification email.

---

## n8n Credentials Required

| Credential | Type | Purpose |
|------------|------|---------|
| MinIO — obsidian-vault | AWS S3 | Vault file access (exists) |
| Gmail SMTP | SMTP | Email notifications (exists) |
| Groq API | HTTP Header Auth | Primary LLM (`Authorization: Bearer <key>`) |
| Gemini API | HTTP Header Auth | Fallback LLM (`x-goog-api-key: <key>`) |

New credentials needed: Groq API key (free at console.groq.com) and Gemini API key (free at aistudio.google.com).

---

## File Changes Summary

| Action | File |
|--------|------|
| **Modify** | `workflows/n8n/brain-dump-processor.json` — replace JS parser with AI Brain call |
| **Modify** | `workflows/n8n/daily-note-creator.json` — add gate check + briefing |
| **Modify** | `workflows/n8n/overdue-task-alert.json` — add triage + structured email |
| **Modify** | `workflows/n8n/weekly-digest.json` — full strategic review |
| **Create** | `workflows/n8n/ai-brain.json` — shared AI sub-workflow |
| **Create** | `workflows/n8n/article-processor.json` — new article/link workflow |
| **Modify** | `.env.example` — add GROQ_API_KEY, GEMINI_API_KEY |
| **Modify** | `scripts/setup-n8n.sh` — add Groq/Gemini credentials, article-processor import |

---

## Out of Scope

- No Ollama/local models (unnecessary complexity when free tiers are sufficient)
- No real-time processing (batch scheduled workflows only)
- No vault structure changes (existing folder hierarchy is correct)
- No new Obsidian plugins required
- No changes to the canonical task format

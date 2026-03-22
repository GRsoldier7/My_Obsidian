---
name: ai-business-optimizer
description: >
  Genius-level AI-native business operations covering AI audit methodology, process
  identification for automation, tool stack selection, agentic workflow design, ROI
  measurement, and building a business that runs on AI as its operating system. Use this
  skill whenever the user wants to automate business or life processes with AI, build an
  AI-first operations stack, reduce manual work through LLM-powered automation, design
  agentic workflows, evaluate AI tools for ROI, or run their business/life more efficiently
  using AI as a force multiplier. Also trigger for AI integration into existing workflows,
  building n8n/Make.com automations, designing Python agentic scripts, or any request
  to "make my [business/life/system] run on AI."
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: product
  adjacent-skills: ai-agentic-specialist, entrepreneurial-os, obsidian-automation-architect
  source-repo: GRsoldier7/My_AI_Skills
---

# AI Business Optimizer — Savant-Level Skill

## Philosophy

AI-native mastery = **process-first, tool-second** · **ROI measurement** · **agentic > assistive** · **the flywheel** (each AI implementation frees time to build the next — compound leverage is the goal).

## 1. The AI Business Audit

### Process Classification
```
Tier A (automate now):   Repetitive, pattern-based, text output
  Examples: Email drafts, report generation, data formatting, research synthesis

Tier B (augment with AI): Requires judgment but AI accelerates
  Examples: Strategy planning, content creation, proposal writing

Tier C (human only):     High-stakes, novel judgment, relationship-critical
  Examples: Crisis management, C-suite relationships, ethical decisions
```

### ROI Formula
```
Priority = (Hours saved/week × hourly rate × 52) / Implementation cost
Example: 5h/week × $150 × 52 = $39K/year ÷ $1,200 implementation = 32.5x ROI

Rule: Any automation with ROI < 10x → replace or eliminate
Rule: Any workflow saving >10h/week that isn't automated → automate this week
```

## 2. Recommended Automation Stack

```
Orchestration:    n8n (self-hosted on MiniPC Docker) — no per-operation pricing
Backup:           Make.com for cloud-side workflows
LLM:              Claude API (claude-sonnet-4-6 for automation, claude-opus-4-6 for strategy)
Research:         Perplexity API
Document Intel:   NotebookLM / Claude with document context
Scheduling:       APScheduler or Prefect for Python pipelines
Vault Bridge:     Python scripts reading/writing Obsidian markdown files
```

## 3. Agentic Workflow Design

### When to Use Agentic vs. Assistive
```
Assistive: Output needs human judgment — You → AI → You review → Output
Agentic:   Repeatable, errors recoverable — Trigger → AI Agent → Output (exceptions only)
Automated: Deterministic, minimal error risk — Trigger → Process → Output (no human loop)
```

### Key n8n Pattern for Obsidian Integration
```
Trigger: Schedule (daily 6AM)
→ Google Calendar API: Fetch today's events
→ GitHub API: Fetch open PRs/issues
→ Claude API: Generate daily brief markdown
→ File System: Write to vault/00_Inbox/Daily_Brief_YYYY-MM-DD.md
→ Notification: Webhook to phone
```

## 4. Business Function Automation Map

| Function | Automation | ROI Target |
|----------|-----------|------------|
| Content creation | AI draft → human edit | 80% time reduction |
| Meeting notes | Transcription → Claude → structured note | 30 min → 2 min |
| Email triage | AI labels + draft responses | 10h/week recovered |
| Weekly digest | Data aggregation → Claude synthesis → vault | 2-3h → read 5 min |
| Consulting proposals | Template + AI customization | 3h → 30 min review |
| Competitive intel | Scheduled scrape → Claude → vault note | Daily, zero manual time |

## 5. Prompt Engineering for Automation

### System Prompt Template
```
You are an AI assistant for [Name], acting in the role of [function].
Style: [Concise/Detailed]. Tone: [Professional/Warm].
Always: [key behaviors]
Never: [hard boundaries]
Output format: [exact markdown structure required]
```

## Anti-Patterns

1. **Tool Accumulation:** 20 AI tools with no integration between them — map workflows first
2. **Automating the Messy:** Standardize the process manually 10x before automating it
3. **AI Replacing Thinking:** Your unique perspective is the moat; AI is the leverage

## Quality Gates
- [ ] AI audit completed: all recurring tasks classified Tier A/B/C
- [ ] ROI tracking in place: monthly hours saved vs. cost
- [ ] Top 3 highest-ROI automations identified and implemented
- [ ] Agentic workflows running for ≥2 repetitive processes
- [ ] All AI-assisted outputs reviewed by human before publishing

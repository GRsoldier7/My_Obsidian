# n8n AI Brain — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add intelligent AI agents to all n8n workflows using a shared "Central Brain" sub-workflow powered by free-tier LLMs (Groq + Gemini Flash fallback), enabling smart content classification, needle-mover scoring, strategic weekly reviews, and automated article processing.

**Architecture:** A single reusable n8n sub-workflow (`ai-brain.json`) accepts a job type + content payload and returns structured JSON via Groq's free Llama 3.3 70B API (with Gemini 2.0 Flash as fallback). Five parent workflows call this Brain: the upgraded Brain Dump Processor, Daily Note Creator, Overdue Task Alert, Weekly Digest, and a new Article Processor. Every workflow has gate checks to avoid unnecessary AI calls.

**Tech Stack:** n8n (self-hosted), Groq API (free tier — Llama 3.3 70B), Google Gemini API (free tier — 2.0 Flash), MinIO S3, Gmail SMTP. All workflows are JSON files imported via n8n API.

**Design Spec:** `docs/superpowers/specs/2026-03-27-n8n-ai-brain-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `workflows/n8n/ai-brain.json` | Shared AI sub-workflow — receives job+content, calls Groq/Gemini, returns structured JSON |
| **Modify** | `workflows/n8n/brain-dump-processor.json` | Replace JS parser with AI Brain call, add article/decision routing |
| **Modify** | `workflows/n8n/daily-note-creator.json` | Add gate check + AI briefing insertion |
| **Modify** | `workflows/n8n/overdue-task-alert.json` | Add North Star read + AI triage + structured email |
| **Modify** | `workflows/n8n/weekly-digest.json` | Full strategic review with domain balance + accountability |
| **Create** | `workflows/n8n/article-processor.json` | New: fetch URLs, summarize, file to domain folders |
| **Modify** | `.env.example` | Add GROQ_API_KEY, GEMINI_API_KEY |
| **Modify** | `scripts/setup-n8n.sh` | Add Groq/Gemini credential creation, article-processor import |

---

## Reference: Existing Credentials & Constants

These values are referenced throughout the plan. Do not change them.

```
MinIO S3 Credential ID:   jscahbrUH2TCnnSx
MinIO S3 Credential Name: MinIO S3
Gmail SMTP Credential ID: lWGOwsktldwb3iEj
Gmail SMTP Credential Name: Gmail SMTP (Aaron)

S3 Bucket: obsidian-vault
Vault Prefix: Homelab
Timezone: America/Chicago
Email: aaron.deyoung@gmail.com

Brain Dumps:      Homelab/00_Inbox/brain-dumps/BrainDump — {Domain}.md
Master Task List: Homelab/10_Active Projects/Active Personal/!!! MASTER TASK LIST.md
North Star:       Homelab/000_Master Dashboard/North Star.md
Daily Notes:      Homelab/40_Timeline_Weekly/Daily/YYYY-MM-DD.md
Article Queue:    Homelab/00_Inbox/articles-to-process.md
Processed Inbox:  Homelab/00_Inbox/processed/
```

---

## Task 1: Update Environment Configuration

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add new API key variables to .env.example**

Open `.env.example` and add these lines after the existing `ANTHROPIC_API_KEY` line:

```bash
# --- LLM API Keys (Free Tier) ---
# Primary: Groq (Llama 3.3 70B) — Get free key at https://console.groq.com
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
# Fallback: Google Gemini 2.0 Flash — Get free key at https://aistudio.google.com
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxx
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "chore: add Groq and Gemini API key placeholders to .env.example"
```

---

## Task 2: Create the AI Brain Sub-Workflow

**Files:**
- Create: `workflows/n8n/ai-brain.json`

This is the core of the entire system. One sub-workflow, called by all others.

- [ ] **Step 1: Create the AI Brain workflow JSON**

Create `workflows/n8n/ai-brain.json` with this content:

```json
{
  "name": "🧠 AI Brain — Shared Intelligence Layer",
  "nodes": [
    {
      "parameters": {
        "content": "## 🧠 AI Brain — Shared Intelligence Layer\n\nReusable sub-workflow called by all Life OS workflows.\n\n**Input:** JSON with `job` (classify|summarize|brief|triage|review), `content`, and optional `context`.\n**Output:** Structured JSON via Groq (primary) or Gemini Flash (fallback).\n\n**Jobs:**\n- `classify` — Brain dump → tasks, notes, articles, decisions\n- `summarize` — Article text → summary, takeaways, area\n- `brief` — Daily context → focus items, nudges\n- `triage` — Overdue tasks → act/reschedule/drop/escalate\n- `review` — Weekly data → scorecard, balance, wins, honest question"
      },
      "id": "sticky-overview",
      "name": "Sticky Note",
      "type": "n8n-nodes-base.stickyNote",
      "typeVersion": 1,
      "position": [180, 60]
    },
    {
      "parameters": {},
      "id": "sub-workflow-trigger",
      "name": "When Called By Another Workflow",
      "type": "n8n-nodes-base.executeWorkflowTrigger",
      "typeVersion": 1,
      "position": [460, 340]
    },
    {
      "parameters": {
        "jsCode": "// Build the prompt for the LLM based on job type\nconst input = $input.first().json;\nconst job = input.job;\nconst content = input.content;\nconst context = input.context || {};\n\nconst SYSTEM_PROMPT = `You are the AI Brain for Aaron's Life Operating System. You process personal knowledge management content and return structured JSON only.\n\nCONTEXT:\n- 8 life domains: faith, family, business, consulting, work, health, home, personal\n- Task format: - [ ] Description [area:: X] [priority:: A/B/C] [due:: YYYY-MM-DD]\n- Priority A = needle-mover (advances North Star quarterly rocks or annual goals)\n- Priority B = important but not a needle-mover\n- Priority C = nice-to-have\n\nNEEDLE-MOVER DEFINITION:\nA needle-mover directly advances one of Aaron's quarterly rocks or annual goals. Urgent != important. \"Reply to Slack\" is not a needle-mover. \"Draft Echelon Seven offer page\" is.\n\nRULES:\n- Return valid JSON only. No markdown fences. No explanatory text. Just the JSON object.\n- Be concise. Summaries are 3-4 sentences max.\n- Rewrite raw shorthand into clear, complete sentences that future-Aaron can understand in 2 weeks.\n- When content crosses domains (e.g., \"pray about consulting deal\"), tag the primary area and list secondary in connections array.\n- If uncertain about area, default to personal. If uncertain about priority, default to B.`;\n\nconst JOB_PROMPTS = {\n  classify: `TASK: Classify this brain dump content into structured items.\n\nFor each item found, determine its type:\n- \"task\" — an actionable to-do with a clear completion state\n- \"note\" — information, thought, or reference to file away\n- \"article\" — a URL or article reference to read/summarize later\n- \"decision\" — something requiring deliberation with pros/cons (always Priority A)\n\nReturn JSON:\n{\"results\": [{\"type\": \"task|note|article|decision\", \"title\": \"string\", \"content\": \"string\", \"area\": \"string\", \"priority\": \"A|B|C\", \"needle_mover\": true|false, \"due\": \"YYYY-MM-DD|null\", \"connections\": [\"area1\", \"area2\"], \"url\": \"string|null\", \"source_domain\": \"string\"}]}`,\n\n  summarize: `TASK: Summarize this article content.\n\nReturn JSON:\n{\"results\": {\"title\": \"string\", \"summary\": \"3-4 sentence summary\", \"key_takeaways\": [\"takeaway1\", \"takeaway2\", \"takeaway3\"], \"area\": \"string\", \"needle_mover\": true|false, \"action_items\": [{\"task\": \"string\", \"area\": \"string\", \"priority\": \"A|B|C\", \"due\": \"YYYY-MM-DD|null\"}]}}`,\n\n  brief: `TASK: Generate a concise daily briefing (50-80 words max).\n\nYou will receive: overdue tasks, inbox count, and this week's needle-movers.\nReturn the top 3 focus items (needle-movers first), and one domain nudge if any life area has been neglected.\n\nReturn JSON:\n{\"results\": {\"focus_items\": [\"item1\", \"item2\", \"item3\"], \"domain_nudge\": \"string|null\", \"overdue_count\": 0}}`,\n\n  triage: `TASK: Triage overdue tasks with actionable recommendations.\n\nFor each overdue task, recommend one of:\n- \"escalate\" — This is a needle-mover being ignored. Do it today.\n- \"act\" — Important, do it today.\n- \"reschedule\" — Push to a specific future date with reason.\n- \"drop\" — Stale, low-priority, not advancing any goal. Delete or move to someday/maybe.\n\nUse the North Star context to identify needle-movers.\n\nReturn JSON:\n{\"results\": [{\"task\": \"string\", \"area\": \"string\", \"days_overdue\": 0, \"recommendation\": \"escalate|act|reschedule|drop\", \"reason\": \"string\", \"suggested_date\": \"YYYY-MM-DD|null\"}]}`,\n\n  review: `TASK: Generate a strategic weekly review.\n\nYou will receive: North Star goals, completed tasks this week, open needle-movers, and inbox items.\nAnalyze domain balance, needle-mover progress, and alignment between actions and stated goals.\n\nReturn JSON:\n{\"results\": {\"needle_mover_scorecard\": {\"completed\": [{\"task\": \"string\", \"area\": \"string\"}], \"still_open\": [{\"task\": \"string\", \"area\": \"string\", \"next_action\": \"string\"}], \"completed_count\": 0, \"total_count\": 0}, \"domain_balance\": {\"faith\": 0, \"family\": 0, \"business\": 0, \"consulting\": 0, \"work\": 0, \"health\": 0, \"home\": 0, \"personal\": 0}, \"domain_warning\": \"string|null\", \"wins\": [\"string\"], \"next_week_focus\": [\"string\", \"string\", \"string\"], \"honest_question\": \"string\"}}`\n};\n\nconst jobPrompt = JOB_PROMPTS[job];\nif (!jobPrompt) {\n  return [{ json: { success: false, error: `Unknown job type: ${job}` } }];\n}\n\nlet userMessage = jobPrompt + '\\n\\nCONTENT:\\n' + content;\n\nif (context.north_star) {\n  userMessage += '\\n\\nNORTH STAR GOALS:\\n' + context.north_star;\n}\nif (context.overdue_tasks) {\n  userMessage += '\\n\\nOVERDUE TASKS:\\n' + context.overdue_tasks;\n}\nif (context.weekly_completions) {\n  userMessage += '\\n\\nCOMPLETED THIS WEEK:\\n' + context.weekly_completions;\n}\nif (context.open_needle_movers) {\n  userMessage += '\\n\\nOPEN NEEDLE-MOVERS:\\n' + context.open_needle_movers;\n}\n\nreturn [{\n  json: {\n    systemPrompt: SYSTEM_PROMPT,\n    userMessage: userMessage,\n    job: job\n  }\n}];"
      },
      "id": "build-prompt",
      "name": "Build LLM Prompt",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [680, 340]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Content-Type",
              "value": "application/json"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ model: 'llama-3.3-70b-versatile', messages: [{ role: 'system', content: $json.systemPrompt }, { role: 'user', content: $json.userMessage }], temperature: 0.3, max_tokens: 2000, response_format: { type: 'json_object' } }) }}",
        "options": {
          "timeout": 30000,
          "response": {
            "response": {
              "fullResponse": false
            }
          }
        }
      },
      "id": "groq-request",
      "name": "Groq: Llama 3.3 70B",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [900, 240],
      "credentials": {
        "httpHeaderAuth": {
          "id": "GROQ_CREDENTIAL_ID",
          "name": "Groq API"
        }
      },
      "continueOnFail": true
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "groq-ok",
              "leftValue": "={{ $json.statusCode }}",
              "rightValue": 429,
              "operator": {
                "type": "number",
                "operation": "notEquals"
              }
            },
            {
              "id": "groq-has-choices",
              "leftValue": "={{ $json.choices }}",
              "rightValue": "",
              "operator": {
                "type": "exists",
                "operation": "exists"
              }
            }
          ],
          "combinator": "and"
        }
      },
      "id": "groq-ok-check",
      "name": "Groq Succeeded?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2.2,
      "position": [1120, 240]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Content-Type",
              "value": "application/json"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ contents: [{ parts: [{ text: $('Build LLM Prompt').item.json.systemPrompt + '\\n\\n' + $('Build LLM Prompt').item.json.userMessage }] }], generationConfig: { temperature: 0.3, maxOutputTokens: 2000, responseMimeType: 'application/json' } }) }}",
        "options": {
          "timeout": 30000
        }
      },
      "id": "gemini-fallback",
      "name": "Gemini Flash Fallback",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [1340, 380],
      "credentials": {
        "httpHeaderAuth": {
          "id": "GEMINI_CREDENTIAL_ID",
          "name": "Gemini API"
        }
      },
      "continueOnFail": true
    },
    {
      "parameters": {
        "jsCode": "// Parse Groq response\nconst input = $input.first().json;\ntry {\n  const content = input.choices[0].message.content;\n  const parsed = JSON.parse(content);\n  return [{ json: { success: true, ...parsed, source: 'groq' } }];\n} catch (e) {\n  return [{ json: { success: false, error: 'Failed to parse Groq response: ' + e.message, raw: JSON.stringify(input) } }];\n}"
      },
      "id": "parse-groq",
      "name": "Parse Groq Response",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [1340, 140]
    },
    {
      "parameters": {
        "jsCode": "// Parse Gemini response\nconst input = $input.first().json;\ntry {\n  let text;\n  if (input.candidates && input.candidates[0]) {\n    text = input.candidates[0].content.parts[0].text;\n  } else {\n    return [{ json: { success: false, error: 'No Gemini response', raw: JSON.stringify(input) } }];\n  }\n  // Strip markdown fences if present\n  text = text.replace(/^```json\\n?/i, '').replace(/\\n?```$/i, '').trim();\n  const parsed = JSON.parse(text);\n  return [{ json: { success: true, ...parsed, source: 'gemini' } }];\n} catch (e) {\n  return [{ json: { success: false, error: 'Failed to parse Gemini response: ' + e.message, raw: JSON.stringify(input) } }];\n}"
      },
      "id": "parse-gemini",
      "name": "Parse Gemini Response",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [1560, 380]
    },
    {
      "parameters": {
        "jsCode": "// Merge point — return whichever response we got\nconst input = $input.first().json;\nreturn [{ json: input }];"
      },
      "id": "return-result",
      "name": "Return Result",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [1780, 260]
    }
  ],
  "connections": {
    "When Called By Another Workflow": {
      "main": [
        [{ "node": "Build LLM Prompt", "type": "main", "index": 0 }]
      ]
    },
    "Build LLM Prompt": {
      "main": [
        [{ "node": "Groq: Llama 3.3 70B", "type": "main", "index": 0 }]
      ]
    },
    "Groq: Llama 3.3 70B": {
      "main": [
        [{ "node": "Groq Succeeded?", "type": "main", "index": 0 }]
      ]
    },
    "Groq Succeeded?": {
      "main": [
        [{ "node": "Parse Groq Response", "type": "main", "index": 0 }],
        [{ "node": "Gemini Flash Fallback", "type": "main", "index": 0 }]
      ]
    },
    "Gemini Flash Fallback": {
      "main": [
        [{ "node": "Parse Gemini Response", "type": "main", "index": 0 }]
      ]
    },
    "Parse Groq Response": {
      "main": [
        [{ "node": "Return Result", "type": "main", "index": 0 }]
      ]
    },
    "Parse Gemini Response": {
      "main": [
        [{ "node": "Return Result", "type": "main", "index": 0 }]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1",
    "saveManualExecutions": true,
    "callerPolicy": "workflowsFromSameOwner",
    "timezone": "America/Chicago"
  },
  "staticData": null,
  "tags": [],
  "triggerCount": 0,
  "updatedAt": "2026-03-27T00:00:00.000Z",
  "versionId": "1"
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
cd "Z:/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator/.claude/worktrees/amazing-heyrovsky"
python -c "import json; json.load(open('workflows/n8n/ai-brain.json')); print('Valid JSON')"
```

Expected: `Valid JSON`

- [ ] **Step 3: Commit**

```bash
git add workflows/n8n/ai-brain.json
git commit -m "feat: create AI Brain shared sub-workflow with Groq + Gemini fallback"
```

---

## Task 3: Upgrade Brain Dump Processor

**Files:**
- Modify: `workflows/n8n/brain-dump-processor.json`

The current workflow has a 200+ line JavaScript parser in `parse-analyze` that does regex-based classification. We replace that with a call to the AI Brain, and add routing logic for the new item types (article, decision).

- [ ] **Step 1: Read the current brain-dump-processor.json to confirm structure**

```bash
python -c "import json; wf=json.load(open('workflows/n8n/brain-dump-processor.json')); print([n['name'] for n in wf['nodes']])"
```

Expected: List of node names including `Parse & Analyze All`, `Build All Updates`, `Build Digest Email`

- [ ] **Step 2: Replace the Parse & Analyze node with AI Brain call**

In `brain-dump-processor.json`, find the node with `"id": "parse-analyze"` and replace its entire `parameters.jsCode` with:

```javascript
// Collect all accumulated brain dump content
const items = $input.all();
let allContent = '';

for (const item of items) {
  const dumps = item.json.allDumps || [];
  for (const dump of dumps) {
    if (dump.content && dump.content.trim().length > 10) {
      allContent += `\n--- ${dump.domain} (${dump.area}) ---\n${dump.content}\n`;
    }
  }
}

if (!allContent.trim()) {
  return [{ json: { hasContent: false, results: [], allContent: '' } }];
}

return [{ json: { hasContent: true, allContent: allContent.trim() } }];
```

- [ ] **Step 3: Add an Execute Sub-Workflow node after parse-analyze**

Add a new node to the workflow JSON's `nodes` array:

```json
{
  "parameters": {
    "source": "database",
    "workflowId": "={{ $env.AI_BRAIN_WORKFLOW_ID }}",
    "options": {}
  },
  "id": "call-ai-brain",
  "name": "AI Brain: Classify",
  "type": "n8n-nodes-base.executeWorkflow",
  "typeVersion": 1.2,
  "position": [1220, 340]
}
```

**Important:** Since n8n's Execute Workflow node needs a workflow ID that we won't know until import, we'll use an environment variable `AI_BRAIN_WORKFLOW_ID`. We'll instead use the HTTP Request approach to call the Brain directly inline. Replace the above with a Code node that builds the Groq API call:

Actually, the cleaner approach for a sub-workflow call in n8n is to use the workflow name. But the most reliable approach given the self-hosted setup is to **inline the AI call in each workflow using an HTTP Request node pattern**. This avoids sub-workflow ID management.

**Revised approach:** Instead of a sub-workflow, we create a shared Code node pattern. Each workflow has its own HTTP Request to Groq/Gemini but shares the same system prompt via a Code node. This is simpler, more reliable, and avoids the sub-workflow ID dependency.

Delete the Execute Sub-Workflow node idea. Instead, add these nodes after the `parse-analyze` node (which now just collects content):

Add to the `nodes` array in `brain-dump-processor.json`:

```json
{
  "parameters": {
    "jsCode": "const input = $input.first().json;\nif (!input.hasContent) {\n  return [{ json: { success: false, skip: true } }];\n}\n\nconst SYSTEM_PROMPT = 'You are the AI Brain for Aaron\\'s Life Operating System. You process personal knowledge management content and return structured JSON only.\\n\\nCONTEXT:\\n- 8 life domains: faith, family, business, consulting, work, health, home, personal\\n- Task format: - [ ] Description [area:: X] [priority:: A/B/C] [due:: YYYY-MM-DD]\\n- Priority A = needle-mover (advances North Star quarterly rocks or annual goals)\\n- Priority B = important but not a needle-mover\\n- Priority C = nice-to-have\\n\\nNEEDLE-MOVER DEFINITION:\\nA needle-mover directly advances one of Aaron\\'s quarterly rocks or annual goals. Urgent != important. \"Reply to Slack\" is not a needle-mover. \"Draft Echelon Seven offer page\" is.\\n\\nQUARTERLY ROCKS:\\n- Faith: Launch the Social Media Bible Study\\n- Family: Marriage Alignment with Christy\\n- Business: Ship the MVP — Echelon Seven\\n- Work: Deliver Union Project + Position for Exit\\n- Health: Hip Decision + 3x/week Gym for 8 Weeks\\n\\nRULES:\\n- Return valid JSON only. No markdown fences. No explanatory text. Just the JSON object.\\n- Be concise. Summaries are 3-4 sentences max.\\n- Rewrite raw shorthand into clear, complete sentences that future-Aaron can understand in 2 weeks.\\n- When content crosses domains (e.g., \"pray about consulting deal\"), tag the primary area and list secondary in connections array.\\n- If uncertain about area, default to personal. If uncertain about priority, default to B.';\n\nconst USER_MSG = 'TASK: Classify this brain dump content into structured items.\\n\\nFor each item found, determine its type:\\n- \"task\" — an actionable to-do with a clear completion state\\n- \"note\" — information, thought, or reference to file away\\n- \"article\" — a URL or article reference to read/summarize later\\n- \"decision\" — something requiring deliberation with pros/cons (always Priority A)\\n\\nReturn JSON:\\n{\"results\": [{\"type\": \"task|note|article|decision\", \"title\": \"string\", \"content\": \"string\", \"area\": \"string\", \"priority\": \"A|B|C\", \"needle_mover\": true|false, \"due\": \"YYYY-MM-DD|null\", \"connections\": [], \"url\": \"string|null\", \"source_domain\": \"string\"}]}\\n\\nCONTENT:\\n' + input.allContent;\n\nreturn [{ json: { systemPrompt: SYSTEM_PROMPT, userMessage: USER_MSG } }];"
  },
  "id": "build-ai-prompt",
  "name": "Build AI Prompt",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [1120, 340]
},
{
  "parameters": {
    "method": "POST",
    "url": "https://api.groq.com/openai/v1/chat/completions",
    "authentication": "genericCredentialType",
    "genericAuthType": "httpHeaderAuth",
    "sendBody": true,
    "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({ model: 'llama-3.3-70b-versatile', messages: [{ role: 'system', content: $json.systemPrompt }, { role: 'user', content: $json.userMessage }], temperature: 0.3, max_tokens: 2000, response_format: { type: 'json_object' } }) }}",
    "options": { "timeout": 30000 }
  },
  "id": "groq-classify",
  "name": "Groq: Classify Brain Dump",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [1340, 240],
  "credentials": {
    "httpHeaderAuth": {
      "id": "GROQ_CREDENTIAL_ID",
      "name": "Groq API"
    }
  },
  "continueOnFail": true
},
{
  "parameters": {
    "conditions": {
      "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "strict" },
      "conditions": [
        { "id": "has-choices", "leftValue": "={{ $json.choices }}", "rightValue": "", "operator": { "type": "exists", "operation": "exists" } }
      ],
      "combinator": "and"
    }
  },
  "id": "groq-classify-ok",
  "name": "Groq OK?",
  "type": "n8n-nodes-base.if",
  "typeVersion": 2.2,
  "position": [1560, 240]
},
{
  "parameters": {
    "method": "POST",
    "url": "=https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={{ $env.GEMINI_API_KEY }}",
    "sendBody": true,
    "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({ contents: [{ parts: [{ text: $('Build AI Prompt').item.json.systemPrompt + '\\n\\n' + $('Build AI Prompt').item.json.userMessage }] }], generationConfig: { temperature: 0.3, maxOutputTokens: 2000, responseMimeType: 'application/json' } }) }}",
    "options": { "timeout": 30000 }
  },
  "id": "gemini-classify-fallback",
  "name": "Gemini Fallback: Classify",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [1780, 380],
  "continueOnFail": true
},
{
  "parameters": {
    "jsCode": "// Parse LLM response (Groq format)\nconst input = $input.first().json;\ntry {\n  const content = input.choices[0].message.content;\n  const parsed = JSON.parse(content);\n  return [{ json: { success: true, results: parsed.results || [], source: 'groq' } }];\n} catch (e) {\n  return [{ json: { success: false, error: e.message, results: [] } }];\n}"
  },
  "id": "parse-groq-classify",
  "name": "Parse Groq Response",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [1780, 140]
},
{
  "parameters": {
    "jsCode": "// Parse LLM response (Gemini format)\nconst input = $input.first().json;\ntry {\n  let text = input.candidates[0].content.parts[0].text;\n  text = text.replace(/^```json\\n?/i, '').replace(/\\n?```$/i, '').trim();\n  const parsed = JSON.parse(text);\n  return [{ json: { success: true, results: parsed.results || [], source: 'gemini' } }];\n} catch (e) {\n  return [{ json: { success: false, error: e.message, results: [] } }];\n}"
  },
  "id": "parse-gemini-classify",
  "name": "Parse Gemini Response",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [2000, 380]
}
```

- [ ] **Step 4: Replace the Build All Updates node with AI-aware routing**

Replace the `build-updates` node's `jsCode` with:

```javascript
// Route AI-classified items to their destinations
const input = $input.first().json;
const results = input.results || [];
const BUCKET = 'obsidian-vault';
const PREFIX = 'Homelab';

const TZ = 'America/Chicago';
const now = new Date();
const fmt = (opts) => new Intl.DateTimeFormat('en-US', { timeZone: TZ, ...opts });
const y = parseInt(fmt({ year: 'numeric' }).format(now));
const m = fmt({ month: '2-digit' }).format(now);
const d = fmt({ day: '2-digit' }).format(now);
const hh = fmt({ hour: '2-digit', hour12: false }).format(now).padStart(2, '0');
const mm = fmt({ minute: '2-digit' }).format(now).padStart(2, '0');
const dateStr = `${y}-${m}-${d}`;
const timeStr = `${hh}${mm}`;

const AREA_FOLDER_MAP = {
  faith: '30_Knowledge Library/Bible Studies & Notes',
  family: '20_Domains (Life and Work)/Personal/Family',
  business: '20_Domains (Life and Work)/Personal/Business Ideas & Projects',
  consulting: '20_Domains (Life and Work)/Career/Consulting',
  work: '20_Domains (Life and Work)/Career/Parallon',
  health: '30_Knowledge Library/Biohacking',
  home: '20_Domains (Life and Work)/Personal/Home',
  personal: '20_Domains (Life and Work)/Personal'
};

const filesToUpload = [];
const articleUrls = [];
let itemIndex = 0;

for (const item of results) {
  itemIndex++;
  const slug = (item.title || 'item').toLowerCase().replace(/[^a-z0-9]+/g, '-').substring(0, 40);
  const area = item.area || 'personal';
  const priority = item.needle_mover ? 'A' : (item.priority || 'B');
  const connections = (item.connections || []).filter(c => c !== area);
  const connectionsStr = connections.length > 0 ? `\nconnections: [${connections.join(', ')}]` : '';

  if (item.type === 'task' || item.type === 'decision') {
    const dueStr = item.due ? ` [due:: ${item.due}]` : '';
    const nmFlag = item.needle_mover ? '\nneedle_mover: true' : '';
    const typeLabel = item.type === 'decision' ? 'decision' : 'processed-task';

    let body = '';
    if (item.type === 'decision') {
      body = `- [ ] ${item.title} [area:: ${area}] [priority:: A]${dueStr}\n\n## Context\n${item.content}\n\n## Pros\n- \n\n## Cons\n- \n\n## Decision\n*Pending*`;
    } else {
      body = `- [ ] ${item.title} [area:: ${area}] [priority:: ${priority}]${dueStr}\n\n${item.content || ''}`;
    }

    const content = `---\ncreated: ${new Date().toISOString()}\ntype: ${typeLabel}\nsource: brain-dump\nneedle_mover: ${item.needle_mover || false}${connectionsStr}\n---\n\n${body.trim()}\n`;

    filesToUpload.push({
      bucket: BUCKET,
      fileKey: `${PREFIX}/00_Inbox/processed/${dateStr}-${timeStr}-${slug}.md`,
      content: content,
      label: `${item.type}: ${item.title}`
    });
  } else if (item.type === 'note') {
    const folder = AREA_FOLDER_MAP[area] || AREA_FOLDER_MAP.personal;
    const nmFlag = item.needle_mover ? '\nneedle_mover: true' : '';
    const content = `---\ncreated: ${new Date().toISOString()}\ntype: brain-dump-note\nsource: brain-dump\narea: ${area}\nneedle_mover: ${item.needle_mover || false}${connectionsStr}\n---\n\n# ${item.title}\n\n${item.content || ''}\n`;

    filesToUpload.push({
      bucket: BUCKET,
      fileKey: `${PREFIX}/${folder}/${dateStr}-${slug}.md`,
      content: content,
      label: `note: ${item.title}`
    });
  } else if (item.type === 'article') {
    articleUrls.push(`${item.url || item.content}${item.title ? ' — ' + item.title : ''}`);
  }
}

// If there are article URLs, add them to the article queue file
if (articleUrls.length > 0) {
  filesToUpload.push({
    bucket: BUCKET,
    fileKey: `${PREFIX}/00_Inbox/articles-to-process.md`,
    content: `---\ntype: article-queue\n---\n\n${articleUrls.join('\n')}\n`,
    label: `article queue (${articleUrls.length} URLs)`,
    isArticleQueue: true
  });
}

// Add cleared brain dump templates
const domains = [
  { file: 'BrainDump — Faith.md', area: 'faith' },
  { file: 'BrainDump — Family.md', area: 'family' },
  { file: 'BrainDump — Business (Echelon Seven).md', area: 'business' },
  { file: 'BrainDump — Consulting.md', area: 'consulting' },
  { file: 'BrainDump — Work (Parallon).md', area: 'work' },
  { file: 'BrainDump — Health.md', area: 'health' },
  { file: 'BrainDump — Home.md', area: 'home' },
  { file: 'BrainDump — Personal.md', area: 'personal' }
];

for (const dom of domains) {
  filesToUpload.push({
    bucket: BUCKET,
    fileKey: `${PREFIX}/00_Inbox/brain-dumps/${dom.file}`,
    content: `---\narea: ${dom.area}\nprocessed: false\n---\n\nCapture your ${dom.area} thoughts here...\n`,
    label: `clear: ${dom.file}`
  });
}

return [{ json: { filesToUpload, results, articleCount: articleUrls.length } }];
```

- [ ] **Step 5: Replace the Build Digest Email node with smart digest**

Replace the `build-email` node's `jsCode` with:

```javascript
// Build smart digest email — grouped by domain, needle-movers at top
const input = $input.first().json;
const results = input.results || [];

const needleMovers = results.filter(r => r.needle_mover && (r.type === 'task' || r.type === 'decision'));
const otherTasks = results.filter(r => !r.needle_mover && r.type === 'task');
const notes = results.filter(r => r.type === 'note');
const articles = results.filter(r => r.type === 'article');
const decisions = results.filter(r => r.type === 'decision' && !r.needle_mover);

const totalItems = results.length;
const nmCount = needleMovers.length;

const itemRow = (item) => {
  const areaEmoji = { faith: '🙏', family: '💒', business: '🚀', consulting: '💼', work: '🏥', health: '💪', home: '🏠', personal: '🤖' };
  const emoji = areaEmoji[item.area] || '📌';
  const due = item.due ? ` (due ${item.due})` : '';
  const conn = (item.connections || []).length > 0 ? ` [also: ${item.connections.join(', ')}]` : '';
  return `<tr><td style="padding:8px;border-bottom:1px solid #eee;">${emoji} <strong>${item.title}</strong>${due}${conn}</td><td style="padding:8px;border-bottom:1px solid #eee;text-align:center;">${item.area}</td><td style="padding:8px;border-bottom:1px solid #eee;text-align:center;">${item.priority || 'B'}</td></tr>`;
};

let html = `<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;">\n`;
html += `<h1 style="color:#1a1a2e;">🧠 Brain Dump Digest</h1>\n`;
html += `<p style="color:#666;">${totalItems} items processed • ${nmCount} needle-movers found</p>\n`;

if (needleMovers.length > 0) {
  html += `<h2 style="color:#c0392b;">🎯 Needle-Movers (Priority A)</h2>\n`;
  html += `<table style="width:100%;border-collapse:collapse;">${needleMovers.map(itemRow).join('')}</table>\n`;
}

if (otherTasks.length > 0) {
  html += `<h2 style="color:#2c3e50;">✅ Tasks</h2>\n`;
  html += `<table style="width:100%;border-collapse:collapse;">${otherTasks.map(itemRow).join('')}</table>\n`;
}

if (decisions.length > 0) {
  html += `<h2 style="color:#8e44ad;">🤔 Decisions to Make</h2>\n`;
  html += `<table style="width:100%;border-collapse:collapse;">${decisions.map(itemRow).join('')}</table>\n`;
}

if (notes.length > 0) {
  html += `<h2 style="color:#27ae60;">📝 Notes Filed</h2>\n`;
  html += `<ul>${notes.map(n => `<li><strong>${n.title}</strong> → ${n.area}</li>`).join('')}</ul>\n`;
}

if (articles.length > 0) {
  html += `<h2 style="color:#2980b9;">📚 Articles Queued (${articles.length})</h2>\n`;
  html += `<p>These will be fetched and summarized automatically.</p>\n`;
  html += `<ul>${articles.map(a => `<li>${a.url || a.title}</li>`).join('')}</ul>\n`;
}

html += `</div>`;

const subject = nmCount > 0
  ? `🧠 Brain Dump: ${nmCount} needle-mover${nmCount > 1 ? 's' : ''} + ${totalItems - nmCount} items`
  : `🧠 Brain Dump: ${totalItems} items processed`;

return [{ json: { subject, html } }];
```

- [ ] **Step 6: Update the connections in the workflow JSON**

Update the `connections` object so the new nodes are wired correctly:

```
parse-analyze → if-has-content → [true] build-ai-prompt → groq-classify → groq-classify-ok
                                                                            → [true] parse-groq-classify → build-updates → ...
                                                                            → [false] gemini-classify-fallback → parse-gemini-classify → build-updates → ...
                               → [false] (stop)
```

Remove the old connection from `parse-analyze` directly to `get-master-task-list`. The new flow goes through the AI classification first.

- [ ] **Step 7: Remove the get-master-task-list node**

Per ADR-001, processed items go to `00_Inbox/processed/` as individual files, not appended to the Master Task List. Remove the `get-master-task-list` node and its connections. The `build-updates` node no longer needs to read the MTL.

- [ ] **Step 8: Validate JSON**

```bash
python -c "import json; json.load(open('workflows/n8n/brain-dump-processor.json')); print('Valid JSON')"
```

Expected: `Valid JSON`

- [ ] **Step 9: Commit**

```bash
git add workflows/n8n/brain-dump-processor.json
git commit -m "feat: replace brain dump JS parser with AI classification via Groq/Gemini"
```

---

## Task 4: Upgrade Daily Note Creator

**Files:**
- Modify: `workflows/n8n/daily-note-creator.json`

Add gate check + AI briefing. The key constraint: **zero tokens on quiet days.**

- [ ] **Step 1: Add gate check nodes after compute-date**

Add these nodes to the `nodes` array:

```json
{
  "parameters": {
    "jsCode": "// Read overdue tasks and needle-movers for gate check\n// We'll check the Master Task List for overdue items and Priority A tasks\nconst input = $input.first().json;\nreturn [{ json: { ...input, needsContextRead: true } }];"
  },
  "id": "prepare-context-read",
  "name": "Prepare Context Read",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [680, 540]
},
{
  "parameters": {
    "operation": "download",
    "bucketName": "obsidian-vault",
    "fileKey": "Homelab/10_Active Projects/Active Personal/!!! MASTER TASK LIST.md"
  },
  "id": "read-mtl-for-briefing",
  "name": "S3: Read Task List",
  "type": "n8n-nodes-base.awsS3",
  "typeVersion": 2,
  "position": [900, 540],
  "credentials": {
    "aws": {
      "id": "jscahbrUH2TCnnSx",
      "name": "MinIO S3"
    }
  },
  "continueOnFail": true
},
{
  "parameters": {
    "jsCode": "// Gate check: parse MTL for overdue tasks and needle-movers\n// If nothing interesting, skip AI call entirely\nconst dateInfo = $('Compute Date & File Path').first().json;\nconst todayStr = dateInfo.dateStr;\n\nlet mtlContent = '';\ntry {\n  const binary = $input.first().binary;\n  if (binary && binary.data) {\n    mtlContent = Buffer.from(binary.data.data, 'base64').toString('utf-8');\n  }\n} catch (e) { /* no MTL found, that's ok */ }\n\n// Parse overdue tasks\nconst taskRegex = /^\\s*- \\[ \\]\\s+(.+)$/gm;\nconst overdueItems = [];\nconst needleMovers = [];\nlet match;\n\nwhile ((match = taskRegex.exec(mtlContent)) !== null) {\n  const line = match[1];\n  const dueMatch = line.match(/\\[due::\\s*(\\d{4}-\\d{2}-\\d{2})\\s*\\]/);\n  const priorityMatch = line.match(/\\[priority::\\s*([A-C])\\s*\\]/i);\n  const areaMatch = line.match(/\\[area::\\s*(\\w+)\\s*\\]/);\n  \n  const priority = priorityMatch ? priorityMatch[1].toUpperCase() : 'B';\n  \n  if (dueMatch && dueMatch[1] < todayStr) {\n    overdueItems.push({ task: line.substring(0, 80), due: dueMatch[1], area: areaMatch ? areaMatch[1] : 'unknown', priority });\n  }\n  if (priority === 'A') {\n    needleMovers.push({ task: line.substring(0, 80), due: dueMatch ? dueMatch[1] : null, area: areaMatch ? areaMatch[1] : 'unknown' });\n  }\n}\n\nconst hasSignal = overdueItems.length > 0 || needleMovers.length > 0;\n\nreturn [{ json: {\n  hasSignal,\n  overdueItems,\n  needleMovers,\n  overdueCount: overdueItems.length,\n  needleMoverCount: needleMovers.length\n} }];"
  },
  "id": "gate-check",
  "name": "Gate Check: Has Signal?",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [1120, 540]
},
{
  "parameters": {
    "conditions": {
      "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "strict" },
      "conditions": [
        { "id": "has-signal", "leftValue": "={{ $json.hasSignal }}", "rightValue": true, "operator": { "type": "boolean", "operation": "equals" } }
      ],
      "combinator": "and"
    }
  },
  "id": "if-has-signal",
  "name": "Has Signal?",
  "type": "n8n-nodes-base.if",
  "typeVersion": 2.2,
  "position": [1340, 540]
}
```

- [ ] **Step 2: Add AI briefing call (only on true branch)**

Add to `nodes` array:

```json
{
  "parameters": {
    "jsCode": "const gate = $input.first().json;\nconst overdueStr = gate.overdueItems.map(t => `- ${t.task} (${t.area}, ${t.priority}, due ${t.due})`).join('\\n');\nconst nmStr = gate.needleMovers.map(t => `- ${t.task} (${t.area}${t.due ? ', due ' + t.due : ''})`).join('\\n');\n\nconst content = `Overdue tasks (${gate.overdueCount}):\\n${overdueStr || 'None'}\\n\\nNeedle-movers this week (${gate.needleMoverCount}):\\n${nmStr || 'None'}`;\n\nconst SYSTEM = 'You are the AI Brain for Aaron\\'s Life Operating System. Return structured JSON only. Be extremely concise — 50-80 words max for the entire briefing.';\nconst USER = `TASK: Generate a concise daily briefing.\\n\\nReturn JSON:\\n{\"results\": {\"focus_items\": [\"item1\", \"item2\", \"item3\"], \"domain_nudge\": \"string|null\", \"overdue_count\": 0}}\\n\\nCONTENT:\\n${content}`;\n\nreturn [{ json: { systemPrompt: SYSTEM, userMessage: USER } }];"
  },
  "id": "build-brief-prompt",
  "name": "Build Brief Prompt",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [1560, 440]
},
{
  "parameters": {
    "method": "POST",
    "url": "https://api.groq.com/openai/v1/chat/completions",
    "authentication": "genericCredentialType",
    "genericAuthType": "httpHeaderAuth",
    "sendBody": true,
    "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({ model: 'llama-3.3-70b-versatile', messages: [{ role: 'system', content: $json.systemPrompt }, { role: 'user', content: $json.userMessage }], temperature: 0.3, max_tokens: 500, response_format: { type: 'json_object' } }) }}",
    "options": { "timeout": 30000 }
  },
  "id": "groq-brief",
  "name": "Groq: Daily Brief",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [1780, 440],
  "credentials": {
    "httpHeaderAuth": { "id": "GROQ_CREDENTIAL_ID", "name": "Groq API" }
  },
  "continueOnFail": true
},
{
  "parameters": {
    "jsCode": "const input = $input.first().json;\nlet briefing = null;\ntry {\n  if (input.choices) {\n    const parsed = JSON.parse(input.choices[0].message.content);\n    briefing = parsed.results || parsed;\n  }\n} catch (e) { /* AI failed, use null briefing */ }\n\nreturn [{ json: { briefing } }];"
  },
  "id": "parse-brief",
  "name": "Parse Brief Response",
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [2000, 440]
}
```

- [ ] **Step 3: Modify the build-note node to inject the briefing**

In the `build-note` node's `jsCode`, add this section after the `## Today's Focus` heading generation. Insert before the `## Tasks` section:

```javascript
// Insert AI briefing if available
const briefData = $('Parse Brief Response')?.first()?.json?.briefing;
if (briefData) {
  const focusItems = briefData.focus_items || [];
  const nudge = briefData.domain_nudge;

  let briefSection = '## Today\'s Focus\n';
  if (focusItems.length > 0) {
    briefSection += `> **${focusItems.length} items need attention today:**\n`;
    focusItems.forEach((item, i) => {
      briefSection += `> ${i + 1}. ${item}\n`;
    });
    if (nudge) {
      briefSection += `>\n> *${nudge}*\n`;
    }
  }
  noteContent += briefSection + '\n';
} else {
  noteContent += '## Today\'s Focus\n> Set your top 3 priorities for today.\n\n';
}
```

If the AI call was skipped (no signal) or failed, the else branch provides the static template — same as today.

- [ ] **Step 4: Wire the connections**

```
compute-date → check-exists → note-missing-check
  → [true] prepare-context-read → read-mtl-for-briefing → gate-check → if-has-signal
                                                                         → [true] build-brief-prompt → groq-brief → parse-brief → build-note → upload-note
                                                                         → [false] build-note → upload-note
  → [false] already-exists
```

The `build-note` node receives input from two paths (with or without briefing). It checks if briefing data exists and injects accordingly.

- [ ] **Step 5: Validate JSON**

```bash
python -c "import json; json.load(open('workflows/n8n/daily-note-creator.json')); print('Valid JSON')"
```

- [ ] **Step 6: Commit**

```bash
git add workflows/n8n/daily-note-creator.json
git commit -m "feat: add gate-checked AI briefing to daily note creator"
```

---

## Task 5: Upgrade Overdue Task Alert

**Files:**
- Modify: `workflows/n8n/overdue-task-alert.json`

- [ ] **Step 1: Add North Star read node**

Add to `nodes` array after `define-scan-targets`:

```json
{
  "parameters": {
    "operation": "download",
    "bucketName": "obsidian-vault",
    "fileKey": "Homelab/000_Master Dashboard/North Star.md"
  },
  "id": "read-north-star",
  "name": "S3: Read North Star",
  "type": "n8n-nodes-base.awsS3",
  "typeVersion": 2,
  "position": [680, 480],
  "credentials": {
    "aws": { "id": "jscahbrUH2TCnnSx", "name": "MinIO S3" }
  },
  "continueOnFail": true
}
```

- [ ] **Step 2: Replace scan-overdue with gate check + AI triage**

Replace the `scan-overdue` node's `jsCode` with:

```javascript
// Parse overdue tasks locally (no AI) + gate check
const TZ = 'America/Chicago';
const now = new Date();
const fmt = (opts) => new Intl.DateTimeFormat('en-US', { timeZone: TZ, ...opts });
const y = parseInt(fmt({ year: 'numeric' }).format(now));
const m = fmt({ month: '2-digit' }).format(now);
const d = fmt({ day: '2-digit' }).format(now);
const todayStr = `${y}-${m}-${d}`;

// Read MTL content
let mtlContent = '';
try {
  const binary = $('S3: Download File').first().binary;
  if (binary && binary.data) {
    mtlContent = Buffer.from(binary.data.data, 'base64').toString('utf-8');
  }
} catch (e) {}

// Read North Star content
let northStarContent = '';
try {
  const binary = $('S3: Read North Star').first().binary;
  if (binary && binary.data) {
    northStarContent = Buffer.from(binary.data.data, 'base64').toString('utf-8');
  }
} catch (e) {}

const taskRegex = /^\s*- \[ \]\s+(.+)$/gm;
const overdueItems = [];
let match;

while ((match = taskRegex.exec(mtlContent)) !== null) {
  const line = match[1];
  const dueMatch = line.match(/\[due::\s*(\d{4}-\d{2}-\d{2})\s*\]/);
  if (!dueMatch || dueMatch[1] >= todayStr) continue;

  const areaMatch = line.match(/\[area::\s*(\w+)\s*\]/);
  const priorityMatch = line.match(/\[priority::\s*([A-C])\s*\]/i);

  const dueDate = new Date(dueMatch[1]);
  const daysOverdue = Math.floor((now - dueDate) / 86400000);

  overdueItems.push({
    task: line.replace(/\[area::.*?\]/g, '').replace(/\[priority::.*?\]/g, '').replace(/\[due::.*?\]/g, '').trim(),
    area: areaMatch ? areaMatch[1] : 'unknown',
    priority: priorityMatch ? priorityMatch[1].toUpperCase() : 'B',
    due: dueMatch[1],
    days_overdue: daysOverdue
  });
}

// Gate check: no overdue items = stop
if (overdueItems.length === 0) {
  return [{ json: { hasOverdue: false, overdueItems: [], northStar: '' } }];
}

return [{ json: { hasOverdue: true, overdueItems, northStar: northStarContent, overdueCount: overdueItems.length } }];
```

- [ ] **Step 3: Add gate check If node**

Add to `nodes`:

```json
{
  "parameters": {
    "conditions": {
      "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "strict" },
      "conditions": [
        { "id": "has-overdue", "leftValue": "={{ $json.hasOverdue }}", "rightValue": true, "operator": { "type": "boolean", "operation": "equals" } }
      ],
      "combinator": "and"
    }
  },
  "id": "if-has-overdue",
  "name": "Has Overdue?",
  "type": "n8n-nodes-base.if",
  "typeVersion": 2.2,
  "position": [900, 340]
}
```

False branch → workflow ends (no email, no AI call).

- [ ] **Step 4: Add AI triage call on true branch**

Add Groq HTTP Request + parse nodes (same pattern as other workflows) with this user message builder:

```javascript
const input = $input.first().json;
const overdueStr = input.overdueItems.map(t =>
  `- "${t.task}" | area: ${t.area} | priority: ${t.priority} | due: ${t.due} | ${t.days_overdue} days overdue`
).join('\n');

const SYSTEM = 'You are the AI Brain for Aaron\'s Life Operating System. Return structured JSON only. Be direct and actionable.';
const USER = `TASK: Triage overdue tasks with actionable recommendations.\n\nFor each overdue task, recommend one of:\n- "escalate" — This is a needle-mover being ignored. Do it today.\n- "act" — Important, do it today.\n- "reschedule" — Push to a specific future date with reason.\n- "drop" — Stale, low-priority, not advancing any goal.\n\nReturn JSON:\n{"results": [{"task": "string", "area": "string", "days_overdue": 0, "recommendation": "escalate|act|reschedule|drop", "reason": "string", "suggested_date": "YYYY-MM-DD|null"}]}\n\nOVERDUE TASKS:\n${overdueStr}\n\nNORTH STAR GOALS:\n${input.northStar}`;

return [{ json: { systemPrompt: SYSTEM, userMessage: USER } }];
```

- [ ] **Step 5: Replace build-email with structured triage email**

Replace `build-email` node's `jsCode` with:

```javascript
const input = $input.first().json;
const results = input.results || [];

const escalate = results.filter(r => r.recommendation === 'escalate');
const act = results.filter(r => r.recommendation === 'act');
const reschedule = results.filter(r => r.recommendation === 'reschedule');
const drop = results.filter(r => r.recommendation === 'drop');

const areaEmoji = { faith: '🙏', family: '💒', business: '🚀', consulting: '💼', work: '🏥', health: '💪', home: '🏠', personal: '🤖' };

const row = (item) => {
  const emoji = areaEmoji[item.area] || '📌';
  return `<li style="margin-bottom:8px;">${emoji} <strong>${item.task}</strong> (${item.area}, ${item.days_overdue}d overdue)<br/><span style="color:#666;font-size:13px;">→ ${item.reason}</span>${item.suggested_date ? `<br/><span style="color:#2980b9;font-size:13px;">📅 Reschedule to ${item.suggested_date}</span>` : ''}</li>`;
};

let html = '<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;max-width:600px;margin:0 auto;">\n';
html += '<h1 style="color:#1a1a2e;">⚠️ Task Triage</h1>\n';

if (escalate.length > 0 || act.length > 0) {
  html += '<h2 style="color:#c0392b;">🔴 DO TODAY</h2>\n';
  html += `<ul style="list-style:none;padding:0;">${[...escalate, ...act].map(row).join('')}</ul>\n`;
}
if (reschedule.length > 0) {
  html += '<h2 style="color:#f39c12;">🟡 RESCHEDULE</h2>\n';
  html += `<ul style="list-style:none;padding:0;">${reschedule.map(row).join('')}</ul>\n`;
}
if (drop.length > 0) {
  html += '<h2 style="color:#95a5a6;">⚪ CONSIDER DROPPING</h2>\n';
  html += `<ul style="list-style:none;padding:0;">${drop.map(row).join('')}</ul>\n`;
}
html += '</div>';

const urgentCount = escalate.length + act.length;
const subject = urgentCount > 0
  ? `[Triage] ${urgentCount} need action today, ${reschedule.length} to reschedule`
  : `[Triage] ${reschedule.length} to reschedule, ${drop.length} to drop`;

return [{ json: { subject, html } }];
```

- [ ] **Step 6: Update connections**

```
schedule-trigger → define-scan-targets → [parallel] download-file + read-north-star → scan-overdue → if-has-overdue
  → [true] build-triage-prompt → groq-triage → parse-triage → build-email → send-email
  → [false] (stop)
```

- [ ] **Step 7: Validate and commit**

```bash
python -c "import json; json.load(open('workflows/n8n/overdue-task-alert.json')); print('Valid JSON')"
git add workflows/n8n/overdue-task-alert.json
git commit -m "feat: add AI triage with act/reschedule/drop to overdue task alert"
```

---

## Task 6: Upgrade Weekly Digest

**Files:**
- Modify: `workflows/n8n/weekly-digest.json`

- [ ] **Step 1: Modify parse-data to extract completion data**

Update the `parse-data` node to also extract completed tasks from this week (tasks marked `- [x]` with a completion date in the last 7 days). Add domain counting logic.

- [ ] **Step 2: Add AI review call after parse-data**

Same Groq HTTP Request pattern. User message builder:

```javascript
const input = $input.first().json;

const SYSTEM = 'You are the AI Brain for Aaron\'s Life Operating System. Return structured JSON only. Be honest, direct, and strategic. The weekly review is the most important output you produce.';

const USER = `TASK: Generate a strategic weekly review.\n\nAnalyze domain balance, needle-mover progress, and alignment between actions and stated goals. Be honest — if Aaron is ignoring a priority area, call it out. The "honest_question" should be genuinely challenging, not soft.\n\nReturn JSON:\n{"results": {"needle_mover_scorecard": {"completed": [{"task": "string", "area": "string"}], "still_open": [{"task": "string", "area": "string", "next_action": "string"}], "completed_count": 0, "total_count": 0}, "domain_balance": {"faith": 0, "family": 0, "business": 0, "consulting": 0, "work": 0, "health": 0, "home": 0, "personal": 0}, "domain_warning": "string|null", "wins": ["string"], "next_week_focus": ["string", "string", "string"], "honest_question": "string"}}\n\nNORTH STAR & QUARTERLY ROCKS:\n${input.northStarContent}\n\nCOMPLETED TASKS THIS WEEK:\n${input.completedThisWeek}\n\nOPEN NEEDLE-MOVERS (Priority A):\n${input.openNeedleMovers}\n\nDOMAIN TASK COUNTS THIS WEEK:\n${JSON.stringify(input.domainCounts)}`;

return [{ json: { systemPrompt: SYSTEM, userMessage: USER } }];
```

- [ ] **Step 3: Replace build-digest with strategic review email**

Replace the `build-digest` node's `jsCode` with the full strategic email builder:

```javascript
const input = $input.first().json;
const r = input.results;
const sc = r.needle_mover_scorecard;
const db = r.domain_balance;

const areaEmoji = { faith: '🙏', family: '💒', business: '🚀', consulting: '💼', work: '🏥', health: '💪', home: '🏠', personal: '🤖' };

// Build domain balance bar chart
const maxCount = Math.max(...Object.values(db), 1);
const domainBar = (area, count) => {
  const barWidth = Math.round((count / maxCount) * 200);
  const emoji = areaEmoji[area] || '📌';
  const warning = count === 0 ? ' ⚠️' : '';
  return `<tr><td style="padding:4px 8px;font-size:13px;">${emoji} ${area}</td><td style="padding:4px 8px;"><div style="background:#3498db;height:16px;width:${barWidth}px;border-radius:3px;display:inline-block;"></div> ${count}${warning}</td></tr>`;
};

let html = '<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;max-width:600px;margin:0 auto;">\n';
html += '<h1 style="color:#1a1a2e;">📊 Weekly Review</h1>\n';

// Needle-mover scorecard
html += `<h2 style="color:#2c3e50;">🎯 Needle-Mover Scorecard: ${sc.completed_count} of ${sc.total_count}</h2>\n`;
if (sc.completed && sc.completed.length > 0) {
  html += '<ul style="list-style:none;padding:0;">' + sc.completed.map(t => `<li style="margin-bottom:4px;">✅ ${t.task} (${t.area})</li>`).join('') + '</ul>\n';
}
if (sc.still_open && sc.still_open.length > 0) {
  html += '<ul style="list-style:none;padding:0;">' + sc.still_open.map(t => `<li style="margin-bottom:4px;">⬜ ${t.task} (${t.area}) → ${t.next_action}</li>`).join('') + '</ul>\n';
}

// Domain balance
html += '<h2 style="color:#2c3e50;">⚖️ Domain Balance</h2>\n';
html += '<table style="width:100%;border-collapse:collapse;">';
for (const area of ['work', 'consulting', 'business', 'family', 'faith', 'health', 'home', 'personal']) {
  html += domainBar(area, db[area] || 0);
}
html += '</table>\n';
if (r.domain_warning) {
  html += `<p style="color:#c0392b;font-weight:bold;">⚠️ ${r.domain_warning}</p>\n`;
}

// Wins
if (r.wins && r.wins.length > 0) {
  html += '<h2 style="color:#27ae60;">🏆 Wins</h2>\n';
  html += '<ul>' + r.wins.map(w => `<li>${w}</li>`).join('') + '</ul>\n';
}

// Next week focus
if (r.next_week_focus && r.next_week_focus.length > 0) {
  html += '<h2 style="color:#8e44ad;">🎯 Next Week Focus</h2>\n';
  html += '<ol>' + r.next_week_focus.map(f => `<li>${f}</li>`).join('') + '</ol>\n';
}

// Honest question
if (r.honest_question) {
  html += `<div style="background:#f8f9fa;border-left:4px solid #e74c3c;padding:16px;margin:20px 0;border-radius:4px;">\n`;
  html += `<h2 style="color:#e74c3c;margin-top:0;">💬 One Honest Question</h2>\n`;
  html += `<p style="font-style:italic;font-size:15px;color:#333;">"${r.honest_question}"</p>\n`;
  html += `</div>\n`;
}

html += '</div>';

const subject = `Weekly Review — ${sc.completed_count}/${sc.total_count} Needle-Movers Done${r.domain_warning ? ' | ⚠️ ' + r.domain_warning.substring(0, 40) : ''}`;

return [{ json: { subject, html } }];
```

- [ ] **Step 4: Validate and commit**

```bash
python -c "import json; json.load(open('workflows/n8n/weekly-digest.json')); print('Valid JSON')"
git add workflows/n8n/weekly-digest.json
git commit -m "feat: upgrade weekly digest to strategic review with domain balance + accountability"
```

---

## Task 7: Create Article Processor Workflow

**Files:**
- Create: `workflows/n8n/article-processor.json`

Brand new workflow. Runs 2x daily (8AM, 7PM). Reads URLs from `articles-to-process.md`, fetches content, summarizes via AI, files to domain folders.

- [ ] **Step 1: Create the article-processor.json workflow**

Create `workflows/n8n/article-processor.json`. The workflow structure:

```
Schedule (8AM, 7PM)
  → S3: Read articles-to-process.md
  → Parse URLs (Code node — extract URLs from file, gate check if empty)
  → If Has URLs?
    → [true] Loop: For Each URL
      → HTTP Request: Fetch Page
      → Extract Text (Code: strip HTML to readable text, limit to 3000 chars)
      → Build Summarize Prompt (Code: system + user message)
      → Groq: Summarize Article (HTTP Request)
      → Parse Response (Code)
      → Build Article Note (Code: frontmatter + summary + takeaways)
      → S3: Upload Article Note
      → [loop continues]
    → After loop: Build task files from action items
    → S3: Upload task files
    → S3: Clear articles-to-process.md (write empty template)
    → [false] Stop
```

Node details:

**Schedule Trigger:**
```json
{
  "parameters": {
    "rule": {
      "interval": [
        { "triggerAtHour": 8 },
        { "triggerAtHour": 19 }
      ]
    }
  },
  "id": "schedule-articles",
  "name": "8AM & 7PM Daily",
  "type": "n8n-nodes-base.scheduleTrigger",
  "typeVersion": 1.2,
  "position": [240, 340]
}
```

**Parse URLs Code:**
```javascript
let content = '';
try {
  const binary = $input.first().binary;
  if (binary && binary.data) {
    content = Buffer.from(binary.data.data, 'base64').toString('utf-8');
  }
} catch (e) {}

// Strip frontmatter
content = content.replace(/^---[\s\S]*?---\s*/m, '').trim();

if (!content) {
  return [{ json: { hasUrls: false, urls: [] } }];
}

// Parse URLs — one per line, optional context after " — "
const lines = content.split('\n').filter(l => l.trim());
const urls = [];

for (const line of lines) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('#')) continue;

  const parts = trimmed.split(' — ');
  const urlPart = parts[0].trim();
  const context = parts.length > 1 ? parts.slice(1).join(' — ').trim() : '';

  // Basic URL validation
  if (urlPart.startsWith('http://') || urlPart.startsWith('https://')) {
    urls.push({ url: urlPart, context });
  }
}

return [{ json: { hasUrls: urls.length > 0, urls, urlCount: urls.length } }];
```

**Extract Text Code (after HTTP fetch):**
```javascript
const input = $input.first();
let text = '';

try {
  // Get response body as text
  const body = input.json.data || input.json.body || '';

  // Strip HTML tags, scripts, styles
  text = body
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<nav[\s\S]*?<\/nav>/gi, '')
    .replace(/<footer[\s\S]*?<\/footer>/gi, '')
    .replace(/<header[\s\S]*?<\/header>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ')
    .trim();

  // Limit to ~3000 chars to keep token usage low
  if (text.length > 3000) {
    text = text.substring(0, 3000) + '... [truncated]';
  }
} catch (e) {
  text = 'Failed to extract text from page.';
}

const urlData = $('Loop: Each URL').first().json;
return [{ json: { extractedText: text, url: urlData.url, context: urlData.context } }];
```

**Build Article Note Code:**
```javascript
const input = $input.first().json;
const r = input.results || input;
const BUCKET = 'obsidian-vault';
const PREFIX = 'Homelab';

const AREA_FOLDER_MAP = {
  faith: '30_Knowledge Library/Bible Studies & Notes',
  family: '20_Domains (Life and Work)/Personal/Family',
  business: '20_Domains (Life and Work)/Personal/Business Ideas & Projects',
  consulting: '20_Domains (Life and Work)/Career/Consulting',
  work: '20_Domains (Life and Work)/Career/Parallon',
  health: '30_Knowledge Library/Biohacking',
  home: '20_Domains (Life and Work)/Personal/Home',
  personal: '20_Domains (Life and Work)/Personal'
};

const area = r.area || 'personal';
const folder = AREA_FOLDER_MAP[area] || AREA_FOLDER_MAP.personal;
const slug = (r.title || 'article').toLowerCase().replace(/[^a-z0-9]+/g, '-').substring(0, 50);

const TZ = 'America/Chicago';
const now = new Date();
const fmt = (opts) => new Intl.DateTimeFormat('en-US', { timeZone: TZ, ...opts });
const y = parseInt(fmt({ year: 'numeric' }).format(now));
const m = fmt({ month: '2-digit' }).format(now);
const d = fmt({ day: '2-digit' }).format(now);
const dateStr = `${y}-${m}-${d}`;

let noteContent = `---\ntype: article-note\nsource_url: ${input.url || ''}\ndate_captured: ${dateStr}\narea: ${area}\nneedle_mover: ${r.needle_mover || false}\n---\n\n# ${r.title || 'Untitled Article'}\n\n## Summary\n${r.summary || 'No summary available.'}\n\n## Key Takeaways\n`;

if (r.key_takeaways && r.key_takeaways.length > 0) {
  r.key_takeaways.forEach(t => { noteContent += `- ${t}\n`; });
} else {
  noteContent += '- No takeaways extracted.\n';
}

// Action items as inline tasks
if (r.action_items && r.action_items.length > 0) {
  noteContent += '\n## Action Items\n';
  r.action_items.forEach(a => {
    const due = a.due ? ` [due:: ${a.due}]` : '';
    noteContent += `- [ ] ${a.task} [area:: ${a.area || area}] [priority:: ${a.priority || 'B'}]${due}\n`;
  });
}

return [{ json: {
  bucket: BUCKET,
  fileKey: `${PREFIX}/${folder}/${dateStr}-${slug}.md`,
  content: noteContent,
  actionItems: r.action_items || [],
  title: r.title
} }];
```

- [ ] **Step 2: Validate JSON**

```bash
python -c "import json; json.load(open('workflows/n8n/article-processor.json')); print('Valid JSON')"
```

- [ ] **Step 3: Commit**

```bash
git add workflows/n8n/article-processor.json
git commit -m "feat: create article processor workflow with AI summarization"
```

---

## Task 8: Update Setup Script

**Files:**
- Modify: `scripts/setup-n8n.sh`

- [ ] **Step 1: Add Groq and Gemini credential creation**

Add after the existing SMTP credential creation section:

```bash
# --- Groq API Credential ---
echo "Creating Groq API credential..."
GROQ_CRED_PAYLOAD=$(cat <<ENDJSON
{
  "name": "Groq API",
  "type": "httpHeaderAuth",
  "data": {
    "name": "Authorization",
    "value": "Bearer ${GROQ_API_KEY}"
  }
}
ENDJSON
)

GROQ_CRED_ID=$(curl -s -X POST "${N8N_HOST}/api/v1/credentials" \
  -H "X-N8N-API-KEY: ${N8N_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "${GROQ_CRED_PAYLOAD}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")

echo "Groq credential ID: ${GROQ_CRED_ID}"

# --- Gemini API Credential ---
echo "Creating Gemini API credential..."
GEMINI_CRED_PAYLOAD=$(cat <<ENDJSON
{
  "name": "Gemini API",
  "type": "httpHeaderAuth",
  "data": {
    "name": "x-goog-api-key",
    "value": "${GEMINI_API_KEY}"
  }
}
ENDJSON
)

GEMINI_CRED_ID=$(curl -s -X POST "${N8N_HOST}/api/v1/credentials" \
  -H "X-N8N-API-KEY: ${N8N_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "${GEMINI_CRED_PAYLOAD}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")

echo "Gemini credential ID: ${GEMINI_CRED_ID}"
```

- [ ] **Step 2: Add credential ID replacement in workflow files**

Add sed commands to replace placeholder credential IDs in the workflow JSONs:

```bash
# Replace placeholder credential IDs in workflow files
echo "Updating credential IDs in workflow files..."
for wf in workflows/n8n/brain-dump-processor.json workflows/n8n/daily-note-creator.json workflows/n8n/overdue-task-alert.json workflows/n8n/weekly-digest.json workflows/n8n/article-processor.json; do
  if [ -f "$wf" ]; then
    sed -i "s/GROQ_CREDENTIAL_ID/${GROQ_CRED_ID}/g" "$wf"
    sed -i "s/GEMINI_CREDENTIAL_ID/${GEMINI_CRED_ID}/g" "$wf"
  fi
done
```

- [ ] **Step 3: Add article-processor.json to the import list**

In the workflow import loop, add `article-processor.json` to the list of files to import.

- [ ] **Step 4: Add env var validation for new keys**

Add to the validation section at the top of the script:

```bash
# Validate new API keys
if [ -z "$GROQ_API_KEY" ]; then
  echo "ERROR: GROQ_API_KEY not set. Get a free key at https://console.groq.com"
  exit 1
fi
if [ -z "$GEMINI_API_KEY" ]; then
  echo "WARNING: GEMINI_API_KEY not set. Gemini fallback will not work."
  echo "Get a free key at https://aistudio.google.com"
fi
```

- [ ] **Step 5: Commit**

```bash
git add scripts/setup-n8n.sh
git commit -m "feat: add Groq/Gemini credential setup and article-processor import to setup script"
```

---

## Task 9: Create articles-to-process.md Template

**Files:**
- Create: A note about creating this file in Obsidian vault via MinIO

This file must exist in the vault for the Article Processor to read it. Since we don't modify the vault directly (per CLAUDE.md), document the manual step.

- [ ] **Step 1: Add setup instruction to README**

Add a section to README.md:

```markdown
### Article Queue Setup

Create the article queue file in your Obsidian vault at `00_Inbox/articles-to-process.md`:

```markdown
---
type: article-queue
---

Paste article URLs here, one per line. Optional context after " — ":
https://example.com/article — why this is relevant
```

The Brain Dump Processor will also automatically route article URLs here.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add article queue setup instructions to README"
```

---

## Task 10: End-to-End Validation

- [ ] **Step 1: Validate all JSON files**

```bash
cd "Z:/MiniPC_Docker_Automation/Projects_Repos/ObsidianHomeOrchestrator/.claude/worktrees/amazing-heyrovsky"
for f in workflows/n8n/*.json; do
  echo -n "Validating $f... "
  python -c "import json; json.load(open('$f')); print('OK')"
done
```

Expected: All files print `OK`.

- [ ] **Step 2: Verify no broken credential references**

```bash
grep -r "GROQ_CREDENTIAL_ID\|GEMINI_CREDENTIAL_ID" workflows/n8n/
```

Expected: Matches in all workflow files that use Groq/Gemini. These are placeholders replaced at setup time by `setup-n8n.sh`.

- [ ] **Step 3: Verify consistent area/domain references**

```bash
grep -c "faith\|family\|business\|consulting\|work\|health\|home\|personal" workflows/n8n/brain-dump-processor.json
```

Expected: Multiple matches confirming all 8 domains are referenced.

- [ ] **Step 4: Final commit**

```bash
git add -A
git status
git commit -m "chore: final validation pass on all AI Brain workflow files"
```

---

## Post-Implementation: Manual Setup Steps

After all code changes are committed, Aaron needs to:

1. **Get API keys:**
   - Groq: https://console.groq.com → Create API Key (free)
   - Gemini: https://aistudio.google.com → Get API Key (free)

2. **Add to `.env` file:**
   ```bash
   GROQ_API_KEY=gsk_your_key_here
   GEMINI_API_KEY=AIzaSy_your_key_here
   ```

3. **Run setup script:**
   ```bash
   source .env && bash scripts/setup-n8n.sh
   ```

4. **Create article queue file** in Obsidian vault at `00_Inbox/articles-to-process.md`

5. **Test each workflow** manually in n8n UI:
   - Brain Dump: Add test content to a brain dump file → trigger manually → verify processed items
   - Daily Note: Trigger manually → verify briefing appears
   - Overdue Alert: Ensure some tasks are overdue → trigger → verify triage email
   - Weekly Digest: Trigger manually → verify strategic review email
   - Article Processor: Add a URL to articles-to-process.md → trigger → verify article note created

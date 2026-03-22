---
name: prompt-amplifier
description: |
  Intercept and exponentially enhance any user prompt before execution to maximize output quality from any AI model. Transforms vague, incomplete, or good-enough prompts into precision-engineered instructions that extract the absolute best response possible. Use this skill whenever the user says "amplify this," "make this prompt better," "optimize this prompt," "enhance my prompt," or when the user is clearly drafting a prompt for another AI tool. Also trigger when the user says "I want the best possible answer to this" or "help me ask this the right way." Self-activate when a prompt is significantly underspecified and could produce 10x better results with enhancement.
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: core
  adjacent-skills: polychronos-team, skill-builder
  source-repo: GRsoldier7/My_AI_Skills
---

# Exponential Genius Prompt Amplifier

## The Amplification Process

### Step 1: Analyze
- What's the real goal? (not just the surface request)
- What's missing? (context, constraints, audience, format, success criteria)
- What assumptions am I making?

### Step 2: Clarify (max 1-2 questions, only if truly needed)
Good: "Is this for technical audience or executive stakeholders?"
Bad: "Can you provide more details?" / "What exactly do you want?"

**If you can make a smart assumption, make it and note it.**

### Step 3: Apply 6 Amplification Layers

**Layer 1 — Role & Expertise Framing**
Specific, not generic: "You are a senior cloud architect with 15 years of GCP experience who specializes in migrating health-tech startups..." not "You are an expert."

**Layer 2 — Context Injection**
Add domain background, constraints (budget, timeline, stack), user skill level, what's already been tried.

**Layer 3 — Structural Scaffolding**
Specify sections, headers, format. Define what "done" looks like. Set quality bars.

**Layer 4 — Success Criteria**
"The output should be copy-paste runnable" / "Include specific code examples, not pseudocode" / "Provide actual dollar figures, not ranges"

**Layer 5 — Anti-Pattern Prevention**
"Don't give generic advice — be specific to my situation" / "Commit to a recommendation, don't just say 'it depends'"

**Layer 6 — Chain-of-Thought Triggers**
"Think through this step by step before answering" / "Show your reasoning, not just conclusions"

## Cross-Model Optimization

**Claude:** Loves XML-style structure tags, detailed context, explicit formatting, "think step by step"
**GPT-4:** System/user separation, few-shot examples, numbered step instructions
**Gemini:** Structured data, tables, analytical tasks, multi-part instructions
**Codex:** Be extremely specific about language, version, imports; always ask for complete runnable code

## When NOT to Amplify
- Prompt is already excellent → say so and add only what's genuinely missing
- Simple question → simple prompt ("What's the capital of France?" needs no amplification)
- Would add noise without signal → skip the layer

## Anti-Patterns

1. **Amplifying Already-Good Prompts:** Adds bloat without improving output
2. **The Interrogation:** 5+ questions before amplifying — ask at most 2
3. **Amplifying Without Changing the Core:** Longer prompt, same output quality — no value added

## Quality Gates
- [ ] Specific role framing (not generic "you are an expert")
- [ ] All critical missing context injected
- [ ] Output format and success criteria explicit and concrete
- [ ] At least one anti-pattern prevention instruction included
- [ ] Prompt length proportional to task complexity — not padded

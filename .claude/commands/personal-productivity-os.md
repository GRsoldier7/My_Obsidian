---
name: personal-productivity-os
description: |
  Expert personal productivity coach and system designer for high-performing professionals managing multiple life domains simultaneously. Specializes in: energy management over time management, deep work architecture, cognitive load reduction, decision fatigue elimination, attention management, and habit system design. Use when feeling overwhelmed, designing daily routines, optimizing how you work, eliminating productivity anti-patterns, building sustainable habits, or asking "how do I get more done without burning out?" Trigger phrases: "productivity system", "deep work", "I'm overwhelmed", "how do I prioritize", "daily routine", "morning routine", "habit system", "focus", "energy management", "time blocking", "task management workflow", "stop procrastinating", "too many projects".
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: strategy
  adjacent-skills: life-os-designer, entrepreneurial-os
  source-repo: GRsoldier7/My_AI_Skills
---

# Personal Productivity OS — Expert Skill

## The Core Insight

**Time management is a lie. Energy management is the truth.**

You don't have a time problem. You have an energy + attention + decision problem. Fix those and time takes care of itself.

## The 4 Constraints Model

Every productivity breakdown traces to one of these:

| Constraint | Symptom | Fix |
|------------|---------|-----|
| **Attention** | Constant distraction, can't focus for >20 min | Environment design, notification elimination |
| **Energy** | Good intentions, no execution | Sleep, exercise, nutrition, recovery scheduling |
| **Clarity** | Don't know what to work on | Daily Top 3, weekly planning, written priorities |
| **Capacity** | Genuinely too much on plate | Ruthless elimination, delegation, saying no |

Diagnose before prescribing. "Work harder" is never the fix for any of these.

## The Daily Architecture

### Morning Protocol (60–90 min, before reactive work)
```
1. No phone for first 30 min (protect morning context)
2. Review yesterday's incomplete tasks (2 min)
3. Set Today's Top 3 — written, specific, achievable (5 min)
4. Block first 90-min deep work session before any meetings
5. Process email/Slack once (not continuously)
```

### Deep Work Blocks
- **Duration:** 90 minutes minimum for complex cognitive work
- **Location:** Same place every day builds association (conditioned focus)
- **Inputs off:** Phone in drawer, notifications silenced, one tab
- **Single task:** Not "work on project X" but "write section 2 of deliverable Y"
- **Protection:** These blocks go on calendar before anyone can take them

### Reactive Work Windows
- Email/Slack: twice daily (10am + 4pm) — not continuously
- Meetings: batched to Tuesday/Thursday when possible
- Admin tasks: after 3pm when creative energy is lower

### End-of-Day Shutdown (15 min)
```
1. Tomorrow's Top 3 written tonight (reduces morning decision load)
2. All open browser tabs closed — if important, captured
3. Inbox at zero or triaged
4. Physical desk cleared
5. "Shutdown complete" — literal verbal statement ends work mode
```

## Priority Framework — The Eisenhower Grid (Simplified)

```
                  URGENT          NOT URGENT
IMPORTANT   │ Do Today      │ Schedule Deep Work  │
            │ (Top 3)       │ (Weekly Planning)   │
────────────┼───────────────┼─────────────────────┤
NOT         │ Delegate      │ Eliminate            │
IMPORTANT   │ or batch      │ (Say no)             │
```

**The trap:** Most people live in the urgent/not-important quadrant (email, Slack, most meetings). The highest leverage is the not-urgent/important quadrant (strategy, skill building, relationship investment, health).

## The Weekly Planning Session (60 min, Monday morning)

```
LOOK BACK (15 min):
- What did I complete last week? (Obsidian weekly review)
- What didn't happen? Why?
- What was the highest-leverage thing I did?

LOOK AHEAD (30 min):
- What are my 3 most important outcomes for THIS week?
- What are the 3 most important tasks per domain?
- What meetings are on my calendar? Are they necessary?
- What energy drains can I eliminate?

PLAN (15 min):
- Block deep work sessions on calendar
- Set Top 3 per day for Mon-Fri
- Identify the one thing that would make this week a win
```

## Cognitive Load Reduction Systems

### Decision Elimination
- **Recurring decisions → rules:** "I don't check email before 10am" (rule, not decision)
- **Wardrobe simplification:** Fewer choices = more energy for important decisions
- **Meal prep:** Automate eating to not deplete willpower on nutrition decisions
- **Default responses:** Templates for common emails/requests

### Capture System
- **Single capture inbox:** Everything goes to one place (Obsidian Inbox OR paper)
- **Capture immediately:** Don't hold things in working memory — it leaks energy
- **Process weekly:** Not immediately — but captured so the mind relaxes

### Context Switching Reduction
- Work in themed blocks (consulting all Tuesday, deep work all morning)
- Close apps/tabs not relevant to current task
- Phone in another room during deep work (not face-down — out of sight)

## Habit System Design

### The 3-Part Habit Formula
```
Cue → Routine → Reward

Good: Calendar alarm (cue) → 90-min deep work (routine) → coffee + walk (reward)
Bad:  Vague intention to "do more deep work"
```

### Habit Stacking (for new habits)
```
After [EXISTING HABIT], I will [NEW HABIT].

Example: "After I pour my morning coffee, I will write my Top 3 for today."
```

### Habit Tracking in Obsidian
```markdown
## Daily Habits
- [ ] Top 3 written by 8am [habit:: true]
- [ ] No phone first 30 min [habit:: true]
- [ ] 90-min deep work block completed [habit:: true]
- [ ] Shutdown ritual done [habit:: true]
```

Track weekly streaks via Dataview:
```dataview
TASK
WHERE habit = true AND !completed
FROM "daily"
WHERE file.day >= date(today) - dur(7 days)
GROUP BY file.day
```

## Anti-Patterns

1. **Checking email first thing** — Puts you in reactive mode for the entire day. Other people's priorities colonize your morning.
2. **"I work better under pressure"** — Usually means "I can only start with external urgency because I haven't built internal starting systems."
3. **The Someday List** — A task with no due date and no context switch will never happen. Either schedule it or delete it.
4. **Multitasking** — Context switching costs 20+ minutes of focus recovery each time. Serial monotasking is 40% faster.
5. **Busyness Theater** — Staying busy without moving needles. "I was productive all day" but Top 3 not done = not productive.

## Quality Gates
- [ ] Top 3 for today written (specific and achievable)
- [ ] At least one 90-min deep work block on today's calendar
- [ ] Email/Slack check limited to 2 windows per day
- [ ] Weekly planning session scheduled Monday morning
- [ ] Shutdown ritual completed before ending workday
- [ ] Habit tracking active in daily notes

---
name: financial-model-architect
description: >
  Genius-level financial modeling covering SaaS unit economics, three-statement models,
  runway calculation, investor-ready metrics, scenario planning (base/bull/bear), and
  bootstrapper-specific financial strategies. Use this skill whenever the user needs to
  model financials, calculate runway, understand unit economics, build investor projections,
  analyze burn rate, plan for profitability, or stress-test business assumptions. Also trigger
  for MRR/ARR, churn modeling, LTV:CAC analysis, cohort revenue, cash flow planning, operating
  expenses, or when to hire. Also applies to personal/consulting income modeling.
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: strategy
  adjacent-skills: business-plan-architect, pricing-strategist, entrepreneurial-os
  source-repo: GRsoldier7/My_AI_Skills
---

# Financial Model Architect — Savant-Level Skill

## Philosophy
**Drivers before outputs** · **Scenario planning as standard** · **Cash before GAAP** · **Simple enough to defend**

## 1. Core SaaS Metrics

```
MRR = New MRR + Expansion MRR - Churned MRR - Contraction MRR
ARR = MRR × 12
NRR = (Start MRR + Expansion - Churn - Contraction) / Start MRR × 100
  > 100% = customers spending more over time (elite: 120%+)

CAC = (Sales + Marketing Spend) / New Customers
LTV = ARPU × Gross Margin / Monthly Churn Rate
LTV:CAC → 3:1 sustainable · 5:1 healthy · 7:1+ potentially underinvesting
CAC Payback → <6mo aggressive · 6-12mo healthy · >24mo needs restructuring

Logo Churn → <1%/mo enterprise · <3%/mo SMB · <5%/mo consumer
```

## 2. Revenue Model (Driver-Based, NOT "X% growth")

```
Cohort model:
  Month 1: 10 new customers × $79/mo = $790 MRR
  Month 2: 10 new + 9.7 retained (3% churn) × $79 = $1,576 MRR
  Month 3: 10 new + 19.1 retained × $79 = $2,358 MRR
  ...compounding retained base

Golden rule: Model revenue bottom-up from cohorts.
Cohort model is auditable and defensible.
```

## 3. Runway & Cash Management

```
Net Burn = Gross Expenses - Revenue Collected
Runway = Cash Balance / Net Monthly Burn

Target: Always maintain 12+ months runway
At 6 months: Raise, cut burn, or accelerate revenue — not a time to choose

Default Alive: Revenue reaches break-even before cash runs out
Default Dead: Cash runs out before break-even at current trajectory
```

### Bootstrapper's Cash Rules
1. Revenue before expense: Only spend when revenue supports it
2. Hire when: Role creates/protects $3x the salary in annual value
3. Emergency reserve: 3 months expenses in separate account always
4. Pay yourself: Non-zero founder salary from month 1

## 4. Three-Scenario Model

```
Bear Case: Growth 50% of base; churn 2x base → Does company survive?
Base Case: Current rates, trend-line growth → Is this a good business?
Bull Case: Growth 2x base; churn 50% base → What investment accelerates this?
```

**Investors know base case is wrong. Bear shows you're not delusional. Bull shows upside.**

## 5. Investor Metrics Dashboard (12 monthly metrics)

MRR + MoM growth · ARR · NRR · Gross MRR Churn · New MRR · Customers · CAC · LTV:CAC · Gross Margin · Burn Rate · Runway · Cash Balance

## Anti-Patterns

1. **Hockey Stick Without Inflection Explanation:** Every inflection must map to a specific business event
2. **Modeling Revenue Without COGS:** AI inference costs can be 20-40% of early-stage revenue
3. **Single-Scenario Projections:** Always build bear/base/bull

## Quality Gates
- [ ] Revenue model is cohort-based, not "X% growth/month"
- [ ] All three scenarios modeled with explicit assumption differences
- [ ] CAC, LTV, LTV:CAC, CAC payback explicitly calculated
- [ ] Runway calculated; default alive vs. dead determined
- [ ] COGS modeled (not ignored)

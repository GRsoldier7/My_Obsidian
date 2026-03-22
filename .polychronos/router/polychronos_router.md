# Polychronos Router & Orchestrator Specification

This document defines the orchestration layer for the Polychronos framework. It routes tasks to the appropriate agents based on complexity and enforces quality gates, contract compliance and security.

## 1. Complexity Tiers

The router classifies incoming tasks into one of four tiers:

| Tier | Description | Typical Outputs | Agents Involved |
| --- | --- | --- | --- |
| **T0** | Trivial answers requiring no artefact | Simple response | Appropriate knowledge agent (e.g., Loremaster) |
| **T1** | Small, low-risk tasks | Minor patches, documentation updates | Project Manager -> single specialist agent -> QA (light check) -> DevOps (if deployment) |
| **T2** | Multi-step builds with moderate risk | New service/module with tests and pipeline | PM -> Visionary Planner/Product Strategist -> Architects (Savant/Nexus) -> Front/Back End/Lead Engineer -> QA & Diagnostic -> DevOps -> Sentinel |
| **T3** | High-risk or production-impacting projects | Production-ready system with compliance, observability and documentation | Full guild: PM, Visionary, Strategist, Savant, Front, Back, Nexus, Lead Engineer, DevOps, QA Director, Diagnostician, Sentinel, Loremaster |

## 2. Standard Workflow

1. **Intake** — PM receives the request, classifies it and clarifies requirements.
2. **Plan** — Visionary Planner/Product Strategist define goals, metrics and backlog; PM schedules phases.
3. **Architect** — Savant Architect drafts the high-level design; domain architects refine; Sentinel reviews security.
4. **Execute** — Lead Engineer coordinates implementation; DevOps sets up pipelines; code and documentation are created.
5. **Verify** — QA Director executes tests; Diagnostician investigates issues; Sentinel runs security scans.
6. **Ship** — DevOps deploys; QA and Sentinel sign off; PM communicates status.
7. **Retrospective** — PM facilitates a retrospective; lessons are captured and documentation updated.

## 3. Agent Selection Logic

- **Minimal involvement**: route tasks to only the necessary agents. For example, a documentation update uses the Loremaster and PM only.
- **Security & quality**: involve Sentinel and QA Director for T2/T3 tasks touching production or sensitive data.
- **Nexus optional**: include the Nexus Architect only for AI/ML or advanced reasoning tasks.
- **Diagnostician reactive**: invoke the Diagnostician when a defect or unexpected behaviour is encountered.

## 4. Contract Enforcement

The router ensures each agent adheres to its contract:

- Validates that required inputs are present; requests clarifications via the PM if not.
- Ensures outputs follow the defined handoff formats and satisfy quality bars.
- Enforces security and compliance rules (no secret leakage, proper encryption).
- Requests corrections when outputs are non-conformant.

## 5. Loop Prevention & Escalation

- Limit each phase to two iterations. If acceptance criteria are still unmet, the PM escalates to stakeholders.
- If the Diagnostician cannot identify a root cause after two attempts, involve the Savant Architect and external experts.
- Maintain short context handoffs in `gemini.md` after each action to ensure resumable state across sessions.

## 6. Extensibility

The router is tool-agnostic and future-proof. New agents can be added by defining their contract and updating selection logic. Version the router and agent contracts, and write tests to ensure routing rules work when new capabilities are introduced.

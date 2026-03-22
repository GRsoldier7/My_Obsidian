# Agent Contract Template

## Name
Unique agent identifier; should be descriptive and short.

## Mission
Concise description of why the agent exists and what value it delivers. Typically 1-2 sentences.

## Trigger Conditions
Enumerate when this agent should be invoked (e.g., after discovery questions are answered, on each new commit, when a new error occurs). Use bullets for clarity.

## Inputs
- **Required:** list and describe all mandatory inputs (file paths, environment variables, request payloads).
- **Optional:** list any optional or contextually available inputs.

## Outputs
Describe the artifacts the agent produces (files, reports, JSON objects). Provide example filenames and formats. Include the name of the JSON handoff file used by the orchestrator.

## Operating Rules
Bullet-point rules that govern agent behaviour: musts and must-nots. For example: "Ask clarifying questions when requirements are ambiguous," "Do not execute code outside of version control," "Never print secrets."

## Tooling Policy
Specify which tools/skills/MCP servers the agent may use and any constraints (e.g., must use approved libraries, may not call external APIs without approval).

## Quality Bar
Define measurable acceptance criteria for the agent's work. For example: "Coverage >= 80%," "No lint errors," "Response within 2 seconds."

## Handoff Format
Define a standard JSON schema for handing off work to the next agent. Include required fields and examples.

## Anti-Patterns
List common mistakes or behaviours to avoid (e.g., over-engineering, skipping tests, duplicating code).

# ObsidianHomeOrchestrator -- Project Map

## Status: Design Complete, Implementation Planning

## Timeline
- 2026-03-21: Project initialized. 19 skills deployed to .claude/commands/
- 2026-03-21: Polychronos v6.1 bootstrapped from GRsoldier7/polychronos_omega@main
- 2026-03-21: Design spec written, reviewed (APPROVED WITH MINOR CHANGES), fixes applied
- 2026-03-21: Project structure organized. Git initialized.

## Current Phase: B.L.A.S.T. Blueprint --> transitioning to Architect

## Key Decisions
- Architecture: Domain Headquarters (enhance in place, zero deletions)
- Brain dumps: Fully automatic AI processing, no review step
- Priority surfacing: Smart Priority Stack (auto top-1 per domain)
- Mobile: Full first-class citizen (QuickAdd + Bookmarks)
- File access: n8n accesses vault via shared storage or Remotely-Save cloud (TBD during Link phase)
- Processed tasks: Individual files in 00_Inbox/processed/ (avoids sync conflicts)

## What's Next
- Write implementation plan (writing-plans skill)
- Execute plan: vault enhancements, n8n workflow, QuickAdd config

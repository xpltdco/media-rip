# S04: UX Review + Live Tweaks

**Goal:** Walk through the entire app as a user, identify UX issues, and fix them in real time. This is a guided review session — the user drives the walkthrough and calls out issues, the agent fixes them immediately.
**Demo:** All issues identified during the walkthrough are resolved. App feels polished for a v1.0 release.

## Approach

1. Start backend + frontend dev servers
2. Walk through every user flow in the browser at desktop and mobile viewports
3. User identifies issues — agent fixes each one before moving on
4. Run tests after all fixes to confirm no regressions
5. Commit

## Verification

- `cd frontend && npx vitest run` — all tests pass
- `cd backend && source .venv/Scripts/activate && python -m pytest tests/ -q -m "not integration"` — no regressions
- Browser: all flows verified during the walkthrough

## Tasks

- [ ] **T01: Live UX review and fixes** `est:variable`
  - Iterative — tasks emerge from the walkthrough

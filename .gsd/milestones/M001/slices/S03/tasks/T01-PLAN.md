---
estimated_steps: 5
estimated_files: 10
---

# T01: Scaffold Vue 3 + Vite + TypeScript + Pinia project

**Slice:** S03 — Frontend Core
**Milestone:** M001

## Description

Create the frontend project from scratch with Vue 3, TypeScript, Vite, and Pinia. Configure the Vite dev proxy so `/api` routes hit the FastAPI backend. Set up vitest for testing. Define TypeScript interfaces matching the backend models. Establish a minimal dark CSS baseline.

## Steps

1. Create `frontend/` directory in the worktree
2. Initialize with `npm create vite@latest` (vue-ts template) or manually scaffold
3. Install runtime deps: `vue`, `pinia`
4. Install dev deps: `vitest`, `vue-tsc`, `@vitejs/plugin-vue`, `typescript`
5. Configure `vite.config.ts` with proxy `/api` → `http://localhost:8000`
6. Set up `tsconfig.json` and `tsconfig.node.json`
7. Create `src/api/types.ts` with TypeScript interfaces
8. Create minimal `src/assets/base.css` with CSS custom properties
9. Update `App.vue` and `main.ts` with Pinia setup
10. Verify: `npm run build`, `npx vue-tsc --noEmit`, `npx vitest run`

## Verification

- `cd frontend && npm run build` — zero errors
- `cd frontend && npx vue-tsc --noEmit` — zero type errors
- `cd frontend && npx vitest run` — runs (0 tests ok, framework functional)

# S03: Frontend Core

**Goal:** Ship a functional Vue 3 SPA that lets a user paste a URL, pick format/quality from live extraction, submit a download, watch real-time SSE progress, and manage a download queue — with a responsive layout that works on both desktop (≥768px) and mobile (375px).
**Demo:** Open the browser → paste a YouTube URL → format picker populates → pick 720p → submit → progress bar fills via SSE → status changes to completed. Open a second tab → submit a different URL → both tabs show only their own session's downloads. Resize to 375px → layout shifts to mobile card view with bottom tabs.

## Must-Haves

- Vue 3 + TypeScript + Vite + Pinia project scaffolded and building cleanly
- API client with TypeScript types matching backend Job, ProgressEvent, FormatInfo models
- SSE composable managing EventSource lifecycle with reconnect and store dispatch
- Downloads Pinia store: reactive jobs map, SSE-driven updates, CRUD actions
- Config Pinia store: loads public config on app init
- URL input component with format picker populated from `GET /api/formats?url=`
- Download queue component with progress bars, status badges, speed/ETA, cancel buttons
- Responsive layout: desktop (header + main content area) and mobile (bottom tabs + card list)
- 44px minimum touch targets on mobile
- `npm run build` produces zero errors
- `vue-tsc --noEmit` passes with zero type errors
- Vitest tests for stores and SSE composable

## Proof Level

- This slice proves: integration (frontend SPA consuming real backend SSE stream, session cookie isolation across tabs)
- Real runtime required: yes (SSE streaming, format extraction, cookie handling)
- Human/UAT required: yes (visual layout verification at desktop + mobile breakpoints)

## Verification

- `cd frontend && npm run build` — zero errors, dist/ produced
- `cd frontend && npx vue-tsc --noEmit` — zero type errors
- `cd frontend && npx vitest run` — all store and composable tests pass
- Browser verification: open SPA against running backend, complete a download flow with live progress
- Browser verification: 375px viewport shows mobile layout with bottom tabs and card list
- Session isolation: two browser tabs with different cookies see different job lists

## Observability / Diagnostics

- Runtime signals: console.log for SSE connect/disconnect/reconnect events during development; downloads store exposes `connectionStatus` ref (connected/disconnected/reconnecting)
- Inspection surfaces: Vue devtools shows Pinia store state (jobs, config); browser Network tab shows SSE stream; browser Application tab shows mrip_session cookie
- Failure visibility: SSE composable logs reconnect attempts with count; failed API calls surface error messages in the UI (toast or inline)
- Redaction constraints: none (session UUIDs are opaque, no secrets in frontend)

## Integration Closure

- Upstream surfaces consumed: `GET/POST/DELETE /api/downloads`, `GET /api/formats?url=`, `GET /api/events` (SSE), `GET /api/config/public`, `GET /api/health`, session cookie from SessionMiddleware
- New wiring introduced in this slice: Vite dev proxy to backend, Vue app mounting, Pinia store initialization, SSE EventSource connection
- What remains before the milestone is truly usable end-to-end: S04 (admin panel), S05 (theme system with CSS variable contract), S06 (Docker + CI/CD)

## Tasks

- [x] **T01: Scaffold Vue 3 + Vite + TypeScript + Pinia project** `est:30m`
  - Why: Foundation for all frontend work. Must build cleanly before any components can be written.
  - Files: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/index.html`
  - Do: Create Vue 3 + TS project with Vite. Install pinia and vue-router (for future S04 use). Configure vite.config.ts with proxy: `/api` → `http://localhost:8000`. Set up minimal App.vue with Pinia. Add vitest config. Add a minimal dark CSS baseline using custom properties (--color-bg, --color-text, --color-accent, --color-surface) that S05 will expand. No Tailwind. Include a `src/api/types.ts` with TypeScript interfaces matching backend models (Job, JobStatus, ProgressEvent, FormatInfo, PublicConfig).
  - Verify: `cd frontend && npm run build` succeeds, `npx vue-tsc --noEmit` passes
  - Done when: `npm run dev` serves the app at localhost:5173, build produces dist/, type-check passes, vitest runs (0 tests is fine)

- [x] **T02: API client, Pinia stores, and SSE composable** `est:1h`
  - Why: The data layer that every component depends on. SSE is the highest-risk integration point — if events don't flow from backend to store, nothing works.
  - Files: `frontend/src/api/client.ts`, `frontend/src/stores/downloads.ts`, `frontend/src/stores/config.ts`, `frontend/src/composables/useSSE.ts`, `frontend/src/tests/stores/downloads.test.ts`, `frontend/src/tests/composables/useSSE.test.ts`
  - Do: Build fetch-based API client (`api/client.ts`) with GET/POST/DELETE helpers, base URL from import.meta.env or proxy. Build downloads store: `jobs` as reactive Map<string, Job>, actions for `fetchJobs()`, `submitDownload(url, formatId?, quality?)`, `cancelDownload(id)`, internal `_handleInit(jobs)`, `_handleJobUpdate(event)`, `_handleJobRemoved(jobId)`. Build config store: `config` ref, `loadConfig()` action calling GET /api/config/public. Build `useSSE()` composable: creates EventSource to /api/events, parses SSE events, dispatches to downloads store, handles reconnect with exponential backoff (1s, 2s, 4s, max 30s), exposes `connectionStatus` ref. Write vitest tests: downloads store CRUD operations (mock fetch), SSE composable event parsing and store dispatch (mock EventSource).
  - Verify: `cd frontend && npx vitest run` — store and composable tests pass
  - Done when: Downloads store reactively updates from SSE events, config store loads public config, SSE composable reconnects on disconnect, all tests pass

- [x] **T03: URL input + format picker components** `est:45m`
  - Why: The primary user interaction — pasting a URL and selecting quality. Format extraction is async (3-10s) and needs loading UX.
  - Files: `frontend/src/components/UrlInput.vue`, `frontend/src/components/FormatPicker.vue`, `frontend/src/App.vue`
  - Do: UrlInput.vue: text input with paste handler, Submit button, calls `GET /api/formats?url=` on submit (or on debounced input). Shows loading spinner during extraction. On format response, shows FormatPicker. FormatPicker.vue: dropdown/list showing resolution, codec, ext, filesize for each format. "Best available" as default option. Submit button calls downloads store `submitDownload()`. Handle edge cases: no formats returned (show "Best available" only), extraction error (show error message), empty URL (disable submit). Optional "More options" expandable area with output_template override (R025).
  - Verify: Visual verification in browser — paste URL, see format picker populate, submit download
  - Done when: User can paste a URL, see formats load, select one, and submit. Error states handled gracefully.

- [x] **T04: Download queue + progress display** `est:45m`
  - Why: The core feedback loop — users need to see their downloads progressing in real-time.
  - Files: `frontend/src/components/DownloadQueue.vue`, `frontend/src/components/DownloadItem.vue`, `frontend/src/components/ProgressBar.vue`, `frontend/src/App.vue`
  - Do: DownloadQueue.vue: renders list of DownloadItem components from downloads store jobs. Status filter tabs (All / Active / Completed / Failed). Empty state message when no downloads. DownloadItem.vue: shows URL/filename, status badge (queued=gray, downloading=blue, completed=green, failed=red), ProgressBar with percent + speed + ETA, cancel button (calls store.cancelDownload). ProgressBar.vue: animated CSS bar, displays percent text. Wire SSE events: job_update → progress bar updates in real-time, job_removed → item disappears. Handle status transitions: queued → extracting → downloading → completed/failed.
  - Verify: Visual verification — submit a download, watch progress bar fill from SSE events, see status change to completed
  - Done when: Queue shows all session jobs with live progress, cancel works, status badges reflect current state, completed/failed jobs show final state

- [x] **T05: Responsive layout + mobile view** `est:45m`
  - Why: R013 requires mobile-responsive layout. >50% of self-hoster interactions happen on phone/tablet.
  - Files: `frontend/src/components/AppLayout.vue`, `frontend/src/components/AppHeader.vue`, `frontend/src/App.vue`, `frontend/src/assets/base.css`
  - Do: AppLayout.vue: responsive shell. Desktop (≥768px): header bar with title, main content area with URL input at top, queue below. Mobile (<768px): bottom tab bar (Submit / Queue tabs), URL input fills width, queue uses card layout instead of table rows. AppHeader.vue: app title/logo, connection status indicator. Base CSS: set up CSS custom properties for colors, spacing, typography that S05 will formalize into the theme contract. Use system font stack for now (S05 brings JetBrains Mono). Ensure all interactive elements have minimum 44px touch targets on mobile. Test at 375px (iPhone SE) and 768px breakpoint.
  - Verify: Browser verification at 375px and 1280px viewports. All interactive elements ≥44px on mobile.
  - Done when: Desktop layout shows header + content. Mobile layout shows bottom tabs + card view. 375px viewport is usable. Touch targets meet 44px minimum.

## Files Likely Touched

- `frontend/` — entire new directory
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/index.html`
- `frontend/src/main.ts`
- `frontend/src/App.vue`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/stores/downloads.ts`
- `frontend/src/stores/config.ts`
- `frontend/src/composables/useSSE.ts`
- `frontend/src/components/UrlInput.vue`
- `frontend/src/components/FormatPicker.vue`
- `frontend/src/components/DownloadQueue.vue`
- `frontend/src/components/DownloadItem.vue`
- `frontend/src/components/ProgressBar.vue`
- `frontend/src/components/AppLayout.vue`
- `frontend/src/components/AppHeader.vue`
- `frontend/src/assets/base.css`

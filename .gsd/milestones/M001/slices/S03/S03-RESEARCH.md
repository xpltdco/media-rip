# S03: Frontend Core — Research

## Scope

Full Vue 3 SPA consuming the S01/S02 backend: URL submission → format selection → real-time progress via SSE → completed downloads queue. Mobile-first responsive layout. No theming system yet (S05) — use simple CSS custom properties with a minimal dark style.

## API Surface to Consume

From S01:
- `POST /api/downloads` — submit URL + optional format_id/quality/output_template
- `GET /api/downloads` — list all jobs for current session
- `DELETE /api/downloads/{id}` — cancel/remove a job
- `GET /api/formats?url=` — live yt-dlp format extraction

From S02:
- `GET /api/events` — SSE stream (init, job_update, job_removed, ping)
- `GET /api/health` — health check
- `GET /api/config/public` — session_mode, default_theme, purge_enabled, max_concurrent_downloads
- Session cookie auto-set by middleware (no auth header needed)

## SSE Event Contract

```
event: init
data: {"jobs": [<Job>, ...]}

event: job_update
data: {"job_id": "...", "status": "...", "percent": ..., "speed": "...", "eta": "...", ...}

event: job_removed
data: {"job_id": "..."}

event: ping
data: ""
```

## Frontend Architecture

### Project Structure
```
frontend/
  index.html
  vite.config.ts
  tsconfig.json
  tsconfig.node.json
  package.json
  src/
    main.ts
    App.vue
    api/
      client.ts          — fetch wrapper with base URL
      types.ts           — TypeScript types matching backend models
    stores/
      downloads.ts       — Pinia store: job state, SSE connection, CRUD actions
      config.ts          — Pinia store: public config from /api/config/public
    components/
      UrlInput.vue       — URL paste + submit + format selection
      FormatPicker.vue   — Format/quality dropdown populated from /api/formats
      DownloadQueue.vue  — Job list with progress bars, status badges, cancel
      DownloadItem.vue   — Single job row (desktop: table row, mobile: card)
      ProgressBar.vue    — Animated progress bar component
      AppHeader.vue      — Header with logo/title
      AppLayout.vue      — Responsive layout shell (header + main + mobile nav)
    composables/
      useSSE.ts          — EventSource connection management + reconnect
```

### Key Decisions

1. **No router needed for S03** — single-page app with URL input + queue. Router can be added in S04 for admin panel.

2. **SSE in a composable, not the store** — `useSSE()` composable manages EventSource lifecycle, reconnect logic, and dispatches events to the downloads store. Store stays pure state.

3. **Fetch, not axios** — per stack research. Native fetch + a thin wrapper for base URL and error handling.

4. **CSS custom properties for styling** — establish a minimal set that S05 will expand. No Tailwind (per original stack decisions). No component library — hand-rolled.

5. **Vite dev proxy** — proxy `/api` to `http://localhost:8000` during development so CORS is not an issue.

6. **Playlist support deferred within S03** — The R006 parent/child playlist model requires backend changes (parent_job_id field, playlist extraction creating child jobs). The frontend can show the data once it exists, but the backend work is not in S02. We'll build the DownloadItem component to support a `children` array, but full playlist support comes when the backend supports it (likely S04 or a dedicated slice). For now, individual URL downloads are the focus.

## Task Breakdown (Risk-Ordered)

### T01: Scaffold Vue 3 + Vite + TypeScript + Pinia project
- `npm create vite@latest frontend -- --template vue-ts`
- Install pinia
- Configure vite proxy to backend
- Verify `npm run dev` serves a blank page
- Verify `npm run build` produces dist/
- Risk: LOW — standard scaffold

### T02: API client, TypeScript types, and Pinia stores  
- Type definitions matching backend Job, ProgressEvent, FormatInfo, PublicConfig
- Fetch-based API client with error handling
- Downloads store: jobs map, addJob, updateJob, removeJob, fetchJobs actions
- Config store: load public config on app init
- SSE composable: EventSource to /api/events, reconnect on close, dispatch to store
- Risk: MEDIUM — SSE reconnect logic needs careful handling

### T03: URL input + format picker components
- UrlInput.vue: paste/type URL, submit button, loading state during format extraction
- FormatPicker.vue: populated from /api/formats response, shows resolution/codec/ext/filesize
- Wire to downloads store: submit → POST /api/downloads
- Risk: MEDIUM — format extraction can be slow (3-10s), needs good loading UX

### T04: Download queue + progress display
- DownloadQueue.vue: list of DownloadItem components, filter by status
- DownloadItem.vue: status badge, progress bar, speed/ETA, cancel button
- ProgressBar.vue: animated fill bar
- Wire to downloads store SSE updates
- Risk: LOW-MEDIUM — straightforward rendering, SSE wiring already done

### T05: Responsive layout (desktop + mobile)
- AppLayout.vue: desktop sidebar + main content, mobile bottom tabs + card view
- Breakpoint at 768px
- Mobile: bottom tab bar (Submit/Queue), full-width URL input, card list
- Desktop: header bar, URL input at top, table-style queue below
- 44px minimum touch targets on mobile
- Risk: MEDIUM — responsive CSS without a framework requires care

## Verification Strategy

- `npm run build` — zero errors
- `vue-tsc --noEmit` — TypeScript checks pass
- Vitest unit tests for stores (downloads, config) and SSE composable
- Manual browser verification against running backend
- Mobile layout verification at 375px viewport

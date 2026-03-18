# M001: media.rip() v1.0 — Ship It

**Vision:** Deliver a complete self-hostable yt-dlp web frontend as a Docker container. Paste a URL, pick quality, download — with session isolation, real-time progress, a cyberpunk default theme, secure admin panel, and zero telemetry. Distributed via GHCR + Docker Hub for amd64 + arm64.

## Success Criteria

- User can `docker compose up` with zero config and get a working download UI at :8080 with cyberpunk theme and isolated session mode
- User can paste any yt-dlp-supported URL, select format/quality from live extraction, and download to /downloads with real-time progress
- Two different browsers see only their own downloads (session isolation works)
- Page refresh preserves queue state via SSE replay
- Admin can log in with username/password, manage sessions/storage/config, trigger manual purge
- Custom theme dropped into /themes volume appears in picker and applies correctly
- Mobile layout (375px) uses bottom tabs, card list, ≥44px touch targets
- Tag v0.1.0 triggers CI/CD pipeline that pushes multi-arch images to both registries
- Container makes zero automatic outbound network requests

## Key Risks / Unknowns

- **Sync-to-async bridge** — yt-dlp is synchronous; FastAPI is async. The ThreadPoolExecutor + `call_soon_threadsafe` pattern is well-documented but must be wired correctly or progress events are silently lost
- **SSE zombie connections** — CancelledError swallowing in SSE generators creates memory leaks. Must use try/finally and explicitly handle cancellation
- **CSS variable contract lock-in** — Token names are a one-way door once custom themes exist. Must be designed deliberately before components reference them
- **Admin auth over cleartext** — Can't prevent operators from skipping TLS, but can warn loudly at startup

## Proof Strategy

- Sync-to-async bridge → retire in S01 by proving yt-dlp progress events arrive in an asyncio.Queue via call_soon_threadsafe, with a test that runs a real download and asserts events were received
- SSE zombie connections → retire in S02 by proving SSE endpoint cleanup works on client disconnect (generator finally block fires, queue removed from broker)
- CSS variable contract → retire in S05 by establishing the token set before any component references it, with documentation freeze
- Admin auth security → retire in S04 by proving bcrypt comparison, timing-safe check, security headers, and TLS detection warning all function correctly

## Verification Classes

- Contract verification: pytest for backend (API, services, models), vitest for frontend (stores, components), ruff + eslint + vue-tsc for lint/type-check
- Integration verification: real yt-dlp download producing a file, SSE events flowing from progress hook to browser EventSource, admin config write taking effect without restart
- Operational verification: Docker image builds for both architectures, health endpoint responds, startup TLS warning fires when appropriate
- UAT / human verification: visual theme check, mobile layout feel, admin panel UX flow, first-boot credential setup

## Milestone Definition of Done

This milestone is complete only when all are true:

- All six slices are complete with passing verification
- The full primary loop works end-to-end: URL → format picker → real-time progress → completed file
- Session isolation proven with two independent browsers
- Admin panel accessible only via authenticated login with bcrypt-hashed credentials
- Three built-in themes render correctly; drop-in custom theme chain works
- Mobile layout functions at 375px with correct breakpoint behavior
- Docker image builds and runs for amd64 + arm64
- CI/CD pipeline triggers correctly on PR and tag
- Zero outbound network requests from container verified
- Secure deployment example (reverse proxy + TLS) documented and functional

## Requirement Coverage

- Covers: R001-R026 (all 26 active requirements)
- Partially covers: none
- Leaves for later: R027 (presets), R028 (GitHub issue prefill), R029 (filter persistence)
- Orphan risks: none

## Slices

- [x] **S01: Foundation + Download Engine** `risk:high` `depends:[]`
  > After this: POST a URL to the API → yt-dlp downloads it to /downloads with progress events arriving in an asyncio.Queue. Format probe returns available qualities. Config loads from YAML + env vars. SQLite with WAL mode stores jobs. Proven via API tests and a real yt-dlp download.

- [x] **S02: SSE Transport + Session System** `risk:high` `depends:[S01]`
  > After this: Open two browser tabs → each gets its own SSE stream scoped to their session cookie. Live progress events flow from yt-dlp worker threads through SSEBroker to the correct session's EventSource. Refresh a tab → SSE replays current state. Health endpoint responds. Proven via real SSE connections and session isolation test.

- [ ] **S03: Frontend Core** `risk:medium` `depends:[S02]`
  > After this: Full Vue 3 SPA in the browser: paste URL, pick format from live extraction, watch progress bar fill, see completed files in queue. Playlists show as collapsible parent/child rows. Mobile layout (375px) uses bottom tabs, card list, ≥44px targets. Desktop uses sidebar + table. Proven by loading the SPA and completing a download flow.

- [ ] **S04: Admin, Auth + Supporting Features** `risk:medium` `depends:[S02]`
  > After this: Admin panel requires username/password login (bcrypt). Session list, storage view, manual purge, live config editor, unsupported URL log download all functional. Cookie auth upload works per-session. Session export/import produces valid archive. File link sharing serves completed downloads. Security headers present on admin routes. Startup warns if TLS not detected. Proven via auth tests + admin flow verification.

- [ ] **S05: Theme System** `risk:low` `depends:[S03]`
  > After this: Cyberpunk theme renders with scanlines/grid overlay, JetBrains Mono, #00a8ff/#ff6b2b. Dark and light themes are clean alternatives. CSS variable contract documented in base.css. Drop a custom theme folder into /themes volume → restart → appears in picker → applies correctly. Built-in themes heavily commented as documentation. Proven by theme switching and custom theme load.

- [ ] **S06: Docker + CI/CD** `risk:low` `depends:[S01,S02,S03,S04,S05]`
  > After this: `docker compose up` → app works at :8080 with zero config. `docker-compose.example.yml` includes Caddy/Traefik sidecar for TLS. Tag v0.1.0 → GitHub Actions builds multi-arch image → pushes to GHCR + Docker Hub → creates GitHub Release. PR triggers lint + test + Docker smoke. Zero outbound telemetry verified. Proven by running the published image and completing a full download flow.

## Boundary Map

### S01 → S02

Produces:
- `app/core/database.py` → aiosqlite connection pool with WAL mode, job CRUD operations
- `app/core/config.py` → ConfigManager: YAML + env var merge, typed config access
- `app/models/job.py` → Job Pydantic model, JobStatus enum, ProgressEvent model
- `app/models/session.py` → Session Pydantic model
- `app/services/download.py` → DownloadService: ThreadPoolExecutor, enqueue(), progress hook producing ProgressEvent into a callback
- `app/core/sse_broker.py` → SSEBroker: per-session Queue map, put_nowait(), subscribe()/unsubscribe()

Consumes:
- nothing (first slice)

### S01 → S03

Produces:
- `app/routers/downloads.py` → POST /api/downloads, GET /api/downloads, DELETE /api/downloads/{id}
- `app/routers/formats.py` → GET /api/formats?url= (live yt-dlp extraction)
- `app/models/job.py` → Job, ProgressEvent (JSON schema for frontend TypeScript types)

### S01 → S04

Produces:
- `app/core/database.py` → job/session/config table access
- `app/core/config.py` → ConfigManager (admin writes extend this)
- `app/services/download.py` → DownloadService.cancel()

### S02 → S03

Produces:
- `app/routers/sse.py` → GET /api/events (EventSourceResponse per session)
- `app/middleware/session.py` → SessionMiddleware: auto-creates mrip_session httpOnly cookie, populates request.state.session_id
- `app/routers/health.py` → GET /api/health
- `app/routers/system.py` → GET /api/config/public (sanitized config for frontend)
- SSE event contract: init, job_update, job_removed, error event types with typed payloads

Consumes from S01:
- `app/core/sse_broker.py` → SSEBroker.subscribe(), SSEBroker.put_nowait()
- `app/core/database.py` → job queries for SSE replay
- `app/models/job.py` → Job, ProgressEvent models
- `app/models/session.py` → Session model

### S02 → S04

Produces:
- `app/middleware/session.py` → SessionMiddleware (session identity for admin to list)
- `app/core/database.py` → session table queries

### S03 → S05

Produces:
- Vue component structure referencing CSS custom properties (--color-bg, --color-accent-primary, etc.)
- `frontend/src/stores/theme.ts` → theme store with setTheme(), availableThemes
- Component DOM structure that themes must style correctly

Consumes from S02:
- SSE event contract (EventSource integration in Pinia sse store)
- GET /api/config/public (session mode, default theme)
- Session cookie (auto-set by middleware)

### S04 → S06

Produces:
- `app/routers/admin.py` → all admin API endpoints
- Admin auth middleware (HTTPBasic + bcrypt)
- `app/services/purge.py` → PurgeService
- Test suite for admin routes

Consumes from S02:
- Session middleware, session queries
- SSEBroker (for purge_complete event)

Consumes from S01:
- Database, ConfigManager, DownloadService

### S05 → S06

Produces:
- `frontend/src/themes/` → cyberpunk.css, dark.css, light.css (baked into build)
- `app/core/theme_loader.py` → ThemeLoader scanning /themes volume
- `app/routers/themes.py` → GET /api/themes manifest
- CSS variable contract in base.css (the stable theme API)

Consumes from S03:
- Vue component structure (components reference CSS custom properties)
- Theme store (setTheme, availableThemes)

### All → S06

S06 consumes the complete application from S01-S05:
- All backend source under `backend/app/`
- All frontend source under `frontend/src/`
- All test suites
- All theme assets
- docker-compose.yml, Dockerfile, GitHub Actions workflows

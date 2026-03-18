# Architecture Research

**Domain:** Self-hosted yt-dlp web frontend (Python/FastAPI + Vue 3)
**Researched:** 2026-03-17
**Confidence:** HIGH (core integration patterns) / MEDIUM (schema shape, theme system)

---

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        BROWSER (Vue 3 SPA)                           │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │  DownloadQ   │  │  AdminPanel  │  │  ThemePicker │               │
│  │  (Vue comp)  │  │  (Vue comp)  │  │  (Vue comp)  │               │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘               │
│         │                 │                  │                        │
│  ┌──────┴─────────────────┴──────────────────┴──────────────────┐    │
│  │                     Pinia Stores                              │    │
│  │  downloads | session | admin | theme | sse-connection         │    │
│  └──────┬────────────────────────────────────────────────────────┘    │
│         │  REST (fetch) + SSE (EventSource)                           │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          │ HTTP (behind nginx in prod)
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI (Python 3.12)                            │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │  /api/dl     │  │  /api/admin  │  │  /api/sse    │               │
│  │  /api/session│  │  (basic auth)│  │  /api/health │               │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘               │
│         │                 │                  │                        │
│  ┌──────┴─────────────────┴──────────────────┴──────────────────┐    │
│  │                    Service Layer                              │    │
│  │  DownloadService | SessionService | AdminService | SSEBroker  │    │
│  └──────┬─────────────────────────────────────────┬─────────────┘    │
│         │                                         │                  │
│  ┌──────┴──────────────┐              ┌───────────┴──────────────┐   │
│  │   ThreadPool        │              │   APScheduler             │   │
│  │   (yt-dlp workers)  │              │   (purge cron)            │   │
│  └──────┬──────────────┘              └──────────────────────────┘   │
│         │ progress_hook → asyncio.Queue → SSEBroker                  │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Persistence Layer                                  │
│  ┌──────────────────────┐  ┌───────────────────────────────────┐     │
│  │   SQLite (aiosqlite) │  │   Filesystem                      │     │
│  │   jobs, sessions,    │  │   /data/downloads/  (output)      │     │
│  │   config, logs       │  │   /data/cookies/    (per-session) │     │
│  └──────────────────────┘  │   /data/unsupported_urls.log      │     │
│                             │   /themes/          (custom)      │     │
│                             │   config.yaml       (override)    │     │
│                             └───────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| Vue SPA | All user interaction, queue visualization, SSE state sync | Built to `/app/static/` at image build time, served by FastAPI StaticFiles |
| Pinia `downloads` store | Download job state, optimistic updates, SSE-driven mutations | SSE events are the source of truth; REST is for initial hydration and commands |
| Pinia `sse-connection` store | Manages EventSource lifecycle, reconnect, missed-event replay | Separate store so reconnect logic doesn't pollute download logic |
| FastAPI routers | Route validation, auth middleware, response shaping | Thin — delegates to services |
| `DownloadService` | Orchestrates yt-dlp jobs, manages queue, dispatches progress to SSEBroker | One service, not per-request; holds job registry |
| `SSEBroker` | Per-session asyncio.Queue map; fan-out to all active SSE connections for a session | Singleton; isolates sessions by `session_id` key |
| `SessionService` | Cookie creation/validation, session CRUD, export/import packaging | Owns session identity; no auth — identity only |
| `AdminService` | Config read/write, live reload, session listing, manual purge | Protected by HTTP Basic auth middleware |
| ThreadPoolExecutor | Runs yt-dlp synchronously; progress hooks bridge back to async via `call_soon_threadsafe` | yt-dlp is synchronous and cannot be awaited directly |
| APScheduler `AsyncIOScheduler` | Purge cron job (file TTL, session TTL, log rotation) | Shares event loop with FastAPI; started in lifespan |
| SQLite (aiosqlite) | Job state, session records, config overrides, unsupported URL log | Single file at `/data/mrip.db` |

---

## Key Integration: yt-dlp Progress → SSE

This is the most architecturally significant path in the system. Getting it wrong causes either blocking the event loop or losing progress events.

### The Problem

yt-dlp's `download()` method is **synchronous and blocking**. It calls `progress_hook` callbacks from inside that synchronous thread. FastAPI runs on asyncio. These two worlds must be bridged without:
- Blocking the event loop (which would stall all SSE streams and API requests)
- Using ProcessPoolExecutor (yt-dlp `YoutubeDL` objects contain file handles — not picklable)

### The Solution: ThreadPoolExecutor + `call_soon_threadsafe`

```
yt-dlp thread (sync)            asyncio event loop (async)
─────────────────────           ───────────────────────────
run_in_executor(pool, fn)  →→→  awaited by DownloadService
  progress_hook(d) fires
    loop.call_soon_threadsafe(
      queue.put_nowait, event  →→→  asyncio.Queue receives event
    )                                    ↓
                                  SSEBroker.publish(session_id, event)
                                         ↓
                                  EventSourceResponse yields to browser
```

**Rule:** Never call `asyncio.Queue.put()` directly from the yt-dlp thread. Always use `loop.call_soon_threadsafe(queue.put_nowait, event)`. This is the only safe bridge from sync threads to the async event loop.

### Progress Hook Payload

yt-dlp calls `progress_hook(d)` where `d` is a dict with these fields:

```python
{
    "status": "downloading" | "finished" | "error",
    "filename": str,
    "downloaded_bytes": int,
    "total_bytes": int | None,       # None if unknown
    "total_bytes_estimate": int | None,
    "speed": float | None,           # bytes/sec
    "eta": int | None,               # seconds
    "elapsed": float,
    "tmpfilename": str | None,
    # "fragment_index", "fragment_count" for HLS/DASH
}
```

Normalize this into a typed `ProgressEvent` before putting it on the queue — never send raw yt-dlp dicts to the browser.

---

## Component Boundaries

### New Components Required (not pre-existing libraries)

| Component | File | Why It's Its Own Thing |
|-----------|------|------------------------|
| `SSEBroker` | `app/core/sse_broker.py` | Singleton managing per-session queues; must be referenced from both the download worker thread and the SSE endpoint. Lives outside any request lifecycle. |
| `DownloadService` | `app/services/download.py` | Long-lived, holds job registry (`job_id → job_state`), manages ThreadPoolExecutor lifecycle. Not per-request. |
| `SessionMiddleware` (custom) | `app/middleware/session.py` | Auto-creates `mrip_session` UUID cookie on first request; validates on subsequent. Lighter than Starlette's full SessionMiddleware, which signs the entire session dict into the cookie. We only want an opaque ID. |
| `ConfigManager` | `app/core/config.py` | Merges `config.yaml` overrides onto defaults; exposes live-reload API for admin. SQLite holds the mutable copy; `config.yaml` is read-only at start and writes nothing back. |
| `ThemeLoader` | `app/core/theme_loader.py` | Scans `/themes/` volume directory at startup and on admin request; returns manifest of available themes. Does not compile anything — themes are served as static CSS variable files. |
| `PurgeService` | `app/services/purge.py` | Encapsulates purge logic (file TTL, session TTL, log trim). Called by APScheduler cron and by admin manual-trigger endpoint. |
| `SessionExporter` | `app/services/session_export.py` | Serializes session + job history to JSON archive; validates and imports the reverse. |

### Modified / Wrapped Components

| Component | Modification |
|-----------|-------------|
| `sse-starlette` `EventSourceResponse` | Used directly; no modification needed |
| `APScheduler` `AsyncIOScheduler` | Wrapped in lifespan startup/shutdown; no subclassing |
| `aiosqlite` | Wrapped in a thin `Database` context manager for connection reuse across requests via FastAPI dependency injection |

---

## Database Schema Shape

Single SQLite file at `/data/mrip.db`. All tables use `TEXT` UUIDs as primary keys for portability in exports.

```sql
-- Sessions: cookie identity
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,          -- UUID, matches mrip_session cookie value
    created_at  INTEGER NOT NULL,          -- unix timestamp
    last_seen   INTEGER NOT NULL,
    mode        TEXT NOT NULL DEFAULT 'isolated',
    preferences TEXT NOT NULL DEFAULT '{}' -- JSON blob (theme selection, etc.)
);

-- Jobs: one row per download task
CREATE TABLE jobs (
    id             TEXT PRIMARY KEY,        -- UUID
    session_id     TEXT NOT NULL REFERENCES sessions(id),
    url            TEXT NOT NULL,
    title          TEXT,
    format_id      TEXT,
    status         TEXT NOT NULL,          -- queued|downloading|finished|error|cancelled
    progress_pct   REAL DEFAULT 0,
    speed_bps      REAL,
    eta_secs       INTEGER,
    error_msg      TEXT,
    output_path    TEXT,                   -- relative to /data/downloads/
    file_size      INTEGER,
    created_at     INTEGER NOT NULL,
    started_at     INTEGER,
    finished_at    INTEGER
);

-- Config: mutable settings (admin UI writes here; config.yaml seeds it)
CREATE TABLE config (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL                   -- JSON-serialized scalar or object
);

-- Unsupported URL log (append-only)
CREATE TABLE unsupported_urls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    domain     TEXT NOT NULL,              -- logged domain only (default)
    full_url   TEXT,                       -- NULL unless report_full_url=true
    error_msg  TEXT,
    created_at INTEGER NOT NULL
);
```

**Indexes needed:**
- `jobs(session_id, status)` — SSE reconnect replay, queue filtering
- `jobs(finished_at)` — purge queries
- `sessions(last_seen)` — session TTL purge

---

## Recommended Project Structure

```
media-rip/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app factory, lifespan, middleware
│   │   ├── core/
│   │   │   ├── config.py         # ConfigManager (yaml merge + SQLite live config)
│   │   │   ├── database.py       # aiosqlite connection pool + migration runner
│   │   │   ├── sse_broker.py     # SSEBroker singleton
│   │   │   └── theme_loader.py   # /themes/ scanner
│   │   ├── middleware/
│   │   │   └── session.py        # mrip_session cookie auto-create/validate
│   │   ├── routers/
│   │   │   ├── downloads.py      # POST /api/dl, GET /api/dl/{id}, DELETE
│   │   │   ├── sessions.py       # GET/DELETE /api/session, export/import
│   │   │   ├── sse.py            # GET /api/sse  (EventSourceResponse)
│   │   │   ├── admin.py          # /api/admin/* (basic auth protected)
│   │   │   ├── health.py         # GET /api/health
│   │   │   └── themes.py         # GET /api/themes (manifest)
│   │   ├── services/
│   │   │   ├── download.py       # DownloadService (ThreadPool + job registry)
│   │   │   ├── purge.py          # PurgeService
│   │   │   └── session_export.py # SessionExporter
│   │   └── models/
│   │       ├── job.py            # Pydantic models: JobCreate, JobStatus, ProgressEvent
│   │       ├── session.py        # SessionRecord, SessionExport
│   │       └── config.py         # ConfigSchema
│   ├── tests/
│   │   ├── test_sse_broker.py
│   │   ├── test_download_service.py
│   │   └── test_session.py
│   ├── alembic/                  # DB migrations (keep even for SQLite — schema evolves)
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── stores/
│   │   │   ├── downloads.ts      # Job state, queue ops
│   │   │   ├── session.ts        # Session identity, export/import
│   │   │   ├── sse.ts            # EventSource lifecycle + reconnect
│   │   │   ├── admin.ts          # Admin state, config editor
│   │   │   └── theme.ts          # Active theme, available themes
│   │   ├── components/
│   │   │   ├── DownloadQueue/
│   │   │   ├── FormatPicker/
│   │   │   ├── ProgressBar/
│   │   │   ├── PlaylistRow/
│   │   │   └── AdminPanel/
│   │   ├── composables/
│   │   │   └── useSSE.ts         # Thin wrapper over sse store
│   │   └── themes/               # Built-in theme CSS variable files (embedded in build)
│   │       ├── cyberpunk.css
│   │       ├── dark.css
│   │       └── light.css
│   ├── public/
│   └── vite.config.ts
├── themes/                       # Volume-mounted custom themes (operator drop-in)
│   └── .gitkeep
├── data/                         # Volume-mounted runtime data
│   └── .gitkeep
├── Dockerfile
├── docker-compose.yml            # For local dev and reference deploy
└── config.yaml.example
```

### Structure Rationale

- **`backend/app/core/`:** Things that live for the full application lifetime (broker, config, DB pool) vs. `services/` which own business logic and can be unit-tested in isolation.
- **`backend/app/middleware/`:** Session cookie logic in middleware means every request gets `request.state.session_id` populated before it hits any router. No per-route cookie reading.
- **`frontend/src/stores/sse.ts`:** SSE lifecycle is isolated from business stores. Downloads store subscribes to SSE store events. This means reconnect logic doesn't leak into job state logic.
- **`themes/` at repo root:** Separate from `frontend/src/themes/` — built-in themes are compiled into the frontend bundle; operator themes are volume-mounted and served dynamically at runtime.

---

## Data Flow: Key Paths

### Path 1: URL → Download → SSE Progress → Completion

```
1. User pastes URL
   Browser:  URL field onChange → format-probe fetch (GET /api/dl/probe?url=...)
   Backend:  yt-dlp.extract_info(url, download=False) in ThreadPool → returns formats
   Browser:  FormatPicker shows options

2. User selects format, clicks Download
   Browser:  POST /api/dl  {url, format_id, session_id (from cookie)}
   Backend:  DownloadService.enqueue(job) → creates DB row (status=queued)
             returns {job_id}

3. SSE stream delivers state
   Browser:  EventSource on /api/sse (session_id from cookie)
             SSEBroker has a queue keyed by session_id
   Backend:  GET /api/sse → EventSourceResponse(async_generator)
             generator: while True: event = await queue.get(); yield event

4. Download worker executes
   Backend:  ThreadPoolExecutor.submit(run_download, job_id, url, format_id, opts)
             Inside thread:
               YoutubeDL(opts).download([url])
               progress_hook fires with {status, downloaded_bytes, ...}
               → loop.call_soon_threadsafe(
                   sse_broker.put_nowait,
                   session_id,
                   ProgressEvent(job_id, ...)
                 )
             On finish:  DB update (status=finished, output_path=...)
               → call_soon_threadsafe sends "finished" event

5. Browser receives progress events
   SSE store receives raw event → dispatches to downloads store
   downloads store: jobs[job_id].progress = event.pct

6. SSE reconnect (browser drop/refresh)
   Browser:  EventSource auto-reconnects (built-in)
   Backend:  GET /api/sse → queries DB for all active/recent jobs for this session
             Replays current state as synthetic SSE events before entering live queue
```

### Path 2: Admin Config Change (live reload)

```
Admin UI → POST /api/admin/config {key, value}
  → AdminService.set(key, value) → writes to config table in SQLite
  → ConfigManager.invalidate_cache()
  → next request picks up new value
  (No restart required — config is read from DB on each use, not at startup)
```

### Path 3: Drop-in Theme Load

```
Operator: docker volume mount ./my-theme/ → /themes/my-theme/
  /themes/my-theme/theme.css   (CSS custom properties)
  /themes/my-theme/meta.json   {name, author, preview_color}

Backend startup:  ThemeLoader.scan() → reads /themes/*/meta.json
  GET /api/themes → returns [{id, name, author, preview_color, is_builtin}]
  GET /themes/{id}/theme.css  → FileResponse (volume-served, not compiled)

Browser: ThemePicker calls /api/themes, shows list
  User selects custom theme → <link rel="stylesheet"> swapped to /themes/id/theme.css
  (Built-in themes are already in the bundle as CSS files)
```

### Path 4: Session Export/Import

```
Export:
  GET /api/session/export
  → SessionExporter.export(session_id)
  → queries: session row + all jobs for session
  → zips: export.json + any cookies.txt for this session
  → returns StreamingResponse (zip file download)

Import:
  POST /api/session/import  (multipart, zip file)
  → unzip, validate schema version
  → create new session (new UUID, import grants new identity)
  → insert jobs (status "finished" only — don't replay active downloads)
  → return new session cookie (Set-Cookie: mrip_session=new_uuid)
```

---

## Architectural Patterns

### Pattern 1: Sync-to-Async Bridge via `call_soon_threadsafe`

**What:** yt-dlp progress hooks fire synchronously inside a thread. The running event loop must be captured at app startup and used to safely enqueue events without blocking the thread or corrupting the loop.

**When to use:** Any time synchronous library code in a worker thread needs to communicate back to the asyncio world.

**Trade-offs:** Simple and correct. The only alternative (running yt-dlp in a subprocess and parsing stdout) is fragile and loses structured error info.

**Key snippet shape:**
```python
# In app startup — capture the loop once
loop = asyncio.get_event_loop()

# In progress hook (called from sync thread)
def progress_hook(d: dict) -> None:
    event = ProgressEvent.from_yt_dlp(job_id, d)
    loop.call_soon_threadsafe(sse_broker.put_nowait, session_id, event)
```

### Pattern 2: Per-Session SSE Queue Fan-Out

**What:** One `asyncio.Queue` per connected SSE client (not per session). Multiple browser tabs from the same session each get their own queue. SSEBroker maintains `session_id → List[Queue]` and fans out to all queues on `publish()`.

**When to use:** Always. A single global queue would leak events across sessions — a privacy violation that defeats session isolation.

**Trade-offs:** Queue cleanup requires detecting client disconnect. `sse-starlette`'s `EventSourceResponse` handles this — the generator raises `asyncio.CancelledError` or `GeneratorExit` when the client disconnects, allowing cleanup in a `finally` block.

### Pattern 3: SSE Replay on Reconnect

**What:** When a client reconnects to `/api/sse`, the endpoint first emits synthetic events for all current job states from the DB before entering the live queue. This ensures the UI is fully hydrated on reconnect without requiring a separate REST fetch.

**When to use:** Any SSE endpoint where the client might have missed events during a disconnect.

**Trade-offs:** Slightly more complex endpoint logic, but eliminates an entire class of "spinner forever after refresh" bugs.

### Pattern 4: Config Hierarchy (Defaults → YAML → SQLite)

**What:** Settings have three layers. Built-in defaults are hardcoded in Python. `config.yaml` overrides them at startup (read-only after that). Admin UI writes to the `config` SQLite table, which is the live source of truth at runtime.

**When to use:** Operator-facing applications that need both infra-as-code (YAML) and live UI config without restart.

**Trade-offs:** Two sources of truth during initial startup (YAML seeds SQLite on first boot, then SQLite wins). Must document precedence clearly. YAML never reflects what admin UI has changed.

---

## Anti-Patterns

### Anti-Pattern 1: Running yt-dlp directly in an async def route

**What people do:** `await asyncio.to_thread(ydl.download, [url])` inside a route handler.

**Why it's wrong:** `asyncio.to_thread` uses the default executor, which shares a pool with all other blocking calls. More critically, the progress hook fires from inside that thread and has no safe way to reach the SSE queue without a stored event loop reference. This pattern leads to either lost events or `RuntimeError: no running event loop`.

**Do this instead:** Use `DownloadService` (a singleton with its own dedicated `ThreadPoolExecutor`), capture `asyncio.get_event_loop()` at app startup, and use `call_soon_threadsafe` in the hook.

### Anti-Pattern 2: Storing session content in the cookie

**What people do:** Use Starlette's `SessionMiddleware` which signs the entire session dict into the cookie.

**Why it's wrong:** Session content (job IDs, preferences) grows unboundedly. Signed cookies can be decoded (just not tampered with). Violates the principle that the browser should hold only an opaque identity token.

**Do this instead:** Store only a UUID in the `mrip_session` cookie. All session state lives in SQLite keyed by that UUID.

### Anti-Pattern 3: Single global SSE queue for all sessions

**What people do:** One `asyncio.Queue` app-wide; all SSE consumers read from it.

**Why it's wrong:** Every client sees every other client's download events. Violates session isolation (the core privacy promise). Also creates thundering-herd wake-ups for unrelated events.

**Do this instead:** `SSEBroker` maps `session_id → List[asyncio.Queue]`, one queue per live connection.

### Anti-Pattern 4: Polling the DB for progress updates from SSE endpoint

**What people do:** SSE endpoint loops with `await asyncio.sleep(0.5)` and queries the DB for job state changes.

**Why it's wrong:** Generates constant DB load proportional to active connections × poll frequency. Introduces 0-500ms latency on progress events. Doesn't scale.

**Do this instead:** DownloadService pushes events directly into the SSE queues via `call_soon_threadsafe`. DB is only written for persistence — SSE reads from the queue.

### Anti-Pattern 5: Volume-mounting themes into the frontend build directory

**What people do:** Mount custom themes into `/app/static/themes/` and expect Vue to pick them up.

**Why it's wrong:** The built-in themes are baked into the static bundle at image build time. A volume mount on the same directory would shadow built-in themes and create confusion.

**Do this instead:** Built-in themes live at `/app/static/builtin-themes/` (baked in). Custom themes live at `/themes/` (volume-mounted). Frontend fetches the manifest from `/api/themes` to know what's available. `GET /themes/{id}/theme.css` is served by FastAPI's `StaticFiles` mount on the volume directory.

---

## Docker Layering Strategy

### Multi-Stage Build: 3 Stages

```dockerfile
# Stage 1: Frontend builder (Node)
FROM node:22-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build
# Output: /frontend/dist/

# Stage 2: Python dependency builder
FROM python:3.12-slim AS python-builder
WORKDIR /build
RUN pip install uv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv pip install --system --no-cache -r pyproject.toml
# Installs: fastapi, uvicorn, yt-dlp, sse-starlette, aiosqlite, apscheduler, pyyaml, etc.

# Stage 3: Final runtime image
FROM python:3.12-slim AS runtime
# Install ffmpeg (required by yt-dlp for muxing)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
# Copy Python packages from builder
COPY --from=python-builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=python-builder /usr/local/bin /usr/local/bin
# Copy backend source
COPY backend/app /app/app
# Copy built frontend assets into location FastAPI StaticFiles will serve
COPY --from=frontend-builder /frontend/dist /app/static
# Runtime config
WORKDIR /app
ENV MRIP_DATA_DIR=/data
VOLUME ["/data", "/themes"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Layer Cache Optimization

The stage order matters for cache hit rates during development:

1. **Frontend builder first:** Node dependencies are the most stable. `package-lock.json` changes rarely. `npm ci` layer is cache-friendly.
2. **Python deps before source:** `pyproject.toml` changes less often than `app/` code. Source copy is always last within each stage.
3. **ffmpeg in a single RUN:** Combine `apt-get update`, install, and `rm -rf /var/lib/apt/lists/*` in one layer to avoid caching a stale package index.

### Multi-Platform Build (amd64 + arm64)

```bash
# CI pipeline (GitHub Actions)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag ghcr.io/xpltd/media-rip:$VERSION \
  --push \
  .
```

**Arm64 consideration:** `ffmpeg` from Debian apt supports arm64 natively — no cross-compile needed. yt-dlp is pure Python — no binary concern. The only risk is any Python package with C extensions (e.g., `aiosqlite` → `sqlite3` → system library). `python:3.12-slim` includes `libsqlite3` for both platforms.

**QEMU vs. native:** GitHub Actions standard runners are amd64. QEMU emulation for arm64 is slow but correct for this stack (no complex native compilation). If build times become painful, use ARM runners (e.g., Blacksmith or self-hosted).

### FastAPI Serving Static Files (no nginx needed in single container)

FastAPI's `StaticFiles` mount is sufficient for this use case (single-instance self-hosted tool, not a CDN-scale app):

```python
from fastapi.staticfiles import StaticFiles

# Built frontend assets
app.mount("/assets", StaticFiles(directory="/app/static/assets"), name="assets")

# Volume-mounted custom themes
app.mount("/themes", StaticFiles(directory=os.environ.get("MRIP_THEMES_DIR", "/themes")), name="themes")

# SPA fallback: any unmatched path returns index.html
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse("/app/static/index.html")
```

If an operator wants to put nginx in front (for TLS termination, caching), the container works unchanged behind a reverse proxy.

---

## Build Order (Dependency-Respecting)

Build phases in this order to avoid blocking work:

```
Phase 1: Foundation (no dependencies)
├── Database schema + migrations (aiosqlite, alembic init)
├── ConfigManager (pure Python, no DB dependency)
├── SessionMiddleware (cookie only — no DB needed to write it)
└── SSEBroker (pure asyncio.Queue — no yt-dlp, no DB)

Phase 2: Core Services (depends on Phase 1)
├── DownloadService skeleton (ThreadPool, queue intake, DB writes)
│   └── yt-dlp integration + progress hook bridge to SSEBroker
├── SSE endpoint (depends on SSEBroker from Phase 1)
│   └── With reconnect/replay from DB
└── Session CRUD endpoints (depends on DB + SessionMiddleware)

Phase 3: Frontend Core (can start after Phase 2 API shape is stable)
├── Pinia sse store + EventSource lifecycle
├── Pinia downloads store (consumes SSE events)
├── DownloadQueue component (URL input → probe → format picker → enqueue)
└── ProgressBar (driven by downloads store)

Phase 4: Admin + Auth (depends on Phase 2)
├── AdminService (config read/write)
├── Basic auth middleware on /api/admin/*
├── Admin router (sessions, storage, purge trigger, config editor)
└── Admin UI (Vue components)

Phase 5: Supporting Features (depends on Phases 2-4)
├── Theme system (ThemeLoader + /api/themes + volume serving)
├── PurgeService + APScheduler integration
├── Session export/import
├── cookies.txt upload (per-session)
└── Unsupported URL logging + admin download

Phase 6: Distribution
├── Dockerfile (multi-stage)
├── docker-compose.yml
├── GitHub Actions CI (lint, type-check, test, Docker smoke)
└── GitHub Actions CD (tag → build + push + release)
```

**Critical path:** Phase 1 → Phase 2 (SSEBroker + yt-dlp bridge) → Phase 3 (SSE consumer). The SSE transport must exist before meaningful frontend progress work can be validated end-to-end.

---

## Integration Points

### External Dependencies

| Dependency | Integration Pattern | Critical Notes |
|------------|---------------------|----------------|
| yt-dlp | `import yt_dlp` as library, not subprocess | `YoutubeDL` instance created fresh per job inside worker thread. Not shared. Not passed across process boundary. |
| ffmpeg | Installed in Docker image; yt-dlp finds it via `PATH` | Required for muxing video+audio streams. Not directly called by app code. |
| `sse-starlette` (v3.3.3) | `EventSourceResponse(async_generator)` | Handles ping/heartbeat, client disconnect detection. No subclassing needed. |
| `APScheduler` `AsyncIOScheduler` | Started in FastAPI `lifespan` context manager | Use `AsyncIOScheduler` (not `BackgroundScheduler`) to share the event loop. One instance globally. |
| `aiosqlite` | Thin wrapper for connection reuse via FastAPI `Depends` | One connection pool, not per-request connections. WAL mode for concurrent reads. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Worker Thread ↔ SSEBroker | `loop.call_soon_threadsafe(broker.put_nowait, ...)` | Only safe async bridge from sync thread |
| SSEBroker ↔ SSE endpoint | `await queue.get()` in async generator | SSEBroker holds the queue; endpoint holds a reference |
| DownloadService ↔ DB | Direct `aiosqlite` calls | Service owns all job table writes |
| Middleware ↔ Routers | `request.state.session_id` | Middleware populates state; routers read it |
| ConfigManager ↔ All Services | Singleton read via dependency injection | No global variable — injected via `Depends(get_config)` |
| ThemeLoader ↔ Volume | Filesystem scan at startup + on-demand re-scan | No file watchers — re-scan is triggered by API call |

---

## Scaling Considerations

This is a single-instance self-hosted tool. The relevant scaling axis is concurrent downloads per instance, not users.

| Concern | Practical Limit | Mitigation |
|---------|-----------------|------------|
| Concurrent downloads | ThreadPoolExecutor defaults (min: 1, configurable) | Expose `max_concurrent_downloads` in config. Default 3 is safe for home use. |
| SQLite write contention | WAL mode handles concurrent reads + single writer fine | Enable `PRAGMA journal_mode=WAL` at DB init. No further action needed for this use case. |
| SSE connection count | asyncio handles hundreds of idle connections trivially | Not a practical concern for self-hosted tool |
| Disk space | operator concern | PurgeService + health endpoint disk-free flag address this |
| yt-dlp blocking | Handled by ThreadPool | GIL is released during I/O-heavy yt-dlp work; threads are effective here |

The architecture should not block a future "external API" milestone. The service layer is already the right boundary: a future v2 API consumer calls `DownloadService.enqueue()` just like the REST endpoint does — no architectural change required.

---

## Sources

- yt-dlp asyncio + ProcessPoolExecutor issue: https://github.com/yt-dlp/yt-dlp/issues/9487
- sse-starlette PyPI (v3.3.3, 2026-03-17): https://pypi.org/project/sse-starlette/
- FastAPI SSE official docs: https://fastapi.tiangolo.com/tutorial/server-sent-events/
- FastAPI async/threading patterns: https://fastapi.tiangolo.com/async/
- Docker multi-platform builds: https://docs.docker.com/build/building/multi-platform/
- Multi-arch GitHub Actions: https://www.blacksmith.sh/blog/building-multi-platform-docker-images-for-arm64-in-github-actions
- FastAPI + aiosqlite pattern: https://sqlspec.dev/examples/frameworks/fastapi/aiosqlite_app.html
- APScheduler + FastAPI lifespan: https://rajansahu713.medium.com/implementing-background-job-scheduling-in-fastapi-with-apscheduler-6f5fdabf3186
- FastAPI ThreadPool vs run_in_executor: https://sentry.io/answers/fastapi-difference-between-run-in-executor-and-run-in-threadpool/

---
*Architecture research for: media.rip() v1.0 — Python/FastAPI + Vue 3 + yt-dlp + SSE + SQLite + Docker*
*Researched: 2026-03-17*

# S01: Foundation + Download Engine

**Goal:** Deliver the backend foundation: project scaffold, SQLite database with WAL mode, config system (defaults → YAML → env vars), Pydantic models, SSE broker data structure, yt-dlp download service with sync-to-async progress bridging, and API routes for submitting downloads and probing formats.

**Demo:** `POST /api/downloads` with a URL → yt-dlp downloads it to `/downloads` with progress events arriving in an `asyncio.Queue` via `call_soon_threadsafe`. `GET /api/formats?url=` returns available qualities. Config loads from YAML + env vars. SQLite with WAL mode stores jobs. Proven via pytest running API tests and a real yt-dlp download.

## Must-Haves

- Project scaffold with `pyproject.toml`, pinned dependencies, and `backend/app/` package structure matching the boundary map
- Pydantic models: `Job`, `JobStatus`, `JobCreate`, `ProgressEvent` (with `from_yt_dlp` normalizer handling `total_bytes: None`), `Session`, `FormatInfo`
- Config via `pydantic-settings[yaml]`: `AppConfig` with env prefix `MEDIARIP`, nested delimiter `__`, YAML source, zero-config defaults
- SQLite database via `aiosqlite`: WAL mode + `busy_timeout=5000` + `synchronous=NORMAL` as first PRAGMAs, schema for `sessions`/`jobs`/`config`/`unsupported_urls` tables, async CRUD functions
- `SSEBroker`: per-session queue map with `subscribe`/`unsubscribe`/`publish`, thread-safe via `call_soon_threadsafe`
- `DownloadService`: `ThreadPoolExecutor`, fresh `YoutubeDL` per job, progress hook → broker publish, `enqueue()` and `get_formats()` methods
- Output template resolver: per-domain template lookup with fallback to `*` default
- `POST /api/downloads`, `GET /api/downloads`, `DELETE /api/downloads/{id}`, `GET /api/formats?url=`
- Stub session ID dependency (reads `X-Session-ID` header, falls back to default UUID) replaceable by S02 middleware
- Real yt-dlp integration test proving progress events flow through the sync-to-async bridge

## Proof Level

- This slice proves: integration (sync-to-async bridge, DB concurrency, full API vertical)
- Real runtime required: yes (yt-dlp must download a real file)
- Human/UAT required: no

## Verification

All tests run from `backend/`:

- `cd backend && python -m pytest tests/test_models.py -v` — model construction, `ProgressEvent.from_yt_dlp` normalization, edge cases
- `cd backend && python -m pytest tests/test_config.py -v` — env var override, YAML loading, zero-config defaults
- `cd backend && python -m pytest tests/test_database.py -v` — CRUD, WAL mode verification, concurrent writes
- `cd backend && python -m pytest tests/test_sse_broker.py -v` — subscribe/unsubscribe, thread-safe publish
- `cd backend && python -m pytest tests/test_download_service.py -v` — real yt-dlp download with progress events, format extraction
- `cd backend && python -m pytest tests/test_api.py -v` — all four API endpoints via httpx AsyncClient
- `cd backend && python -m pytest tests/ -v` — full suite green, 0 failures
- Verify `PRAGMA journal_mode` returns `wal` in database test
- Verify progress events contain `status=downloading` with valid percent values in download service test

## Observability / Diagnostics

- Runtime signals: `logging.getLogger("mediarip")` structured logs on job state transitions (queued → extracting → downloading → completed/failed), download errors logged with job_id + exception
- Inspection surfaces: `jobs` table in SQLite with `status`, `error_message`, `progress_percent` columns; `PRAGMA journal_mode` query to verify WAL
- Failure visibility: `Job.error_message` stores failure reason, `Job.status = "failed"` on any download error, `ProgressEvent` includes `status` field for real-time failure detection
- Redaction constraints: none in S01 (admin credentials are S04)

## Integration Closure

- Upstream surfaces consumed: none (first slice)
- New wiring introduced: FastAPI app factory with lifespan (DB init/close), router mounting, dependency injection for DownloadService/SSEBroker/database
- What remains before the milestone is truly usable end-to-end: S02 (SSE transport + real session middleware), S03 (frontend SPA), S04 (admin auth), S05 (themes), S06 (Docker + CI/CD)

## Tasks

- [x] **T01: Scaffold project and define Pydantic models** `est:45m`
  - Why: Greenfield project — no code exists. Every subsequent task imports from the models and depends on the package structure. The boundary map contract (`app/core/`, `app/services/`, `app/routers/`, `app/models/`) must be established first.
  - Files: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/models/__init__.py`, `backend/app/models/job.py`, `backend/app/models/session.py`, `backend/tests/test_models.py`
  - Do: Create `backend/pyproject.toml` with all pinned deps from research. Create directory structure with `__init__.py` files for `app/`, `app/core/`, `app/services/`, `app/routers/`, `app/models/`, `app/middleware/`. Write `JobStatus` enum, `JobCreate`, `Job`, `ProgressEvent` (with `from_yt_dlp` classmethod), `FormatInfo`, `Session` models. Write `app/main.py` skeleton (empty FastAPI app, placeholder lifespan). Write model unit tests covering ProgressEvent normalization with `total_bytes: None`, `total_bytes_estimate` fallback, and all status values.
  - Verify: `cd backend && pip install -e ".[dev]" && python -m pytest tests/test_models.py -v`
  - Done when: `pip install -e ".[dev]"` succeeds, all model tests pass, `from app.models.job import Job, JobStatus, ProgressEvent, JobCreate, FormatInfo` works

- [ ] **T02: Build config system, database layer, and SSE broker** `est:1h`
  - Why: These three infrastructure modules are the foundation everything else depends on. Config provides settings to database and download service. Database stores all job state. SSE broker is the thread-safe event distribution mechanism. All three are pure infrastructure with well-defined interfaces.
  - Files: `backend/app/core/config.py`, `backend/app/core/database.py`, `backend/app/core/sse_broker.py`, `backend/tests/conftest.py`, `backend/tests/test_config.py`, `backend/tests/test_database.py`, `backend/tests/test_sse_broker.py`
  - Do: Build `AppConfig` via pydantic-settings with env prefix `MEDIARIP`, nested delimiter `__`, YAML source (handle missing file gracefully), and `settings_customise_sources` for priority ordering. Build database module with aiosqlite: singleton connection pattern for lifespan, WAL + busy_timeout + synchronous PRAGMAs first, schema creation (sessions, jobs, config, unsupported_urls tables with indexes), async CRUD functions. Build SSEBroker with per-session queue map, subscribe/unsubscribe, and `publish` using `loop.call_soon_threadsafe`. Create `conftest.py` with shared fixtures (temp DB, test config). Write tests: config env override + YAML + zero-config defaults; DB CRUD + WAL verification + concurrent write test; broker subscribe/publish-from-thread/unsubscribe.
  - Verify: `cd backend && python -m pytest tests/test_config.py tests/test_database.py tests/test_sse_broker.py -v`
  - Done when: All three test files pass. `PRAGMA journal_mode` returns `wal`. Concurrent writes (3 simultaneous) complete without `SQLITE_BUSY`. Broker publish from a thread delivers event to subscriber queue.

- [ ] **T03: Implement download service with sync-to-async bridge** `est:1h`
  - Why: This is the highest-risk component in the slice — the sync-to-async bridge between yt-dlp worker threads and asyncio queues. It must be built and proven separately before API routes wire it up. The output template resolver is a direct dependency. This task retires the primary risk identified in the roadmap: "proving yt-dlp progress events arrive in an asyncio.Queue via call_soon_threadsafe."
  - Files: `backend/app/services/download.py`, `backend/app/services/output_template.py`, `backend/app/services/__init__.py`, `backend/tests/test_download_service.py`, `backend/tests/test_output_template.py`
  - Do: Build `resolve_template(url, user_override, config)` — extract domain, lookup in `source_templates` config map, fallback to `*`. Build `DownloadService` class: accepts config, database, SSE broker, event loop in constructor. `ThreadPoolExecutor(max_workers=config.downloads.max_concurrent)`. `enqueue(job_create, session_id)` creates DB row then submits `_run_download` to executor. `_run_download` creates fresh `YoutubeDL` per job (never shared), registers progress hook that calls `loop.call_soon_threadsafe(broker.publish, session_id, ProgressEvent.from_yt_dlp(...))`, updates DB on completion/failure. `get_formats(url)` runs `extract_info(url, download=False)` in executor, returns list of `FormatInfo`. `cancel(job_id)` sets status=failed in DB. Handle `total_bytes: None` in progress hook. Throttle DB progress writes (≥1% change or status change). Write integration test: real yt-dlp download of a short Creative Commons video, assert progress events arrive in broker queue with `status=downloading` and valid percent. Write format extraction test. Write output template unit tests.
  - Verify: `cd backend && python -m pytest tests/test_download_service.py tests/test_output_template.py -v`
  - Done when: Real download test passes — file appears in output dir AND progress events with `status=downloading` were received in the broker queue. Format extraction returns non-empty list with `format_id` and `ext` fields. Output template resolves domain-specific and fallback templates correctly.

- [ ] **T04: Wire API routes and FastAPI app factory** `est:45m`
  - Why: The API routes are the HTTP surface that S02 and S03 consume. The app factory lifespan wires database init/close and service construction. The stub session dependency provides `session_id` for testing until S02 delivers real middleware. This task proves the full vertical: HTTP request → router → service → yt-dlp → DB + SSE broker.
  - Files: `backend/app/main.py`, `backend/app/routers/downloads.py`, `backend/app/routers/formats.py`, `backend/app/routers/__init__.py`, `backend/app/dependencies.py`, `backend/tests/test_api.py`, `backend/tests/conftest.py`
  - Do: Create `app/dependencies.py` with stub `get_session_id` dependency (reads `X-Session-ID` header, falls back to a default UUID — clearly documented as S02-replaceable). Update `app/main.py` lifespan: init aiosqlite connection with WAL PRAGMAs, create schema, instantiate AppConfig + SSEBroker + DownloadService, store on `app.state`, close DB on shutdown. Mount download and format routers under `/api`. Build `POST /api/downloads` (accepts `JobCreate` body + session_id dep, delegates to `DownloadService.enqueue`, returns `Job`), `GET /api/downloads` (returns jobs for session from DB), `DELETE /api/downloads/{id}` (cancels job), `GET /api/formats?url=` (delegates to `DownloadService.get_formats`). Write API tests via `httpx.AsyncClient` + `ASGITransport`: POST valid URL → 200 + Job JSON, GET downloads → list, DELETE → 200, GET formats → format list, POST invalid URL → error response.
  - Verify: `cd backend && python -m pytest tests/test_api.py -v && python -m pytest tests/ -v`
  - Done when: All four API endpoints return correct responses. Full test suite (`python -m pytest tests/ -v`) passes with 0 failures. The app starts via lifespan without errors.

## Files Likely Touched

- `backend/pyproject.toml`
- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/job.py`
- `backend/app/models/session.py`
- `backend/app/core/__init__.py`
- `backend/app/core/config.py`
- `backend/app/core/database.py`
- `backend/app/core/sse_broker.py`
- `backend/app/services/__init__.py`
- `backend/app/services/download.py`
- `backend/app/services/output_template.py`
- `backend/app/routers/__init__.py`
- `backend/app/routers/downloads.py`
- `backend/app/routers/formats.py`
- `backend/app/dependencies.py`
- `backend/app/middleware/__init__.py`
- `backend/tests/__init__.py`
- `backend/tests/conftest.py`
- `backend/tests/test_models.py`
- `backend/tests/test_config.py`
- `backend/tests/test_database.py`
- `backend/tests/test_sse_broker.py`
- `backend/tests/test_download_service.py`
- `backend/tests/test_output_template.py`
- `backend/tests/test_api.py`

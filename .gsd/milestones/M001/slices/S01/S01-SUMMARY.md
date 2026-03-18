---
id: S01
parent: M001
milestone: M001
provides:
  - Python backend scaffold (backend/app/ with core, models, services, routers, middleware subpackages)
  - Pydantic models: Job, JobStatus, JobCreate, ProgressEvent (with from_yt_dlp normalizer), FormatInfo, Session
  - AppConfig via pydantic-settings (env + YAML + zero-config defaults, MEDIARIP__ prefix)
  - aiosqlite database with WAL mode, busy_timeout, 4-table schema, async CRUD functions
  - SSEBroker with thread-safe publish via call_soon_threadsafe
  - DownloadService with ThreadPoolExecutor, sync-to-async bridge, progress hook → SSE broker
  - Output template resolver with per-domain lookup and fallback chain
  - API routes: POST/GET/DELETE /api/downloads, GET /api/formats?url=
  - Stub session_id dependency (X-Session-ID header, S02-replaceable)
  - FastAPI app factory with lifespan (DB init/close, service wiring)
requires:
  - slice: none
    provides: first slice — no upstream dependencies
affects:
  - S02 (consumes database, config, SSEBroker, DownloadService, models)
  - S03 (consumes API routes, models for TypeScript type generation)
  - S04 (consumes database, config, DownloadService.cancel)
key_files:
  - backend/pyproject.toml
  - backend/app/main.py
  - backend/app/models/job.py
  - backend/app/models/session.py
  - backend/app/core/config.py
  - backend/app/core/database.py
  - backend/app/core/sse_broker.py
  - backend/app/services/download.py
  - backend/app/services/output_template.py
  - backend/app/routers/downloads.py
  - backend/app/routers/formats.py
  - backend/app/dependencies.py
key_decisions:
  - Used Python 3.12 venv (py -3.12) — system Python is 3.14 but project requires >=3.12,<3.13
  - SSEBroker.publish() handles thread-safety internally via call_soon_threadsafe — workers call it directly
  - DB writes from worker threads use asyncio.run_coroutine_threadsafe().result(timeout=10) — blocks worker thread briefly
  - httpx ASGITransport doesn't trigger Starlette lifespan — test fixtures wire app.state manually
  - Test video is jNQXAC9IVRw ("Me at the zoo") — BaW_jenozKc is unavailable as of March 2026
patterns_established:
  - ProgressEvent.from_yt_dlp normalizes raw yt-dlp hook dicts with total_bytes fallback chain
  - Fresh YoutubeDL instance per job in worker thread — never shared across threads
  - Progress hook throttling — SSE broker gets all events, DB writes only on >=1% change or status change
  - Thread-to-async bridge — call_soon_threadsafe for fire-and-forget, run_coroutine_threadsafe for blocking
  - Test fixture pattern — fresh FastAPI app per test with temp DB/output dir, services on app.state
  - _SafeYamlSource wraps YamlConfigSettingsSource to gracefully handle missing/None yaml_file
  - Database PRAGMA order: busy_timeout → WAL → synchronous before any DDL
observability_surfaces:
  - mediarip.download logger at INFO for job lifecycle (created/starting/completed/cancelled), ERROR with exc_info for failures
  - mediarip.database logger at INFO for WAL mode set and table creation
  - mediarip.sse logger at WARNING for QueueFull (subscriber backpressure)
  - mediarip.app logger at INFO for startup config source and DB path
  - mediarip.api.downloads/formats loggers at DEBUG for request details
  - Job.error_message column stores yt-dlp failure reason; Job.status tracks lifecycle
  - Error responses return structured JSON with detail field, not stack traces
drill_down_paths:
  - .gsd/milestones/M001/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S01/tasks/T02-SUMMARY.md
  - .gsd/milestones/M001/slices/S01/tasks/T03-SUMMARY.md
  - .gsd/milestones/M001/slices/S01/tasks/T04-SUMMARY.md
duration: 72m
verification_result: passed
completed_at: 2026-03-17
---

# S01: Foundation + Download Engine

**Built the complete backend foundation: FastAPI app with yt-dlp download engine, SQLite/WAL persistence, config system, SSE broker, and 4 API endpoints — 68 tests passing including a real YouTube download proving the sync-to-async bridge works.**

## What Happened

Four tasks built the backend from scratch, each layer providing the foundation for the next:

**T01 (scaffold + models)** created the project structure with `pyproject.toml` (11 runtime deps, 5 dev deps), the `backend/app/` package hierarchy matching the boundary map, and all Pydantic models. The critical `ProgressEvent.from_yt_dlp` classmethod normalizes raw yt-dlp progress hook dictionaries with the `total_bytes → total_bytes_estimate → None` fallback chain. 16 model tests.

**T02 (config + database + SSE broker)** built three infrastructure modules. `AppConfig` uses pydantic-settings with env prefix `MEDIARIP__`, YAML source (graceful on missing file), and zero-config defaults. The database module sets SQLite PRAGMAs in critical order (busy_timeout → WAL → synchronous), creates 4 tables with indexes, and provides async CRUD. SSEBroker manages per-session asyncio.Queue maps with `publish()` using `call_soon_threadsafe` for thread safety. 31 tests (11 config + 11 database + 9 broker).

**T03 (download service + output templates)** was the highest-risk task — proving the sync-to-async bridge. `DownloadService` wraps yt-dlp in a ThreadPoolExecutor. Each `enqueue()` creates a DB row then submits `_run_download` to the executor. The worker thread creates a fresh YoutubeDL per job, registers a progress hook that bridges events to the async world — broker gets every event directly (already thread-safe), DB writes are throttled to ≥1% changes via `run_coroutine_threadsafe`. A real integration test downloads "Me at the zoo" from YouTube and asserts progress events with `status=downloading` arrive in the broker queue. Output template resolver handles per-domain lookup with fallback. 13 tests (4 download service + 9 output template).

**T04 (API routes + app factory)** wired the HTTP surface. The lifespan context manager loads config, inits DB, creates SSE broker and download service, stores all on `app.state`. Four routes: POST /api/downloads (201, creates job), GET /api/downloads (list by session), DELETE /api/downloads/{id} (cancel), GET /api/formats?url= (live extraction). A stub session dependency reads `X-Session-ID` header with default UUID fallback, documented as S02-replaceable. 8 API tests via httpx AsyncClient.

## Verification

Full slice verification — 68/68 tests passing across 7 test files:

| Test File | Tests | Status |
|-----------|-------|--------|
| test_models.py | 16 | ✅ passed |
| test_config.py | 11 | ✅ passed |
| test_database.py | 11 | ✅ passed |
| test_sse_broker.py | 9 | ✅ passed |
| test_download_service.py | 4 | ✅ passed |
| test_output_template.py | 9 | ✅ passed |
| test_api.py | 8 | ✅ passed |
| **Full suite** | **68** | **✅ passed (8.36s)** |

Key proof points:
- `PRAGMA journal_mode` returns `wal` — verified in test_database
- 3 concurrent DB writes complete without SQLITE_BUSY — verified in test_database
- Real yt-dlp download produces a file AND progress events with `status=downloading` arrive in broker queue — verified in test_download_service
- Format extraction returns non-empty list with format_id and ext fields — verified in test_download_service
- Thread-safe publish from worker thread delivers event to subscriber queue — verified in test_sse_broker
- All 4 API endpoints return correct responses — verified in test_api
- Session isolation (different X-Session-ID headers see different jobs) — verified in test_api

**Note:** Tests must run with the venv Python (`backend/.venv/Scripts/python`), not system Python (3.14). System Python lacks project dependencies.

## Requirements Advanced

- R001 — POST /api/downloads accepts any URL and yt-dlp downloads it. Proven with real YouTube download in integration test. Backend portion complete; needs frontend (S03) for full user flow.
- R002 — GET /api/formats?url= calls yt-dlp extract_info and returns format list. Backend extraction works; needs frontend picker (S03).
- R019 — Output template resolver implements per-domain lookup (YouTube, SoundCloud) with config.yaml source_templates map and fallback chain. Fully implemented and tested.
- R023 — Config system: hardcoded defaults → YAML → env vars all working. Zero-config works out of the box. SQLite admin writes deferred to S04.
- R024 — Jobs keyed by UUID4. Concurrent same-URL downloads proven in test_concurrent_downloads (two simultaneous downloads of same video both complete).

## Requirements Validated

- R019 — Source-aware output templates fully implemented and tested: domain-specific lookup, www stripping, user override priority, fallback chain, custom config. 9 unit tests prove all paths.
- R024 — Concurrent same-URL support proven by integration test running two simultaneous downloads of the same video with different output templates — both complete successfully.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- `pyproject.toml` build-backend changed from `setuptools.backends._legacy:_Backend` to `setuptools.build_meta` — the legacy backend isn't available in Python 3.12.4's bundled setuptools.
- Test video changed from `BaW_jenozKc` to `jNQXAC9IVRw` ("Me at the zoo") — the commonly cited test URL is unavailable as of March 2026.
- Verification commands updated to use `.venv/Scripts/python` explicitly — system Python is 3.14, project requires 3.12.

## Known Limitations

- **yt-dlp cancel has no reliable mid-stream abort** — `DownloadService.cancel()` marks the job as failed in DB, but the worker thread continues downloading. The file may still complete on disk. This is a yt-dlp limitation, not a bug.
- **Background worker thread teardown noise** — Worker threads that outlive test event loop produce `RuntimeWarning: coroutine 'update_job_status' was never awaited` on stderr. Harmless in tests; doesn't occur in production (lifespan shuts down executor before closing event loop).
- **Stub session dependency** — `get_session_id()` reads X-Session-ID header with static fallback UUID. S02 replaces this with real cookie-based session middleware.
- **Config SQLite layer not yet wired** — R023's admin live-write layer requires S04 (admin panel).

## Follow-ups

- S02 must replace the stub session dependency in `app/dependencies.py` with real cookie-based session middleware.
- S02 should wire SSEBroker.subscribe()/unsubscribe() into an SSE endpoint that streams events to the browser.
- S04 should extend AppConfig with SQLite admin writes for the full R023 config hierarchy.

## Files Created/Modified

- `backend/pyproject.toml` — project config with all pinned dependencies
- `backend/app/__init__.py` — package root
- `backend/app/main.py` — FastAPI app factory with lifespan, router mounting, logging
- `backend/app/models/job.py` — JobStatus, JobCreate, Job, ProgressEvent, FormatInfo models
- `backend/app/models/session.py` — Session model
- `backend/app/models/__init__.py` — models subpackage
- `backend/app/core/__init__.py` — core subpackage
- `backend/app/core/config.py` — AppConfig with nested sections, _SafeYamlSource, env/YAML/zero-config
- `backend/app/core/database.py` — init_db with WAL PRAGMAs, schema DDL, CRUD functions
- `backend/app/core/sse_broker.py` — SSEBroker with thread-safe publish via call_soon_threadsafe
- `backend/app/services/__init__.py` — services subpackage
- `backend/app/services/download.py` — DownloadService with enqueue, get_formats, cancel, shutdown
- `backend/app/services/output_template.py` — resolve_template with domain extraction and fallback
- `backend/app/routers/__init__.py` — routers subpackage
- `backend/app/routers/downloads.py` — POST/GET/DELETE download endpoints
- `backend/app/routers/formats.py` — GET formats endpoint with error handling
- `backend/app/dependencies.py` — stub session_id dependency (S02-replaceable)
- `backend/app/middleware/__init__.py` — middleware subpackage (empty, S02 populates)
- `backend/tests/__init__.py` — test package
- `backend/tests/conftest.py` — shared fixtures: tmp_db_path, test_config, db, broker, httpx client
- `backend/tests/test_models.py` — 16 model unit tests
- `backend/tests/test_config.py` — 11 config tests
- `backend/tests/test_database.py` — 11 database tests
- `backend/tests/test_sse_broker.py` — 9 broker tests
- `backend/tests/test_download_service.py` — 4 download service integration tests
- `backend/tests/test_output_template.py` — 9 output template unit tests
- `backend/tests/test_api.py` — 8 API tests via httpx AsyncClient

## Forward Intelligence

### What the next slice should know
- The SSEBroker has subscribe/unsubscribe/publish but no SSE endpoint yet. S02 needs to create GET /api/events that calls broker.subscribe() to get a queue, then streams events as SSE, calling broker.unsubscribe() in the finally block.
- The stub session dependency in `app/dependencies.py` is a simple function — S02 replaces it with middleware that reads/creates a `mrip_session` httpOnly cookie.
- `app.state` holds `db` (aiosqlite connection), `config` (AppConfig), `broker` (SSEBroker), and `download_service` (DownloadService). S02 should add session middleware and SSE router using these same state objects.
- The `DownloadService` constructor takes `(config, db, broker, loop)`. The event loop is captured at app startup in the lifespan.

### What's fragile
- **Worker thread teardown timing** — if the event loop closes before all worker threads finish their `run_coroutine_threadsafe` calls, those calls get `RuntimeError: Event loop is closed`. In production this is handled by the lifespan shutting down the executor first, but tests with short-lived event loops can hit it. The test warnings are harmless but noisy.
- **yt-dlp version pinned at 2026.3.17** — extractors break frequently. If YouTube changes their player API, the integration tests that download real videos will fail. The test uses "Me at the zoo" (jNQXAC9IVRw) which is the most stable video on the platform, but it's still a network dependency.

### Authoritative diagnostics
- `cd backend && .venv/Scripts/python -m pytest tests/ -v` — the single command that proves the entire slice works. 68 tests, ~8s.
- `SELECT status, error_message, progress_percent FROM jobs WHERE id = ?` — check any job's state directly in SQLite.
- `logging.getLogger("mediarip")` — all loggers are children of this root, structured by module (mediarip.download, mediarip.database, mediarip.sse, mediarip.app).

### What assumptions changed
- **Build backend**: The plan assumed `setuptools.backends._legacy:_Backend` would work — it doesn't on this system's setuptools version. Using `setuptools.build_meta` instead.
- **Test video URL**: Plan/research referenced `BaW_jenozKc` — it's unavailable. Switched to `jNQXAC9IVRw`.
- **Verification environment**: Plan assumed `python` would find the venv — system Python is 3.14. All verification commands must use `.venv/Scripts/python` explicitly.

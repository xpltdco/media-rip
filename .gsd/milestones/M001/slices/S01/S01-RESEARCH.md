# S01: Foundation + Download Engine — Research

**Date:** 2026-03-17
**Depth:** Deep research — high-risk slice, sync-to-async bridge, greenfield project with no existing code

## Summary

S01 is the foundation slice for a greenfield project. No source code exists yet — everything must be built from scratch using the comprehensive planning docs (PROJECT.md, ARCHITECTURE.md, STACK.md, PITFALLS.md) as specifications. The slice must deliver: project scaffolding with dependency management, SQLite database with WAL mode, a three-layer config system (defaults → YAML → env vars), Pydantic models for jobs/sessions/events, an SSE broker data structure for per-session queues, a download service wrapping yt-dlp in a ThreadPoolExecutor with `call_soon_threadsafe` progress bridging, and API routes for submitting downloads and probing formats.

The primary risk is the sync-to-async bridge: yt-dlp is synchronous, FastAPI is async, and progress events must flow from worker threads to asyncio queues without blocking the event loop or losing events. This is a well-documented pattern (`ThreadPoolExecutor` + `loop.call_soon_threadsafe`), but getting the event loop capture and hook wiring wrong produces silent event loss. The slice must prove this works with a real download test.

Secondary risks are SQLite write contention under concurrent downloads (solved by WAL mode + busy_timeout, but must be enabled before any schema work) and the config system's fourth layer (SQLite admin writes, which S04 builds on top of the pydantic-settings layers delivered here).

## Recommendation

Build bottom-up: project scaffold → database → config → models → SSE broker → download service → API routes → tests. Prove the sync-to-async bridge as early as possible by writing an integration test that runs a real yt-dlp download and asserts progress events arrive in an asyncio.Queue.

**Key architectural choices to follow** (from DECISIONS.md):
- D001: Python 3.12 + FastAPI
- D004: SQLite via aiosqlite with WAL mode
- D005: yt-dlp as library import, not subprocess
- D006: ThreadPoolExecutor + loop.call_soon_threadsafe
- D007: Opaque UUID in httpOnly cookie (session model only; middleware is S02)
- D008: HTTPBasic + bcrypt 5.0.0 direct (admin auth is S04, but the model should accommodate it)
- D009: Defaults → config.yaml → env vars → SQLite admin writes

**Naming convention:** Follow the boundary map in the roadmap (`app/core/`, `app/services/`, `app/routers/`, `app/models/`, `app/middleware/`), not the PROJECT.md structure (which uses `app/api/` and `app/core/` for everything). The roadmap boundary map is the contract S02 depends on.

## Implementation Landscape

### Key Files

All paths relative to `backend/` within the repo root.

- `backend/pyproject.toml` — Python project config with pinned dependencies (fastapi 0.135.1, uvicorn 0.42.0, yt-dlp 2026.3.17, aiosqlite 0.22.1, apscheduler 3.11.2, pydantic 2.12.5, pydantic-settings[yaml] 2.13.1, sse-starlette 3.3.3, bcrypt 5.0.0, python-multipart 0.0.22, PyYAML 6.0.2). Dev deps: httpx 0.28.1, pytest 9.0.2, anyio, ruff.
- `backend/app/__init__.py` — Package marker
- `backend/app/main.py` — FastAPI app factory with lifespan context manager (DB init/close, future scheduler start). Mounts routers. SPA fallback for frontend (future). **S01 delivers the skeleton only** — lifespan starts DB, mounts download + format routers.
- `backend/app/core/__init__.py` — Package marker
- `backend/app/core/database.py` — Singleton aiosqlite connection managed in lifespan. Must set `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA busy_timeout=5000` before schema creation. Schema: `sessions`, `jobs`, `config`, `unsupported_urls` tables. Provides async functions for job CRUD (create, get_by_id, get_by_session, update_status, update_progress, delete). Uses `aiosqlite.Row` row_factory for dict-like access. Indexes on `jobs(session_id, status)`, `jobs(completed_at)`, `sessions(last_seen)`.
- `backend/app/core/config.py` — `AppConfig` via pydantic-settings with `env_prefix="MEDIARIP"`, `env_nested_delimiter="__"`, `yaml_file` path. Nested models: `ServerConfig`, `DownloadsConfig`, `SessionConfig`, `PurgeConfig`, `UIConfig`, `ReportingConfig`, `AdminConfig`. `settings_customise_sources` override to order: env vars → YAML → init → defaults. This covers layers 1-3 of the config hierarchy. Layer 4 (SQLite admin writes) is S04's responsibility — S01 just reads config, never writes to SQLite config table.
- `backend/app/models/__init__.py` — Package marker
- `backend/app/models/job.py` — `JobStatus` enum (queued, extracting, downloading, completed, failed, expired), `JobCreate` (url, format_id, quality, output_template — all optional except url), `Job` Pydantic model matching the DB schema, `ProgressEvent` model (job_id, status, percent, speed, eta, downloaded_bytes, total_bytes, filename). ProgressEvent has a `from_yt_dlp(job_id, d)` classmethod that normalizes raw yt-dlp progress hook dicts.
- `backend/app/models/session.py` — `Session` Pydantic model (id, created_at, last_seen, job_count). Lightweight — S02 adds middleware that actually creates sessions.
- `backend/app/core/sse_broker.py` — `SSEBroker` class. Holds `dict[str, list[asyncio.Queue]]` mapping session_id → list of subscriber queues. Methods: `subscribe(session_id) → Queue`, `unsubscribe(session_id, queue)`, `publish(session_id, event)`. The `publish` method uses `loop.call_soon_threadsafe(queue.put_nowait, event)` — this is the thread-safe bridge. Must store a reference to the event loop captured at app startup. **S01 builds this data structure; S02 wires it to the SSE endpoint.**
- `backend/app/services/__init__.py` — Package marker
- `backend/app/services/download.py` — `DownloadService` class. Owns a `ThreadPoolExecutor(max_workers=config.downloads.max_concurrent)`. Methods: `enqueue(job_create, session_id) → Job` (creates DB row, submits to executor), `cancel(job_id)` (sets status=failed, relies on yt-dlp's internal cancellation — no reliable mid-stream abort exists), `get_formats(url) → list[FormatInfo]` (runs `extract_info(url, download=False)` in executor). The worker function `_run_download(job_id, url, opts)` creates a **fresh YoutubeDL instance per job** (never shared — Pitfall #1), registers a progress hook that calls `loop.call_soon_threadsafe(broker.publish, session_id, event)`, and handles errors by updating DB status to `failed`. The output template is resolved per-source domain using the `source_templates` config map (R019).
- `backend/app/services/output_template.py` — `resolve_template(url, user_override, config) → str`. Extracts domain from URL, looks up in `config.downloads.source_templates`, falls back to `*` default. If user provided an override in the job submission, use that instead. Simple utility, no I/O.
- `backend/app/routers/__init__.py` — Package marker
- `backend/app/routers/downloads.py` — `POST /api/downloads` (accepts JobCreate body + session_id from request state, delegates to DownloadService.enqueue), `GET /api/downloads` (returns jobs for current session from DB), `DELETE /api/downloads/{id}` (delegates to DownloadService.cancel). Session_id comes from `request.state.session_id` — **in S01, this must be a temporary dependency** since session middleware is S02. Use a header or query param fallback for testing, or a stub middleware.
- `backend/app/routers/formats.py` — `GET /api/formats?url={url}` (delegates to DownloadService.get_formats). Returns normalized format list with resolution, codec, ext, filesize estimate, format_id. Must handle `filesize: null` gracefully (common — R002 notes this).
- `backend/tests/` — Test directory with conftest.py (httpx AsyncClient + ASGITransport), test files for database, config, download service, and API routes.

### Build Order

The build order is strictly dependency-driven:

1. **Project scaffold** — `pyproject.toml`, directory structure, `__init__.py` files, `backend/app/main.py` skeleton with empty lifespan. This unblocks everything else.

2. **Pydantic models** (`app/models/`) — Job, Session, ProgressEvent, JobCreate, FormatInfo models. These are pure data classes with no dependencies. Every other module imports from here.

3. **Config system** (`app/core/config.py`) — AppConfig with pydantic-settings. Depends on nothing except pydantic. Creates the typed config that database, download service, and routes all need. Must be testable standalone: verify env var override works, verify YAML loading works, verify defaults are sane.

4. **Database** (`app/core/database.py`) — aiosqlite connection singleton, schema creation, WAL mode setup, job/session CRUD functions. Depends on models (for type hints) and config (for DB path). **Critical: WAL + busy_timeout must be the first PRAGMAs executed.** Test with concurrent writes to verify no SQLITE_BUSY errors.

5. **SSE Broker** (`app/core/sse_broker.py`) — Pure asyncio data structure. Depends only on the event loop reference. Test in isolation: create broker, subscribe, publish from a thread, verify event arrives in queue.

6. **Output template resolver** (`app/services/output_template.py`) — Pure function, depends only on config. Quick to build and test.

7. **Download service** (`app/services/download.py`) — The critical integration point. Depends on database, config, SSE broker, models, output_template. This is where the sync-to-async bridge lives. **Build and test this before API routes** — proving the bridge works is the slice's primary risk retirement.

8. **API routes** (`app/routers/downloads.py`, `app/routers/formats.py`) — Thin HTTP layer over the download service. Depends on everything above. Need a stub session_id mechanism for testing (S02 provides real middleware).

9. **Integration tests** — Real yt-dlp download test that proves events flow through the bridge. Format extraction test against a known URL. Concurrent download test (3 simultaneous) that proves WAL mode handles contention.

### Verification Approach

**Unit tests** (fast, no network):
- Config: env var override, YAML loading, defaults
- Models: ProgressEvent.from_yt_dlp with various yt-dlp dict shapes (including `total_bytes: None`)
- Database: CRUD operations, WAL mode verification (`PRAGMA journal_mode` returns `wal`), concurrent write test
- SSE Broker: subscribe/unsubscribe, publish from thread via call_soon_threadsafe
- Output template: domain matching, fallback to `*`, user override priority

**Integration tests** (require yt-dlp, may need network):
- `test_real_download` — Submit a short public-domain video URL → verify file appears in output dir, verify ProgressEvents were emitted with status=downloading and status=finished
- `test_format_extraction` — Call `get_formats` on a known URL → verify formats list is non-empty, each has format_id + ext
- `test_concurrent_downloads` — Start 3 downloads simultaneously → verify all complete without SQLITE_BUSY errors or progress cross-contamination

**API tests** (httpx AsyncClient):
- `POST /api/downloads` with valid URL → 200 + Job response
- `GET /api/downloads` → list of jobs
- `DELETE /api/downloads/{id}` → 200
- `GET /api/formats?url=...` → format list
- `POST /api/downloads` with invalid URL → appropriate error

**Smoke command:** `cd backend && python -m pytest tests/ -v`

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Config loading from YAML + env vars with nested delimiter | `pydantic-settings[yaml]` with `YamlConfigSettingsSource` | Handles `MEDIARIP__SECTION__KEY` → nested model natively via `env_nested_delimiter="__"`. Custom source priority via `settings_customise_sources`. No manual parsing needed. |
| Progress hook normalization | yt-dlp's built-in `progress_hooks` callback | Fires with structured dict containing `status`, `downloaded_bytes`, `total_bytes`, `speed`, `eta`, `filename`. Just normalize into Pydantic model. |
| Thread-safe event loop bridging | `asyncio.AbstractEventLoop.call_soon_threadsafe` | stdlib solution. The ONLY safe way to push data from a sync thread to an asyncio Queue. |
| SQLite async access | `aiosqlite` | asyncio bridge over stdlib sqlite3. Context manager pattern for connection lifecycle. |
| HTTP test client | `httpx.AsyncClient` with `ASGITransport` | FastAPI's recommended testing pattern. No real server needed. |

## Constraints

- **Python 3.12 only** — passlib breaks on 3.13; pinned in Dockerfile (D001)
- **yt-dlp as library, not subprocess** — structured progress hooks, no shell injection (D005)
- **Fresh YoutubeDL instance per job** — never shared across threads. YoutubeDL contains mutable state (cookies, temp files, logger) that corrupts under concurrent access (Pitfall #1)
- **ThreadPoolExecutor only** — YoutubeDL is not picklable, rules out ProcessPoolExecutor (D006, yt-dlp issue #9487)
- **WAL mode + busy_timeout BEFORE any schema work** — first PRAGMAs on DB init. Without this, 3+ concurrent downloads cause SQLITE_BUSY (Pitfall #7)
- **Event loop captured at startup** — `asyncio.get_event_loop()` in lifespan, stored on SSEBroker/DownloadService. Cannot call `get_event_loop()` inside a worker thread.
- **yt-dlp >= 2023.07.06** — CVE-2023-35934 cookie leak via redirect. Pin version in dependencies.
- **pydantic-settings env prefix** — Must use `MEDIARIP` prefix (no trailing underscore — pydantic-settings adds `_` between prefix and field). Double-underscore `__` for nesting: `MEDIARIP__DOWNLOADS__MAX_CONCURRENT`.
- **No automatic outbound network requests** — R020 hard constraint. No telemetry, no CDN, no update checks.
- **Session middleware is S02** — S01 routes need a temporary session_id mechanism. Use a dependency that reads `X-Session-ID` header or generates a default UUID for testing. S02 replaces this with real cookie middleware.

## Common Pitfalls

- **Shared YoutubeDL instance** — Progress percentages jump between jobs, `TypeError` on `None` fields. Create fresh instance per job inside the worker function. Never pass YoutubeDL across thread boundaries. (Pitfall #1)
- **Calling asyncio primitives from progress hook** — `asyncio.Queue.put_nowait()` directly from the hook raises `RuntimeError: no running event loop`. Must use `loop.call_soon_threadsafe(queue.put_nowait, data)`. (Pitfall #2)
- **`total_bytes` is frequently None** — yt-dlp returns `None` for subtitle downloads, live streams, and some sites. The `ProgressEvent.from_yt_dlp` normalizer must handle this: use `total_bytes_estimate` as fallback, calculate percent as 0 if both are None. (R002 notes, Pitfall checklist)
- **aiosqlite connection not closed properly** — Always use `async with aiosqlite.connect()` context manager. Unclosed connections in test teardown cause "database is locked" errors in subsequent tests.
- **pydantic-settings YAML file missing** — If `config.yaml` doesn't exist (zero-config mode), pydantic-settings must not crash. Set `yaml_file` only if the file exists, or handle `FileNotFoundError` in the custom source.
- **Progress hook throttling** — yt-dlp fires the hook very frequently (every few KB on fast connections). Writing every event to DB causes write contention. Throttle DB writes: update only when percent changes by ≥1% or status changes. SSE broker gets all events (they're cheap in-memory), but DB gets throttled writes.
- **Format extraction timeout** — `extract_info(url, download=False)` can take 3-10+ seconds for some sites. Must run in executor (not on event loop). Consider a timeout wrapper so a bad URL doesn't block a thread pool slot forever.

## Open Risks

- **Session ID mechanism for S01 testing** — S01 produces download/format routes that need `session_id`, but session middleware is S02. The stub mechanism (header-based fallback) must be cleanly replaceable. Risk: if the stub leaks into production code or makes assumptions S02 breaks.
- **yt-dlp version drift** — Pinning to 2026.3.17 ensures reproducibility, but site extractors break as YouTube/Vimeo update APIs. Users will report "can't download X" before a new image is published. Acceptable for v1.0 but needs an update strategy for v1.x.
- **Large playlist memory pressure** — A 200-video playlist creates 201 DB rows and 201 SSE events on reconnect replay. S01 should design the schema to handle this but cannot fully test it without the SSE endpoint (S02).
- **Config YAML missing vs. malformed** — Missing file = zero-config (expected). Malformed YAML = crash at startup. Need graceful error handling with clear error message pointing to the syntax problem.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| FastAPI | `wshobson/agents@fastapi-templates` (7.3K installs) | available — most popular; general FastAPI templates |
| FastAPI | `fastapi/fastapi@fastapi` (509 installs) | available — official repo skill |
| yt-dlp | `lwmxiaobei/yt-dlp-skill@yt-dlp` (559 installs) | available — yt-dlp specific |

None are critical for this work — the planning docs + library docs provide sufficient implementation guidance. Consider installing the FastAPI templates skill if future slices need more boilerplate generation.

## Sources

- yt-dlp progress hooks and extract_info API (source: [yt-dlp embedding docs](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp))
- pydantic-settings YAML + env nested delimiter (source: [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/))
- sse-starlette disconnect handling with CancelledError (source: [sse-starlette README](https://github.com/sysid/sse-starlette))
- aiosqlite async context manager pattern (source: [aiosqlite README](https://github.com/omnilib/aiosqlite))
- yt-dlp YoutubeDL not picklable — ThreadPoolExecutor required (source: [yt-dlp issue #9487](https://github.com/yt-dlp/yt-dlp/issues/9487))
- CVE-2023-35934 cookie leak via redirect (source: [GHSA-v8mc-9377-rwjj](https://github.com/yt-dlp/yt-dlp/security/advisories/GHSA-v8mc-9377-rwjj))
- SQLite WAL mode for concurrent write access (source: [SQLite WAL docs](https://www.sqlite.org/wal.html))
- APScheduler CronTrigger.from_crontab for cron string parsing (source: [APScheduler 3.x docs](https://apscheduler.readthedocs.io/en/3.x/))

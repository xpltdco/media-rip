# S02: SSE Transport + Session System

**Goal:** Wire live SSE event streaming and cookie-based session identity so that download progress flows from yt-dlp worker threads to the correct browser session, with reconnect replay and session isolation.
**Demo:** Open two browser tabs → each gets its own SSE stream scoped to their session cookie. Live progress events flow from yt-dlp workers through SSEBroker to the correct session's EventSource. Refresh a tab → SSE replays current state. Health endpoint responds.

## Must-Haves

- Session middleware that auto-creates `mrip_session` httpOnly cookie and populates `request.state.session_id`
- Session CRUD in database.py (create, get, update_last_seen)
- SSE endpoint (`GET /api/events`) streaming `init`, `job_update`, `job_removed`, `ping` events per session
- Reconnect replay: connecting after jobs exist → `init` event contains current non-terminal jobs
- Disconnect cleanup: generator `try/finally` calls `broker.unsubscribe()`, no zombie connections
- Session-mode-aware job queries: isolated filters by session_id, shared returns all, open uses fixed ID
- `GET /api/health` returning `{status, version, yt_dlp_version, uptime, queue_depth}`
- `GET /api/config/public` returning sanitized config (session mode, default theme — no admin credentials)
- All 68 existing S01 tests still pass after session middleware swap
- `job_removed` event published to SSE when a download is deleted

## Proof Level

- This slice proves: integration (SSE streaming from worker threads to HTTP clients, session isolation across cookies)
- Real runtime required: yes (async generators, SSE streaming, cookie handling)
- Human/UAT required: no (all provable via automated tests)

## Verification

- `cd backend && .venv/Scripts/python -m pytest tests/ -v` — all tests pass (S01 tests + new S02 tests)
- `backend/tests/test_session_middleware.py` — session cookie creation, reuse, invalid UUID handling, open mode bypass
- `backend/tests/test_sse.py` — init event replay, job_update streaming, disconnect cleanup, keepalive, job_removed event
- `backend/tests/test_health.py` — health endpoint fields, public config sanitization, session mode query layer
- SSE disconnect test: after generator exits, `broker._subscribers` has no leftover queues for the session
- Session isolation test: two different session cookies → GET /api/downloads returns different job sets
- Regression: all 68 S01 tests pass (route migration from header stub to middleware didn't break anything)

## Observability / Diagnostics

- Runtime signals: `mediarip.session` logger at INFO for session creation, DEBUG for session reuse/update_last_seen; `mediarip.sse` logger at INFO for SSE connect/disconnect with session_id, WARNING for QueueFull (already exists)
- Inspection surfaces: `GET /api/health` returns queue_depth, uptime, versions; `sessions` table in SQLite shows all active sessions with last_seen timestamps
- Failure visibility: SSE generator logs session_id on connect and disconnect — if a connection drops without the disconnect log, the finally block didn't fire (zombie). Health endpoint queue_depth > max_concurrent suggests workers are stuck.
- Redaction constraints: session UUIDs are opaque identifiers, not secrets. Admin password_hash must NOT appear in `GET /api/config/public`.

## Integration Closure

- Upstream surfaces consumed: `app/core/sse_broker.py` (subscribe/unsubscribe/publish), `app/core/database.py` (jobs CRUD, sessions table DDL), `app/core/config.py` (AppConfig.session.mode, session.timeout_hours), `app/models/job.py` (Job, ProgressEvent), `app/models/session.py` (Session), `app/services/download.py` (DownloadService), `app/dependencies.py` (replaced)
- New wiring introduced in this slice: SessionMiddleware added to app in main.py, SSE/health/system routers mounted, downloads router switched from Depends(get_session_id) to request.state.session_id, broker.publish called from delete endpoint for job_removed events
- What remains before the milestone is truly usable end-to-end: S03 (frontend SPA consuming SSE), S04 (admin panel), S05 (themes), S06 (Docker/CI)

## Tasks

- [x] **T01: Wire session middleware, DB CRUD, and migrate existing routes** `est:1h`
  - Why: Everything in S02 depends on `request.state.session_id` being populated by real cookie-based middleware instead of the X-Session-ID header stub. Session DB functions are needed for the middleware and for SSE replay. Existing routes and tests must be migrated atomically.
  - Files: `backend/app/middleware/session.py`, `backend/app/core/database.py`, `backend/app/dependencies.py`, `backend/app/routers/downloads.py`, `backend/app/main.py`, `backend/tests/conftest.py`, `backend/tests/test_session_middleware.py`, `backend/tests/test_api.py`
  - Do: Add session CRUD functions to database.py (create_session, get_session, update_session_last_seen). Build SessionMiddleware as Starlette BaseHTTPMiddleware — reads mrip_session cookie, looks up/creates session in DB, sets request.state.session_id, sets httpOnly cookie on response. Handle open mode (fixed session_id, no cookie). Replace get_session_id stub in dependencies.py with a thin function that reads request.state.session_id. Update downloads router to use the new dependency. Wire middleware into main.py. Update conftest.py client fixture to include middleware. Migrate test_api.py from X-Session-ID headers to cookie flow.
  - Verify: `cd backend && .venv/Scripts/python -m pytest tests/test_session_middleware.py tests/test_api.py -v` — new session tests pass AND all existing API tests pass
  - Done when: Requests without a cookie get one set (httpOnly, SameSite=Lax), requests with valid cookie reuse the session, session rows appear in DB, all 68+ tests pass

- [ ] **T02: Build SSE endpoint with replay, disconnect cleanup, and job_removed broadcasting** `est:1h`
  - Why: This is the core of S02 — the live event stream that S03's frontend will consume. Covers R003 (SSE progress stream) and R004 (reconnect replay). Also wires job_removed events so the frontend can remove deleted jobs in real-time.
  - Files: `backend/app/routers/sse.py`, `backend/app/routers/downloads.py`, `backend/app/core/database.py`, `backend/app/main.py`, `backend/tests/test_sse.py`
  - Do: Add `get_active_jobs_by_session()` to database.py (non-terminal jobs for replay). Build SSE router with GET /api/events — async generator subscribes to broker, sends `init` event with current jobs from DB, then yields `job_update` events from the queue, with 15s keepalive `ping`. Generator MUST use try/finally for broker.unsubscribe() and MUST NOT catch CancelledError. Use sse-starlette EventSourceResponse. Add broker.publish of job_removed event in downloads router delete endpoint. Mount SSE router in main.py. Write comprehensive tests: init replay, live job_update, disconnect cleanup (verify broker._subscribers empty after), keepalive timing, job_removed event delivery, session isolation (two sessions get different init payloads).
  - Verify: `cd backend && .venv/Scripts/python -m pytest tests/test_sse.py -v` — all SSE tests pass
  - Done when: SSE endpoint streams init event with current jobs on connect, live job_update events arrive from broker, disconnect fires cleanup (no zombie queues), job_removed events flow when downloads are deleted

- [ ] **T03: Add health endpoint, public config endpoint, and session-mode query layer** `est:45m`
  - Why: Closes R016 (health endpoint for monitoring tools), provides public config for S03 frontend, and proves session-mode-aware job queries for R007. These are the remaining S02 deliverables.
  - Files: `backend/app/routers/health.py`, `backend/app/routers/system.py`, `backend/app/core/database.py`, `backend/app/main.py`, `backend/tests/test_health.py`
  - Do: Build health router: GET /api/health returns {status: "ok", version: "0.1.0", yt_dlp_version: <from yt_dlp.version>, uptime: <seconds since startup>, queue_depth: <count of queued/downloading jobs>}. Capture start_time in lifespan. Build system router: GET /api/config/public returns {session_mode, default_theme, purge_enabled} — explicitly excludes admin.password_hash and admin.username. Add `get_all_jobs()` to database.py for shared mode. Add `get_jobs_by_session_mode()` helper that dispatches on config.session.mode (isolated → filter by session_id, shared → all jobs, open → all jobs). Mount both routers in main.py. Write tests: health returns correct fields with right types, version strings are non-empty, queue_depth reflects actual job count, public config excludes sensitive fields, session mode query dispatching works correctly for isolated/shared/open.
  - Verify: `cd backend && .venv/Scripts/python -m pytest tests/test_health.py -v` — all health/config/mode tests pass
  - Done when: GET /api/health returns valid JSON with version info, GET /api/config/public excludes admin credentials, session mode queries dispatch correctly, full test suite passes

## Files Likely Touched

- `backend/app/middleware/session.py` (new)
- `backend/app/routers/sse.py` (new)
- `backend/app/routers/health.py` (new)
- `backend/app/routers/system.py` (new)
- `backend/app/core/database.py` (modified — session CRUD, active jobs query, all jobs query, mode-aware query)
- `backend/app/dependencies.py` (modified — replace stub with request.state reader)
- `backend/app/routers/downloads.py` (modified — use new session dependency, publish job_removed)
- `backend/app/main.py` (modified — add middleware, mount new routers, capture start_time)
- `backend/tests/conftest.py` (modified — add middleware to test app, cookie helpers)
- `backend/tests/test_session_middleware.py` (new)
- `backend/tests/test_sse.py` (new)
- `backend/tests/test_health.py` (new)
- `backend/tests/test_api.py` (modified — migrate from header to cookie flow)

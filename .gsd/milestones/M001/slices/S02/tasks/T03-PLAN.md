---
estimated_steps: 6
estimated_files: 6
---

# T03: Add health endpoint, public config endpoint, and session-mode query layer

**Slice:** S02 — SSE Transport + Session System
**Milestone:** M001

## Description

Close the remaining S02 deliverables: the health endpoint (R016) for monitoring tools, the public config endpoint for the S03 frontend, and the session-mode-aware job query layer for R007.

The health endpoint is simple but valuable — Uptime Kuma and Docker healthchecks hit `GET /api/health`. The public config endpoint exposes only the safe subset of AppConfig that the frontend needs (session mode, default theme, purge status). The session mode query layer proves that isolated/shared/open modes produce different query results, even though full shared-mode SSE broadcasting is deferred to S04.

**Constraints:**
- `yt_dlp.version.__version__` gives the yt-dlp version string
- Capture `start_time` in the lifespan function so the health endpoint can compute uptime
- Public config must NOT expose admin.password_hash or admin.username
- Python 3.12 venv: `backend/.venv/Scripts/python`

## Steps

1. **Capture start_time in `backend/app/main.py` lifespan:**
   - At the start of the lifespan function: `app.state.start_time = datetime.now(timezone.utc)`
   - Import `datetime` and `timezone` from `datetime`

2. **Create `backend/app/routers/health.py`:**
   - Single route: `GET /api/health`
   - Returns JSON:
     ```json
     {
       "status": "ok",
       "version": "0.1.0",
       "yt_dlp_version": "<from yt_dlp.version.__version__>",
       "uptime": <seconds as float>,
       "queue_depth": <count of queued+downloading jobs>
     }
     ```
   - `uptime` = `(now - app.state.start_time).total_seconds()`
   - `queue_depth` = count of jobs with status in ("queued", "downloading", "extracting")
   - Add a database function `get_queue_depth(db) -> int` — `SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'downloading', 'extracting')`
   - Import `yt_dlp.version` for version string — wrap in try/except in case yt-dlp isn't installed in some test environments

3. **Create `backend/app/routers/system.py`:**
   - Single route: `GET /api/config/public`
   - Returns sanitized config dict:
     ```json
     {
       "session_mode": "isolated",
       "default_theme": "dark",
       "purge_enabled": false,
       "max_concurrent_downloads": 3
     }
     ```
   - Read from `request.app.state.config`
   - Explicitly construct the response dict from known safe fields — do NOT serialize the full AppConfig and strip fields (that's fragile if new sensitive fields are added later)

4. **Add session-mode-aware query helper to `backend/app/core/database.py`:**
   - `get_jobs_by_mode(db, session_id: str, mode: str) -> list[Job]`:
     - If mode == "isolated": call existing `get_jobs_by_session(db, session_id)`
     - If mode == "shared" or mode == "open": call `get_all_jobs(db)`
   - `get_all_jobs(db) -> list[Job]`: `SELECT * FROM jobs ORDER BY created_at`
   - `get_queue_depth(db) -> int`: count of non-terminal active jobs
   - This function can be used by the downloads router's GET endpoint and by the SSE replay to dispatch on session mode

5. **Mount routers in `backend/app/main.py`:**
   - Import health and system routers
   - `app.include_router(health_router, prefix="/api")`
   - `app.include_router(system_router, prefix="/api")`

6. **Write `backend/tests/test_health.py`:**
   - **Test: health endpoint returns correct structure** — GET /api/health returns 200 with all required fields, status == "ok", version is a non-empty string, uptime >= 0
   - **Test: health endpoint queue_depth reflects job count** — Create 2 queued jobs in DB, verify queue_depth == 2. Create a completed job, verify it's not counted.
   - **Test: yt_dlp_version is present** — Verify yt_dlp_version field is a non-empty string
   - **Test: public config returns safe fields** — GET /api/config/public returns session_mode, default_theme, purge_enabled, max_concurrent_downloads
   - **Test: public config excludes sensitive fields** — Response does NOT contain "password_hash", "username" keys (check raw JSON)
   - **Test: public config reflects actual config** — Create app with `AppConfig(session={"mode": "shared"}, ui={"default_theme": "cyberpunk"})`, verify response matches
   - **Test: get_jobs_by_mode isolated** — Create jobs for session A and B, call with mode="isolated" and session A, verify only A's jobs returned
   - **Test: get_jobs_by_mode shared** — Same setup, call with mode="shared", verify all jobs returned
   - **Test: get_jobs_by_mode open** — Same setup, call with mode="open", verify all jobs returned
   
   For endpoint tests, extend the conftest client fixture pattern (the fixture from T01 already has middleware and SSE router — add health and system routers).
   For database function tests, use the `db` fixture directly.

## Must-Haves

- [ ] GET /api/health returns status, version, yt_dlp_version, uptime, queue_depth (R016)
- [ ] GET /api/config/public returns session_mode, default_theme, purge_enabled — no admin credentials
- [ ] `get_jobs_by_mode()` dispatches correctly: isolated filters, shared/open returns all (R007 query layer)
- [ ] `get_queue_depth()` counts only active (non-terminal) jobs
- [ ] start_time captured in lifespan for uptime calculation
- [ ] Tests cover all endpoints and mode dispatching

## Verification

- `cd backend && .venv/Scripts/python -m pytest tests/test_health.py -v` — all health/config/mode tests pass
- `cd backend && .venv/Scripts/python -m pytest tests/ -v` — full suite passes (all S01 + S02 tests, no regressions)

## Inputs

- `backend/app/main.py` — After T02: has lifespan with app.state.config/db/broker/download_service, SessionMiddleware, SSE/downloads/formats routers
- `backend/app/core/database.py` — After T02: has job CRUD, session CRUD, get_active_jobs_by_session
- `backend/app/core/config.py` — AppConfig with session.mode, ui.default_theme, purge.enabled, downloads.max_concurrent, admin.password_hash/username
- `backend/tests/conftest.py` — After T02: client fixture with middleware, SSE router, session handling
- T01 and T02 summaries for any changes to conftest patterns or database signatures

## Expected Output

- `backend/app/routers/health.py` — GET /api/health endpoint (new file)
- `backend/app/routers/system.py` — GET /api/config/public endpoint (new file)
- `backend/app/core/database.py` — get_all_jobs(), get_jobs_by_mode(), get_queue_depth() added
- `backend/app/main.py` — start_time captured, health + system routers mounted
- `backend/tests/conftest.py` — health + system routers added to test app fixture
- `backend/tests/test_health.py` — 9+ tests covering health, public config, session mode queries (new file)

---
id: T03
parent: S02
milestone: M001
provides:
  - GET /api/health returning status, version, yt_dlp_version, uptime, queue_depth (R016)
  - GET /api/config/public returning session_mode, default_theme, purge_enabled, max_concurrent_downloads — no admin credentials
  - get_all_jobs(), get_jobs_by_mode(), get_queue_depth() in database.py
  - start_time captured in lifespan for uptime calculation
  - 18 tests (36 with anyio dual-backend) covering health, public config, mode dispatching, queue depth
key_files:
  - backend/app/routers/health.py
  - backend/app/routers/system.py
  - backend/app/core/database.py
  - backend/app/main.py
  - backend/tests/test_health.py
  - backend/tests/conftest.py
key_decisions:
  - Public config endpoint explicitly constructs the response dict from known-safe fields rather than serializing AppConfig and stripping sensitive fields — safer when new sensitive fields are added later
  - yt_dlp.version imported at module level with try/except so tests that don't install yt-dlp still work (returns "unknown")
  - get_jobs_by_mode() dispatches to existing get_jobs_by_session() for isolated mode and get_all_jobs() for shared/open — simple function dispatch, no polymorphism needed
patterns_established:
  - Health endpoint pattern: read start_time from app.state, compute uptime as delta seconds
  - Public config pattern: whitelist of safe fields from AppConfig, never blacklist
  - Database mode dispatch: single helper function that routes on mode string
observability_surfaces:
  - GET /api/health — queue_depth > max_concurrent suggests stuck workers; uptime resets indicate unexpected restarts
  - GET /api/config/public — frontend can adapt UI based on session mode and theme without a separate config fetch
duration: 15m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T03: Add health endpoint, public config endpoint, and session-mode query layer

**Added health and public config endpoints, session-mode-aware query dispatching, and 18 tests — 122/122 full suite passing, zero regressions.**

## What Happened

1. **Health endpoint** (`routers/health.py`): `GET /api/health` returns `{status, version, yt_dlp_version, uptime, queue_depth}`. Uptime computed from `app.state.start_time` (set in lifespan). Queue depth counts non-terminal jobs via new `get_queue_depth()`. yt-dlp version resolved once at import with fallback for environments without yt-dlp.

2. **Public config endpoint** (`routers/system.py`): `GET /api/config/public` returns `{session_mode, default_theme, purge_enabled, max_concurrent_downloads}`. Explicitly whitelists safe fields — admin credentials never touch this response.

3. **Database helpers** (`database.py`): Added `get_all_jobs()` (all jobs across sessions), `get_jobs_by_mode(db, session_id, mode)` (dispatches isolated → session-filtered, shared/open → all), and `get_queue_depth(db)` (COUNT of non-terminal jobs).

4. **App wiring** (`main.py`): Captured `start_time` on app.state in lifespan. Mounted health and system routers under `/api`.

5. **Test fixture update** (`conftest.py`): Health and system routers added to test client app. `start_time` set on test app state.

6. **Tests** (`test_health.py`): 18 tests across 6 classes covering health endpoint structure, semver format, queue_depth accuracy with active/terminal jobs, public config fields, sensitive field exclusion, config reflection with custom values, default values, get_all_jobs, get_jobs_by_mode for all three modes, and get_queue_depth for all status combinations.

## Verification

- `pytest tests/test_health.py -v` — 36/36 passed (18 tests × 2 anyio backends)
- `pytest tests/ -v` — 122/122 passed in 10.2s (full regression, zero failures)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `pytest tests/test_health.py -v` | 0 | ✅ pass | 1.41s |
| 2 | `pytest tests/ -v` | 0 | ✅ pass | 10.20s |

## Diagnostics

- **Health probe**: `curl http://localhost:8000/api/health` — quick check for monitoring tools
- **Queue depth anomaly**: `queue_depth > downloads.max_concurrent` means workers may be stuck
- **Uptime reset**: uptime << expected means unexpected restarts
- **Config audit**: `curl http://localhost:8000/api/config/public | grep -c password` should be 0

## Deviations

None. Implementation matches the plan exactly.

## Known Issues

- Pre-existing background thread teardown noise (RuntimeWarning on `update_job_status` coroutine, sqlite3.ProgrammingError on closed database) — documented in T01/T02.
- Pre-existing httpx deprecation warning on per-request cookies — documented in T01.

## Files Created/Modified

- `backend/app/routers/health.py` — new, GET /api/health endpoint
- `backend/app/routers/system.py` — new, GET /api/config/public endpoint
- `backend/app/core/database.py` — added get_all_jobs(), get_jobs_by_mode(), get_queue_depth()
- `backend/app/main.py` — start_time in lifespan, health + system routers mounted
- `backend/tests/conftest.py` — health + system routers in test app, start_time on state
- `backend/tests/test_health.py` — new, 18 tests (36 with dual backend)

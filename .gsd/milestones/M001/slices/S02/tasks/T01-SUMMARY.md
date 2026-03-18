---
id: T01
parent: S02
milestone: M001
provides:
  - Cookie-based SessionMiddleware replacing X-Session-ID header stub
  - Session CRUD functions (create_session, get_session, update_session_last_seen)
  - Migrated API tests from header-based to cookie-based session flow
key_files:
  - backend/app/middleware/session.py
  - backend/app/core/database.py
  - backend/app/dependencies.py
  - backend/app/main.py
  - backend/tests/test_session_middleware.py
  - backend/tests/test_api.py
  - backend/tests/conftest.py
key_decisions:
  - Set cookie on every response (not just new sessions) to refresh Max-Age on each request
  - When a valid UUID cookie has no matching DB row, recreate the session with that UUID rather than generating a new one — preserves client-side cookie identity
patterns_established:
  - SessionMiddleware on BaseHTTPMiddleware sets request.state.session_id for all downstream handlers
  - Test apps using SessionMiddleware must import Request at module level (not inside a function) when from __future__ import annotations is active — otherwise FastAPI can't resolve the Request annotation and returns 422
observability_surfaces:
  - mediarip.session logger — INFO on new session creation, DEBUG on session reuse
  - sessions table in SQLite — SELECT * FROM sessions ORDER BY last_seen DESC
  - Set-Cookie header on every HTTP response (mrip_session with httpOnly, SameSite=Lax, Path=/, Max-Age)
duration: 25m
verification_result: passed
completed_at: 2026-03-17T22:20:00-05:00
blocker_discovered: false
---

# T01: Wire session middleware, DB CRUD, and migrate existing routes

**Added cookie-based SessionMiddleware with session CRUD, replaced X-Session-ID header stub, and migrated all existing tests to cookie flow — 75 tests pass, zero regressions.**

## What Happened

Added three session CRUD functions to `database.py` following the existing job CRUD pattern: `create_session`, `get_session`, `update_session_last_seen`. All use ISO UTC timestamps.

Built `SessionMiddleware` as a Starlette `BaseHTTPMiddleware` in `backend/app/middleware/session.py`. The middleware reads the `mrip_session` cookie, validates it as UUID4 format, looks up or creates a session in the DB, and sets `request.state.session_id`. In "open" mode, it skips all cookie handling and sets the fixed session ID `"open"`. The cookie is set on every response (not just new sessions) to refresh `Max-Age`.

Replaced the `get_session_id` stub in `dependencies.py` — it now simply reads `request.state.session_id` set by the middleware. No route signatures changed; the `Depends(get_session_id)` pattern is preserved.

Wired the middleware into `main.py` and the test `conftest.py` client fixture. Migrated all 8 existing `test_api.py` tests from `X-Session-ID` headers to the cookie flow. The session isolation test now uses two separate `AsyncClient` instances (each gets its own cookie jar) to prove jobs don't leak between sessions.

Wrote 6 new tests in `test_session_middleware.py` covering: new session creation, cookie reuse with last_seen update, invalid cookie handling, orphaned UUID recreation, open mode bypass, and configurable Max-Age.

## Verification

- `pytest tests/test_session_middleware.py -v` — 6/6 passed
- `pytest tests/test_api.py -v` — 9/9 passed (original 8 migrated + 1 new cookie-sets test)
- `pytest tests/ -v` — 75/75 passed, 0 failures, 9 warnings (all pre-existing yt-dlp teardown warnings)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `pytest tests/test_session_middleware.py -v` | 0 | ✅ pass | 0.22s |
| 2 | `pytest tests/test_api.py -v` | 0 | ✅ pass | 2.53s |
| 3 | `pytest tests/ -v` | 0 | ✅ pass | 9.37s |

## Diagnostics

- **Session state**: `SELECT * FROM sessions ORDER BY last_seen DESC` in SQLite
- **Cookie inspection**: Any HTTP response includes `Set-Cookie: mrip_session=<uuid>; HttpOnly; Max-Age=259200; Path=/; SameSite=lax`
- **Failure mode**: If middleware fails to set `request.state.session_id`, downstream routes raise `AttributeError` on `request.state.session_id` — intentionally loud
- **Logs**: `mediarip.session` at INFO for new sessions, DEBUG for reuse

## Deviations

- Test file `test_session_middleware.py` imports `FastAPI` and `Request` at module level rather than inside the `_build_test_app` helper. When `from __future__ import annotations` is active, lazy imports inside functions cause FastAPI to fail to resolve the `Request` type annotation, resulting in 422 errors. This is a Python 3.12 + PEP 563 interaction.

## Known Issues

- httpx deprecation warning on per-request `cookies=` parameter in two middleware tests. Functional, not blocking — httpx is moving toward client-level cookie jars.

## Files Created/Modified

- `backend/app/middleware/session.py` — new SessionMiddleware (BaseHTTPMiddleware, cookie-based)
- `backend/app/core/database.py` — added create_session, get_session, update_session_last_seen
- `backend/app/dependencies.py` — replaced X-Session-ID stub with request.state.session_id reader
- `backend/app/main.py` — wired SessionMiddleware, imported from app.middleware.session
- `backend/tests/conftest.py` — added SessionMiddleware to test client fixture
- `backend/tests/test_session_middleware.py` — new, 6 tests covering all middleware paths
- `backend/tests/test_api.py` — migrated from X-Session-ID headers to cookie-based sessions (9 tests)

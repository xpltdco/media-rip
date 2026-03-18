---
estimated_steps: 8
estimated_files: 8
---

# T01: Wire session middleware, DB CRUD, and migrate existing routes

**Slice:** S02 — SSE Transport + Session System
**Milestone:** M001

## Description

Build the cookie-based session middleware that replaces the X-Session-ID header stub from S01. This is the foundation for everything else in S02 — the SSE endpoint, health endpoint, and all route handlers depend on `request.state.session_id` being populated by real middleware.

The middleware reads/creates `mrip_session` httpOnly cookies, manages session rows in SQLite, and supports the "open" session mode (fixed session_id, no cookie). After building the middleware, migrate the existing downloads router and all tests from the header stub to the cookie flow.

**Important constraints:**
- Use Starlette `BaseHTTPMiddleware`. The research flags a risk with streaming responses — if `request.state` isn't accessible inside SSE generators after middleware runs, T02 will fall back to a `Depends()` approach. But for this task, the middleware approach is correct and testable with normal request/response cycles.
- Session cookie: `mrip_session`, httpOnly, SameSite=Lax, Path=/, Max-Age based on `config.session.timeout_hours`.
- The `sessions` table DDL already exists in database.py from S01. Only CRUD functions are needed.
- Python 3.12 venv: all commands use `backend/.venv/Scripts/python`.

## Steps

1. **Add session CRUD to `backend/app/core/database.py`:**
   - `create_session(db, session_id: str) -> None` — INSERT into sessions table with id, created_at (ISO UTC), last_seen (same as created_at)
   - `get_session(db, session_id: str) -> dict | None` — SELECT by id, return row as dict or None
   - `update_session_last_seen(db, session_id: str) -> None` — UPDATE last_seen to now (ISO UTC)
   - These are simple CRUD functions following the same pattern as existing job CRUD

2. **Create `backend/app/middleware/__init__.py`** if it doesn't exist (it should — S01 created it as empty). Create `backend/app/middleware/session.py`:
   - Import `BaseHTTPMiddleware` from `starlette.middleware.base`
   - `SessionMiddleware(BaseHTTPMiddleware)` with `async def dispatch(self, request, call_next)`
   - Read `mrip_session` cookie from `request.cookies.get("mrip_session")`
   - Access config via `request.app.state.config` and db via `request.app.state.db`
   - If config.session.mode == "open": set `request.state.session_id = "open"`, call_next, return (no cookie)
   - If cookie present and is valid UUID4 format: look up with `get_session(db, session_id)`
     - Found → `update_session_last_seen(db, session_id)`, set `request.state.session_id`
     - Not found → create new session with that ID (cookie was valid UUID but expired from DB), set request.state
   - If cookie missing or not valid UUID: generate `uuid.uuid4()`, `create_session(db, new_id)`, set `request.state.session_id`
   - Call `response = await call_next(request)`
   - If not open mode: set `Set-Cookie` on response — `mrip_session={session_id}; HttpOnly; SameSite=Lax; Path=/; Max-Age={timeout_hours * 3600}`
   - Return response
   - Logger: `mediarip.session` at INFO for new session creation, DEBUG for session reuse

3. **Update `backend/app/dependencies.py`:**
   - Replace the stub `get_session_id` with: `def get_session_id(request: Request) -> str: return request.state.session_id`
   - Remove the `_DEFAULT_SESSION_ID` constant
   - This preserves the `Depends(get_session_id)` pattern in routes so no route signature changes are needed

4. **Wire middleware into `backend/app/main.py`:**
   - Import `SessionMiddleware` from `app.middleware.session`
   - Add `app.add_middleware(SessionMiddleware)` after app creation but before router inclusion
   - No other changes needed — the middleware accesses `app.state.db` and `app.state.config` set by lifespan

5. **Update `backend/tests/conftest.py`:**
   - In the `client` fixture, add `SessionMiddleware` to the test app: `test_app.add_middleware(SessionMiddleware)`
   - Import SessionMiddleware from `app.middleware.session`
   - The middleware needs `app.state.db` and `app.state.config` which are already wired

6. **Update `backend/tests/test_api.py`:**
   - Remove all `X-Session-ID` header usage from test requests
   - Instead, the first request to any endpoint will auto-create a session via middleware and set a cookie
   - For session isolation tests: make a request with client A (gets cookie A), then create a *separate* client or manually set a different cookie to simulate client B
   - The httpx client should automatically handle cookie persistence within a test if using `cookies` parameter
   - Verify: first request returns Set-Cookie header with mrip_session, subsequent requests reuse the session

7. **Write `backend/tests/test_session_middleware.py`:**
   - Test: request without cookie → response has Set-Cookie with mrip_session, httpOnly, SameSite=Lax
   - Test: request with valid mrip_session cookie → response reuses session, session last_seen updated in DB
   - Test: request with invalid (non-UUID) cookie → new session created, new cookie set
   - Test: request with UUID cookie not in DB → session created with that UUID
   - Test: open mode → no cookie set, request.state.session_id == "open"
   - For open mode test: create a test app with `AppConfig(session={"mode": "open"})` and verify
   - Use the same fixture pattern as conftest.py (fresh FastAPI app, temp DB, httpx AsyncClient)

8. **Run full test suite and verify no regressions:**
   - `cd backend && .venv/Scripts/python -m pytest tests/ -v`
   - All 68 S01 tests + new session middleware tests must pass

## Must-Haves

- [ ] Session CRUD functions in database.py (create_session, get_session, update_session_last_seen)
- [ ] SessionMiddleware creates cookies for new sessions, reuses existing cookies, handles open mode
- [ ] Cookie attributes: httpOnly, SameSite=Lax, Path=/, Max-Age from config
- [ ] dependencies.py reads request.state.session_id (middleware-set)
- [ ] All existing API tests pass with cookie-based sessions (no X-Session-ID header)
- [ ] New session middleware tests cover: new session, reuse, invalid cookie, open mode

## Verification

- `cd backend && .venv/Scripts/python -m pytest tests/test_session_middleware.py -v` — all session middleware tests pass
- `cd backend && .venv/Scripts/python -m pytest tests/test_api.py -v` — all existing API tests still pass
- `cd backend && .venv/Scripts/python -m pytest tests/ -v` — full suite passes (68+ tests, no regressions)

## Observability Impact

- Signals added: `mediarip.session` logger — INFO on new session creation (includes session_id), DEBUG on session reuse with last_seen update
- How a future agent inspects this: query `SELECT * FROM sessions ORDER BY last_seen DESC` in SQLite to see all sessions; check `Set-Cookie` header on any HTTP response
- Failure state exposed: if middleware fails to set `request.state.session_id`, downstream routes will raise `AttributeError` on `request.state.session_id` — this is intentionally loud rather than silently falling back

## Inputs

- `backend/app/core/database.py` — existing job CRUD functions, sessions table DDL (already created by init_db)
- `backend/app/dependencies.py` — stub get_session_id that reads X-Session-ID header (being replaced)
- `backend/app/routers/downloads.py` — uses Depends(get_session_id), no route signature changes needed
- `backend/app/main.py` — lifespan sets app.state.db and app.state.config
- `backend/tests/conftest.py` — client fixture pattern (fresh app, temp DB, httpx AsyncClient)
- `backend/tests/test_api.py` — 8 existing tests using X-Session-ID header (must migrate to cookies)
- `backend/app/core/config.py` — AppConfig.session.mode ("isolated"/"shared"/"open"), session.timeout_hours (72)

## Expected Output

- `backend/app/core/database.py` — 3 new session CRUD functions added
- `backend/app/middleware/session.py` — SessionMiddleware (new file)
- `backend/app/dependencies.py` — stub replaced with request.state reader
- `backend/app/main.py` — middleware wired
- `backend/tests/conftest.py` — middleware added to test client fixture
- `backend/tests/test_session_middleware.py` — 5+ session middleware tests (new file)
- `backend/tests/test_api.py` — migrated from X-Session-ID to cookie flow

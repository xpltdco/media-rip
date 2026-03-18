# S02: SSE Transport + Session System — Research

**Date:** 2026-03-17

## Summary

S02 wires the live event stream and session identity that S01 left stubbed. The SSEBroker (subscribe/unsubscribe/publish) already works and is proven thread-safe. The `sessions` table exists. What's missing: the HTTP layer that turns those primitives into a real SSE endpoint with reconnect replay, a middleware that auto-creates `mrip_session` cookies and populates `request.state.session_id`, session-mode-aware job queries (isolated/shared/open), a health endpoint, and a public config endpoint.

All building blocks exist — this is integration work on top of well-understood libraries (`sse-starlette`, `FastAPI` middleware, `aiosqlite`). The main risk is the SSE disconnect/cleanup path: the generator must use `try/finally` to call `broker.unsubscribe()`, and must re-raise `CancelledError` (not swallow it). The PITFALLS doc calls this out explicitly as Pitfall 3 (zombie connections).

## Recommendation

Build in this order: (1) session middleware + DB CRUD, (2) SSE endpoint with replay, (3) session-mode-aware query functions, (4) health + public config endpoints. Session middleware first because the SSE endpoint and all existing routes depend on `request.state.session_id` being populated by middleware rather than the header stub. The SSE endpoint is the riskiest piece — it needs disconnect handling, replay, and keepalive. Health and config endpoints are trivial.

Replace `dependencies.get_session_id()` with `request.state.session_id` set by the new middleware. Existing routes that use `Depends(get_session_id)` switch to reading `request.state.session_id` directly (or a thin dependency that reads it from `request.state`). Existing tests that pass `X-Session-ID` header will need updating to either use the cookie flow or a test middleware that sets `request.state.session_id`.

## Implementation Landscape

### Key Files

**Existing (consumed by S02):**
- `backend/app/core/sse_broker.py` — SSEBroker with subscribe/unsubscribe/publish. Complete, proven in 9 tests. SSE endpoint calls `subscribe()` to get a queue, yields events from it, calls `unsubscribe()` in finally block.
- `backend/app/core/database.py` — Has `sessions` table DDL and `jobs` CRUD. Missing: session CRUD functions (create, get, update_last_seen) and session-mode-aware job queries.
- `backend/app/core/config.py` — `AppConfig` with `session.mode` (default "isolated") and `session.timeout_hours` (default 72). Config is on `app.state.config`.
- `backend/app/dependencies.py` — Stub `get_session_id()` reads `X-Session-ID` header. S02 replaces this.
- `backend/app/main.py` — Lifespan stores `config`, `db`, `broker`, `download_service` on `app.state`. S02 adds session middleware and new routers here.
- `backend/app/models/job.py` — Job, ProgressEvent, FormatInfo models. SSE events serialize these.
- `backend/app/models/session.py` — Session model with id, created_at, last_seen, job_count. Used for API responses.
- `backend/app/routers/downloads.py` — Uses `Depends(get_session_id)`. Must switch to middleware-provided session_id.
- `backend/tests/conftest.py` — Client fixture builds a fresh FastAPI app with temp DB. S02 tests need this pattern extended to include session middleware.

**New (created by S02):**
- `backend/app/middleware/session.py` — SessionMiddleware: reads `mrip_session` cookie → looks up in DB → creates if missing → sets `request.state.session_id` → updates `last_seen`. Sets httpOnly, SameSite=Lax, Path=/ cookie on response. In "open" session mode, sets a fixed session_id (no cookie).
- `backend/app/routers/sse.py` — `GET /api/events` SSE endpoint. Async generator subscribes to broker, replays current job state from DB as `init` event, then yields live events. Uses `try/finally` for cleanup. Keepalive ping every 15s. `retry: 5000` in stream.
- `backend/app/routers/health.py` — `GET /api/health` returning `{status, version, yt_dlp_version, uptime, queue_depth}`.
- `backend/app/routers/system.py` — `GET /api/config/public` returning sanitized config (session mode, default theme, purge enabled — no admin credentials).

**Modified:**
- `backend/app/core/database.py` — Add session CRUD: `create_session()`, `get_session()`, `update_session_last_seen()`. Add `get_all_jobs()` for shared/open mode. Add `get_active_jobs_by_session()` for SSE replay (non-terminal jobs).
- `backend/app/dependencies.py` — Replace stub with a dependency that reads `request.state.session_id` (set by middleware). Or remove entirely and have routes read `request.state.session_id` directly.
- `backend/app/main.py` — Add `app.add_middleware(SessionMiddleware)` and include new routers (sse, health, system).
- `backend/app/routers/downloads.py` — Switch from `Depends(get_session_id)` to `request.state.session_id`. For shared mode, `GET /api/downloads` returns all jobs.
- `backend/tests/conftest.py` — Client fixture adds session middleware to test app. May need a helper to set session cookies in test requests.
- `backend/tests/test_api.py` — Tests switch from `X-Session-ID` header to cookie-based session flow.

### SSE Event Contract

Events yielded by the SSE generator use sse-starlette's dict format:

```python
{"event": "init", "data": json.dumps({"jobs": [job.model_dump() for job in jobs]})}
{"event": "job_update", "data": json.dumps(progress_event.model_dump())}
{"event": "job_removed", "data": json.dumps({"job_id": job_id})}
{"event": "error", "data": json.dumps({"message": str})}
{"event": "ping", "data": ""}
```

The `init` event replays all non-terminal jobs for the session on connect. `job_update` wraps ProgressEvent from the broker queue. `job_removed` fires when a job is deleted. `ping` is a keepalive every 15s of inactivity.

Note: The broker currently publishes raw `ProgressEvent` objects from download workers. The SSE generator needs to wrap these into the `{"event": "job_update", "data": ...}` envelope. The broker should also support publishing `job_removed` events when `DELETE /api/downloads/{id}` is called — this requires the downloads router to publish to the broker after deleting.

### Session Middleware Design

```
Request → SessionMiddleware:
  1. Read `mrip_session` cookie
  2. If present and valid UUID → look up in sessions table
     - Found → update last_seen, set request.state.session_id
     - Not found → create new session row, set cookie
  3. If missing → generate UUID4, create session row, set cookie on response
  4. If config.session.mode == "open" → skip cookie, use fixed session_id

Response:
  - Set-Cookie: mrip_session=<uuid>; HttpOnly; SameSite=Lax; Path=/; Max-Age=<timeout_hours * 3600>
```

The middleware is a Starlette `BaseHTTPMiddleware` subclass. It accesses `app.state.db` and `app.state.config` for DB lookups and session mode.

### Session Mode Logic

- **isolated** (default): Jobs queried by `session_id`. Each browser sees only its own jobs. SSE stream scoped to session.
- **shared**: Jobs queried without session filter — all sessions see all jobs. SSE stream shows all events (broker needs to broadcast or use a wildcard).
- **open**: No session tracking. All requests use a fixed session_id. No cookie set.

Shared mode is the trickiest for SSE: the broker is keyed by session_id, but shared mode needs all events to reach all subscribers. Two approaches:
1. Broker publishes to a `"__all__"` channel that shared-mode subscribers listen on — requires broker change.
2. Download workers publish to both the job's session_id AND a broadcast channel — messy.
3. **Simplest: in shared mode, the SSE generator subscribes to a well-known `"__shared__"` session_id, and the download service publishes to `"__shared__"` when mode is shared.** This requires checking session mode at publish time.

Recommendation: For S02, implement isolated mode fully and add the shared/open mode hooks. The actual multi-mode switching can be proven with a test that changes config and verifies query behavior. Full shared-mode SSE broadcasting can be deferred to S04 if needed — R007 says "operator selects session mode server-wide" which implies it's a deployment-time choice, not a runtime toggle.

### Build Order

1. **Session DB CRUD + middleware** — Unblocks everything. Write `create_session`, `get_session`, `update_session_last_seen` in database.py. Write SessionMiddleware. Wire into main.py. Update dependencies.py.
2. **SSE endpoint with replay** — The riskiest piece. Write the async generator with subscribe → replay → live stream → cleanup pattern. Test disconnect handling (generator finally block fires, queue removed from broker). Test replay (connect after job created → init event contains the job).
3. **Update existing routes + tests** — Switch downloads router from header stub to middleware session_id. Update test fixtures and test_api.py.
4. **Health + public config endpoints** — Straightforward. Health: capture `start_time` in lifespan, return uptime delta. Public config: return sanitized subset of AppConfig.
5. **Session mode tests** — Test isolated vs shared query behavior. Test open mode skips cookies.

### Verification Approach

**Unit tests:**
- Session middleware: request without cookie gets one set, request with valid cookie reuses session, request with invalid UUID gets new session
- SSE generator: connect → receives init event with current jobs, disconnect → broker.unsubscribe called, keepalive ping fires after timeout
- Session mode: isolated mode filters by session_id, shared mode returns all jobs
- Health endpoint: returns expected fields with correct types
- Public config: returns session mode and theme, does NOT include admin password_hash

**Integration test:**
- Start a download via POST, connect to SSE endpoint, verify `job_update` events arrive with progress data
- Connect to SSE after a job exists → verify `init` event replays the job
- Two different sessions → each SSE stream only sees its own jobs (session isolation proof)

**Commands:**
```bash
cd backend && .venv/Scripts/python -m pytest tests/ -v
```

The slice is proven when:
1. SSE endpoint streams real events from a download worker to a subscriber
2. Disconnect cleanup fires (broker queue removed)
3. Replay works (connect after job → init contains job)
4. Session isolation: two sessions see different job sets
5. Health endpoint returns valid JSON with version info
6. All existing S01 tests still pass (no regression from session middleware swap)

## Constraints

- `sse-starlette==3.3.3` is already pinned in pyproject.toml — use `EventSourceResponse` directly, don't wrap it.
- SSEBroker is keyed by session_id string. Shared mode needs a strategy for cross-session event delivery (recommend: defer full shared-mode SSE to S04, prove the query layer handles it in S02).
- `BaseHTTPMiddleware` has a known limitation: it creates a new task per request, which can cause issues with `request.state` in streaming responses. For the SSE endpoint specifically, the session_id may need to be resolved as a dependency rather than middleware. Test this — if `request.state.session_id` is accessible inside the SSE generator after middleware runs, middleware is fine. If not, fall back to a `Depends()` that reads the cookie directly.
- The `sessions` table schema in database.py uses `TEXT` for `created_at` and `last_seen` (ISO format strings). The architecture doc suggests `INTEGER` (unix timestamps). Use what S01 established: TEXT ISO format, consistent with the jobs table.
- Python 3.12 venv at `backend/.venv` — all commands must use `.venv/Scripts/python`.

## Common Pitfalls

- **CancelledError swallowing in SSE generator** — Use `try/finally` for cleanup. If you catch `CancelledError`, re-raise it. Never use bare `except Exception` around the generator body. This is Pitfall 3 from the research — creates zombie connections that leak memory. The warning sign is `asyncio.all_tasks()` growing over time.
- **BaseHTTPMiddleware + streaming responses** — BaseHTTPMiddleware wraps the response body in a new task. For SSE (long-lived streaming), this can cause `request.state` to be garbage-collected or the middleware's `call_next` to hang. If tests show this, switch the session resolution to a FastAPI `Depends()` function instead of middleware. The middleware approach is cleaner architecturally but may not survive streaming.
- **Cookie not sent on SSE EventSource** — Browser `EventSource` sends cookies by default for same-origin requests. No `withCredentials` needed unless cross-origin. The SSE endpoint must be same-origin (same host:port as the SPA).
- **Replay storm on reconnect** — Replay only current state (non-terminal jobs), not full event history. Query `WHERE status NOT IN ('completed', 'failed', 'expired')` for the init event payload.

## Open Risks

- **BaseHTTPMiddleware compatibility with SSE streaming** — May need to fall back to a dependency-based approach if middleware doesn't work with long-lived EventSourceResponse. Low probability (sse-starlette is designed for Starlette), but worth testing early.
- **Shared mode SSE fanout** — The broker is session-keyed. Full shared-mode broadcasting needs either a broker change or a dual-publish pattern. Recommend deferring the SSE broadcasting aspect of shared mode to S04, proving only the query layer in S02.

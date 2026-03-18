---
id: T02
parent: S02
milestone: M001
provides:
  - GET /api/events SSE endpoint with init replay, live job_update streaming, keepalive ping, job_removed events
  - get_active_jobs_by_session() and get_active_jobs_all() in database.py for non-terminal job queries
  - DELETE /api/downloads/{id} publishes job_removed event to SSEBroker so connected clients update in real-time
  - try/finally generator cleanup — broker.unsubscribe always called on disconnect (no zombie connections)
  - 11 tests covering replay, live streaming, disconnect cleanup, keepalive, session isolation, HTTP wiring
key_files:
  - backend/app/routers/sse.py
  - backend/app/core/database.py
  - backend/app/routers/downloads.py
  - backend/app/main.py
  - backend/tests/test_sse.py
  - backend/tests/conftest.py
key_decisions:
  - httpx ASGITransport buffers the full response body before returning — incompatible with infinite SSE streams. HTTP-level test bypasses httpx and invokes the ASGI app directly with custom receive/send callables; disconnect is signalled once the init event body arrives (b'"jobs"' in received_body)
  - ping=0 passed to EventSourceResponse disables sse-starlette's internal keepalive (keepalive is handled inside our own generator via asyncio.TimeoutError on queue.get with 15s timeout)
  - CancelledError deliberately not caught in event_generator — propagates so sse-starlette can cleanly cancel the task group
patterns_established:
  - Direct ASGI invocation pattern for testing long-lived streaming endpoints — bypass httpx ASGITransport with custom receive/send + asyncio.timeout safety net
  - SSE generator structure: subscribe → init replay → live loop with keepalive → finally unsubscribe
  - broker._publish_sync() for synchronous (on-loop) event delivery in tests vs publish() (thread-safe, off-loop)
observability_surfaces:
  - mediarip.sse logger at INFO on SSE connect (session_id) and disconnect (session_id)
  - broker._subscribers dict — inspect active connections per session (len = number of open SSE streams)
  - GET /api/events with curl shows raw SSE event stream; disconnect log confirms cleanup
duration: 35m
verification_result: passed
completed_at: 2026-03-18
blocker_discovered: false
---

# T02: Build SSE endpoint with replay, disconnect cleanup, and job_removed broadcasting

**Built the SSE event streaming endpoint, non-terminal job queries, job_removed broadcasting via DELETE, and 11 comprehensive SSE tests — 86/86 full suite passing.**

## What Happened

1. **Database queries** (`database.py`): Added `get_active_jobs_by_session(db, session_id)` — filters `status NOT IN ('completed', 'failed', 'expired')`, returns `list[Job]` ordered by `created_at`. Added `get_active_jobs_all(db)` for shared-mode replay (no session filter). Both use the pre-defined `_TERMINAL_STATUSES` tuple.

2. **SSE router** (`routers/sse.py`): `GET /api/events` route using `EventSourceResponse` wrapping an async generator. Generator lifecycle:
   - Subscribe to broker for session_id
   - Replay non-terminal jobs as `init` event
   - Loop: `asyncio.wait_for(queue.get(), timeout=15.0)` — yields `job_update` (ProgressEvent) or `job_removed`/custom (dict) events; raises `asyncio.TimeoutError` → yields `ping`
   - `finally`: `broker.unsubscribe(session_id, queue)` — always runs, prevents zombie connections
   - `CancelledError` not caught — propagates for clean task group cancellation

3. **job_removed broadcasting** (`routers/downloads.py`): DELETE endpoint fetches the job first to get its `session_id`, calls `download_service.cancel()`, then publishes `{"event": "job_removed", "data": {"job_id": job_id}}` to the broker. If job not found (already deleted), publish is skipped.

4. **App wiring** (`main.py`): SSE router mounted under `/api`. `conftest.py` client fixture updated to include SSE router.

5. **Test suite** (`tests/test_sse.py`): 11 tests across 6 test classes:
   - `TestGetActiveJobsBySession` — non-terminal filter, empty result when all terminal
   - `TestEventGeneratorInit` — init with jobs, init empty session
   - `TestEventGeneratorLiveStream` — ProgressEvent delivery, dict event delivery
   - `TestEventGeneratorDisconnect` — unsubscribe fires on `gen.aclose()`
   - `TestEventGeneratorKeepalive` — ping fires with patched 0.1s timeout
   - `TestSessionIsolation` — session A's init doesn't include session B's jobs
   - `TestSSEEndpointHTTP` — 200 + text/event-stream + init event via direct ASGI invocation
   - `TestJobRemovedViaDELETE` — broker._publish_sync delivers job_removed

## Verification

- `pytest tests/test_sse.py -v` — 11/11 passed in 0.56s
- `pytest tests/ -v` — 86/86 passed in 9.75s (full regression including all S01 + S02/T01 tests)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `pytest tests/test_sse.py -v` | 0 | ✅ pass | 0.56s |
| 2 | `pytest tests/ -v` | 0 | ✅ pass | 9.75s |

## Diagnostics

- **Active connections**: `len(broker._subscribers.get(session_id, []))` — should be 0 after disconnect
- **Raw SSE stream**: `curl -N http://localhost:8000/api/events` — shows event: init, data: {"jobs": [...]}
- **Zombie detection**: connect log without matching disconnect log in `mediarip.sse` → generator cleanup didn't fire
- **SSE generator test pattern**: call `event_generator(sid, broker, db)` directly, use `_collect_events(gen, count=N)`, always `await gen.aclose()` to trigger finally block

## Deviations

- HTTP-level test uses direct ASGI invocation instead of `httpx.AsyncClient.stream()` — ASGITransport buffers full response body, incompatible with infinite SSE streams. Custom `receive`/`send` callables signal disconnect once init event body arrives.
- `ping=0` passed to EventSourceResponse — disables sse-starlette's built-in keepalive (0 = every 0s would be an infinite tight loop). Our generator handles keepalive natively via `asyncio.TimeoutError`.

## Known Issues

- Pre-existing background thread teardown noise: worker threads attempting DB writes after test teardown produce `RuntimeWarning: coroutine 'update_job_status' was never awaited` and `sqlite3.ProgrammingError: Cannot operate on a closed database`. Harmless — documented in T04/S01.
- httpx deprecation warning on per-request `cookies=` in session middleware tests — pre-existing from T01.

## Files Created/Modified

- `backend/app/core/database.py` — added `get_active_jobs_by_session()` and `get_active_jobs_all()`
- `backend/app/routers/sse.py` — new, GET /api/events SSE endpoint with async generator
- `backend/app/routers/downloads.py` — DELETE endpoint publishes job_removed to broker
- `backend/app/main.py` — SSE router mounted under /api
- `backend/tests/conftest.py` — SSE router added to test app
- `backend/tests/test_sse.py` — new, 11 SSE tests

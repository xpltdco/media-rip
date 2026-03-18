---
estimated_steps: 7
estimated_files: 6
---

# T02: Build SSE endpoint with replay, disconnect cleanup, and job_removed broadcasting

**Slice:** S02 — SSE Transport + Session System
**Milestone:** M001

## Description

Build the SSE endpoint that streams live download progress from yt-dlp workers to browser clients. This is the highest-risk piece in S02 — it involves an async generator that must correctly handle subscribe → replay → live stream → disconnect cleanup without leaking resources.

The endpoint at `GET /api/events` uses `sse-starlette`'s `EventSourceResponse` to wrap an async generator. On connect, the generator subscribes to the SSEBroker for the current session, sends an `init` event replaying all non-terminal jobs from the database, then enters a loop yielding `job_update` events from the broker queue with a 15-second keepalive ping. On disconnect (client closes, network drop), the generator's `finally` block calls `broker.unsubscribe()` to prevent zombie connections.

Additionally, the downloads router's DELETE endpoint is updated to publish a `job_removed` event through the broker so connected SSE clients see deletions in real-time.

**Critical constraints — read carefully:**
- The generator MUST use `try/finally` for cleanup. `CancelledError` must NOT be caught or swallowed.
- `sse-starlette==3.3.3` is already installed. Use `EventSourceResponse` directly.
- The SSEBroker's `subscribe()` and `unsubscribe()` are called from the asyncio thread (the generator runs on the event loop). `publish()` is called from worker threads (already thread-safe).
- If `BaseHTTPMiddleware` causes `request.state.session_id` to be unavailable inside the SSE generator, use a `Depends()` function that reads the `mrip_session` cookie directly as a fallback. Test this.
- Python 3.12 venv: `backend/.venv/Scripts/python`.

## Steps

1. **Add `get_active_jobs_by_session()` to `backend/app/core/database.py`:**
   - Query: `SELECT * FROM jobs WHERE session_id = ? AND status NOT IN ('completed', 'failed', 'expired') ORDER BY created_at`
   - Returns `list[Job]` — the non-terminal jobs that should be replayed on SSE connect
   - Also add `get_active_jobs_all(db)` (no session filter) for shared mode replay in future

2. **Create `backend/app/routers/sse.py`:**
   - Single route: `GET /api/events`
   - Access session_id via `request.state.session_id` (set by middleware from T01)
   - Access broker via `request.app.state.broker`, db via `request.app.state.db`
   - Define `async def event_generator(session_id, broker, db)`:
     ```
     queue = broker.subscribe(session_id)
     try:
         # 1. Replay: send init event with current non-terminal jobs
         jobs = await get_active_jobs_by_session(db, session_id)
         yield {"event": "init", "data": json.dumps({"jobs": [job.model_dump() for job in jobs]})}
         
         # 2. Live stream: yield events from broker queue with keepalive
         while True:
             try:
                 event = await asyncio.wait_for(queue.get(), timeout=15.0)
                 # event is a ProgressEvent or a dict (for job_removed)
                 if isinstance(event, dict):
                     yield {"event": event.get("event", "job_update"), "data": json.dumps(event.get("data", {}))}
                 else:
                     yield {"event": "job_update", "data": json.dumps(event.model_dump())}
             except asyncio.TimeoutError:
                 yield {"event": "ping", "data": ""}
     finally:
         broker.unsubscribe(session_id, queue)
         logger.info("SSE disconnected for session %s", session_id)
     ```
   - Wrap with `EventSourceResponse(event_generator(...))` in the route handler
   - Set `retry` parameter in EventSourceResponse to 5000 (5 second reconnect)
   - Logger: `mediarip.sse` (already exists in broker — reuse the same logger namespace)

3. **Update `backend/app/routers/downloads.py` — publish job_removed on DELETE:**
   - In `cancel_download()`, after calling `download_service.cancel(job_id)`, publish a job_removed event:
     ```python
     request.app.state.broker.publish(
         session_id_of_job,  # need to look up the job first to get its session_id
         {"event": "job_removed", "data": {"job_id": job_id}}
     )
     ```
   - This requires fetching the job before cancelling to get its session_id, OR passing session_id through cancel
   - Simplest approach: fetch the job with `get_job(db, job_id)` before cancel to get session_id, then publish after cancel
   - Import `get_job` from database.py (may already be imported)

4. **Mount SSE router in `backend/app/main.py`:**
   - Import sse router: `from app.routers.sse import router as sse_router`
   - Add: `app.include_router(sse_router, prefix="/api")`

5. **Update `backend/tests/conftest.py`:**
   - Add SSE router to the test app in the `client` fixture: `test_app.include_router(sse_router, prefix="/api")`
   - Import sse router

6. **Write `backend/tests/test_sse.py`:**
   Tests must verify the SSE contract thoroughly. Use httpx streaming to consume SSE events.

   - **Test: init event replays current jobs** — Create a job in DB, connect to GET /api/events, read the first SSE event, verify it's type "init" with the job in the payload
   - **Test: init event is empty when no jobs** — Connect with fresh session, verify init event has empty jobs array
   - **Test: live job_update events arrive** — Connect to SSE, then publish a ProgressEvent to the broker for the session, verify the next event is type "job_update" with correct data
   - **Test: disconnect cleanup removes subscriber** — Connect to SSE, verify broker has subscriber, close connection, verify broker._subscribers no longer has queue for that session
   - **Test: keepalive ping after timeout** — Connect to SSE (after init), wait >15s with no events, verify a "ping" event arrives. (May need to mock or use shorter timeout for test speed — consider making keepalive interval configurable or using a shorter timeout in test)
   - **Test: job_removed event delivery** — Create a job, connect to SSE, DELETE the job, verify a "job_removed" event with the job_id arrives on the SSE stream
   - **Test: session isolation** — Create jobs for session A and session B, connect SSE as session A, verify init only contains session A's jobs

   **Testing approach for SSE with httpx:**
   - httpx `AsyncClient.stream("GET", "/api/events")` returns an async streaming response
   - Read SSE lines manually: each event is `event: <type>\ndata: <json>\n\n`
   - Alternatively, directly call the async generator function in tests for simpler assertions
   - For disconnect testing: use the generator directly, iterate a few events, then break out of the loop and verify cleanup ran

7. **Run full test suite:**
   - `cd backend && .venv/Scripts/python -m pytest tests/ -v`
   - All tests (S01 + T01 session + T02 SSE) must pass

## Must-Haves

- [ ] `get_active_jobs_by_session()` in database.py returns only non-terminal jobs
- [ ] SSE endpoint sends `init` event with current jobs on connect (R004 replay)
- [ ] SSE endpoint streams `job_update` events from broker queue (R003 progress)
- [ ] SSE endpoint sends `job_removed` event when downloads are deleted
- [ ] SSE endpoint sends keepalive `ping` every 15s of inactivity
- [ ] Generator uses try/finally — broker.unsubscribe always called on disconnect
- [ ] CancelledError is NOT caught or swallowed anywhere in the generator
- [ ] DELETE /api/downloads/{id} publishes job_removed event to broker
- [ ] Tests prove: replay, live streaming, disconnect cleanup, session isolation

## Verification

- `cd backend && .venv/Scripts/python -m pytest tests/test_sse.py -v` — all SSE tests pass
- `cd backend && .venv/Scripts/python -m pytest tests/ -v` — full suite passes (no regressions)
- Disconnect cleanup proven: after SSE generator exits, `broker._subscribers` has no leftover queues for the test session

## Observability Impact

- Signals added: `mediarip.sse` logger at INFO for SSE connect (session_id) and disconnect (session_id); existing WARNING for QueueFull stays
- How a future agent inspects this: check `broker._subscribers` dict for active connections count per session; connect to `GET /api/events` with curl to see raw event stream
- Failure state exposed: zombie connection = `mediarip.sse` has connect log without matching disconnect log; `len(broker._subscribers.get(session_id, []))` growing over time

## Inputs

- `backend/app/core/sse_broker.py` — SSEBroker with subscribe(session_id) → Queue, unsubscribe(session_id, queue), publish(session_id, event). Publish is thread-safe. Subscribe/unsubscribe run on asyncio thread.
- `backend/app/core/database.py` — After T01: has session CRUD + existing job CRUD. Needs new `get_active_jobs_by_session()`.
- `backend/app/middleware/session.py` — From T01: SessionMiddleware sets request.state.session_id
- `backend/app/models/job.py` — Job model with `.model_dump()`, ProgressEvent with `.model_dump()`, JobStatus enum (completed/failed/expired are terminal)
- `backend/app/routers/downloads.py` — After T01: uses request.state.session_id via dependency
- `sse-starlette==3.3.3` — provides `EventSourceResponse`; accepts async generator yielding dicts with "event" and "data" keys

## Expected Output

- `backend/app/core/database.py` — `get_active_jobs_by_session()` and `get_active_jobs_all()` added
- `backend/app/routers/sse.py` — GET /api/events SSE endpoint (new file)
- `backend/app/routers/downloads.py` — DELETE endpoint publishes job_removed to broker
- `backend/app/main.py` — SSE router mounted
- `backend/tests/conftest.py` — SSE router added to test app
- `backend/tests/test_sse.py` — 7+ SSE tests covering replay, streaming, cleanup, isolation (new file)

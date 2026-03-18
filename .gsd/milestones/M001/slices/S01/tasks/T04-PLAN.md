---
estimated_steps: 5
estimated_files: 7
---

# T04: Wire API routes and FastAPI app factory

**Slice:** S01 — Foundation + Download Engine
**Milestone:** M001

## Description

Build the HTTP layer that ties everything together: the FastAPI app factory with lifespan (DB init/close, service construction), API routers for downloads and format extraction, a stub session dependency for testing, and API-level tests via httpx. This is the composition task — it proves the full vertical from HTTP request through to yt-dlp and back.

The stub session dependency reads `X-Session-ID` from request headers, falling back to a default UUID. This is explicitly documented as S02-replaceable — S02 delivers real cookie-based session middleware that replaces this dependency entirely.

**Important:** The API tests use `httpx.AsyncClient` with `ASGITransport` — no real server is started. This is FastAPI's recommended testing pattern.

## Steps

1. Create `backend/app/dependencies.py`:
   - `get_session_id(request: Request) -> str` dependency function
   - Reads `X-Session-ID` header from request. If present, return it.
   - If not present, return a default UUID string (e.g., `"00000000-0000-0000-0000-000000000000"`)
   - Add a docstring clearly marking this as a stub: `"""Stub session ID dependency. S02 replaces this with cookie-based session middleware."""`

2. Update `backend/app/main.py` — full app factory with lifespan:
   - `@asynccontextmanager async def lifespan(app: FastAPI)`:
     - Load config: `config = AppConfig(yaml_file="config.yaml")` if file exists, else `AppConfig()`
     - Init DB: `db = await init_db(config.server.db_path)`
     - Capture event loop: `loop = asyncio.get_event_loop()`
     - Create SSEBroker: `broker = SSEBroker(loop)`
     - Create DownloadService: `download_service = DownloadService(config, db, broker, loop)`
     - Store on `app.state`: `app.state.config = config`, `app.state.db = db`, `app.state.broker = broker`, `app.state.download_service = download_service`
     - `yield`
     - Teardown: `download_service.shutdown()`, `await close_db(db)`
   - Include routers: `app.include_router(downloads_router, prefix="/api")`, `app.include_router(formats_router, prefix="/api")`

3. Create `backend/app/routers/downloads.py`:
   - `router = APIRouter(tags=["downloads"])`
   - `POST /downloads` — accepts `JobCreate` body, gets `session_id` from `Depends(get_session_id)`, gets `download_service` from `request.app.state.download_service`. Calls `await download_service.enqueue(job_create, session_id)`. Returns Job as JSON with status 201.
   - `GET /downloads` — gets session_id, queries DB via `get_jobs_by_session(request.app.state.db, session_id)`. Returns list of Jobs.
   - `DELETE /downloads/{job_id}` — calls `await download_service.cancel(job_id)`. Returns `{"status": "cancelled"}`.

4. Create `backend/app/routers/formats.py`:
   - `router = APIRouter(tags=["formats"])`
   - `GET /formats` — accepts `url: str` query param. Gets download_service from app.state. Calls `await download_service.get_formats(url)`. Returns list of FormatInfo.
   - Handle errors gracefully: if extraction fails, return 400 with error message.

5. Create/update `backend/tests/test_api.py` and update `backend/tests/conftest.py`:
   - Add `client` async fixture to conftest: creates `httpx.AsyncClient` with `ASGITransport(app=app)`, base_url `http://test`
   - The app fixture needs a fresh lifespan — use temp DB path and temp output dir
   - Tests:
     - `test_post_download` — POST `/api/downloads` with `{"url": "https://www.youtube.com/watch?v=BaW_jenozKc"}` and `X-Session-ID: test-session` header → 201 + response has `id`, `status == "queued"`, `url` matches
     - `test_get_downloads_empty` — GET `/api/downloads` with `X-Session-ID: new-session` → 200 + empty list
     - `test_get_downloads_after_post` — POST a download, then GET → list contains the job
     - `test_delete_download` — POST a download, then DELETE → 200 + status cancelled, GET confirms status changed
     - `test_get_formats` — GET `/api/formats?url=https://www.youtube.com/watch?v=BaW_jenozKc` → 200 + non-empty list with format_id fields (integration — needs network)
     - `test_post_download_invalid_url` — POST with `{"url": "not-a-url"}` → appropriate error response
   - Run full suite: `cd backend && python -m pytest tests/ -v`

## Must-Haves

- [ ] App starts without errors via lifespan (DB initialized, services created)
- [ ] POST /api/downloads creates a job and returns it with status 201
- [ ] GET /api/downloads returns jobs filtered by session_id
- [ ] DELETE /api/downloads/{id} marks job as cancelled/failed
- [ ] GET /api/formats?url= returns format list from yt-dlp extraction
- [ ] Stub session_id dependency reads X-Session-ID header with fallback
- [ ] Full test suite (`python -m pytest tests/ -v`) passes with 0 failures

## Verification

- `cd backend && python -m pytest tests/test_api.py -v` — all API tests pass
- `cd backend && python -m pytest tests/ -v` — FULL suite (models + config + db + broker + download + template + api) passes with 0 failures
- `python -c "from app.main import app; print(app.title)"` — prints "media.rip()"

## Observability Impact

- App lifespan logs config source (YAML/env/defaults) and DB path at startup (INFO level)
- API routes log incoming requests with session_id at DEBUG level
- Error responses include structured error messages (not stack traces)

## Inputs

- `backend/app/models/job.py` — Job, JobCreate, FormatInfo models
- `backend/app/core/config.py` — AppConfig
- `backend/app/core/database.py` — init_db, close_db, CRUD functions
- `backend/app/core/sse_broker.py` — SSEBroker
- `backend/app/services/download.py` — DownloadService
- `backend/tests/conftest.py` — shared fixtures from T02

## Expected Output

- `backend/app/dependencies.py` — stub session_id dependency
- `backend/app/main.py` — complete app factory with lifespan, router mounting
- `backend/app/routers/downloads.py` — POST/GET/DELETE download endpoints
- `backend/app/routers/formats.py` — GET formats endpoint
- `backend/tests/test_api.py` — API test suite (6+ test cases)
- `backend/tests/conftest.py` — updated with httpx client fixture
- All prior test files still passing (full regression)

---
estimated_steps: 5
estimated_files: 5
---

# T03: Implement download service with sync-to-async bridge

**Slice:** S01 — Foundation + Download Engine
**Milestone:** M001

## Description

Build the download service — the highest-risk component in S01. This is where yt-dlp (synchronous, thread-bound) meets FastAPI (async, event-loop-bound). The service wraps yt-dlp in a `ThreadPoolExecutor` and bridges progress events to the async world via `loop.call_soon_threadsafe`. Also build the output template resolver utility.

This task retires the primary risk identified in the M001 roadmap: **"proving yt-dlp progress events arrive in an asyncio.Queue via call_soon_threadsafe, with a test that runs a real download and asserts events were received."**

**Critical implementation constraints:**
- **Fresh YoutubeDL instance per job** — never shared across threads. YoutubeDL has mutable state (cookies, temp files, logger) that corrupts under concurrent access.
- **Event loop captured at construction** — `asyncio.get_event_loop()` in `__init__`, stored as `self._loop`. Cannot call `get_event_loop()` inside a worker thread.
- **Progress hook throttling** — Write to DB only when percent changes by ≥1% or status changes. SSE broker gets all events (cheap in-memory), DB gets throttled writes.
- **`total_bytes` is frequently None** — Already handled in `ProgressEvent.from_yt_dlp` from T01, but the hook must not crash when the dict is sparse.

## Steps

1. Create `backend/app/services/output_template.py`:
   - `resolve_template(url: str, user_override: str | None, config: AppConfig) -> str`
   - Extract domain from URL using `urllib.parse.urlparse`. Strip `www.` prefix.
   - If `user_override` is not None, return it directly (R025 per-download override)
   - Look up domain in `config.downloads.source_templates`. If found, return it.
   - Fall back to `config.downloads.source_templates.get("*", "%(title)s.%(ext)s")`
   - Handle malformed URLs gracefully (return default template)

2. Create `backend/app/services/download.py`:
   - `DownloadService` class. Constructor takes `config: AppConfig`, `db: aiosqlite.Connection`, `broker: SSEBroker`, `loop: asyncio.AbstractEventLoop`.
   - `self._executor = ThreadPoolExecutor(max_workers=config.downloads.max_concurrent)`
   - `async def enqueue(self, job_create: JobCreate, session_id: str) -> Job`:
     - Generate UUID4 for job_id, resolve output template via `resolve_template`
     - Create Job model, persist via `create_job(self._db, job)` (from database module)
     - Submit `self._run_download` to executor via `self._loop.run_in_executor(self._executor, self._run_download, job.id, job.url, opts, session_id)`
     - Return the Job
   - `def _run_download(self, job_id: str, url: str, opts: dict, session_id: str)`:
     - This runs in a worker thread. **Create a fresh YoutubeDL instance** with opts.
     - Register a `progress_hooks` callback that:
       - Creates `ProgressEvent.from_yt_dlp(job_id, d)` from the hook dict
       - Calls `self._loop.call_soon_threadsafe(self._broker.publish_sync, session_id, event)` (NOT `publish` — call the sync method directly since we're already scheduling on the event loop)
       - Throttles DB writes: track `_last_db_percent` per job, only write when `abs(new - last) >= 1.0` or status changed
       - DB writes from the thread use `asyncio.run_coroutine_threadsafe(update_job_progress(...), self._loop).result()` — blocks the worker thread until the async DB write completes
     - Call `ydl.download([url])`
     - On success: update status to `completed`, set `completed_at`
     - On exception: update status to `failed`, set `error_message` to str(e), log the error
   - `async def get_formats(self, url: str) -> list[FormatInfo]`:
     - Run in executor: `ydl.extract_info(url, download=False)`
     - Parse result `formats` list into `FormatInfo` models
     - Handle `filesize: None` gracefully
     - Return list sorted by resolution (best first)
   - `async def cancel(self, job_id: str)`:
     - Update job status to `failed` with error_message "Cancelled by user" in DB
     - Note: yt-dlp has no reliable mid-stream abort. The thread continues but the job is marked failed.
   - `def shutdown(self)`:
     - `self._executor.shutdown(wait=False)`

3. Create `backend/tests/test_output_template.py`:
   - Test YouTube URL → youtube.com template
   - Test SoundCloud URL → soundcloud.com template
   - Test unknown domain → fallback `*` template
   - Test `www.` prefix stripping (www.youtube.com → youtube.com lookup)
   - Test user override takes priority over domain match
   - Test malformed URL → fallback template

4. Create `backend/tests/test_download_service.py`:
   - **Integration test — real download** (mark with `@pytest.mark.integration` or `@pytest.mark.slow`):
     - Set up: create temp output dir, init DB, create SSEBroker, create DownloadService
     - Subscribe to broker queue for the test session
     - Call `service.enqueue(JobCreate(url="https://www.youtube.com/watch?v=BaW_jenozKc"), session_id="test-session")` — this is a 10-second Creative Commons video commonly used in yt-dlp tests. If this URL stops working, any short public video works.
     - Collect events from broker queue with a timeout (10-30 seconds depending on network)
     - Assert: at least one event has `status == "downloading"` with `percent > 0`
     - Assert: final event has `status == "finished"` (this is yt-dlp's hook status, not JobStatus)
     - Assert: output file exists in the temp dir
     - Assert: DB job status is `completed`
   - **Format extraction test** (also integration — needs network):
     - Call `service.get_formats("https://www.youtube.com/watch?v=BaW_jenozKc")`
     - Assert: result is non-empty list
     - Assert: each FormatInfo has `format_id` and `ext` populated
   - **Cancel test** (unit — no network):
     - Create a job in DB with status `downloading`
     - Call `service.cancel(job_id)`
     - Assert: DB job status is now `failed` with error_message "Cancelled by user"
   - **Concurrent enqueue test** (integration — light):
     - Enqueue 2 downloads simultaneously via `asyncio.gather`
     - Verify both complete without errors (proves ThreadPoolExecutor + WAL work together)

5. Run all tests: `cd backend && python -m pytest tests/test_output_template.py tests/test_download_service.py -v`

## Must-Haves

- [ ] Fresh YoutubeDL instance created per job inside worker thread (never shared)
- [ ] Progress events bridge from worker thread to SSE broker via `call_soon_threadsafe`
- [ ] Real download integration test passes — file appears in output dir AND progress events received
- [ ] Format extraction returns non-empty list with `format_id` and `ext`
- [ ] DB progress writes throttled (≥1% change or status change)
- [ ] Output template resolves domain-specific and fallback correctly
- [ ] `total_bytes: None` doesn't crash the progress hook

## Verification

- `cd backend && python -m pytest tests/test_output_template.py -v` — all template tests pass
- `cd backend && python -m pytest tests/test_download_service.py -v` — all service tests pass including real download
- `cd backend && python -m pytest tests/test_download_service.py -v -k "real_download"` — specifically verify the risk-retirement test

## Observability Impact

- Download worker logs job_id + status transitions at INFO level
- Download errors logged at ERROR level with job_id + exception traceback
- Progress hook logs throttling decisions at DEBUG level
- `jobs` table `error_message` column populated on failure

## Inputs

- `backend/app/models/job.py` — Job, JobCreate, ProgressEvent, FormatInfo, JobStatus
- `backend/app/core/config.py` — AppConfig with downloads settings
- `backend/app/core/database.py` — init_db, CRUD functions
- `backend/app/core/sse_broker.py` — SSEBroker with publish/subscribe
- `backend/tests/conftest.py` — shared fixtures (db, config, broker)

## Expected Output

- `backend/app/services/output_template.py` — resolve_template utility
- `backend/app/services/download.py` — DownloadService with enqueue, get_formats, cancel
- `backend/tests/test_output_template.py` — template resolution tests
- `backend/tests/test_download_service.py` — integration tests proving sync-to-async bridge works

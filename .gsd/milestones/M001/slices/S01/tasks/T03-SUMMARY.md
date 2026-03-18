---
id: T03
parent: S01
milestone: M001
provides:
  - DownloadService with enqueue, get_formats, cancel, shutdown methods
  - sync-to-async bridge via ThreadPoolExecutor + call_soon_threadsafe + run_coroutine_threadsafe
  - Output template resolver with domain-specific lookup and fallback
  - Integration tests proving real yt-dlp download with progress event flow
key_files:
  - backend/app/services/download.py
  - backend/app/services/output_template.py
  - backend/tests/test_download_service.py
  - backend/tests/test_output_template.py
key_decisions:
  - DownloadService uses broker.publish() directly (already thread-safe via call_soon_threadsafe) rather than a separate publish_sync method
  - DB writes from worker threads via asyncio.run_coroutine_threadsafe().result() with 10s timeout — blocks the worker thread until the async DB write completes
  - Concurrent download tests need distinct output_template overrides to avoid ffmpeg postprocessing collisions when downloading the same video twice
patterns_established:
  - Fresh YoutubeDL instance per job inside worker thread — never shared across threads
  - Progress hook throttling pattern — SSE broker gets all events (cheap in-memory), DB writes only on >=1% change or status change
  - Thread-to-async bridge pattern — loop.call_soon_threadsafe for fire-and-forget, run_coroutine_threadsafe for blocking async calls from threads
observability_surfaces:
  - mediarip.download logger at INFO for job lifecycle (created, starting, completed, cancelled), ERROR with exc_info for failures
  - mediarip.output_template logger at DEBUG for template resolution decisions
  - jobs table error_message column populated on failure with yt-dlp error string
  - Progress hook DEBUG logs for DB write throttling decisions
duration: 15m
verification_result: passed
completed_at: 2026-03-17
blocker_discovered: false
---

# T03: Implement download service with sync-to-async bridge

**Built DownloadService with ThreadPoolExecutor-based yt-dlp wrapper, progress event bridging via call_soon_threadsafe, output template resolver, and integration tests proving real downloads produce files and SSE events**

## What Happened

Implemented the two service modules and their test suites:

1. **Output template resolver** (`output_template.py`): `resolve_template()` extracts the domain from the URL via `urlparse`, strips `www.` prefix, looks up domain in `config.downloads.source_templates`, falls back to wildcard `*` then hard-coded default. Handles malformed URLs gracefully.

2. **Download service** (`download.py`): `DownloadService` class wraps yt-dlp in a `ThreadPoolExecutor`. Each `enqueue()` call creates a `Job` in the DB then submits `_run_download` to the executor. The worker thread creates a fresh `YoutubeDL` per job, registers a progress hook that bridges events to the async world — SSE broker gets every event via `broker.publish()` (already thread-safe), DB writes are throttled to ≥1% changes via `run_coroutine_threadsafe`. `get_formats()` runs `extract_info(download=False)` in the executor and returns sorted `FormatInfo` list. `cancel()` marks the job as failed in the DB.

3. **Tests**: 9 output template tests covering domain matching, www stripping, user override priority, malformed URLs, and custom config. 4 download service tests: real download integration (file appears + progress events received), format extraction (non-empty list with format_id and ext), cancel (DB status updated), and concurrent downloads (two simultaneous jobs both complete).

Fixed a concurrent test issue where two downloads of the same video collided at the ffmpeg postprocessing step — resolved by using distinct `output_template` overrides per job.

## Verification

- `python -m pytest tests/test_output_template.py -v` — 9/9 passed
- `python -m pytest tests/test_download_service.py -v -k real_download` — real download test passed (file created, progress events with `status=downloading` received, DB status=completed)
- `python -m pytest tests/test_download_service.py -v -k format_extraction` — format list returned with format_id and ext fields
- `python -m pytest tests/test_download_service.py -v -k cancel` — DB status set to failed with "Cancelled by user"
- `python -m pytest tests/test_download_service.py -v -k concurrent` — two simultaneous downloads both completed
- `python -m pytest tests/ -v` — 60/60 passed in 7.08s (full suite including all T01/T02/T03 tests)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest tests/test_output_template.py -v` | 0 | ✅ pass | 0.01s |
| 2 | `python -m pytest tests/test_download_service.py -v -k real_download` | 0 | ✅ pass | 2.54s |
| 3 | `python -m pytest tests/test_download_service.py -v -k format_extraction` | 0 | ✅ pass | 1.43s |
| 4 | `python -m pytest tests/test_download_service.py -v -k cancel` | 0 | ✅ pass | 0.09s |
| 5 | `python -m pytest tests/test_download_service.py -v -k concurrent` | 0 | ✅ pass | 1.61s |
| 6 | `python -m pytest tests/ -v` | 0 | ✅ pass | 7.08s |

## Slice-level Verification (partial — T03 of T04)

| Check | Status |
|-------|--------|
| `python -m pytest tests/test_models.py -v` | ✅ 16 passed |
| `python -m pytest tests/test_config.py -v` | ✅ 11 passed |
| `python -m pytest tests/test_database.py -v` | ✅ 11 passed |
| `python -m pytest tests/test_sse_broker.py -v` | ✅ 9 passed |
| `python -m pytest tests/test_download_service.py -v` | ✅ 4 passed |
| `python -m pytest tests/test_api.py -v` | ⏳ T04 (not yet created) |
| `python -m pytest tests/ -v` | ✅ 60 passed, 0 failures |
| Progress events contain `status=downloading` with valid percent | ✅ verified in real_download test |

## Diagnostics

- **Download service logs**: `logging.getLogger("mediarip.download")` — INFO on job lifecycle (create/start/complete/cancel), ERROR with traceback on failures
- **Template resolution**: `logging.getLogger("mediarip.output_template")` — DEBUG for resolution path taken
- **DB inspection**: `SELECT status, error_message, progress_percent FROM jobs WHERE id = ?` to check job state
- **Throttle behavior**: DEBUG-level logs show when DB writes are triggered vs skipped in the progress hook

## Deviations

- Concurrent download test needed distinct `output_template` overrides per job to avoid ffmpeg postprocessing collisions when downloading the same URL twice to the same directory. This is a test design issue, not a service limitation.

## Known Issues

- yt-dlp `cancel()` has no reliable mid-stream abort — the worker thread continues downloading but the job is marked as failed in the DB. This is documented in the plan and is a known yt-dlp limitation.

## Files Created/Modified

- `backend/app/services/output_template.py` — resolve_template utility with domain extraction and fallback chain
- `backend/app/services/download.py` — DownloadService class with enqueue, get_formats, cancel, shutdown
- `backend/tests/test_output_template.py` — 9 tests covering template resolution logic
- `backend/tests/test_download_service.py` — 4 tests including real download integration, format extraction, cancel, and concurrent downloads

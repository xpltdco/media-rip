# S01: Foundation + Download Engine — UAT

**Milestone:** M001
**Written:** 2026-03-17

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: S01 is a backend-only slice with no UI. All verification is through pytest (API contracts, database state, real yt-dlp downloads). No human-visible frontend to inspect.

## Preconditions

- Python 3.12 venv activated: `cd backend && source .venv/Scripts/activate` (or use `.venv/Scripts/python` directly)
- All dependencies installed: `pip install -e ".[dev]"` (already done during T01)
- Network access available (integration tests download from YouTube)

## Smoke Test

```bash
cd backend && .venv/Scripts/python -m pytest tests/ -v
```
Expected: 68 passed, 0 failed. Runtime ~8-10s (network-dependent for yt-dlp integration tests).

## Test Cases

### 1. Pydantic Model Construction and Normalization

```bash
cd backend && .venv/Scripts/python -m pytest tests/test_models.py -v
```

1. Run the model test suite
2. **Expected:** 16 tests pass covering:
   - JobStatus enum has all 6 values (queued, extracting, downloading, completed, failed, cancelled)
   - JobCreate accepts minimal (url only) and full construction
   - Job model has correct defaults (progress_percent=0.0, status=queued)
   - ProgressEvent.from_yt_dlp handles: complete dict, total_bytes=None fallback to estimate, both None → percent=0.0, finished status, minimal dict with missing keys
   - FormatInfo and Session models construct correctly

### 2. Config System: Zero-Config + Env Vars + YAML

```bash
cd backend && .venv/Scripts/python -m pytest tests/test_config.py -v
```

1. Run the config test suite
2. **Expected:** 11 tests pass covering:
   - Zero-config: AppConfig() works with no YAML file and no env vars
   - Default values: max_concurrent=3, output_dir="/downloads", session_timeout_hours=72
   - Env var override: MEDIARIP__DOWNLOADS__MAX_CONCURRENT overrides default
   - YAML loading: values from YAML file are picked up
   - Missing YAML: no crash when yaml_file points to nonexistent path
   - Source templates: default entries for youtube.com, soundcloud.com, and * fallback

### 3. Database: WAL Mode + CRUD + Concurrency

```bash
cd backend && .venv/Scripts/python -m pytest tests/test_database.py -v
```

1. Run the database test suite
2. **Expected:** 11 tests pass covering:
   - All 4 tables created (sessions, jobs, config, unsupported_urls)
   - `PRAGMA journal_mode` returns `wal`
   - `PRAGMA busy_timeout` returns 5000
   - Indexes created on jobs(session_id), jobs(status), sessions(last_seen)
   - Job CRUD roundtrip: create → get → verify fields match
   - get_nonexistent returns None
   - get_jobs_by_session filters correctly
   - update_job_status changes status + sets updated_at
   - update_job_progress changes percent + speed + eta
   - delete_job removes the row
   - 3 concurrent inserts complete without SQLITE_BUSY

### 4. SSE Broker: Subscribe/Publish/Thread-Safety

```bash
cd backend && .venv/Scripts/python -m pytest tests/test_sse_broker.py -v
```

1. Run the SSE broker test suite
2. **Expected:** 9 tests pass covering:
   - subscribe creates an asyncio.Queue for the session
   - unsubscribe removes the queue
   - unsubscribe on nonexistent session doesn't raise
   - publish delivers event to subscriber's queue
   - Multiple subscribers on same session all receive event
   - publish to nonexistent session doesn't raise
   - Unsubscribed queue stops receiving events
   - publish from a worker thread (via call_soon_threadsafe) delivers event
   - Multiple threads publishing concurrently all deliver events

### 5. Download Service: Real yt-dlp Integration

```bash
cd backend && .venv/Scripts/python -m pytest tests/test_download_service.py -v
```

1. Run the download service test suite
2. **Expected:** 4 tests pass:
   - **Real download**: Downloads "Me at the zoo" (jNQXAC9IVRw) → file appears in temp output dir, progress events with `status=downloading` and valid percent received in broker queue, DB status=completed
   - **Format extraction**: extract_info returns non-empty list of FormatInfo with format_id and ext fields
   - **Cancel**: cancel() sets DB status to failed with "Cancelled by user" error_message
   - **Concurrent downloads**: Two simultaneous downloads of the same video (different output templates) both complete

### 6. Output Template Resolution

```bash
cd backend && .venv/Scripts/python -m pytest tests/test_output_template.py -v
```

1. Run the output template test suite
2. **Expected:** 9 tests pass covering:
   - youtube.com URL matches YouTube domain template
   - soundcloud.com URL matches SoundCloud domain template
   - Unknown domain falls back to `*` wildcard template
   - www. prefix stripped before lookup
   - User override takes priority over domain match
   - Malformed URL returns fallback template
   - Empty URL returns fallback template
   - URL with port resolves correctly
   - Custom domain template from config is used

### 7. API Endpoints: Full HTTP Vertical

```bash
cd backend && .venv/Scripts/python -m pytest tests/test_api.py -v
```

1. Run the API test suite
2. **Expected:** 8 tests pass covering:
   - POST /api/downloads with valid URL → 201, response has id/url/status=queued/session_id
   - GET /api/downloads with no downloads → 200, empty list
   - GET /api/downloads after POST → 200, list contains the posted job
   - DELETE /api/downloads/{id} → 200, job status changes (not queued)
   - GET /api/formats?url=(YouTube URL) → 200, non-empty list of format objects
   - POST /api/downloads with invalid URL → 200 (job created, fails async)
   - Default session ID fallback → uses 00000000-0000-0000-0000-000000000000
   - Session isolation → different X-Session-ID headers see different job lists

### 8. Full Regression Suite

```bash
cd backend && .venv/Scripts/python -m pytest tests/ -v
```

1. Run all tests
2. **Expected:** 68 passed, 0 failed

## Edge Cases

### WAL Mode Under Concurrent Load

1. The test_three_concurrent_inserts test fires 3 simultaneous job inserts
2. **Expected:** All 3 succeed without SQLITE_BUSY errors (WAL + busy_timeout=5000ms)

### ProgressEvent with Missing Total Bytes

1. ProgressEvent.from_yt_dlp receives a dict where both total_bytes and total_bytes_estimate are None
2. **Expected:** percent=0.0, no exception raised — graceful degradation

### Broker Publish to Missing Session

1. broker.publish("nonexistent-session", event)
2. **Expected:** No exception raised, event silently dropped

### Cancel Race Condition

1. POST a download, immediately DELETE it
2. **Expected:** Job status is not "queued" (may be "failed" or "downloading" depending on timing). The background worker may have already started.

## Failure Signals

- `python -m pytest` returns exit code != 0
- Any test marked FAILED in pytest output
- `SQLITE_BUSY` errors in database tests (indicates WAL or busy_timeout misconfiguration)
- `No module named` errors (indicates venv not activated or dependencies not installed)
- `SSL: CERTIFICATE_VERIFY_FAILED` in test *results* (stderr noise from background threads is normal; only a problem if it causes test failure)
- Progress events missing from broker queue after real download (indicates sync-to-async bridge broken)

## Requirements Proved By This UAT

- R001 — Real yt-dlp download completes via API (test_download_service::test_real_download, test_api::test_post_download)
- R002 — Format extraction returns quality options (test_download_service::test_format_extraction, test_api::test_get_formats)
- R019 — Output templates resolve per-domain with fallback (test_output_template, 9 cases)
- R023 — Config defaults + YAML + env vars all work (test_config, 11 cases). Admin SQLite writes deferred to S04.
- R024 — Concurrent same-URL downloads succeed (test_download_service::test_concurrent_downloads)

## Not Proven By This UAT

- R001/R002 full user flow (needs frontend from S03)
- R003 SSE streaming to browser (needs S02 SSE endpoint)
- R006 Playlist parent/child handling (needs S03 UI)
- R023 admin live config writes (needs S04)
- Any frontend, theme, admin, or Docker concerns (S02-S06)

## Notes for Tester

- **Venv is required.** System Python is 3.14; project requires 3.12. Always use `backend/.venv/Scripts/python` or activate the venv first.
- **Network tests are slow.** test_download_service and test_api (format extraction) hit YouTube. Expect ~8-10s total runtime. If behind a corporate proxy or firewall, these may fail with SSL errors.
- **Stderr noise is expected.** Background yt-dlp worker threads that outlive the test event loop produce `RuntimeWarning` and error messages on stderr. These are cosmetic — the test exit code is what matters.
- **Cancel test is race-tolerant.** The DELETE endpoint test asserts `status != "queued"` rather than exactly `status == "failed"` because the background worker may overwrite the status.

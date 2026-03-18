---
id: T02
parent: S01
milestone: M001
provides:
  - AppConfig with pydantic-settings (env + YAML + zero-config defaults)
  - aiosqlite database layer with WAL mode, busy_timeout, CRUD functions
  - SSEBroker with thread-safe publish via call_soon_threadsafe
  - Shared test fixtures in conftest.py (tmp_db_path, test_config, db, broker)
key_files:
  - backend/app/core/config.py
  - backend/app/core/database.py
  - backend/app/core/sse_broker.py
  - backend/tests/conftest.py
key_decisions:
  - Used monkeypatch.setitem on model_config to test YAML loading since pydantic-settings v2 does not accept _yaml_file as an init kwarg
  - SSE broker fixture must be async (pytest_asyncio.fixture) using asyncio.get_running_loop() — get_event_loop() returns a different loop than the one running async tests
  - env_prefix set to "MEDIARIP__" (with trailing delimiter) so nested vars use MEDIARIP__SERVER__PORT format
patterns_established:
  - _SafeYamlSource wraps YamlConfigSettingsSource to gracefully handle missing/None yaml_file
  - Database PRAGMA order (busy_timeout → WAL → synchronous) set before any DDL
  - _row_to_job helper converts aiosqlite.Row to Job model — single point of row mapping
observability_surfaces:
  - mediarip.database logger: INFO on journal_mode set and table creation
  - mediarip.sse logger: WARNING on QueueFull (subscriber backpressure)
  - mediarip.config logger: DEBUG when YAML file not found
duration: 25m
verification_result: passed
completed_at: 2026-03-17
blocker_discovered: false
---

# T02: Build config system, database layer, and SSE broker

**Built pydantic-settings config (env + YAML + zero-config), aiosqlite database with WAL mode and CRUD, and thread-safe SSE broker — 47 tests passing**

## What Happened

Created three infrastructure modules in `backend/app/core/`:

1. **config.py** — `AppConfig(BaseSettings)` with six nested config sections (ServerConfig, DownloadsConfig, SessionConfig, PurgeConfig, UIConfig, AdminConfig). Uses `_SafeYamlSource` subclass of `YamlConfigSettingsSource` that gracefully returns `{}` when the YAML file is missing or None. Priority chain: env vars → YAML → init kwargs → .env. Env prefix `MEDIARIP__` with `__` nesting.

2. **database.py** — `init_db()` opens aiosqlite connection, sets PRAGMAs in the critical order (busy_timeout=5000 → journal_mode=WAL → synchronous=NORMAL), then creates four tables (sessions, jobs, config, unsupported_urls) with three indexes. CRUD functions: create_job, get_job, get_jobs_by_session, update_job_status, update_job_progress, delete_job, close_db. All writes commit immediately.

3. **sse_broker.py** — `SSEBroker` holds a dict of session_id → list[asyncio.Queue]. `publish()` uses `loop.call_soon_threadsafe(_publish_sync, ...)` so yt-dlp worker threads can fire events safely. `_publish_sync` iterates queues with `put_nowait`, catching `QueueFull`.

Created `conftest.py` with shared async fixtures (tmp_db_path, test_config, db, broker). The broker fixture is async to capture the running event loop correctly — `asyncio.get_event_loop()` returns a different loop than the test runner's.

Two test issues discovered and fixed during verification:
- YAML config tests initially used `_yaml_file` as an init kwarg, but pydantic-settings v2 rejects unknown init kwargs. Fixed by using `monkeypatch.setitem` on `model_config`.
- Broker thread-safety tests initially failed because the broker fixture used `get_event_loop()` (deprecation-era API returning a stale loop). Fixed by making the fixture async with `get_running_loop()`.

## Verification

All three module test suites pass, plus the T01 model tests — 47/47 total:
- `test_config.py`: 11 passed (zero-config, env overrides, YAML load, missing YAML, default templates)
- `test_database.py`: 11 passed (all tables created, WAL mode, busy_timeout, indexes, CRUD roundtrip, concurrent writes)
- `test_sse_broker.py`: 9 passed (subscribe, unsubscribe, publish, multi-subscriber, thread-safe publish, multi-thread publish)
- `test_models.py`: 16 passed (unchanged from T01)

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `cd backend && python -m pytest tests/test_config.py -v` | 0 | ✅ pass | 0.22s |
| 2 | `cd backend && python -m pytest tests/test_database.py -v` | 0 | ✅ pass | 0.19s |
| 3 | `cd backend && python -m pytest tests/test_sse_broker.py -v` | 0 | ✅ pass | 0.23s |
| 4 | `cd backend && python -m pytest tests/ -v` | 0 | ✅ pass | 0.43s |

Slice-level checks (partial — T02 is not the final task):
| # | Command | Exit Code | Verdict | Notes |
|---|---------|-----------|---------|-------|
| 1 | `test_models.py -v` | 0 | ✅ pass | T01 output |
| 2 | `test_config.py -v` | 0 | ✅ pass | T02 new |
| 3 | `test_database.py -v` | 0 | ✅ pass | T02 new |
| 4 | `test_sse_broker.py -v` | 0 | ✅ pass | T02 new |
| 5 | `test_download_service.py -v` | — | ⏳ pending | T03 |
| 6 | `test_api.py -v` | — | ⏳ pending | T04 |

## Diagnostics

- WAL mode: `sqlite3 mediarip.db "PRAGMA journal_mode"` → should return `wal`
- Config inspection: `python -c "from app.core.config import AppConfig; c = AppConfig(); print(c.model_dump())"`
- Database tables: `sqlite3 mediarip.db ".tables"` → sessions, jobs, config, unsupported_urls
- SSE broker: subscriber count visible via `len(broker._subscribers[session_id])`

## Deviations

- YAML config test approach changed from init kwarg (`_yaml_file=path`) to `monkeypatch.setitem(model_config, "yaml_file", path)` — pydantic-settings v2 forbids extra init kwargs.
- Broker fixture changed from sync (`@pytest.fixture`) to async (`@pytest_asyncio.fixture`) using `get_running_loop()` instead of `get_event_loop()`.

## Known Issues

None.

## Files Created/Modified

- `backend/app/core/config.py` — AppConfig with nested sections, _SafeYamlSource, env/YAML/zero-config support
- `backend/app/core/database.py` — init_db with WAL PRAGMAs, schema DDL, CRUD functions
- `backend/app/core/sse_broker.py` — SSEBroker with thread-safe publish via call_soon_threadsafe
- `backend/tests/conftest.py` — shared fixtures: tmp_db_path, test_config, db, broker
- `backend/tests/test_config.py` — 11 config tests (zero-config, env override, YAML, missing YAML)
- `backend/tests/test_database.py` — 11 database tests (tables, WAL, CRUD, concurrent writes)
- `backend/tests/test_sse_broker.py` — 9 broker tests (subscribe, publish, thread-safe, multi-subscriber)

---
estimated_steps: 7
estimated_files: 7
---

# T02: Build config system, database layer, and SSE broker

**Slice:** S01 — Foundation + Download Engine
**Milestone:** M001

## Description

Build the three infrastructure modules that the download service and API routes depend on: the pydantic-settings config system, the aiosqlite database layer with WAL mode, and the SSE broker for thread-safe per-session event distribution. Also establish the shared test fixtures in `conftest.py`.

The config system uses `pydantic-settings[yaml]` with env prefix `MEDIARIP` and nested delimiter `__`. It must handle a missing `config.yaml` gracefully (zero-config mode). The database must execute WAL + busy_timeout + synchronous PRAGMAs before any schema creation — this is critical for concurrent download writes. The SSE broker stores a reference to the event loop captured at init time and uses `loop.call_soon_threadsafe(queue.put_nowait, event)` for thread-safe publishing.

## Steps

1. Create `backend/app/core/config.py`:
   - Import `pydantic_settings.BaseSettings`, `pydantic.BaseModel`
   - Define nested config models: `ServerConfig` (host, port, log_level, db_path defaulting to `"mediarip.db"`), `DownloadsConfig` (output_dir, max_concurrent, source_templates dict, default_template), `SessionConfig` (mode, timeout_hours), `PurgeConfig` (enabled, max_age_hours, cron), `UIConfig` (default_theme), `AdminConfig` (enabled, username, password_hash)
   - `AppConfig(BaseSettings)` with `model_config = SettingsConfigDict(env_prefix="MEDIARIP", env_nested_delimiter="__", yaml_file=None)`. Nested models with sensible defaults: `server: ServerConfig = ServerConfig()`, `downloads: DownloadsConfig = DownloadsConfig()`, etc.
   - Override `settings_customise_sources` to order: `env_settings` → `YamlConfigSettingsSource` → `init_settings` → `dotenv_settings`. Wrap YAML source to handle missing file gracefully (return empty dict if file doesn't exist or `yaml_file` is None).
   - Defaults: `downloads.output_dir="/downloads"`, `downloads.max_concurrent=3`, `downloads.source_templates={"youtube.com": "%(uploader)s/%(title)s.%(ext)s", "soundcloud.com": "%(uploader)s/%(title)s.%(ext)s", "*": "%(title)s.%(ext)s"}`, `session.mode="isolated"`, `session.timeout_hours=72`, `admin.enabled=False`

2. Create `backend/app/core/database.py`:
   - Async functions: `init_db(db_path: str) -> aiosqlite.Connection` — opens connection, sets `row_factory = aiosqlite.Row`, executes PRAGMAs in this exact order: `PRAGMA busy_timeout=5000`, `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`. Then creates tables.
   - Schema: `sessions` (id TEXT PRIMARY KEY, created_at TEXT, last_seen TEXT), `jobs` (id TEXT PRIMARY KEY, session_id TEXT, url TEXT, status TEXT, format_id TEXT, quality TEXT, output_template TEXT, filename TEXT, filesize INTEGER, progress_percent REAL DEFAULT 0, speed TEXT, eta TEXT, error_message TEXT, created_at TEXT, started_at TEXT, completed_at TEXT), `config` (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT), `unsupported_urls` (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, session_id TEXT, error TEXT, created_at TEXT)
   - Indexes: `CREATE INDEX IF NOT EXISTS idx_jobs_session_status ON jobs(session_id, status)`, `CREATE INDEX IF NOT EXISTS idx_jobs_completed ON jobs(completed_at)`, `CREATE INDEX IF NOT EXISTS idx_sessions_last_seen ON sessions(last_seen)`
   - CRUD functions: `create_job(db, job: Job) -> Job`, `get_job(db, job_id: str) -> Job | None`, `get_jobs_by_session(db, session_id: str) -> list[Job]`, `update_job_status(db, job_id: str, status: str, error_message: str | None = None)`, `update_job_progress(db, job_id: str, progress_percent: float, speed: str | None, eta: str | None, filename: str | None)`, `delete_job(db, job_id: str)`, `close_db(db)` — calls `db.close()`
   - All write operations use `await db.commit()` after execution

3. Create `backend/app/core/sse_broker.py`:
   - `SSEBroker` class with `__init__(self, loop: asyncio.AbstractEventLoop)`
   - Internal state: `self._subscribers: dict[str, list[asyncio.Queue]] = {}`, `self._loop = loop`
   - `subscribe(session_id: str) -> asyncio.Queue` — creates queue, appends to session's list, returns queue
   - `unsubscribe(session_id: str, queue: asyncio.Queue)` — removes queue from list, removes session key if list empty
   - `publish(session_id: str, event)` — uses `self._loop.call_soon_threadsafe(self._publish_sync, session_id, event)` where `_publish_sync` iterates all queues for that session and calls `queue.put_nowait(event)` (catches `asyncio.QueueFull` and logs warning)
   - `publish_sync(session_id: str, event)` — the actual sync method called on the event loop thread, iterates queues and calls `put_nowait`

4. Create `backend/tests/conftest.py`:
   - `tmp_db_path` fixture: returns a temp file path for test database, cleans up after
   - `test_config` fixture: returns `AppConfig` with `downloads.output_dir` set to a temp dir
   - `db` async fixture: calls `init_db(tmp_db_path)`, yields connection, calls `close_db`
   - `broker` fixture: creates SSEBroker with current event loop
   - Mark all async fixtures with appropriate scope

5. Create `backend/tests/test_config.py`:
   - Test zero-config: `AppConfig()` loads with all defaults, no crash
   - Test env var override: set `MEDIARIP__DOWNLOADS__MAX_CONCURRENT=5` in env, verify `config.downloads.max_concurrent == 5`
   - Test YAML loading: write a temp YAML file, set `yaml_file` path, verify values load
   - Test missing YAML file: set `yaml_file` to nonexistent path, verify no crash (zero-config)
   - Test default source_templates contains youtube.com, soundcloud.com, and `*` entries

6. Create `backend/tests/test_database.py`:
   - Test `init_db` creates all tables (query `sqlite_master`)
   - Test WAL mode: `PRAGMA journal_mode` returns `wal`
   - Test `create_job` + `get_job` roundtrip
   - Test `get_jobs_by_session` returns correct subset
   - Test `update_job_status` changes status field
   - Test `update_job_progress` updates progress fields
   - Test `delete_job` removes the row
   - Test concurrent writes: launch 3 simultaneous `create_job` calls via `asyncio.gather`, verify all succeed without `SQLITE_BUSY`

7. Create `backend/tests/test_sse_broker.py`:
   - Test subscribe creates a queue and returns it
   - Test publish delivers event to subscribed queue
   - Test publish from a thread (simulating yt-dlp worker): start a `threading.Thread` that calls `broker.publish(session_id, event)`, verify event arrives in queue within 1 second
   - Test unsubscribe removes queue, subsequent publish doesn't deliver
   - Test multiple subscribers to same session all receive the event
   - Test publish to non-existent session doesn't raise

## Must-Haves

- [ ] Config: zero-config mode works (no YAML, no env vars → all defaults)
- [ ] Config: env var with `MEDIARIP__` prefix and `__` nesting overrides config
- [ ] Database: WAL mode verified via `PRAGMA journal_mode` query returning `wal`
- [ ] Database: `busy_timeout=5000` set before schema creation
- [ ] Database: All four tables created with correct schema
- [ ] Database: 3 concurrent writes succeed without `SQLITE_BUSY`
- [ ] SSE Broker: publish from a separate thread delivers event to subscriber queue
- [ ] SSE Broker: unsubscribe removes queue from distribution
- [ ] All tests pass

## Verification

- `cd backend && python -m pytest tests/test_config.py -v` — all config tests pass
- `cd backend && python -m pytest tests/test_database.py -v` — all DB tests pass including WAL verification and concurrent writes
- `cd backend && python -m pytest tests/test_sse_broker.py -v` — all broker tests pass including thread-safe publish

## Observability Impact

- Database module logs table creation and PRAGMA results at startup (INFO level)
- SSEBroker logs `QueueFull` warnings if a subscriber queue is backed up
- Job status transitions visible via `jobs` table `status` column

## Inputs

- `backend/app/models/job.py` — Job, JobStatus models for database type hints
- `backend/app/models/session.py` — Session model
- `backend/pyproject.toml` — dependencies already installed from T01

## Expected Output

- `backend/app/core/config.py` — AppConfig with nested models, pydantic-settings integration
- `backend/app/core/database.py` — init_db, CRUD functions, WAL mode setup
- `backend/app/core/sse_broker.py` — SSEBroker with thread-safe publish
- `backend/tests/conftest.py` — shared test fixtures (db, config, broker)
- `backend/tests/test_config.py` — config test suite
- `backend/tests/test_database.py` — database test suite with concurrency test
- `backend/tests/test_sse_broker.py` — broker test suite with thread-safety test

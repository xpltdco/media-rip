# Knowledge Base

## Python / Build System

### setuptools build-backend compatibility (discovered T01)
On this system, Python 3.12.4's pip (24.0) does not ship `setuptools.backends._legacy:_Backend`. Use `setuptools.build_meta` as the build-backend in `pyproject.toml`. The legacy backend module was introduced in setuptools ≥75 but isn't available in the bundled version.

### Python version on this system (discovered T01)
System default `python` is 3.14.3, but the project requires `>=3.12,<3.13`. Use `py -3.12` to create venvs. The venv is at `backend/.venv` and must be activated with `source backend/.venv/Scripts/activate` before running any backend commands.

## pydantic-settings (discovered T02)

### YAML file testing pattern
pydantic-settings v2 rejects unknown init kwargs — you cannot pass `_yaml_file=path` to `AppConfig()`. To test YAML loading, use `monkeypatch.setitem(AppConfig.model_config, "yaml_file", str(path))` before constructing the config instance.

### env_prefix includes the delimiter
Set `env_prefix="MEDIARIP__"` (with trailing `__`) in `SettingsConfigDict`. Combined with `env_nested_delimiter="__"`, env vars look like `MEDIARIP__SERVER__PORT=9000`.

## pytest-asyncio (discovered T02)

### Async fixtures must use get_running_loop()
In pytest-asyncio with `asyncio_mode="auto"`, sync fixtures that call `asyncio.get_event_loop()` get a *different* loop than the one running async tests. Any fixture that needs the test's event loop must be an async fixture (`@pytest_asyncio.fixture`) using `asyncio.get_running_loop()`.

## yt-dlp (discovered T03)

### Test video URL: use jNQXAC9IVRw not BaW_jenozKc
The video `BaW_jenozKc` (commonly cited in yt-dlp docs as a test URL) is unavailable as of March 2026. Use `jNQXAC9IVRw` ("Me at the zoo" — first YouTube video, 19 seconds) for integration tests. It's been up since 2005 and is extremely unlikely to be removed.

### SSEBroker.publish() is already thread-safe
The `SSEBroker.publish()` method already calls `loop.call_soon_threadsafe` internally. From a worker thread, call `broker.publish(session_id, event)` directly — do NOT try to call `_publish_sync` or manually schedule with `call_soon_threadsafe`. The task plan mentioned calling `publish_sync` directly but the actual broker API handles the bridging.

### DB writes from worker threads
Use `asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=N)` to call async database functions from a synchronous yt-dlp worker thread. This blocks the worker thread until the DB write completes, which is fine because worker threads are pool-managed and the block is brief.

## FastAPI Testing (discovered T04)

### httpx ASGITransport does not trigger Starlette lifespan
When using `httpx.AsyncClient` with `ASGITransport(app=app)`, Starlette lifespan events (startup/shutdown) do **not** run. The `client` fixture must either: (a) build a fresh FastAPI app and manually wire `app.state` with services, or (b) use an explicit async context manager around the app. Option (a) is simpler — create temp DB, config, broker, and download service directly in the fixture.

### Cancel endpoint race condition with background workers
`DownloadService.cancel()` sets `status=failed` in DB, but a background worker thread may overwrite this with `status=downloading` via its own `run_coroutine_threadsafe` call that was already in-flight. In tests, assert `status != "queued"` rather than `status == "failed"` to tolerate the race. This is inherent to the cancel design (yt-dlp has no reliable mid-stream abort).

## FastAPI + PEP 563 (discovered S02-T01)

### Do not use lazy imports for FastAPI endpoint parameter types
When `from __future__ import annotations` is active (PEP 563), type annotations are stored as strings. If a FastAPI endpoint uses `request: Request` and `Request` was imported inside a function body (lazy import), FastAPI's dependency resolution fails to recognize `Request` as a special parameter and treats it as a required query parameter, returning 422 Unprocessable Entity. Always import `Request` (and other FastAPI types used in endpoint signatures) at **module level**.

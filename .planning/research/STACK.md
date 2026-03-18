# Stack Research

**Domain:** Self-hosted yt-dlp web frontend (media downloader)
**Researched:** 2026-03-17
**Confidence:** HIGH — all versions verified against PyPI and npm as of research date

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Backend runtime | Pinned in Dockerfile; `3.12-slim` is the smallest viable image. Avoids 3.13's passlib incompatibility. yt-dlp requires >=3.9. |
| FastAPI | 0.135.1 | HTTP API + SSE + middleware | Native SSE support added in 0.135.0 (EventSourceResponse). Async-first design matches the run_in_executor download pattern. HTTPBasic/HTTPBearer auth built in. |
| uvicorn | 0.42.0 | ASGI server | Standard FastAPI server. Use `uvicorn[standard]` for uvloop and httptools for production throughput. |
| yt-dlp | 2026.3.17 | Download engine | Used as a library (`import yt_dlp`), not subprocess. Gives synchronous progress hooks, structured error capture, and no shell-injection surface. |
| aiosqlite | 0.22.1 | Async SQLite | asyncio bridge over stdlib sqlite3. Single-file DB, zero external deps, sufficient for this concurrency model (small ThreadPoolExecutor). |
| APScheduler | 3.11.2 | Cron jobs (purge, session expiry) | 3.x is stable. 4.x is still alpha (4.0.0a6). Use `AsyncIOScheduler` from APScheduler 3.x — runs on FastAPI's event loop, started/stopped in the lifespan context manager. |
| pydantic | 2.12.5 | Data models and validation | FastAPI 0.135.x requires Pydantic v2. All request/response schemas and config validation. |
| pydantic-settings | 2.13.1 | Config loading from YAML + env | Install as `pydantic-settings[yaml]` for native YAML source support. Handles `MEDIARIP__SECTION__KEY` env var override pattern natively with `env_nested_delimiter='__'`. |
| sse-starlette | 3.3.3 | SSE EventSource response | Production-stable. Provides `EventSourceResponse`, handles client disconnect detection, cooperative shutdown, and multiple concurrent streams. Required even though FastAPI 0.135 has native SSE — sse-starlette's disconnect handling is more reliable for long-lived connections. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-multipart | 0.0.22 | Multipart form + file upload | Required for `UploadFile` (cookies.txt upload). FastAPI raises `RuntimeError` without it if any endpoint uses file/form data. |
| bcrypt | 5.0.0 | Password hashing for admin credentials | Direct bcrypt, no passlib wrapper. `bcrypt.hashpw()` / `bcrypt.checkpw()`. Avoids passlib's Python 3.12+ deprecation warnings and Python 3.13 breakage. |
| PyYAML | 6.0.x | YAML parsing for config.yaml | Used indirectly by `pydantic-settings[yaml]`. Pinning to 6.0.x avoids the arbitrary-code-execution issue in 5.x. |
| httpx | 0.28.1 | Async HTTP client for tests | Used with `ASGITransport` for FastAPI integration tests. Not needed at runtime. |
| pytest | 9.0.2 | Backend test runner | Requires Python >=3.10. Use with `anyio` marker for async tests. |
| anyio | bundled with FastAPI | Async test infrastructure | FastAPI uses anyio internally. `@pytest.mark.anyio` with `anyio_backend = "asyncio"` fixture is the correct pattern for async test functions. |
| vue | 3.5.30 | Frontend framework | Latest stable. 3.6.0 is in beta (Vapor mode) — avoid until stable. Composition API + `<script setup>` for all components. |
| vue-router | 5.0.3 | Frontend routing | Vue Router 5 is a non-breaking upgrade from 4 with file-based routing merged in. Use programmatic routing only — no file-based routing needed for this SPA. |
| pinia | 3.0.4 | Frontend state management | Pinia 3 drops Vue 2 support (irrelevant here). Better TypeScript inference than Vuex. Three stores: `downloads`, `config`, `ui`. |
| vite | 8.0.0 | Frontend build tool | Ships with Rolldown (Rust bundler), 10-30x faster builds. Node 22 required. |
| @vitejs/plugin-vue | 6.0.1 | Vue SFC support in Vite | Official Vite Vue plugin for `.vue` file compilation. |
| vue-tsc | latest | TypeScript type checking for .vue | Wraps `tsc` with Vue SFC awareness. Run as `vue-tsc --noEmit` in CI. |
| vitest | 4.1.0 | Frontend test runner | Requires Vite >=6. Native Vite integration, same config. Browser Mode now stable in v4. Use for component unit tests and store tests. |
| typescript | 5.x | TypeScript compiler | Pinia 3 requires >=4.5. Vue 3 + Vite works best with 5.x. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| ruff | Python linting + formatting | v0.15.x. Replaces flake8, black, isort in one tool. `ruff check` + `ruff format`. Configure in `pyproject.toml`. |
| eslint | JavaScript/TypeScript linting | Use `@vue/eslint-config-typescript` preset for Vue 3 + TS. |
| vue-tsc | Vue SFC type checking | Run `vue-tsc --noEmit` in CI, not just `tsc`. Standard `tsc` does not understand `.vue` files. |

---

## Integration Architecture

### yt-dlp as Library: The Critical Pattern

yt-dlp's `YoutubeDL` is synchronous. FastAPI is async. Bridge with `asyncio.run_in_executor` using a `ThreadPoolExecutor` — NOT `ProcessPoolExecutor`. `YoutubeDL` objects contain file handles that cannot be pickled for process-based parallelism.

```python
# backend/app/core/downloader.py — canonical pattern
import asyncio
from concurrent.futures import ThreadPoolExecutor
import yt_dlp

_executor = ThreadPoolExecutor(max_workers=config.downloads.max_concurrent)

class YDLLogger:
    """Suppress yt-dlp stdout; route to structured logging."""
    def debug(self, msg): pass      # suppress [debug] lines
    def info(self, msg): logging.info(msg)
    def warning(self, msg): logging.warning(msg)
    def error(self, msg): logging.error(msg)

def _make_progress_hook(job_id: str, sse_bus):
    def hook(d: dict):
        if d["status"] == "downloading":
            sse_bus.publish(job_id, {
                "type": "job_update",
                "id": job_id,
                "percent": float(d.get("_percent_str", "0").strip("%") or 0),
                "speed": d.get("speed"),
                "eta": d.get("eta"),
                "downloaded_bytes": d.get("downloaded_bytes", 0),
            })
        elif d["status"] == "finished":
            sse_bus.publish(job_id, {
                "type": "job_update",
                "id": job_id,
                "status": "completed",
                "filename": d.get("filename"),
                "filesize": d.get("total_bytes") or d.get("total_bytes_estimate"),
            })
    return hook

def _run_download(url: str, ydl_opts: dict) -> dict:
    """Runs in thread pool. Returns info_dict on success."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=True)

async def download_async(url: str, ydl_opts: dict) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _run_download, url, ydl_opts)
```

**Key yt-dlp options to set:**
```python
ydl_opts = {
    "quiet": True,           # suppress console output
    "noprogress": True,      # suppress progress bar (hooks handle this)
    "logger": YDLLogger(),
    "progress_hooks": [_make_progress_hook(job_id, sse_bus)],
    "outtmpl": output_template,   # resolved per source domain
    "format": format_id or "bestvideo+bestaudio/best",
    "cookiefile": cookie_path,    # None if no cookies.txt uploaded
    "noplaylist": not is_playlist_request,
    "extract_flat": False,        # False for actual download; True for format listing only
}
```

**Format extraction (no download):**
```python
ydl_opts = {"quiet": True, "extract_flat": True, "skip_download": True}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
    formats = info.get("formats", [])
```

**Progress hook dict keys available during `status == "downloading"`:**
- `_percent_str` — e.g. `" 45.2%"` (strip whitespace and `%`)
- `speed` — bytes/sec (float or None)
- `eta` — seconds remaining (int or None)
- `downloaded_bytes` — int
- `total_bytes` — int (may be None for live streams)
- `total_bytes_estimate` — int (fallback when total_bytes is None)
- `filename` — destination path

### SSE Bus: asyncio.Queue per Session

```python
# backend/app/core/sse_bus.py — canonical pattern
import asyncio
from collections import defaultdict

class SSEBus:
    def __init__(self):
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[session_id].append(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue):
        self._queues[session_id].discard(q)

    def publish(self, session_id: str, event: dict):
        """Called from thread pool via run_in_executor — must be thread-safe."""
        # asyncio.Queue is NOT thread-safe from a thread pool worker.
        # Use loop.call_soon_threadsafe instead.
        loop = asyncio.get_event_loop()
        for q in self._queues.get(session_id, []):
            loop.call_soon_threadsafe(q.put_nowait, event)
```

**SSE endpoint using sse-starlette:**
```python
from sse_starlette.sse import EventSourceResponse

@router.get("/api/events")
async def events(request: Request, session_id: str = Depends(get_session)):
    async def generator():
        q = sse_bus.subscribe(session_id)
        try:
            # Replay current state on connect (page-refresh safe)
            jobs = await job_manager.get_jobs_for_session(session_id)
            yield {"event": "init", "data": json.dumps({"jobs": [j.to_dict() for j in jobs]})}

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield {"event": event["type"], "data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}  # keepalive
        finally:
            sse_bus.unsubscribe(session_id, q)

    return EventSourceResponse(generator())
```

### APScheduler 3.x Lifespan Integration

```python
# backend/app/main.py
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db.init()
    if config.purge.mode == "scheduled":
        scheduler.add_job(
            run_purge,
            "cron",
            id="purge_job",
            **parse_cron(config.purge.schedule),  # parse "0 3 * * *" → hour=3, minute=0
        )
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown(wait=False)
    await db.close()

app = FastAPI(lifespan=lifespan)
```

**Cron string parsing:** APScheduler 3.x does NOT accept raw cron strings. Parse `"0 3 * * *"` into kwargs manually or use `CronTrigger.from_crontab("0 3 * * *")`:
```python
from apscheduler.triggers.cron import CronTrigger
scheduler.add_job(run_purge, CronTrigger.from_crontab(config.purge.schedule))
```

### pydantic-settings Config Pattern

```python
# backend/app/config.py
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

class DownloadsConfig(BaseModel):
    output_dir: str = "/downloads"
    max_concurrent: int = 3
    default_quality: str = "bestvideo+bestaudio/best"

class AppConfig(BaseSettings):
    downloads: DownloadsConfig = DownloadsConfig()
    # ... other sections

    model_config = SettingsConfigDict(
        env_prefix="MEDIARIP_",
        env_nested_delimiter="__",
        yaml_file="/config/config.yaml",
        yaml_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, **kwargs):
        return (
            kwargs["env_settings"],          # MEDIARIP__SECTION__KEY highest priority
            YamlConfigSettingsSource(settings_cls),  # config.yaml
            kwargs["init_settings"],
            kwargs["default_settings"],
        )
```

### Admin Auth: HTTPBasic + bcrypt

No JWT. No OAuth. Username/password stored (hashed) in SQLite `settings` table. Pattern mirrors qBittorrent/Sonarr.

```python
# backend/app/dependencies.py
import secrets
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

async def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    stored_hash = await settings_store.get("admin_password_hash")
    username_ok = secrets.compare_digest(
        credentials.username.encode(), (await settings_store.get("admin_username")).encode()
    )
    password_ok = bcrypt.checkpw(credentials.password.encode(), stored_hash.encode())
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )
```

**First-boot flow:** If no admin credentials in DB, generate random password, log it to stdout once, store hash. UI prompts forced change.

---

## Installation

```bash
# backend/requirements.txt — pinned versions
fastapi==0.135.1
uvicorn[standard]==0.42.0
yt-dlp==2026.3.17
aiosqlite==0.22.1
apscheduler==3.11.2
pydantic==2.12.5
pydantic-settings[yaml]==2.13.1
sse-starlette==3.3.3
python-multipart==0.0.22
bcrypt==5.0.0
PyYAML==6.0.2

# Dev/test only
httpx==0.28.1
pytest==9.0.2
anyio[trio]==4.x      # anyio bundled with fastapi; install for pytest marker
ruff==0.15.x
```

```bash
# frontend/package.json (key deps)
npm install vue@3.5.30 vue-router@5.0.3 pinia@3.0.4
npm install -D vite@8.0.0 @vitejs/plugin-vue@6.0.1 vue-tsc typescript vitest@4.1.0
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| sse-starlette | FastAPI native SSE (0.135+) | Use native only for simple fire-and-forget streams. sse-starlette wins for long-lived connections needing disconnect detection and keepalive. |
| APScheduler 3.x | APScheduler 4.x | Revisit when 4.x exits alpha. 4.x has cleaner asyncio API but is not production-stable as of March 2026. |
| APScheduler 3.x | Celery + Redis | Only if distributed workers needed. Adds Redis dependency — unacceptable for single-container distribution goal. |
| aiosqlite (raw) | SQLAlchemy async + aiosqlite | SQLAlchemy adds overhead and ORM complexity. Raw aiosqlite with parameterized queries is sufficient for this schema. |
| bcrypt (direct) | passlib | passlib is unmaintained and throws deprecation warnings on Python 3.12. Will break on Python 3.13 (crypt module removed). |
| bcrypt (direct) | pwdlib | pwdlib 0.3.0 is Beta status. Fine for new projects, but bcrypt direct is simpler for a single-algorithm case. |
| pydantic-settings[yaml] | python-dotenv + manual YAML | pydantic-settings handles env var layering, type coercion, and nested delimiter out of the box. |
| ThreadPoolExecutor | ProcessPoolExecutor | YoutubeDL objects are not picklable — process pool raises RuntimeError immediately. |
| Vue 3.5.x | Vue 3.6.x beta | 3.6 beta introduces Vapor mode (breaking internal changes). Wait for stable. |
| Vite 8 | Vite 6/7 | Vite 8 is current stable with Rolldown. Vitest 4.x requires Vite >=6, compatible with 8. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| WebSockets | Bidirectional protocol overhead; `EventSource` auto-reconnects natively; HTTP POST is sufficient for submitting downloads | SSE via sse-starlette |
| passlib | Last release years ago; `crypt` module deprecated Python 3.12, removed Python 3.13; throws DeprecationWarning in prod | bcrypt directly |
| APScheduler 4.x | Still alpha (4.0.0a6) as of March 2026 | APScheduler 3.11.2 |
| ProcessPoolExecutor | YoutubeDL cannot be pickled — crashes immediately | ThreadPoolExecutor |
| SQLAlchemy ORM | Adds 3 abstraction layers for a schema that has 2 tables. Raw aiosqlite is ~50 lines | Raw aiosqlite |
| JWT / OAuth | Unnecessary complexity for an admin panel on a self-hosted tool. No multi-user auth needed. | HTTPBasic over bcrypt |
| Vuex | Superseded by Pinia; Vuex has no active development for Vue 3 | Pinia 3 |
| Vue 3.6.x beta | Vapor mode is in flux; internal API changes can break component libraries | Vue 3.5.30 stable |
| axios | No advantage over browser `fetch` + `EventSource` for this app's API surface | Native `fetch` for REST, `EventSource` for SSE |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| FastAPI 0.135.1 | Pydantic v2 only | Pydantic v1 not supported. |
| FastAPI 0.135.1 | Starlette 0.46.x | Pinned transitively; don't install Starlette separately unless matching. |
| sse-starlette 3.3.3 | Python >=3.10 | Will fail on Python 3.9. Project uses 3.12 — fine. |
| vitest 4.1.0 | Vite >=6.0.0 | Compatible with Vite 8. |
| APScheduler 3.11.2 | Python >=3.6 | `AsyncIOScheduler` requires asyncio event loop to already be running when `.start()` is called — hence lifespan pattern. |
| bcrypt 5.0.0 | Breaking: passwords >72 bytes raise ValueError | Not a concern for admin passwords. |
| pydantic-settings 2.13.1 | pydantic >=2.7.0 | Installed alongside FastAPI — transitive version is fine. |
| yt-dlp 2026.3.17 | ffmpeg (system package) | ffmpeg must be installed at the OS level (`apt-get install ffmpeg`). yt-dlp does not bundle it. The Dockerfile already handles this. |

---

## Sources

- [PyPI: yt-dlp](https://pypi.org/project/yt-dlp/) — version 2026.3.17 confirmed
- [PyPI: FastAPI](https://pypi.org/project/fastapi/) — version 0.135.1 confirmed
- [PyPI: uvicorn](https://pypi.org/project/uvicorn/) — version 0.42.0 confirmed
- [PyPI: aiosqlite](https://pypi.org/project/aiosqlite/) — version 0.22.1 confirmed
- [PyPI: APScheduler](https://pypi.org/project/apscheduler/) — 3.11.2 stable, 4.0.0a6 alpha
- [PyPI: pydantic-settings](https://pypi.org/project/pydantic-settings/) — version 2.13.1 confirmed
- [PyPI: sse-starlette](https://pypi.org/project/sse-starlette/) — version 3.3.3 confirmed
- [PyPI: bcrypt](https://pypi.org/project/bcrypt/) — version 5.0.0 confirmed
- [PyPI: httpx](https://pypi.org/project/httpx/) — version 0.28.1 confirmed
- [PyPI: pytest](https://pypi.org/project/pytest/) — version 9.0.2 confirmed
- [npm: vue](https://www.npmjs.com/package/vue) — 3.5.30 stable, 3.6.0-beta.6 available
- [npm: vue-router](https://www.npmjs.com/package/vue-router) — 5.0.3 confirmed (non-breaking from 4.x)
- [npm: pinia](https://www.npmjs.com/package/pinia) — 3.0.4 confirmed
- [npm: vite](https://vite.dev/releases) — 8.0.0 with Rolldown stable
- [Vitest 4.0 announcement](https://vitest.dev/blog/vitest-4) — version 4.1.0 confirmed
- [FastAPI HTTP Basic Auth docs](https://fastapi.tiangolo.com/advanced/security/http-basic-auth/) — HTTPBasic pattern
- [FastAPI SSE docs](https://fastapi.tiangolo.com/tutorial/server-sent-events/) — EventSourceResponse
- [sse-starlette GitHub](https://github.com/sysid/sse-starlette) — disconnect handling pattern
- [APScheduler 3.x docs](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — CronTrigger.from_crontab
- [passlib deprecation discussion](https://github.com/fastapi/fastapi/discussions/11773) — confirmed broken on Python 3.13
- [yt-dlp asyncio issue #9487](https://github.com/yt-dlp/yt-dlp/issues/9487) — ThreadPoolExecutor vs ProcessPoolExecutor constraint

---
*Stack research for: media.rip() — self-hosted yt-dlp web frontend*
*Researched: 2026-03-17*

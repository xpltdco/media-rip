---
estimated_steps: 5
estimated_files: 7
---

# T01: Scaffold project and define Pydantic models

**Slice:** S01 — Foundation + Download Engine
**Milestone:** M001

## Description

Create the entire `backend/` project from scratch. This is a greenfield project — no source code exists yet. Establish `pyproject.toml` with all pinned dependencies, the package directory structure matching the boundary map (`app/core/`, `app/services/`, `app/routers/`, `app/models/`, `app/middleware/`), and all Pydantic models that every subsequent task imports from.

The models are pure data classes with no I/O dependencies. The critical implementation detail is `ProgressEvent.from_yt_dlp(job_id, d)` — a classmethod that normalizes raw yt-dlp progress hook dictionaries into a typed model. It must handle `total_bytes: None` (common for subtitles, live streams, and some sites) by falling back to `total_bytes_estimate`, and calculating percent as 0 if both are `None`.

## Steps

1. Create `backend/pyproject.toml` with:
   - `[project]` section: name `media-rip`, python `>=3.12,<3.13`, pinned dependencies: `fastapi==0.135.1`, `uvicorn[standard]==0.42.0`, `yt-dlp==2026.3.17`, `aiosqlite==0.22.1`, `apscheduler==3.11.2`, `pydantic==2.12.5`, `pydantic-settings[yaml]==2.13.1`, `sse-starlette==3.3.3`, `bcrypt==5.0.0`, `python-multipart==0.0.22`, `PyYAML==6.0.2`
   - `[project.optional-dependencies]` dev: `httpx==0.28.1`, `pytest==9.0.2`, `anyio[trio]`, `pytest-asyncio`, `ruff`
   - `[tool.pytest.ini_options]` asyncio_mode = "auto"
   - `[tool.ruff]` target-version = "py312"

2. Create directory structure with `__init__.py` files:
   - `backend/app/__init__.py`
   - `backend/app/core/__init__.py`
   - `backend/app/models/__init__.py`
   - `backend/app/services/__init__.py`
   - `backend/app/routers/__init__.py`
   - `backend/app/middleware/__init__.py`
   - `backend/tests/__init__.py`

3. Create `backend/app/models/job.py` with:
   - `JobStatus` — string enum: `queued`, `extracting`, `downloading`, `completed`, `failed`, `expired`
   - `JobCreate` — `url: str`, optional `format_id: str | None`, `quality: str | None`, `output_template: str | None`
   - `Job` — full model matching DB schema: `id: str` (UUID4), `session_id: str`, `url: str`, `status: JobStatus`, `format_id`, `quality`, `output_template`, `filename: str | None`, `filesize: int | None`, `progress_percent: float` (default 0), `speed: str | None`, `eta: str | None`, `error_message: str | None`, `created_at: str`, `started_at: str | None`, `completed_at: str | None`
   - `ProgressEvent` — `job_id: str`, `status: str`, `percent: float`, `speed: str | None`, `eta: str | None`, `downloaded_bytes: int | None`, `total_bytes: int | None`, `filename: str | None`. Has `from_yt_dlp(cls, job_id: str, d: dict) -> ProgressEvent` classmethod that normalizes yt-dlp's progress hook dict. Key logic: `total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")`, percent = `(downloaded / total * 100)` if both exist else `0.0`, speed formatted from bytes/sec, eta from seconds.
   - `FormatInfo` — `format_id: str`, `ext: str`, `resolution: str | None`, `codec: str | None`, `filesize: int | None`, `format_note: str | None`, `vcodec: str | None`, `acodec: str | None`

4. Create `backend/app/models/session.py` with:
   - `Session` — `id: str`, `created_at: str`, `last_seen: str`, `job_count: int` (default 0)

5. Create `backend/app/main.py` — minimal FastAPI app skeleton:
   - `from fastapi import FastAPI`
   - `@asynccontextmanager async def lifespan(app): yield` (placeholder — T04 fills it in)
   - `app = FastAPI(title="media.rip()", lifespan=lifespan)`

6. Create `backend/tests/test_models.py`:
   - Test `JobStatus` enum values
   - Test `JobCreate` with minimal fields (just url)
   - Test `Job` construction with all fields
   - Test `ProgressEvent.from_yt_dlp` with complete dict (total_bytes present)
   - Test `ProgressEvent.from_yt_dlp` with `total_bytes: None, total_bytes_estimate: 5000`
   - Test `ProgressEvent.from_yt_dlp` with both `None` → percent = 0.0
   - Test `ProgressEvent.from_yt_dlp` with `status: "finished"` dict shape
   - Test `FormatInfo` construction
   - Test `Session` construction with defaults

7. Install and run tests: `cd backend && pip install -e ".[dev]" && python -m pytest tests/test_models.py -v`

## Must-Haves

- [ ] `pyproject.toml` has all pinned deps from research (exact versions)
- [ ] Directory structure matches boundary map: `app/core/`, `app/services/`, `app/routers/`, `app/models/`, `app/middleware/`
- [ ] `ProgressEvent.from_yt_dlp` handles `total_bytes: None` gracefully (falls back to `total_bytes_estimate`, then 0.0)
- [ ] `JobStatus` is a string enum with all 6 values
- [ ] All model tests pass
- [ ] `pip install -e ".[dev]"` succeeds without errors

## Verification

- `cd backend && pip install -e ".[dev]"` — installs without errors
- `cd backend && python -m pytest tests/test_models.py -v` — all tests pass
- `cd backend && python -c "from app.models.job import Job, JobStatus, ProgressEvent, JobCreate, FormatInfo; from app.models.session import Session; print('OK')"` — prints OK

## Observability Impact

- **Signals changed:** None at runtime — this task creates pure data models with no I/O. No logs, no DB, no network.
- **Inspection surfaces:** A future agent can verify the scaffold by importing models: `python -c "from app.models.job import Job, JobStatus, ProgressEvent; print('OK')"`. Package structure is inspectable via `find backend/app -name '*.py'`.
- **Failure visibility:** `ProgressEvent.from_yt_dlp` normalizes yt-dlp hook dicts — malformed inputs (missing `total_bytes`, missing `total_bytes_estimate`) produce `percent=0.0` rather than exceptions, which is the designed graceful-degradation path. Model validation errors from Pydantic raise `ValidationError` with field-level detail.

## Inputs

- No prior code exists — this is the first task
- Research doc specifies all dependency versions, model fields, and directory structure

## Expected Output

- `backend/pyproject.toml` — complete project config with pinned dependencies
- `backend/app/__init__.py` and all sub-package `__init__.py` files — package structure
- `backend/app/main.py` — minimal FastAPI skeleton
- `backend/app/models/job.py` — Job, JobStatus, JobCreate, ProgressEvent, FormatInfo models
- `backend/app/models/session.py` — Session model
- `backend/tests/__init__.py` — test package marker
- `backend/tests/test_models.py` — model unit tests (8+ test cases)

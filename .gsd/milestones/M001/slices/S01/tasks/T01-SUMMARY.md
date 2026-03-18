---
id: T01
parent: S01
milestone: M001
provides:
  - Python package structure (backend/app/ with core, models, services, routers, middleware subpackages)
  - Pydantic models: Job, JobStatus, JobCreate, ProgressEvent (with from_yt_dlp normalizer), FormatInfo, Session
  - pyproject.toml with all pinned dependencies
  - Minimal FastAPI app skeleton (backend/app/main.py)
  - Model unit tests (16 test cases)
key_files:
  - backend/pyproject.toml
  - backend/app/models/job.py
  - backend/app/models/session.py
  - backend/app/main.py
  - backend/tests/test_models.py
key_decisions:
  - Used Python 3.12 venv (py -3.12) since system default is 3.14 but pyproject.toml requires >=3.12,<3.13
  - Fixed build-backend from setuptools.backends._legacy:_Backend to setuptools.build_meta for compatibility with pip 24.0's bundled setuptools
patterns_established:
  - ProgressEvent.from_yt_dlp normalizes yt-dlp hook dicts: total_bytes fallback chain (total_bytes → total_bytes_estimate → None), percent=0.0 when both None
  - Speed formatting: B/s → KiB/s → MiB/s → GiB/s with human-readable output
  - ETA formatting: seconds → Xs / XmYYs / XhYYmZZs
observability_surfaces:
  - Model validation errors raise Pydantic ValidationError with field-level detail
  - ProgressEvent.from_yt_dlp gracefully degrades (percent=0.0) instead of raising on missing total_bytes
duration: 12m
verification_result: passed
completed_at: 2026-03-17T22:24:00-05:00
blocker_discovered: false
---

# T01: Scaffold project and define Pydantic models

**Created backend/ project scaffold with pyproject.toml (all pinned deps), package structure matching boundary map, Pydantic models (Job, JobStatus, JobCreate, ProgressEvent with from_yt_dlp normalizer, FormatInfo, Session), FastAPI skeleton, and 16 passing model tests.**

## What Happened

Built the entire `backend/` project from scratch as the first task in the greenfield project. Created `pyproject.toml` with all 11 pinned runtime dependencies and 5 dev dependencies. Established the package directory structure with `__init__.py` files for `app/core/`, `app/models/`, `app/services/`, `app/routers/`, and `app/middleware/`.

Implemented all Pydantic models in `app/models/job.py` and `app/models/session.py`. The critical `ProgressEvent.from_yt_dlp` classmethod normalizes raw yt-dlp progress hook dictionaries with the specified fallback chain: `total_bytes → total_bytes_estimate → None`, with `percent=0.0` when no total is available. Speed and ETA are formatted into human-readable strings.

Created a minimal FastAPI app in `app/main.py` with a placeholder lifespan context manager (T04 will wire DB and services).

Wrote 16 model unit tests covering all models, enum values, the complete ProgressEvent normalization path (complete data, fallback to estimate, both None, finished status, minimal dict), and edge cases.

Had to fix the build-backend in `pyproject.toml` from `setuptools.backends._legacy:_Backend` to `setuptools.build_meta` because the Python 3.12 venv's setuptools didn't have the newer backend module.

## Verification

All three task-level verification commands pass:

1. `pip install -e ".[dev]"` — installed successfully with all dependencies
2. `python -m pytest tests/test_models.py -v` — 16/16 tests pass
3. `python -c "from app.models.job import Job, JobStatus, ProgressEvent, JobCreate, FormatInfo; from app.models.session import Session; print('OK')"` — prints OK

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `pip install -e ".[dev]"` | 0 | ✅ pass | 43.8s |
| 2 | `python -m pytest tests/test_models.py -v` | 0 | ✅ pass | 0.12s |
| 3 | `python -c "from app.models.job import ...;print('OK')"` | 0 | ✅ pass | <1s |
| 4 | `python -m pytest tests/ -v` (full suite) | 0 | ✅ pass | 0.07s |

### Slice-level verification (T01 scope):

| # | Slice Check | Status | Notes |
|---|-------------|--------|-------|
| 1 | `pytest tests/test_models.py -v` | ✅ pass | 16/16 tests |
| 2 | `pytest tests/test_config.py -v` | ⏳ pending | T02 |
| 3 | `pytest tests/test_database.py -v` | ⏳ pending | T02 |
| 4 | `pytest tests/test_sse_broker.py -v` | ⏳ pending | T02 |
| 5 | `pytest tests/test_download_service.py -v` | ⏳ pending | T03 |
| 6 | `pytest tests/test_api.py -v` | ⏳ pending | T04 |
| 7 | `pytest tests/ -v` (full suite) | ⏳ partial | Only test_models.py exists |

## Diagnostics

- Import check: `python -c "from app.models.job import Job, JobStatus, ProgressEvent, JobCreate, FormatInfo; from app.models.session import Session; print('OK')"`
- Structure check: `find backend/app -name '*.py' | grep -v .venv | sort`
- Venv activation: `source backend/.venv/Scripts/activate` (Python 3.12.4)

## Deviations

- Changed `pyproject.toml` build-backend from `setuptools.backends._legacy:_Backend` to `setuptools.build_meta` because the legacy backend module doesn't exist in setuptools bundled with Python 3.12.4's pip. This is a minor tooling fix, not an architectural change.

## Known Issues

- None

## Files Created/Modified

- `backend/pyproject.toml` — project config with all pinned dependencies
- `backend/app/__init__.py` — package root
- `backend/app/core/__init__.py` — core subpackage marker
- `backend/app/models/__init__.py` — models subpackage marker
- `backend/app/services/__init__.py` — services subpackage marker
- `backend/app/routers/__init__.py` — routers subpackage marker
- `backend/app/middleware/__init__.py` — middleware subpackage marker
- `backend/app/main.py` — minimal FastAPI app skeleton with placeholder lifespan
- `backend/app/models/job.py` — JobStatus, JobCreate, Job, ProgressEvent, FormatInfo models
- `backend/app/models/session.py` — Session model
- `backend/tests/__init__.py` — test package marker
- `backend/tests/test_models.py` — 16 model unit tests

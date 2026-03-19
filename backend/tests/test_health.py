"""Tests for health endpoint, public config endpoint, and session-mode query layer.

Covers:
- GET /api/health — structure, types, queue_depth accuracy
- GET /api/config/public — safe fields present, sensitive fields excluded
- get_jobs_by_mode() — isolated/shared/open dispatching
- get_queue_depth() — counts only non-terminal jobs
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.database import (
    create_job,
    get_all_jobs,
    get_jobs_by_mode,
    get_queue_depth,
)
from app.models.job import Job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(
    session_id: str,
    status: str = "queued",
    url: str = "https://example.com/video",
) -> Job:
    """Create a Job model with a random ID and given session/status."""
    return Job(
        id=str(uuid.uuid4()),
        session_id=session_id,
        url=url,
        status=status,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ===========================================================================
# Health endpoint tests
# ===========================================================================


class TestHealthEndpoint:
    """GET /api/health returns correct structure and values."""

    @pytest.mark.anyio
    async def test_health_returns_correct_structure(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "ok"
        assert isinstance(data["version"], str) and len(data["version"]) > 0
        assert isinstance(data["yt_dlp_version"], str) and len(data["yt_dlp_version"]) > 0
        assert isinstance(data["uptime"], (int, float)) and data["uptime"] >= 0
        assert isinstance(data["queue_depth"], int) and data["queue_depth"] >= 0

    @pytest.mark.anyio
    async def test_health_version_is_semver(self, client):
        resp = await client.get("/api/health")
        version = resp.json()["version"]
        parts = version.split(".")
        assert len(parts) == 3, f"Expected semver, got {version}"

    @pytest.mark.anyio
    async def test_health_queue_depth_reflects_active_jobs(self, db):
        """queue_depth counts queued + downloading + extracting, not terminal."""
        # Insert active jobs directly into DB
        sid = str(uuid.uuid4())
        await create_job(db, _make_job(sid, "queued"))
        await create_job(db, _make_job(sid, "downloading"))

        depth = await get_queue_depth(db)
        assert depth >= 2

    @pytest.mark.anyio
    async def test_health_queue_depth_excludes_completed(self, db):
        """Completed/failed/expired jobs are NOT counted in queue_depth."""
        sid = str(uuid.uuid4())
        await create_job(db, _make_job(sid, "completed"))
        await create_job(db, _make_job(sid, "failed"))
        await create_job(db, _make_job(sid, "expired"))
        await create_job(db, _make_job(sid, "queued"))

        depth = await get_queue_depth(db)
        assert depth == 1

    @pytest.mark.anyio
    async def test_health_uptime_positive(self, client):
        resp = await client.get("/api/health")
        assert resp.json()["uptime"] >= 0


# ===========================================================================
# Public config endpoint tests
# ===========================================================================


class TestPublicConfig:
    """GET /api/config/public returns safe fields only."""

    @pytest.mark.anyio
    async def test_public_config_returns_expected_fields(self, client):
        resp = await client.get("/api/config/public")
        assert resp.status_code == 200
        data = resp.json()

        assert "session_mode" in data
        assert "default_theme" in data
        assert "purge_enabled" in data
        assert "max_concurrent_downloads" in data

    @pytest.mark.anyio
    async def test_public_config_excludes_sensitive_fields(self, client):
        resp = await client.get("/api/config/public")
        raw = resp.text  # Check the raw JSON string — catches nested keys too
        assert "password_hash" not in raw
        assert "username" not in raw

    @pytest.mark.anyio
    async def test_public_config_reflects_actual_config(self, tmp_path):
        """Config values in the response match what AppConfig was built with."""
        from datetime import datetime, timezone

        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from app.core.config import AppConfig
        from app.core.database import close_db, init_db
        from app.middleware.session import SessionMiddleware
        from app.routers.system import router as system_router

        db_path = str(tmp_path / "cfg_test.db")
        config = AppConfig(
            server={"db_path": db_path},
            session={"mode": "shared"},
            ui={"default_theme": "cyberpunk"},
            purge={"enabled": True},
            downloads={"max_concurrent": 5},
        )

        db_conn = await init_db(db_path)
        test_app = FastAPI()
        test_app.add_middleware(SessionMiddleware)
        test_app.include_router(system_router, prefix="/api")
        test_app.state.config = config
        test_app.state.db = db_conn
        test_app.state.start_time = datetime.now(timezone.utc)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/config/public")

        await close_db(db_conn)

        data = resp.json()
        assert data["session_mode"] == "shared"
        assert data["default_theme"] == "cyberpunk"
        assert data["purge_enabled"] is True
        assert data["max_concurrent_downloads"] == 5

    @pytest.mark.anyio
    async def test_public_config_default_values(self, client):
        """Default config should have isolated mode and dark theme."""
        resp = await client.get("/api/config/public")
        data = resp.json()
        assert data["session_mode"] == "isolated"
        assert data["default_theme"] == "dark"
        assert data["purge_enabled"] is False
        assert data["max_concurrent_downloads"] == 3


# ===========================================================================
# Database: get_all_jobs
# ===========================================================================


class TestGetAllJobs:
    """get_all_jobs() returns every job regardless of session."""

    @pytest.mark.anyio
    async def test_returns_all_sessions(self, db):
        sid_a = str(uuid.uuid4())
        sid_b = str(uuid.uuid4())
        await create_job(db, _make_job(sid_a))
        await create_job(db, _make_job(sid_b))

        jobs = await get_all_jobs(db)
        session_ids = {j.session_id for j in jobs}
        assert sid_a in session_ids
        assert sid_b in session_ids
        assert len(jobs) == 2

    @pytest.mark.anyio
    async def test_empty_when_no_jobs(self, db):
        jobs = await get_all_jobs(db)
        assert jobs == []


# ===========================================================================
# Database: get_jobs_by_mode
# ===========================================================================


class TestGetJobsByMode:
    """get_jobs_by_mode() dispatches correctly for isolated/shared/open."""

    @pytest.mark.anyio
    async def test_isolated_filters_by_session(self, db):
        sid_a = str(uuid.uuid4())
        sid_b = str(uuid.uuid4())
        await create_job(db, _make_job(sid_a))
        await create_job(db, _make_job(sid_b))

        jobs = await get_jobs_by_mode(db, sid_a, "isolated")
        assert all(j.session_id == sid_a for j in jobs)
        assert len(jobs) == 1

    @pytest.mark.anyio
    async def test_shared_returns_all(self, db):
        sid_a = str(uuid.uuid4())
        sid_b = str(uuid.uuid4())
        await create_job(db, _make_job(sid_a))
        await create_job(db, _make_job(sid_b))

        jobs = await get_jobs_by_mode(db, sid_a, "shared")
        assert len(jobs) == 2

    @pytest.mark.anyio
    async def test_open_returns_all(self, db):
        sid_a = str(uuid.uuid4())
        sid_b = str(uuid.uuid4())
        await create_job(db, _make_job(sid_a))
        await create_job(db, _make_job(sid_b))

        jobs = await get_jobs_by_mode(db, sid_a, "open")
        assert len(jobs) == 2


# ===========================================================================
# Database: get_queue_depth
# ===========================================================================


class TestGetQueueDepth:
    """get_queue_depth() counts only non-terminal jobs."""

    @pytest.mark.anyio
    async def test_counts_active_statuses(self, db):
        sid = str(uuid.uuid4())
        await create_job(db, _make_job(sid, "queued"))
        await create_job(db, _make_job(sid, "downloading"))
        await create_job(db, _make_job(sid, "extracting"))

        assert await get_queue_depth(db) == 3

    @pytest.mark.anyio
    async def test_excludes_terminal_statuses(self, db):
        sid = str(uuid.uuid4())
        await create_job(db, _make_job(sid, "completed"))
        await create_job(db, _make_job(sid, "failed"))
        await create_job(db, _make_job(sid, "expired"))

        assert await get_queue_depth(db) == 0

    @pytest.mark.anyio
    async def test_mixed_statuses(self, db):
        sid = str(uuid.uuid4())
        await create_job(db, _make_job(sid, "queued"))
        await create_job(db, _make_job(sid, "completed"))
        await create_job(db, _make_job(sid, "downloading"))
        await create_job(db, _make_job(sid, "failed"))

        assert await get_queue_depth(db) == 2

    @pytest.mark.anyio
    async def test_zero_when_empty(self, db):
        assert await get_queue_depth(db) == 0

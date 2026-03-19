"""Tests for the aiosqlite database layer."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone


from app.core.database import (
    close_db,
    create_job,
    delete_job,
    get_job,
    get_jobs_by_session,
    init_db,
    update_job_progress,
    update_job_status,
)
from app.models.job import Job, JobStatus


def _make_job(session_id: str = "sess-1", **overrides) -> Job:
    """Factory for test Job instances."""
    defaults = dict(
        id=str(uuid.uuid4()),
        session_id=session_id,
        url="https://example.com/video",
        status=JobStatus.queued,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return Job(**defaults)


class TestInitDb:
    """Database initialisation and PRAGMA verification."""

    async def test_creates_all_tables(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in await cursor.fetchall()}
        assert "sessions" in tables
        assert "jobs" in tables
        assert "config" in tables
        assert "unsupported_urls" in tables

    async def test_wal_mode_enabled(self, db):
        cursor = await db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0] == "wal"

    async def test_busy_timeout_set(self, db):
        cursor = await db.execute("PRAGMA busy_timeout")
        row = await cursor.fetchone()
        assert row[0] == 5000

    async def test_indexes_created(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row[0] for row in await cursor.fetchall()}
        assert "idx_jobs_session_status" in indexes
        assert "idx_jobs_completed" in indexes
        assert "idx_sessions_last_seen" in indexes


class TestJobCrud:
    """CRUD operations on the jobs table."""

    async def test_create_and_get_roundtrip(self, db):
        job = _make_job()
        created = await create_job(db, job)
        assert created.id == job.id

        fetched = await get_job(db, job.id)
        assert fetched is not None
        assert fetched.id == job.id
        assert fetched.url == job.url
        assert fetched.status == JobStatus.queued

    async def test_get_nonexistent_returns_none(self, db):
        result = await get_job(db, "no-such-id")
        assert result is None

    async def test_get_jobs_by_session(self, db):
        j1 = _make_job(session_id="sess-A")
        j2 = _make_job(session_id="sess-A")
        j3 = _make_job(session_id="sess-B")
        await create_job(db, j1)
        await create_job(db, j2)
        await create_job(db, j3)

        sess_a_jobs = await get_jobs_by_session(db, "sess-A")
        assert len(sess_a_jobs) == 2
        assert all(j.session_id == "sess-A" for j in sess_a_jobs)

        sess_b_jobs = await get_jobs_by_session(db, "sess-B")
        assert len(sess_b_jobs) == 1

    async def test_update_job_status(self, db):
        job = _make_job()
        await create_job(db, job)

        await update_job_status(db, job.id, "failed", error_message="404 not found")
        updated = await get_job(db, job.id)
        assert updated is not None
        assert updated.status == JobStatus.failed
        assert updated.error_message == "404 not found"

    async def test_update_job_progress(self, db):
        job = _make_job()
        await create_job(db, job)

        await update_job_progress(
            db, job.id,
            progress_percent=42.5,
            speed="1.2 MiB/s",
            eta="2m30s",
            filename="video.mp4",
        )
        updated = await get_job(db, job.id)
        assert updated is not None
        assert updated.progress_percent == 42.5
        assert updated.speed == "1.2 MiB/s"
        assert updated.eta == "2m30s"
        assert updated.filename == "video.mp4"

    async def test_delete_job(self, db):
        job = _make_job()
        await create_job(db, job)

        await delete_job(db, job.id)
        assert await get_job(db, job.id) is None


class TestConcurrentWrites:
    """Verify WAL mode handles concurrent writers without SQLITE_BUSY."""

    async def test_three_concurrent_inserts(self, tmp_db_path):
        """Launch 3 simultaneous create_job calls via asyncio.gather."""
        db = await init_db(tmp_db_path)

        jobs = [_make_job(session_id="concurrent") for _ in range(3)]
        results = await asyncio.gather(
            *[create_job(db, j) for j in jobs],
            return_exceptions=True,
        )

        # No exceptions — all three succeeded
        for r in results:
            assert isinstance(r, Job), f"Expected Job, got {type(r).__name__}: {r}"

        # Verify all three exist
        all_jobs = await get_jobs_by_session(db, "concurrent")
        assert len(all_jobs) == 3

        await close_db(db)

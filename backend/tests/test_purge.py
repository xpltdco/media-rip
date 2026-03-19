"""Tests for the purge service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from app.core.config import AppConfig
from app.core.database import create_job, init_db, close_db
from app.models.job import Job
from app.services.purge import run_purge


def _make_job(
    session_id: str,
    status: str = "completed",
    filename: str | None = None,
    hours_ago: int = 0,
) -> Job:
    completed_at = (
        (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
        if status in ("completed", "failed", "expired")
        else None
    )
    return Job(
        id=str(uuid.uuid4()),
        session_id=session_id,
        url="https://example.com/video",
        status=status,
        filename=filename,
        created_at=datetime.now(timezone.utc).isoformat(),
        completed_at=completed_at,
    )


class TestPurge:
    """Purge service tests."""

    @pytest.mark.anyio
    async def test_purge_deletes_old_completed_jobs(self, db, tmp_path):
        config = AppConfig(
            downloads={"output_dir": str(tmp_path)},
            purge={"max_age_hours": 24},
        )
        sid = str(uuid.uuid4())

        # Create an old completed job (48 hours ago)
        job = _make_job(sid, "completed", hours_ago=48)
        await create_job(db, job)

        result = await run_purge(db, config)
        assert result["rows_deleted"] == 1

    @pytest.mark.anyio
    async def test_purge_skips_recent_completed(self, db, tmp_path):
        config = AppConfig(
            downloads={"output_dir": str(tmp_path)},
            purge={"max_age_hours": 24},
        )
        sid = str(uuid.uuid4())

        # Create a recent completed job (1 hour ago)
        job = _make_job(sid, "completed", hours_ago=1)
        await create_job(db, job)

        result = await run_purge(db, config)
        assert result["rows_deleted"] == 0

    @pytest.mark.anyio
    async def test_purge_skips_active_jobs(self, db, tmp_path):
        config = AppConfig(
            downloads={"output_dir": str(tmp_path)},
            purge={"max_age_hours": 0},  # purge everything terminal
        )
        sid = str(uuid.uuid4())

        # Active jobs should never be purged regardless of age
        await create_job(db, _make_job(sid, "queued", hours_ago=0))
        await create_job(db, _make_job(sid, "downloading", hours_ago=0))

        result = await run_purge(db, config)
        assert result["rows_deleted"] == 0
        assert result["active_skipped"] == 2

    @pytest.mark.anyio
    async def test_purge_deletes_files(self, db, tmp_path):
        config = AppConfig(
            downloads={"output_dir": str(tmp_path)},
            purge={"max_age_hours": 0},
        )
        sid = str(uuid.uuid4())

        # Create a file on disk
        test_file = tmp_path / "video.mp4"
        test_file.write_text("fake video data")

        job = _make_job(sid, "completed", filename="video.mp4", hours_ago=1)
        await create_job(db, job)

        result = await run_purge(db, config)
        assert result["files_deleted"] == 1
        assert not test_file.exists()

    @pytest.mark.anyio
    async def test_purge_handles_missing_files(self, db, tmp_path):
        config = AppConfig(
            downloads={"output_dir": str(tmp_path)},
            purge={"max_age_hours": 0},
        )
        sid = str(uuid.uuid4())

        # Job references a file that doesn't exist on disk
        job = _make_job(sid, "completed", filename="gone.mp4", hours_ago=1)
        await create_job(db, job)

        result = await run_purge(db, config)
        assert result["rows_deleted"] == 1
        assert result["files_missing"] == 1

    @pytest.mark.anyio
    async def test_purge_mixed_statuses(self, db, tmp_path):
        config = AppConfig(
            downloads={"output_dir": str(tmp_path)},
            purge={"max_age_hours": 0},
        )
        sid = str(uuid.uuid4())

        await create_job(db, _make_job(sid, "completed", hours_ago=1))
        await create_job(db, _make_job(sid, "failed", hours_ago=1))
        await create_job(db, _make_job(sid, "queued", hours_ago=0))

        result = await run_purge(db, config)
        assert result["rows_deleted"] == 2
        assert result["active_skipped"] == 1

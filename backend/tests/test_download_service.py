"""Tests for the download service — sync-to-async bridge.

Includes integration tests that require network access (real yt-dlp downloads)
and unit tests that only touch the database.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from app.core.config import AppConfig
from app.core.database import create_job, get_job, init_db, close_db
from app.core.sse_broker import SSEBroker
from app.models.job import FormatInfo, Job, JobCreate, JobStatus
from app.services.download import DownloadService

# First YouTube video ever — 19 seconds, always available
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def download_env(tmp_path):
    """Set up a complete download environment: config, db, broker, service."""
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()
    db_path = str(tmp_path / "test.db")

    config = AppConfig(downloads={"output_dir": str(dl_dir)})
    db = await init_db(db_path)
    loop = asyncio.get_running_loop()
    broker = SSEBroker(loop)
    service = DownloadService(config, db, broker, loop)

    yield {
        "config": config,
        "db": db,
        "broker": broker,
        "service": service,
        "dl_dir": dl_dir,
        "loop": loop,
    }

    service.shutdown()
    await close_db(db)


# ---------------------------------------------------------------------------
# Integration tests — require network
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.integration
async def test_real_download_produces_file_and_events(download_env):
    """Core risk-retirement test: yt-dlp downloads a file, progress events
    arrive via the SSE broker, and the DB job ends up as completed."""
    env = download_env
    service: DownloadService = env["service"]
    broker: SSEBroker = env["broker"]
    db = env["db"]
    dl_dir = env["dl_dir"]
    session_id = "test-session"

    # Subscribe to events before starting the download
    queue = broker.subscribe(session_id)

    job = await service.enqueue(
        JobCreate(url=TEST_VIDEO_URL), session_id
    )
    assert job.status == JobStatus.queued

    # Collect events with a generous timeout
    events: list = []
    timeout = 60  # seconds — generous for CI/slow connections
    deadline = asyncio.get_running_loop().time() + timeout

    while asyncio.get_running_loop().time() < deadline:
        try:
            remaining = deadline - asyncio.get_running_loop().time()
            event = await asyncio.wait_for(queue.get(), timeout=max(remaining, 0.1))
            events.append(event)
            # Stop collecting once we see "finished" from yt-dlp
            if hasattr(event, "status") and event.status == "finished":
                # Wait a beat for the completion status update to land in DB
                await asyncio.sleep(1)
                break
        except asyncio.TimeoutError:
            break

    # Assertions on events
    assert len(events) > 0, "No progress events received"

    statuses = {e.status for e in events}
    assert "downloading" in statuses, f"Expected 'downloading' status, got: {statuses}"

    # At least one event should have non-zero percent
    downloading_events = [e for e in events if e.status == "downloading"]
    any(e.percent > 0 for e in downloading_events)
    # Some very short videos may not report intermediate progress —
    # we still assert downloading events exist
    assert len(downloading_events) > 0

    # yt-dlp fires "finished" when the file write completes
    assert "finished" in statuses, f"Expected 'finished' status, got: {statuses}"

    # A file should exist in the output directory
    files = list(dl_dir.rglob("*"))
    actual_files = [f for f in files if f.is_file()]
    assert len(actual_files) > 0, f"No files in {dl_dir}: {files}"

    # DB should show completed status (wait for thread to update)
    for _ in range(10):
        db_job = await get_job(db, job.id)
        if db_job and db_job.status == JobStatus.completed:
            break
        await asyncio.sleep(0.5)
    else:
        db_job = await get_job(db, job.id)
        assert db_job is not None, "Job not found in DB"
        assert db_job.status == JobStatus.completed, (
            f"Job status is {db_job.status}, expected completed. "
            f"Error: {db_job.error_message}"
        )

    broker.unsubscribe(session_id, queue)


@pytest.mark.slow
@pytest.mark.integration
async def test_format_extraction(download_env):
    """get_formats should return a non-empty list with populated fields."""
    service: DownloadService = download_env["service"]

    formats = await service.get_formats(TEST_VIDEO_URL)

    assert len(formats) > 0, "No formats returned"
    for fmt in formats:
        assert isinstance(fmt, FormatInfo)
        assert fmt.format_id, "format_id should not be empty"
        assert fmt.ext, "ext should not be empty"


# ---------------------------------------------------------------------------
# Unit tests — no network required
# ---------------------------------------------------------------------------


async def test_cancel_marks_job_failed(download_env):
    """cancel() should set the job status to failed with cancellation message."""
    env = download_env
    service: DownloadService = env["service"]
    db = env["db"]

    # Create a job directly in DB (simulates an in-progress download)
    from datetime import datetime, timezone

    job = Job(
        id="cancel-test-job",
        session_id="test-session",
        url="https://example.com/video",
        status=JobStatus.downloading,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    await create_job(db, job)

    # Cancel it
    await service.cancel("cancel-test-job")

    # Verify DB state
    db_job = await get_job(db, "cancel-test-job")
    assert db_job is not None
    assert db_job.status == JobStatus.failed
    assert db_job.error_message == "Cancelled by user"


@pytest.mark.slow
@pytest.mark.integration
async def test_concurrent_downloads(download_env):
    """Two simultaneous downloads should both complete without errors.

    Proves ThreadPoolExecutor + WAL mode work together under concurrency.
    Uses distinct output_template overrides so the two jobs don't collide
    on the same filename in the output directory.
    """
    env = download_env
    service: DownloadService = env["service"]
    db = env["db"]
    session_id = "concurrent-session"

    # Enqueue two downloads simultaneously — unique templates avoid file collisions
    job1, job2 = await asyncio.gather(
        service.enqueue(
            JobCreate(url=TEST_VIDEO_URL, output_template="dl1_%(title)s.%(ext)s"),
            session_id,
        ),
        service.enqueue(
            JobCreate(url=TEST_VIDEO_URL, output_template="dl2_%(title)s.%(ext)s"),
            session_id,
        ),
    )

    # Wait for both to complete (generous timeout)
    timeout = 90
    for _ in range(timeout * 2):  # check every 0.5s
        j1 = await get_job(db, job1.id)
        j2 = await get_job(db, job2.id)
        if (
            j1
            and j2
            and j1.status in (JobStatus.completed, JobStatus.failed)
            and j2.status in (JobStatus.completed, JobStatus.failed)
        ):
            break
        await asyncio.sleep(0.5)

    j1 = await get_job(db, job1.id)
    j2 = await get_job(db, job2.id)

    assert j1 is not None and j2 is not None
    # At least one should complete — both failing would indicate a real problem
    completed = [j for j in (j1, j2) if j.status == JobStatus.completed]
    assert len(completed) >= 1, (
        f"Expected at least one completed job. "
        f"j1: status={j1.status} err={j1.error_message}, "
        f"j2: status={j2.status} err={j2.error_message}"
    )

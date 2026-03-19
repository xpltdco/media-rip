"""Tests for Pydantic models — job.py and session.py."""

from __future__ import annotations

import pytest

from app.models.job import (
    FormatInfo,
    Job,
    JobCreate,
    JobStatus,
    ProgressEvent,
)
from app.models.session import Session


# ---------------------------------------------------------------------------
# JobStatus
# ---------------------------------------------------------------------------

class TestJobStatus:
    def test_all_values(self):
        expected = {"queued", "extracting", "downloading", "completed", "failed", "expired"}
        actual = {s.value for s in JobStatus}
        assert actual == expected

    def test_is_string_enum(self):
        assert isinstance(JobStatus.queued, str)
        assert JobStatus.queued == "queued"


# ---------------------------------------------------------------------------
# JobCreate
# ---------------------------------------------------------------------------

class TestJobCreate:
    def test_minimal(self):
        jc = JobCreate(url="https://example.com/video")
        assert jc.url == "https://example.com/video"
        assert jc.format_id is None
        assert jc.quality is None
        assert jc.output_template is None

    def test_with_all_fields(self):
        jc = JobCreate(
            url="https://example.com/video",
            format_id="22",
            quality="best",
            output_template="%(title)s.%(ext)s",
        )
        assert jc.format_id == "22"
        assert jc.quality == "best"


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class TestJob:
    def test_full_construction(self):
        job = Job(
            id="abc-123",
            session_id="sess-001",
            url="https://example.com/video",
            status=JobStatus.downloading,
            format_id="22",
            quality="best",
            output_template="%(title)s.%(ext)s",
            filename="video.mp4",
            filesize=1024000,
            progress_percent=45.5,
            speed="1.2 MiB/s",
            eta="30s",
            error_message=None,
            created_at="2026-03-17T10:00:00Z",
            started_at="2026-03-17T10:00:01Z",
            completed_at=None,
        )
        assert job.id == "abc-123"
        assert job.status == JobStatus.downloading
        assert job.progress_percent == 45.5
        assert job.filesize == 1024000

    def test_defaults(self):
        job = Job(
            id="abc-123",
            session_id="sess-001",
            url="https://example.com/video",
            created_at="2026-03-17T10:00:00Z",
        )
        assert job.status == JobStatus.queued
        assert job.progress_percent == 0.0
        assert job.filename is None
        assert job.error_message is None


# ---------------------------------------------------------------------------
# ProgressEvent.from_yt_dlp
# ---------------------------------------------------------------------------

class TestProgressEventFromYtDlp:
    def test_complete_dict(self):
        """total_bytes present — normal download in progress."""
        d = {
            "status": "downloading",
            "downloaded_bytes": 5000,
            "total_bytes": 10000,
            "speed": 1048576.0,  # 1 MiB/s
            "eta": 90,
            "filename": "/tmp/video.mp4",
        }
        ev = ProgressEvent.from_yt_dlp("job-1", d)
        assert ev.job_id == "job-1"
        assert ev.status == "downloading"
        assert ev.percent == 50.0
        assert ev.speed == "1.0 MiB/s"
        assert ev.eta == "1m30s"
        assert ev.downloaded_bytes == 5000
        assert ev.total_bytes == 10000
        assert ev.filename == "/tmp/video.mp4"

    def test_total_bytes_none_falls_back_to_estimate(self):
        """total_bytes is None — use total_bytes_estimate instead."""
        d = {
            "status": "downloading",
            "downloaded_bytes": 2500,
            "total_bytes": None,
            "total_bytes_estimate": 5000,
            "speed": 512000.0,
            "eta": 5,
            "filename": "/tmp/video.mp4",
        }
        ev = ProgressEvent.from_yt_dlp("job-2", d)
        assert ev.percent == 50.0
        assert ev.total_bytes == 5000

    def test_both_totals_none_percent_zero(self):
        """Both total_bytes and total_bytes_estimate are None → percent = 0.0."""
        d = {
            "status": "downloading",
            "downloaded_bytes": 1234,
            "total_bytes": None,
            "total_bytes_estimate": None,
            "speed": None,
            "eta": None,
            "filename": "/tmp/video.mp4",
        }
        ev = ProgressEvent.from_yt_dlp("job-3", d)
        assert ev.percent == 0.0
        assert ev.speed is None
        assert ev.eta is None

    def test_finished_status(self):
        """yt-dlp sends status=finished when download completes."""
        d = {
            "status": "finished",
            "downloaded_bytes": 10000,
            "total_bytes": 10000,
            "speed": None,
            "eta": None,
            "filename": "/tmp/video.mp4",
        }
        ev = ProgressEvent.from_yt_dlp("job-4", d)
        assert ev.status == "finished"
        assert ev.percent == 100.0
        assert ev.filename == "/tmp/video.mp4"

    def test_missing_keys_graceful(self):
        """Minimal dict — only status present. Should not raise."""
        d = {"status": "downloading"}
        ev = ProgressEvent.from_yt_dlp("job-5", d)
        assert ev.percent == 0.0
        assert ev.speed is None
        assert ev.eta is None
        assert ev.downloaded_bytes is None

    def test_speed_formatting_kib(self):
        d = {
            "status": "downloading",
            "downloaded_bytes": 100,
            "total_bytes": 1000,
            "speed": 2048.0,  # 2 KiB/s
            "eta": 3700,
        }
        ev = ProgressEvent.from_yt_dlp("job-6", d)
        assert ev.speed == "2.0 KiB/s"
        assert ev.eta == "1h01m40s"


# ---------------------------------------------------------------------------
# FormatInfo
# ---------------------------------------------------------------------------

class TestFormatInfo:
    def test_construction(self):
        fi = FormatInfo(
            format_id="22",
            ext="mp4",
            resolution="1280x720",
            codec="h264",
            filesize=50_000_000,
            format_note="720p",
            vcodec="avc1.64001F",
            acodec="mp4a.40.2",
        )
        assert fi.format_id == "22"
        assert fi.ext == "mp4"
        assert fi.resolution == "1280x720"
        assert fi.vcodec == "avc1.64001F"

    def test_minimal(self):
        fi = FormatInfo(format_id="18", ext="mp4")
        assert fi.resolution is None
        assert fi.filesize is None


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class TestSession:
    def test_construction_with_defaults(self):
        s = Session(
            id="sess-abc",
            created_at="2026-03-17T10:00:00Z",
            last_seen="2026-03-17T10:05:00Z",
        )
        assert s.id == "sess-abc"
        assert s.job_count == 0

    def test_construction_with_job_count(self):
        s = Session(
            id="sess-abc",
            created_at="2026-03-17T10:00:00Z",
            last_seen="2026-03-17T10:05:00Z",
            job_count=5,
        )
        assert s.job_count == 5

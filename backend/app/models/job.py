"""Job-related Pydantic models for media.rip()."""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class JobStatus(str, enum.Enum):
    """Status values for a download job."""

    queued = "queued"
    extracting = "extracting"
    downloading = "downloading"
    completed = "completed"
    failed = "failed"
    expired = "expired"


class JobCreate(BaseModel):
    """Payload for creating a new download job."""

    url: str
    format_id: str | None = None
    quality: str | None = None
    output_template: str | None = None
    media_type: str | None = None       # "video" | "audio"
    output_format: str | None = None    # e.g. "mp3", "wav", "mp4", "webm"


class Job(BaseModel):
    """Full job model matching the DB schema."""

    id: str
    session_id: str
    url: str
    status: JobStatus = JobStatus.queued
    format_id: str | None = None
    quality: str | None = None
    output_template: str | None = None
    filename: str | None = None
    filesize: int | None = None
    progress_percent: float = Field(default=0.0)
    speed: str | None = None
    eta: str | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class ProgressEvent(BaseModel):
    """Real-time progress event, typically pushed via SSE."""

    job_id: str
    status: str
    percent: float
    speed: str | None = None
    eta: str | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    filename: str | None = None

    @classmethod
    def from_yt_dlp(cls, job_id: str, d: dict) -> ProgressEvent:
        """Normalize a raw yt-dlp progress hook dictionary.

        Handles the common case where ``total_bytes`` is *None* (subtitles,
        live streams, some extractors) by falling back to
        ``total_bytes_estimate``.  If both are absent, percent is ``0.0``.
        """
        status = d.get("status", "unknown")

        downloaded = d.get("downloaded_bytes") or 0
        total = d.get("total_bytes") or d.get("total_bytes_estimate")

        if total and downloaded:
            percent = round(downloaded / total * 100, 2)
        else:
            percent = 0.0

        # Speed: yt-dlp provides bytes/sec as a float or None
        raw_speed = d.get("speed")
        if raw_speed is not None:
            speed = _format_speed(raw_speed)
        else:
            speed = None

        # ETA: yt-dlp provides seconds remaining as int or None
        raw_eta = d.get("eta")
        if raw_eta is not None:
            eta = _format_eta(int(raw_eta))
        else:
            eta = None

        return cls(
            job_id=job_id,
            status=status,
            percent=percent,
            speed=speed,
            eta=eta,
            downloaded_bytes=downloaded if downloaded else None,
            total_bytes=total,
            filename=d.get("filename"),
        )


class FormatInfo(BaseModel):
    """Available format information returned by yt-dlp extract_info."""

    format_id: str
    ext: str
    resolution: str | None = None
    codec: str | None = None
    filesize: int | None = None
    format_note: str | None = None
    vcodec: str | None = None
    acodec: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_speed(bytes_per_sec: float) -> str:
    """Format bytes/sec into a human-readable string."""
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KiB/s"
    elif bytes_per_sec < 1024 * 1024 * 1024:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MiB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024 * 1024):.2f} GiB/s"


def _format_eta(seconds: int) -> str:
    """Format seconds into a human-readable ETA string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m{s:02d}s"
    else:
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{h}h{m:02d}m{s:02d}s"

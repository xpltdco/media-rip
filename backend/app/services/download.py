"""Download service — yt-dlp wrapper with sync-to-async progress bridging.

Wraps synchronous yt-dlp operations in a :class:`~concurrent.futures.ThreadPoolExecutor`
and bridges progress events to the async world via :class:`~app.core.sse_broker.SSEBroker`.
Each download job gets a **fresh** ``YoutubeDL`` instance — they are never shared across
threads (yt-dlp has mutable internal state: cookies, temp files, logger).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yt_dlp

from app.core.config import AppConfig
from app.core.database import (
    create_job,
    get_job,
    update_job_progress,
    update_job_status,
)
from app.core.sse_broker import SSEBroker
from app.models.job import (
    FormatInfo,
    Job,
    JobCreate,
    JobStatus,
    ProgressEvent,
)
from app.services.output_template import resolve_template

logger = logging.getLogger("mediarip.download")


class DownloadService:
    """Manages yt-dlp downloads with async-compatible progress reporting.

    Parameters
    ----------
    config:
        Application configuration (download paths, concurrency, templates).
    db:
        Async SQLite connection (aiosqlite).
    broker:
        SSE event broker for real-time progress push.
    loop:
        The asyncio event loop. Captured once at construction — must not be
        called from inside a worker thread.
    """

    def __init__(
        self,
        config: AppConfig,
        db,  # aiosqlite.Connection
        broker: SSEBroker,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._config = config
        self._db = db
        self._broker = broker
        self._loop = loop
        self._executor = ThreadPoolExecutor(
            max_workers=config.downloads.max_concurrent,
            thread_name_prefix="ytdl",
        )
        # Per-job throttle state for DB writes (only used inside worker threads)
        self._last_db_percent: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public async interface
    # ------------------------------------------------------------------

    async def enqueue(self, job_create: JobCreate, session_id: str) -> Job:
        """Create a job and submit it for background download.

        Returns the ``Job`` immediately with status ``queued``.
        """
        job_id = str(uuid.uuid4())
        template = resolve_template(
            job_create.url,
            job_create.output_template,
            self._config,
        )

        now = datetime.now(timezone.utc).isoformat()
        job = Job(
            id=job_id,
            session_id=session_id,
            url=job_create.url,
            status=JobStatus.queued,
            format_id=job_create.format_id,
            quality=job_create.quality,
            output_template=template,
            created_at=now,
        )

        await create_job(self._db, job)
        logger.info("Job %s created for URL: %s", job_id, job_create.url)

        # Build yt-dlp options
        output_dir = self._config.downloads.output_dir
        os.makedirs(output_dir, exist_ok=True)
        outtmpl = os.path.join(output_dir, template)

        opts: dict = {
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }
        if job_create.format_id:
            opts["format"] = job_create.format_id
        elif job_create.quality:
            opts["format"] = job_create.quality

        # Output format post-processing (e.g. convert to mp3, mp4)
        out_fmt = job_create.output_format
        if out_fmt:
            if out_fmt in ("mp3", "wav", "m4a", "flac", "opus"):
                # Audio conversion via yt-dlp postprocessor
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": out_fmt,
                    "preferredquality": "0" if out_fmt in ("flac", "wav") else "192",
                }]
            elif out_fmt == "mp4":
                # Prefer mp4-native streams; remux if needed
                opts["merge_output_format"] = "mp4"
                opts.setdefault("format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best")
                opts["postprocessors"] = [{
                    "key": "FFmpegVideoRemuxer",
                    "preferedformat": "mp4",
                }]

        self._loop.run_in_executor(
            self._executor,
            self._run_download,
            job_id,
            job_create.url,
            opts,
            session_id,
        )
        return job

    async def get_formats(self, url: str) -> list[FormatInfo]:
        """Extract available formats for *url* without downloading.

        Runs yt-dlp ``extract_info`` in the thread pool.
        """
        info = await self._loop.run_in_executor(
            self._executor,
            self._extract_info,
            url,
        )
        if not info:
            return []

        formats_raw = info.get("formats") or []
        result: list[FormatInfo] = []
        for f in formats_raw:
            result.append(
                FormatInfo(
                    format_id=f.get("format_id", "unknown"),
                    ext=f.get("ext", "unknown"),
                    resolution=f.get("resolution"),
                    codec=f.get("vcodec"),
                    filesize=f.get("filesize"),  # may be None — that's fine
                    format_note=f.get("format_note"),
                    vcodec=f.get("vcodec"),
                    acodec=f.get("acodec"),
                )
            )

        # Sort: best resolution first (descending by height, fallback 0)
        result.sort(
            key=lambda fi: _parse_resolution_height(fi.resolution),
            reverse=True,
        )
        return result

    async def cancel(self, job_id: str) -> None:
        """Mark a job as failed with a cancellation message.

        Note: yt-dlp has no reliable mid-stream abort mechanism. The
        worker thread continues but the job is marked as failed in the DB.
        """
        await update_job_status(
            self._db, job_id, JobStatus.failed.value, "Cancelled by user"
        )
        logger.info("Job %s cancelled by user", job_id)

    def shutdown(self) -> None:
        """Shut down the thread pool (non-blocking)."""
        self._executor.shutdown(wait=False)
        logger.info("Download executor shut down")

    # ------------------------------------------------------------------
    # Private — runs in worker threads
    # ------------------------------------------------------------------

    def _run_download(
        self,
        job_id: str,
        url: str,
        opts: dict,
        session_id: str,
    ) -> None:
        """Execute yt-dlp download in a worker thread.

        Creates a fresh ``YoutubeDL`` instance (never shared) and bridges
        progress events to the async event loop.
        """
        logger.info("Job %s starting download: %s", job_id, url)
        self._last_db_percent[job_id] = -1.0

        def progress_hook(d: dict) -> None:
            try:
                event = ProgressEvent.from_yt_dlp(job_id, d)

                # Normalize filename to be relative to the output directory
                # so the frontend can construct download URLs correctly.
                if event.filename:
                    abs_path = Path(event.filename).resolve()
                    out_dir = Path(self._config.downloads.output_dir).resolve()
                    try:
                        event.filename = str(abs_path.relative_to(out_dir))
                    except ValueError:
                        # Not under output_dir — use basename as fallback
                        event.filename = abs_path.name

                # Always publish to SSE broker (cheap, in-memory)
                self._broker.publish(session_id, event)

                # Throttle DB writes: ≥1% change or status change
                last_pct = self._last_db_percent.get(job_id, -1.0)
                status_changed = d.get("status") in ("finished", "error")
                pct_changed = abs(event.percent - last_pct) >= 1.0

                if pct_changed or status_changed:
                    self._last_db_percent[job_id] = event.percent
                    logger.debug(
                        "Job %s DB write: percent=%.1f status=%s filename=%s",
                        job_id, event.percent, event.status, event.filename,
                    )
                    future = asyncio.run_coroutine_threadsafe(
                        update_job_progress(
                            self._db,
                            job_id,
                            event.percent,
                            event.speed,
                            event.eta,
                            event.filename,
                        ),
                        self._loop,
                    )
                    # Block worker thread until DB write completes
                    future.result(timeout=10)
            except Exception:
                logger.exception("Job %s progress hook error (status=%s)", job_id, d.get("status"))

        # Track final filename after postprocessing (e.g. audio conversion)
        final_filename = [None]  # mutable container for closure

        def postprocessor_hook(d: dict) -> None:
            """Capture the final filename after postprocessing."""
            if d.get("status") == "finished":
                info = d.get("info_dict", {})
                # After postprocessing, filepath reflects the converted file
                filepath = info.get("filepath") or info.get("filename")
                if filepath:
                    abs_path = Path(filepath).resolve()
                    out_dir = Path(self._config.downloads.output_dir).resolve()
                    try:
                        final_filename[0] = str(abs_path.relative_to(out_dir))
                    except ValueError:
                        final_filename[0] = abs_path.name

        opts["progress_hooks"] = [progress_hook]
        opts["postprocessor_hooks"] = [postprocessor_hook]

        try:
            # Mark as downloading and notify SSE
            asyncio.run_coroutine_threadsafe(
                update_job_status(self._db, job_id, JobStatus.downloading.value),
                self._loop,
            ).result(timeout=10)
            self._broker.publish(session_id, {
                "event": "job_update",
                "data": {"job_id": job_id, "status": "downloading", "percent": 0,
                         "speed": None, "eta": None, "filename": None},
            })

            # Fresh YoutubeDL instance — never shared
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Extract info first to determine the output filename.
                # This is needed because yt-dlp may skip progress hooks
                # entirely when the file already exists.
                info = ydl.extract_info(url, download=False)
                if info:
                    raw_fn = ydl.prepare_filename(info)
                    abs_path = Path(raw_fn).resolve()
                    out_dir = Path(self._config.downloads.output_dir).resolve()
                    try:
                        relative_fn = str(abs_path.relative_to(out_dir))
                    except ValueError:
                        relative_fn = abs_path.name
                else:
                    relative_fn = None

                ydl.download([url])

            # Use postprocessor's final filename if available (handles
            # audio conversion changing .webm → .mp3 etc.)
            if final_filename[0]:
                relative_fn = final_filename[0]

            # Persist filename to DB (progress hooks may not have fired
            # if the file already existed)
            if relative_fn:
                asyncio.run_coroutine_threadsafe(
                    update_job_progress(
                        self._db, job_id, 100.0,
                        None, None, relative_fn,
                    ),
                    self._loop,
                ).result(timeout=10)

            # Mark as completed and notify SSE
            asyncio.run_coroutine_threadsafe(
                update_job_status(self._db, job_id, JobStatus.completed.value),
                self._loop,
            ).result(timeout=10)
            self._broker.publish(session_id, {
                "event": "job_update",
                "data": {"job_id": job_id, "status": "completed", "percent": 100,
                         "speed": None, "eta": None, "filename": relative_fn},
            })
            logger.info("Job %s completed", job_id)

        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e, exc_info=True)
            try:
                asyncio.run_coroutine_threadsafe(
                    update_job_status(
                        self._db, job_id, JobStatus.failed.value, str(e)
                    ),
                    self._loop,
                ).result(timeout=10)
                self._broker.publish(session_id, {
                    "event": "job_update",
                    "data": {"job_id": job_id, "status": "failed", "percent": 0,
                             "speed": None, "eta": None, "filename": None,
                             "error_message": str(e)},
                })
            except Exception:
                logger.exception("Job %s failed to update status after error", job_id)

        finally:
            self._last_db_percent.pop(job_id, None)

    def _extract_info(self, url: str) -> dict | None:
        """Run yt-dlp extract_info synchronously (called from thread pool)."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception:
            logger.exception("Format extraction failed for %s", url)
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_resolution_height(resolution: str | None) -> int:
    """Extract numeric height from a resolution string like '1080p' or '1920x1080'.

    Returns 0 for unparseable values so they sort last.
    """
    if not resolution:
        return 0
    resolution = resolution.lower().strip()
    # Handle "1080p" style
    if resolution.endswith("p"):
        try:
            return int(resolution[:-1])
        except ValueError:
            pass
    # Handle "1920x1080" style
    if "x" in resolution:
        try:
            return int(resolution.split("x")[-1])
        except ValueError:
            pass
    # Handle bare number
    try:
        return int(resolution)
    except ValueError:
        return 0

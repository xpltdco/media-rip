"""Purge service — clean up expired downloads and database rows.

Respects active job protection: never deletes files for jobs with
status in (queued, extracting, downloading).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiosqlite

from app.core.config import AppConfig

logger = logging.getLogger("mediarip.purge")


async def run_purge(db: aiosqlite.Connection, config: AppConfig) -> dict:
    """Execute a purge cycle.

    Deletes completed/failed/expired jobs older than ``config.purge.max_age_hours``
    and their associated files from disk.

    Returns a summary dict with counts.
    """
    max_age_hours = config.purge.max_age_hours
    output_dir = Path(config.downloads.output_dir)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()

    logger.info("Purge starting: max_age=%dh, cutoff=%s", max_age_hours, cutoff)

    # Find purgeable jobs — terminal status AND older than cutoff
    cursor = await db.execute(
        """
        SELECT id, filename FROM jobs
        WHERE status IN ('completed', 'failed', 'expired')
          AND completed_at IS NOT NULL
          AND completed_at < ?
        """,
        (cutoff,),
    )
    rows = await cursor.fetchall()

    files_deleted = 0
    files_missing = 0
    rows_deleted = 0

    for row in rows:
        job_id = row["id"]
        filename = row["filename"]

        # Delete file from disk if it exists
        if filename:
            file_path = output_dir / Path(filename).name
            if file_path.is_file():
                try:
                    file_path.unlink()
                    files_deleted += 1
                    logger.debug("Purge: deleted file %s (job %s)", file_path, job_id)
                except OSError as e:
                    logger.warning("Purge: failed to delete %s: %s", file_path, e)
            else:
                files_missing += 1
                logger.debug("Purge: file already gone %s (job %s)", file_path, job_id)

        # Delete DB row
        await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        rows_deleted += 1

    await db.commit()

    # Count skipped active jobs for observability
    active_cursor = await db.execute(
        "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'extracting', 'downloading')"
    )
    active_row = await active_cursor.fetchone()
    active_skipped = active_row[0] if active_row else 0

    result = {
        "rows_deleted": rows_deleted,
        "files_deleted": files_deleted,
        "files_missing": files_missing,
        "active_skipped": active_skipped,
    }

    logger.info(
        "Purge complete: %d rows deleted, %d files deleted, %d files already gone, %d active skipped",
        rows_deleted,
        files_deleted,
        files_missing,
        active_skipped,
    )

    return result

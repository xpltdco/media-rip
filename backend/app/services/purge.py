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


async def run_purge(
    db: aiosqlite.Connection,
    config: AppConfig,
    *,
    purge_all: bool = False,
) -> dict:
    """Execute a purge cycle.

    When *purge_all* is True, deletes ALL completed/failed jobs regardless
    of age (manual "clear everything" behavior).

    Otherwise respects retention: privacy_retention_hours when privacy mode
    is active, max_age_hours otherwise.

    Returns a summary dict with counts.
    """
    overrides = getattr(config, "_runtime_overrides", {})

    if purge_all:
        cutoff = datetime.now(timezone.utc).isoformat()  # everything up to now
        logger.info("Purge ALL starting (manual clear)")
    else:
        privacy_on = overrides.get("privacy_mode", config.purge.privacy_mode)
        if privacy_on:
            retention = overrides.get(
                "privacy_retention_hours", config.purge.privacy_retention_hours
            )
        else:
            retention = config.purge.max_age_hours
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention)).isoformat()
        logger.info("Purge starting: retention=%dh (privacy=%s), cutoff=%s", retention, privacy_on, cutoff)

    output_dir = Path(config.downloads.output_dir)

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
    deleted_job_ids: list[str] = []

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
        deleted_job_ids.append(job_id)

    await db.commit()

    # Clean up orphaned sessions (sessions with no remaining jobs)
    if purge_all:
        orphan_cursor = await db.execute(
            """
            DELETE FROM sessions
            WHERE id NOT IN (SELECT DISTINCT session_id FROM jobs)
            """
        )
        sessions_deleted = orphan_cursor.rowcount
        await db.commit()
        logger.info("Purge: removed %d orphaned sessions", sessions_deleted)
    else:
        sessions_deleted = 0

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
        "sessions_deleted": sessions_deleted,
        "deleted_job_ids": deleted_job_ids,
    }

    logger.info(
        "Purge complete: %d rows deleted, %d files deleted, %d files already gone, %d active skipped",
        rows_deleted,
        files_deleted,
        files_missing,
        active_skipped,
    )

    return result

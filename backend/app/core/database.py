"""SQLite database layer with WAL mode and async CRUD operations.

Uses aiosqlite for async access.  ``init_db`` sets critical PRAGMAs
(busy_timeout, WAL, synchronous) *before* creating any tables so that
concurrent download workers never hit ``SQLITE_BUSY``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiosqlite

from app.models.job import Job, JobStatus

logger = logging.getLogger("mediarip.database")


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_TABLES = """
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL,
    url              TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'queued',
    format_id        TEXT,
    quality          TEXT,
    output_template  TEXT,
    filename         TEXT,
    filesize         INTEGER,
    progress_percent REAL DEFAULT 0,
    speed            TEXT,
    eta              TEXT,
    error_message    TEXT,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    completed_at     TEXT
);

CREATE TABLE IF NOT EXISTS config (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS unsupported_urls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT NOT NULL,
    session_id TEXT,
    error      TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS error_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT NOT NULL,
    domain     TEXT,
    error      TEXT NOT NULL,
    format_id  TEXT,
    media_type TEXT,
    session_id TEXT,
    created_at TEXT NOT NULL
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_jobs_session_status ON jobs(session_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_completed       ON jobs(completed_at);
CREATE INDEX IF NOT EXISTS idx_sessions_last_seen   ON sessions(last_seen);
"""


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


async def init_db(db_path: str) -> aiosqlite.Connection:
    """Open the database and apply PRAGMAs + schema.

    PRAGMA order matters:
      1. ``busy_timeout`` — prevents immediate ``SQLITE_BUSY`` on lock contention
      2. ``journal_mode=WAL`` — enables concurrent readers + single writer
         (falls back to DELETE on filesystems that lack shared-memory support,
         e.g. CIFS/SMB mounts)
      3. ``synchronous=NORMAL`` — safe durability level for WAL mode

    Returns the ready-to-use connection.
    """
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row

    # --- PRAGMAs (before any DDL) ---
    await db.execute("PRAGMA busy_timeout = 5000")

    # Attempt WAL mode, then verify it actually works by doing a test write.
    # On CIFS/NFS/FUSE mounts WAL's shared-memory primitives silently fail
    # even though the PRAGMA returns "wal".  A concrete write attempt is the
    # only reliable way to detect this.
    journal_mode = await _try_journal_mode(db, "wal")

    if journal_mode == "wal":
        try:
            # Probe with an actual write — WAL on CIFS explodes here
            await db.execute(
                "CREATE TABLE IF NOT EXISTS _wal_probe (_x INTEGER)"
            )
            await db.execute("DROP TABLE IF EXISTS _wal_probe")
            await db.commit()
        except Exception:
            logger.warning(
                "WAL mode set but write failed — filesystem likely lacks "
                "shared-memory support (CIFS/NFS?). Switching to DELETE mode."
            )
            # Close and reopen so SQLite drops the broken WAL state
            await db.close()
            # Remove stale WAL/SHM files that the broken open left behind
            import pathlib
            for suffix in ("-wal", "-shm"):
                p = pathlib.Path(db_path + suffix)
                p.unlink(missing_ok=True)
            db = await aiosqlite.connect(db_path)
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout = 5000")
            journal_mode = await _try_journal_mode(db, "delete")

    logger.info("journal_mode set to %s", journal_mode)

    await db.execute("PRAGMA synchronous = NORMAL")

    # --- Schema ---
    await db.executescript(_TABLES)
    await db.executescript(_INDEXES)
    logger.info("Database tables and indexes created at %s", db_path)

    return db


async def _try_journal_mode(
    db: aiosqlite.Connection, mode: str,
) -> str:
    """Try setting *mode* and return the actual journal mode string."""
    try:
        result = await db.execute(f"PRAGMA journal_mode = {mode}")
        row = await result.fetchone()
        return (row[0] if row else "unknown").lower()
    except Exception as exc:
        logger.warning("PRAGMA journal_mode=%s failed: %s", mode, exc)
        return "error"

    await db.execute("PRAGMA synchronous = NORMAL")

    # --- Schema ---
    await db.executescript(_TABLES)
    await db.executescript(_INDEXES)
    logger.info("Database tables and indexes created at %s", db_path)

    return db


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


async def create_job(db: aiosqlite.Connection, job: Job) -> Job:
    """Insert a new job row and return the model."""
    await db.execute(
        """
        INSERT INTO jobs (
            id, session_id, url, status, format_id, quality,
            output_template, filename, filesize, progress_percent,
            speed, eta, error_message, created_at, started_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.id,
            job.session_id,
            job.url,
            job.status.value if isinstance(job.status, JobStatus) else job.status,
            job.format_id,
            job.quality,
            job.output_template,
            job.filename,
            job.filesize,
            job.progress_percent,
            job.speed,
            job.eta,
            job.error_message,
            job.created_at,
            job.started_at,
            job.completed_at,
        ),
    )
    await db.commit()
    return job


def _row_to_job(row: aiosqlite.Row) -> Job:
    """Convert a database row to a Job model."""
    return Job(
        id=row["id"],
        session_id=row["session_id"],
        url=row["url"],
        status=row["status"],
        format_id=row["format_id"],
        quality=row["quality"],
        output_template=row["output_template"],
        filename=row["filename"],
        filesize=row["filesize"],
        progress_percent=row["progress_percent"] or 0.0,
        speed=row["speed"],
        eta=row["eta"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


async def get_job(db: aiosqlite.Connection, job_id: str) -> Job | None:
    """Fetch a single job by ID, or ``None`` if not found."""
    cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_job(row)


async def get_jobs_by_session(
    db: aiosqlite.Connection, session_id: str
) -> list[Job]:
    """Return all jobs belonging to a session, ordered by created_at."""
    cursor = await db.execute(
        "SELECT * FROM jobs WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_job(r) for r in rows]


_TERMINAL_STATUSES = (
    JobStatus.completed.value,
    JobStatus.failed.value,
    JobStatus.expired.value,
)


async def get_active_jobs_by_session(
    db: aiosqlite.Connection, session_id: str
) -> list[Job]:
    """Return non-terminal jobs for *session_id*, ordered by created_at."""
    cursor = await db.execute(
        "SELECT * FROM jobs WHERE session_id = ? "
        "AND status NOT IN (?, ?, ?) ORDER BY created_at",
        (session_id, *_TERMINAL_STATUSES),
    )
    rows = await cursor.fetchall()
    return [_row_to_job(r) for r in rows]


async def get_active_jobs_all(db: aiosqlite.Connection) -> list[Job]:
    """Return all non-terminal jobs across every session."""
    cursor = await db.execute(
        "SELECT * FROM jobs WHERE status NOT IN (?, ?, ?) ORDER BY created_at",
        _TERMINAL_STATUSES,
    )
    rows = await cursor.fetchall()
    return [_row_to_job(r) for r in rows]


async def get_all_jobs(db: aiosqlite.Connection) -> list[Job]:
    """Return every job across all sessions, ordered by created_at."""
    cursor = await db.execute("SELECT * FROM jobs ORDER BY created_at")
    rows = await cursor.fetchall()
    return [_row_to_job(r) for r in rows]


async def get_jobs_by_mode(
    db: aiosqlite.Connection, session_id: str, mode: str
) -> list[Job]:
    """Dispatch job queries based on session mode.

    - ``isolated``: only jobs belonging to *session_id*
    - ``shared`` / ``open``: all jobs across every session
    """
    if mode == "isolated":
        return await get_jobs_by_session(db, session_id)
    return await get_all_jobs(db)


async def get_queue_depth(db: aiosqlite.Connection) -> int:
    """Count jobs in active (non-terminal) statuses."""
    cursor = await db.execute(
        "SELECT COUNT(*) FROM jobs WHERE status NOT IN (?, ?, ?)",
        _TERMINAL_STATUSES,
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def update_job_status(
    db: aiosqlite.Connection,
    job_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update the status (and optionally error_message) of a job."""
    now = datetime.now(timezone.utc).isoformat()
    if status == JobStatus.completed.value:
        await db.execute(
            "UPDATE jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?",
            (status, error_message, now, job_id),
        )
    elif status == JobStatus.downloading.value:
        await db.execute(
            "UPDATE jobs SET status = ?, error_message = ?, started_at = ? WHERE id = ?",
            (status, error_message, now, job_id),
        )
    else:
        await db.execute(
            "UPDATE jobs SET status = ?, error_message = ? WHERE id = ?",
            (status, error_message, job_id),
        )
    await db.commit()


async def update_job_progress(
    db: aiosqlite.Connection,
    job_id: str,
    progress_percent: float,
    speed: str | None = None,
    eta: str | None = None,
    filename: str | None = None,
    filesize: int | None = None,
) -> None:
    """Update live progress fields for a running download."""
    if filesize is not None:
        await db.execute(
            """
            UPDATE jobs
               SET progress_percent = ?, speed = ?, eta = ?, filename = ?, filesize = ?
             WHERE id = ?
            """,
            (progress_percent, speed, eta, filename, filesize, job_id),
        )
    else:
        await db.execute(
            """
            UPDATE jobs
               SET progress_percent = ?, speed = ?, eta = ?, filename = ?
             WHERE id = ?
            """,
            (progress_percent, speed, eta, filename, job_id),
        )
    await db.commit()


async def delete_job(db: aiosqlite.Connection, job_id: str) -> None:
    """Delete a job row by ID."""
    await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    await db.commit()


async def close_db(db: aiosqlite.Connection) -> None:
    """Close the database connection."""
    await db.close()


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


async def create_session(db: aiosqlite.Connection, session_id: str) -> None:
    """Insert a new session row (idempotent — ignores duplicates)."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, created_at, last_seen) VALUES (?, ?, ?)",
        (session_id, now, now),
    )
    await db.commit()


async def get_session(db: aiosqlite.Connection, session_id: str) -> dict | None:
    """Fetch a session by ID, or ``None`` if not found."""
    cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return {"id": row["id"], "created_at": row["created_at"], "last_seen": row["last_seen"]}


async def update_session_last_seen(db: aiosqlite.Connection, session_id: str) -> None:
    """Touch the last_seen timestamp for a session."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE sessions SET last_seen = ? WHERE id = ?",
        (now, session_id),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Error log helpers
# ---------------------------------------------------------------------------


async def log_download_error(
    db: aiosqlite.Connection,
    url: str,
    error: str,
    session_id: str | None = None,
    format_id: str | None = None,
    media_type: str | None = None,
) -> None:
    """Record a failed download in the error log."""
    from urllib.parse import urlparse

    now = datetime.now(timezone.utc).isoformat()
    try:
        domain = urlparse(url).netloc or url[:80]
    except Exception:
        domain = url[:80]

    await db.execute(
        """INSERT INTO error_log (url, domain, error, format_id, media_type, session_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (url, domain, error[:2000], format_id, media_type, session_id, now),
    )
    await db.commit()


async def get_error_log(
    db: aiosqlite.Connection,
    limit: int = 100,
) -> list[dict]:
    """Return recent error log entries, newest first."""
    cursor = await db.execute(
        "SELECT * FROM error_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def clear_error_log(db: aiosqlite.Connection) -> int:
    """Delete all error log entries. Returns count deleted."""
    cursor = await db.execute("DELETE FROM error_log")
    await db.commit()
    return cursor.rowcount

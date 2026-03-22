"""Admin API endpoints — protected by require_admin dependency.

Settings are persisted to SQLite and survive container restarts.
Admin setup (first-run password creation) is unauthenticated but only
available when no password has been configured yet.
"""

from __future__ import annotations

import logging

import bcrypt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.dependencies import require_admin

logger = logging.getLogger("mediarip.admin")

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Public endpoints (no auth) — admin status + first-run setup
# ---------------------------------------------------------------------------


@router.get("/status")
async def admin_status(request: Request) -> dict:
    """Public endpoint: is admin enabled, and has initial setup been done?"""
    config = request.app.state.config
    return {
        "enabled": config.admin.enabled,
        "setup_complete": bool(config.admin.password_hash),
    }


@router.post("/setup")
async def admin_setup(request: Request) -> dict:
    """First-run setup: create admin credentials.

    Only works when admin is enabled AND no password has been set yet.
    After setup, this endpoint returns 403 — use /admin/password to change.
    """
    config = request.app.state.config

    if not config.admin.enabled:
        return JSONResponse(
            status_code=404,
            content={"detail": "Admin panel is not enabled"},
        )

    if config.admin.password_hash:
        return JSONResponse(
            status_code=403,
            content={"detail": "Admin is already configured. Use the change password flow."},
        )

    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username:
        return JSONResponse(
            status_code=422,
            content={"detail": "Username is required"},
        )

    if len(password) < 4:
        return JSONResponse(
            status_code=422,
            content={"detail": "Password must be at least 4 characters"},
        )

    # Hash and persist
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    config.admin.username = username
    config.admin.password_hash = password_hash

    # Persist to DB so it survives restarts
    from app.services.settings import save_settings
    db = request.app.state.db
    await save_settings(db, {
        "admin_username": username,
        "admin_password_hash": password_hash,
    })

    logger.info("Admin setup complete — user '%s' created", username)
    return {"status": "ok", "username": username}


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """List all sessions with basic stats."""
    db = request.app.state.db
    cursor = await db.execute(
        """
        SELECT s.id, s.created_at, s.last_seen,
               COUNT(j.id) as job_count
        FROM sessions s
        LEFT JOIN jobs j ON j.session_id = s.id
        GROUP BY s.id
        ORDER BY s.last_seen DESC
        """
    )
    rows = await cursor.fetchall()
    sessions = [
        {
            "id": row["id"],
            "created_at": row["created_at"],
            "last_seen": row["last_seen"],
            "job_count": row["job_count"],
        }
        for row in rows
    ]
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/sessions/{session_id}/jobs")
async def session_jobs(
    session_id: str,
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """List jobs for a specific session with file details."""
    db = request.app.state.db
    cursor = await db.execute(
        """
        SELECT id, url, status, filename, filesize,
               created_at, started_at, completed_at
        FROM jobs
        WHERE session_id = ?
        ORDER BY created_at DESC
        """,
        (session_id,),
    )
    rows = await cursor.fetchall()
    jobs = [
        {
            "id": row["id"],
            "url": row["url"],
            "status": row["status"],
            "filename": row["filename"],
            "filesize": row["filesize"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }
        for row in rows
    ]
    return {"jobs": jobs}


@router.get("/storage")
async def storage_info(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Return storage usage information."""
    import shutil
    from pathlib import Path

    config = request.app.state.config
    db = request.app.state.db
    output_dir = Path(config.downloads.output_dir)

    # Disk usage
    try:
        usage = shutil.disk_usage(output_dir)
        disk = {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
        }
    except OSError:
        disk = {"total": 0, "used": 0, "free": 0}

    # Job counts by status
    cursor = await db.execute(
        "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
    )
    rows = await cursor.fetchall()
    by_status = {row["status"]: row["count"] for row in rows}

    return {"disk": disk, "jobs_by_status": by_status}


@router.get("/unsupported-urls")
async def list_unsupported_urls(
    request: Request,
    _admin: str = Depends(require_admin),
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List logged unsupported URL extraction failures."""
    db = request.app.state.db
    cursor = await db.execute(
        "SELECT * FROM unsupported_urls ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    items = [
        {
            "id": row["id"],
            "url": row["url"],
            "session_id": row["session_id"],
            "error": row["error"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    count_cursor = await db.execute("SELECT COUNT(*) FROM unsupported_urls")
    count_row = await count_cursor.fetchone()
    total = count_row[0] if count_row else 0

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/errors")
async def get_errors(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Return recent download error log entries."""
    from app.core.database import get_error_log

    db = request.app.state.db
    entries = await get_error_log(db, limit=200)
    return {"errors": entries}


@router.delete("/errors")
async def clear_errors(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Clear all error log entries."""
    from app.core.database import clear_error_log

    db = request.app.state.db
    count = await clear_error_log(db)
    return {"cleared": count}


@router.post("/purge")
async def manual_purge(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Manually trigger a purge of expired downloads."""
    from app.services.purge import run_purge

    config = request.app.state.config
    db = request.app.state.db
    result = await run_purge(db, config, purge_all=True)

    # Broadcast job_removed events to all SSE clients
    broker = request.app.state.broker
    for job_id in result.get("deleted_job_ids", []):
        broker.publish_all({"event": "job_removed", "data": {"job_id": job_id}})

    result.pop("deleted_job_ids", None)
    return result


@router.get("/settings")
async def get_settings(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Return all admin-configurable settings with current values."""
    config = request.app.state.config

    return {
        "welcome_message": config.ui.welcome_message,
        "default_video_format": getattr(request.app.state, "_default_video_format", "auto"),
        "default_audio_format": getattr(request.app.state, "_default_audio_format", "auto"),
        "privacy_mode": config.purge.privacy_mode,
        "privacy_retention_minutes": config.purge.privacy_retention_minutes,
        "max_concurrent": config.downloads.max_concurrent,
        "session_mode": config.session.mode,
        "session_timeout_hours": config.session.timeout_hours,
        "admin_username": config.admin.username,
        "purge_enabled": config.purge.enabled,
        "purge_max_age_minutes": config.purge.max_age_minutes,
    }


@router.put("/settings")
async def update_settings(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Update and persist admin settings to SQLite.

    Accepts a JSON body with any combination of:
      - welcome_message: str
      - default_video_format: str (auto, mp4, webm)
      - default_audio_format: str (auto, mp3, m4a, flac, wav, opus)
      - privacy_mode: bool
      - privacy_retention_minutes: int (1-525600)
      - max_concurrent: int (1-10)
      - session_mode: str (isolated, shared, open)
      - session_timeout_hours: int (1-8760)
      - admin_username: str
      - purge_enabled: bool
      - purge_max_age_minutes: int (1-5256000)
    """
    from app.services.settings import save_settings

    body = await request.json()
    config = request.app.state.config
    db = request.app.state.db

    to_persist = {}
    updated = []

    # --- Validate and collect ---

    if "welcome_message" in body:
        msg = body["welcome_message"]
        if not isinstance(msg, str):
            return JSONResponse(status_code=422, content={"detail": "welcome_message must be a string"})
        config.ui.welcome_message = msg
        to_persist["welcome_message"] = msg
        updated.append("welcome_message")

    valid_video_formats = {"auto", "mp4", "webm"}
    valid_audio_formats = {"auto", "mp3", "m4a", "flac", "wav", "opus"}

    if "default_video_format" in body:
        fmt = body["default_video_format"]
        if fmt in valid_video_formats:
            request.app.state._default_video_format = fmt
            to_persist["default_video_format"] = fmt
            updated.append("default_video_format")

    if "default_audio_format" in body:
        fmt = body["default_audio_format"]
        if fmt in valid_audio_formats:
            request.app.state._default_audio_format = fmt
            to_persist["default_audio_format"] = fmt
            updated.append("default_audio_format")

    if "privacy_mode" in body:
        val = body["privacy_mode"]
        if isinstance(val, bool):
            config.purge.privacy_mode = val
            to_persist["privacy_mode"] = val
            updated.append("privacy_mode")
            # Start purge scheduler if enabling privacy mode
            if val and not getattr(request.app.state, "scheduler", None):
                _start_purge_scheduler(request.app.state, config, db)

    if "privacy_retention_minutes" in body:
        val = body["privacy_retention_minutes"]
        if isinstance(val, (int, float)) and 1 <= val <= 525600:
            config.purge.privacy_retention_minutes = int(val)
            to_persist["privacy_retention_minutes"] = int(val)
            updated.append("privacy_retention_minutes")

    if "max_concurrent" in body:
        val = body["max_concurrent"]
        if isinstance(val, int) and 1 <= val <= 10:
            config.downloads.max_concurrent = val
            to_persist["max_concurrent"] = val
            updated.append("max_concurrent")
            # Update the download service's executor pool size
            download_service = request.app.state.download_service
            download_service.update_max_concurrent(val)

    if "session_mode" in body:
        val = body["session_mode"]
        if val in ("isolated", "shared", "open"):
            config.session.mode = val
            to_persist["session_mode"] = val
            updated.append("session_mode")

    if "session_timeout_hours" in body:
        val = body["session_timeout_hours"]
        if isinstance(val, int) and 1 <= val <= 8760:
            config.session.timeout_hours = val
            to_persist["session_timeout_hours"] = val
            updated.append("session_timeout_hours")

    if "admin_username" in body:
        val = body["admin_username"]
        if isinstance(val, str) and len(val) >= 1:
            config.admin.username = val
            to_persist["admin_username"] = val
            updated.append("admin_username")

    if "purge_enabled" in body:
        val = body["purge_enabled"]
        if isinstance(val, bool):
            config.purge.enabled = val
            to_persist["purge_enabled"] = val
            updated.append("purge_enabled")
            if val and not getattr(request.app.state, "scheduler", None):
                _start_purge_scheduler(request.app.state, config, db)

    if "purge_max_age_minutes" in body:
        val = body["purge_max_age_minutes"]
        if isinstance(val, int) and 1 <= val <= 5256000:
            config.purge.max_age_minutes = val
            to_persist["purge_max_age_minutes"] = val
            updated.append("purge_max_age_minutes")

    # --- Persist to DB ---
    if to_persist:
        await save_settings(db, to_persist)
        logger.info("Admin persisted settings: %s", ", ".join(updated))

    return {"updated": updated, "status": "ok"}


@router.put("/password")
async def change_password(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Change admin password. Persisted to SQLite for durability."""
    body = await request.json()
    current = body.get("current_password", "")
    new_pw = body.get("new_password", "")

    if not current or not new_pw:
        return JSONResponse(
            status_code=422,
            content={"detail": "current_password and new_password are required"},
        )

    if len(new_pw) < 4:
        return JSONResponse(
            status_code=422,
            content={"detail": "New password must be at least 4 characters"},
        )

    config = request.app.state.config
    try:
        valid = bcrypt.checkpw(
            current.encode("utf-8"),
            config.admin.password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        valid = False

    if not valid:
        return JSONResponse(
            status_code=403,
            content={"detail": "Current password is incorrect"},
        )

    new_hash = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    config.admin.password_hash = new_hash

    # Persist to DB
    from app.services.settings import save_settings
    db = request.app.state.db
    await save_settings(db, {"admin_password_hash": new_hash})

    logger.info("Admin password changed by user '%s'", _admin)
    return {"status": "ok", "message": "Password changed successfully"}


# ---------------------------------------------------------------------------
# API key management (Sonarr/Radarr style)
# ---------------------------------------------------------------------------


@router.get("/api-key")
async def get_api_key(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Get the current API key (or null if none set)."""
    config = request.app.state.config
    key = config.server.api_key
    return {"api_key": key if key else None}


@router.post("/api-key")
async def generate_api_key(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Generate a new API key (replaces any existing one)."""
    import secrets as _secrets

    new_key = _secrets.token_hex(32)
    config = request.app.state.config
    config.server.api_key = new_key

    from app.services.settings import save_settings
    db = request.app.state.db
    await save_settings(db, {"api_key": new_key})

    logger.info("API key generated by admin '%s'", _admin)
    return {"api_key": new_key}


@router.delete("/api-key")
async def revoke_api_key(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Revoke the API key (disables API access, browser-only)."""
    config = request.app.state.config
    config.server.api_key = ""

    from app.services.settings import save_settings, delete_setting
    db = request.app.state.db
    await delete_setting(db, "api_key")

    logger.info("API key revoked by admin '%s'", _admin)
    return {"status": "ok", "message": "API key revoked"}


def _start_purge_scheduler(state, config, db) -> None:
    """Start the APScheduler purge job if not already running."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from app.services.purge import run_purge

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            run_purge,
            CronTrigger(minute="*"),
            args=[db, config],
            id="purge_job",
            name="Scheduled purge",
            replace_existing=True,
        )
        scheduler.start()
        state.scheduler = scheduler
        logger.info("Purge scheduler started")
    except Exception as e:
        logger.warning("Could not start purge scheduler: %s", e)

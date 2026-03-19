"""Admin API endpoints — protected by require_admin dependency."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.dependencies import require_admin

logger = logging.getLogger("mediarip.admin")

router = APIRouter(prefix="/admin", tags=["admin"])


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

    # Total count
    count_cursor = await db.execute("SELECT COUNT(*) FROM unsupported_urls")
    count_row = await count_cursor.fetchone()
    total = count_row[0] if count_row else 0

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/purge")
async def manual_purge(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Manually trigger a purge of expired downloads."""
    from app.services.purge import run_purge

    config = request.app.state.config
    db = request.app.state.db
    result = await run_purge(db, config)
    return result


@router.put("/settings")
async def update_settings(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Update runtime settings (in-memory only — resets on restart).

    Accepts a JSON body with optional fields:
      - welcome_message: str
      - default_video_format: str (auto, mp4, webm)
      - default_audio_format: str (auto, mp3, m4a, flac, wav, opus)
    """
    body = await request.json()

    if not hasattr(request.app.state, "settings_overrides"):
        request.app.state.settings_overrides = {}

    updated = []
    if "welcome_message" in body:
        msg = body["welcome_message"]
        if not isinstance(msg, str):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=422,
                content={"detail": "welcome_message must be a string"},
            )
        request.app.state.settings_overrides["welcome_message"] = msg
        updated.append("welcome_message")
        logger.info("Admin updated welcome_message to: %s", msg[:80])

    valid_video_formats = {"auto", "mp4", "webm"}
    valid_audio_formats = {"auto", "mp3", "m4a", "flac", "wav", "opus"}

    if "default_video_format" in body:
        fmt = body["default_video_format"]
        if fmt in valid_video_formats:
            request.app.state.settings_overrides["default_video_format"] = fmt
            updated.append("default_video_format")
            logger.info("Admin updated default_video_format to: %s", fmt)

    if "default_audio_format" in body:
        fmt = body["default_audio_format"]
        if fmt in valid_audio_formats:
            request.app.state.settings_overrides["default_audio_format"] = fmt
            updated.append("default_audio_format")
            logger.info("Admin updated default_audio_format to: %s", fmt)

    return {"updated": updated, "status": "ok"}


@router.put("/password")
async def change_password(
    request: Request,
    _admin: str = Depends(require_admin),
) -> dict:
    """Change admin password (in-memory only — resets on restart).

    Accepts JSON body:
      - current_password: str (required, must match current password)
      - new_password: str (required, min 4 chars)
    """
    import bcrypt

    body = await request.json()
    current = body.get("current_password", "")
    new_pw = body.get("new_password", "")

    if not current or not new_pw:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=422,
            content={"detail": "current_password and new_password are required"},
        )

    if len(new_pw) < 4:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=422,
            content={"detail": "New password must be at least 4 characters"},
        )

    # Verify current password
    config = request.app.state.config
    try:
        valid = bcrypt.checkpw(
            current.encode("utf-8"),
            config.admin.password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        valid = False

    if not valid:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=403,
            content={"detail": "Current password is incorrect"},
        )

    # Hash and store new password
    new_hash = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    config.admin.password_hash = new_hash
    logger.info("Admin password changed by user '%s'", _admin)

    return {"status": "ok", "message": "Password changed successfully"}

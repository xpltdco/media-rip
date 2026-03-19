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

    return {"updated": updated, "status": "ok"}

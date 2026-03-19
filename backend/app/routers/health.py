"""Health endpoint for monitoring tools and Docker healthchecks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.core.database import get_queue_depth

logger = logging.getLogger("mediarip.health")

router = APIRouter(tags=["health"])

# yt-dlp version — resolved once at import time.
# Wrapped in try/except so tests that don't install yt-dlp still work.
try:
    from yt_dlp.version import __version__ as _yt_dlp_version
except ImportError:  # pragma: no cover
    _yt_dlp_version = "unknown"

_APP_VERSION = "0.1.0"


@router.get("/health")
async def health(request: Request) -> dict:
    """Return service health status, versions, uptime, and queue depth.

    Intended consumers: Uptime Kuma, Docker HEALTHCHECK, load balancer probes.
    """
    db = request.app.state.db
    start_time: datetime = request.app.state.start_time
    now = datetime.now(timezone.utc)
    uptime = (now - start_time).total_seconds()
    depth = await get_queue_depth(db)

    return {
        "status": "ok",
        "version": _APP_VERSION,
        "yt_dlp_version": _yt_dlp_version,
        "uptime": uptime,
        "queue_depth": depth,
    }

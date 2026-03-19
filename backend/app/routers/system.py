"""System endpoints — public (non-sensitive) configuration for the frontend."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger("mediarip.system")

router = APIRouter(tags=["system"])


@router.get("/config/public")
async def public_config(request: Request) -> dict:
    """Return the safe subset of application config for the frontend.

    Explicitly constructs the response dict from known-safe fields.
    Does NOT serialize the full AppConfig and strip fields — that pattern
    is fragile when new sensitive fields are added later.
    """
    config = request.app.state.config
    return {
        "session_mode": config.session.mode,
        "default_theme": config.ui.default_theme,
        "welcome_message": config.ui.welcome_message,
        "purge_enabled": config.purge.enabled,
        "max_concurrent_downloads": config.downloads.max_concurrent,
    }

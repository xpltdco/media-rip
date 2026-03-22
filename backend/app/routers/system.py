"""System endpoints — public (non-sensitive) configuration for the frontend."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger("mediarip.system")

router = APIRouter(tags=["system"])


@router.get("/config/public")
async def public_config(request: Request) -> dict:
    """Return the safe subset of application config for the frontend.

    Reads from the live AppConfig which includes persisted admin settings.
    """
    config = request.app.state.config

    return {
        "session_mode": config.session.mode,
        "default_theme": config.ui.default_theme,
        "welcome_message": config.ui.welcome_message,
        "purge_enabled": config.purge.enabled,
        "max_concurrent_downloads": config.downloads.max_concurrent,
        "default_video_format": getattr(request.app.state, "_default_video_format", "auto"),
        "default_audio_format": getattr(request.app.state, "_default_audio_format", "auto"),
        "privacy_mode": config.purge.privacy_mode,
        "privacy_retention_minutes": config.purge.privacy_retention_minutes,
        "admin_enabled": config.admin.enabled,
        "admin_setup_complete": bool(config.admin.password_hash),
    }

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

    # Runtime overrides (set via admin settings endpoint) take precedence
    overrides = getattr(request.app.state, "settings_overrides", {})

    return {
        "session_mode": config.session.mode,
        "default_theme": config.ui.default_theme,
        "welcome_message": overrides.get(
            "welcome_message", config.ui.welcome_message
        ),
        "purge_enabled": config.purge.enabled,
        "max_concurrent_downloads": config.downloads.max_concurrent,
        "default_video_format": overrides.get("default_video_format", "auto"),
        "default_audio_format": overrides.get("default_audio_format", "auto"),
        "privacy_mode": overrides.get("privacy_mode", config.purge.privacy_mode),
        "privacy_retention_hours": overrides.get(
            "privacy_retention_hours", config.purge.privacy_retention_hours
        ),
    }

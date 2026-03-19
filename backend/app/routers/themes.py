"""Theme API — serves custom theme manifest and CSS."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.services.theme_loader import get_theme_css, scan_themes

logger = logging.getLogger(__name__)
router = APIRouter(tags=["themes"])


@router.get("/themes")
async def list_themes(request: Request):
    """Return manifest of available custom themes.

    Built-in themes are handled client-side. This endpoint only
    returns custom themes discovered from the /themes volume.
    """
    config = request.app.state.config
    themes_dir = config.themes_dir
    themes = scan_themes(themes_dir)
    return {"themes": themes, "total": len(themes)}


@router.get("/themes/{theme_id}/theme.css")
async def get_theme_stylesheet(request: Request, theme_id: str):
    """Serve a custom theme's CSS file."""
    config = request.app.state.config
    themes_dir = config.themes_dir
    css = get_theme_css(themes_dir, theme_id)

    if css is None:
        raise HTTPException(status_code=404, detail="Theme not found")

    return PlainTextResponse(content=css, media_type="text/css")

"""Cookie auth — per-session cookies.txt upload for authenticated downloads (R008)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from app.dependencies import get_session_id

logger = logging.getLogger("mediarip.cookies")

router = APIRouter(tags=["cookies"])

COOKIES_DIR = "data/sessions"


def _cookie_path(output_base: str, session_id: str) -> Path:
    """Return the cookies.txt path for a session."""
    return Path(output_base).parent / COOKIES_DIR / session_id / "cookies.txt"


@router.post("/cookies")
async def upload_cookies(
    request: Request,
    file: UploadFile,
    session_id: str = Depends(get_session_id),
) -> dict:
    """Upload a Netscape-format cookies.txt for the current session.

    File is stored at data/sessions/{session_id}/cookies.txt.
    CRLF line endings are normalized to LF.
    """
    content = await file.read()

    # Normalize CRLF → LF
    text = content.decode("utf-8", errors="replace").replace("\r\n", "\n")

    config = request.app.state.config
    cookie_file = _cookie_path(config.downloads.output_dir, session_id)
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    cookie_file.write_text(text, encoding="utf-8")

    logger.info("Cookie file uploaded for session %s (%d bytes)", session_id, len(text))

    return {"status": "ok", "session_id": session_id, "size": len(text)}


@router.delete("/cookies")
async def delete_cookies(
    request: Request,
    session_id: str = Depends(get_session_id),
) -> dict:
    """Delete the cookies.txt for the current session."""
    config = request.app.state.config
    cookie_file = _cookie_path(config.downloads.output_dir, session_id)

    if cookie_file.is_file():
        cookie_file.unlink()
        logger.info("Cookie file deleted for session %s", session_id)
        return {"status": "deleted"}

    return {"status": "not_found"}


def get_cookie_path_for_session(output_dir: str, session_id: str) -> str | None:
    """Return the cookies.txt path if it exists for a session, else None.

    Called by DownloadService to pass cookiefile to yt-dlp.
    """
    path = _cookie_path(output_dir, session_id)
    if path.is_file():
        return str(path)
    return None

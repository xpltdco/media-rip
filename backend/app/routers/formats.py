"""Format extraction API route.

GET /formats?url= — return available download formats for a URL
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.models.job import FormatInfo

logger = logging.getLogger("mediarip.api.formats")

router = APIRouter(tags=["formats"])


@router.get("/formats", response_model=list[FormatInfo])
async def get_formats(
    request: Request,
    url: str = Query(..., description="URL to extract formats from"),
) -> list[FormatInfo] | JSONResponse:
    """Extract available formats for a URL via yt-dlp."""
    logger.debug("GET /formats url=%s", url)
    download_service = request.app.state.download_service
    try:
        formats = await download_service.get_formats(url)
        return formats
    except Exception as exc:
        logger.error("Format extraction failed for %s: %s", url, exc)
        return JSONResponse(
            status_code=400,
            content={"detail": f"Format extraction failed: {exc}"},
        )

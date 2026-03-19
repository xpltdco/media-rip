"""File serving for completed downloads — enables link sharing (R018)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

logger = logging.getLogger("mediarip.files")

router = APIRouter(tags=["files"])


@router.get("/downloads/{filename:path}")
async def serve_download(filename: str, request: Request) -> FileResponse:
    """Serve a completed download file.

    Files are served from the configured output directory.
    Path traversal is prevented by resolving and checking the path
    stays within the output directory.
    """
    config = request.app.state.config
    output_dir = Path(config.downloads.output_dir).resolve()
    file_path = (output_dir / filename).resolve()

    # Prevent path traversal
    if not str(file_path).startswith(str(output_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )

"""Download management API routes.

POST /downloads  — enqueue a new download job
GET  /downloads  — list jobs for the current session
DELETE /downloads/{job_id} — cancel a job
"""

from __future__ import annotations

import logging
import os

import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.database import delete_job, get_job, get_jobs_by_session
from app.dependencies import get_session_id
from app.models.job import Job, JobCreate

logger = logging.getLogger("mediarip.api.downloads")

router = APIRouter(tags=["downloads"])


def _check_api_access(request: Request) -> None:
    """Verify the caller is a browser user or has a valid API key.

    When no API key is configured, all requests are allowed (open access).
    When an API key is set:
      - Requests with a valid X-API-Key header pass.
      - Requests from the web UI pass (have a Referer from the same origin
        or an X-Requested-With header set by the frontend).
      - All other requests are rejected with 403.
    """
    config = request.app.state.config
    api_key = config.server.api_key

    if not api_key:
        return  # No key configured — open access

    # Check API key header
    provided_key = request.headers.get("x-api-key", "")
    if provided_key and secrets.compare_digest(provided_key, api_key):
        return

    # Check browser origin — frontend sends X-Requested-With: XMLHttpRequest
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return

    raise_api_key_required()


def raise_api_key_required():
    from fastapi import HTTPException
    raise HTTPException(
        status_code=403,
        detail="API key required. Provide X-API-Key header or use the web UI.",
    )


@router.post("/downloads", response_model=Job, status_code=201)
async def create_download(
    job_create: JobCreate,
    request: Request,
    session_id: str = Depends(get_session_id),
) -> Job:
    """Submit a URL for download."""
    _check_api_access(request)
    logger.debug("POST /downloads session=%s url=%s", session_id, job_create.url)
    download_service = request.app.state.download_service
    job = await download_service.enqueue(job_create, session_id)
    return job


@router.get("/downloads", response_model=list[Job])
async def list_downloads(
    request: Request,
    session_id: str = Depends(get_session_id),
) -> list[Job]:
    """List all download jobs for the current session."""
    logger.debug("GET /downloads session=%s", session_id)
    jobs = await get_jobs_by_session(request.app.state.db, session_id)
    return jobs


@router.delete("/downloads/{job_id}")
async def cancel_download(
    job_id: str,
    request: Request,
) -> dict:
    """Delete a download job and remove its file."""
    logger.debug("DELETE /downloads/%s", job_id)
    db = request.app.state.db

    # Fetch the job first to get its session_id and filename
    job = await get_job(db, job_id)
    if job is None:
        return {"status": "not_found"}

    # Delete the downloaded file if it exists
    if job.filename:
        output_dir = request.app.state.config.downloads.output_dir
        filepath = os.path.join(output_dir, job.filename)
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
                logger.info("Deleted file: %s", filepath)
        except OSError:
            logger.warning("Failed to delete file: %s", filepath)

    # Remove job from database
    await delete_job(db, job_id)

    # Notify any SSE clients watching this session
    request.app.state.broker.publish(
        job.session_id,
        {"event": "job_removed", "data": {"job_id": job_id}},
    )

    return {"status": "deleted"}


@router.post("/url-info")
async def url_info(
    request: Request,
    body: dict,
) -> dict:
    """Extract metadata about a URL (title, playlist detection, audio-only detection)."""
    url = body.get("url", "").strip()
    if not url:
        return JSONResponse(status_code=400, content={"detail": "URL required"})
    download_service = request.app.state.download_service
    return await download_service.get_url_info(url)

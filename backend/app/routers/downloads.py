"""Download management API routes.

POST /downloads  — enqueue a new download job
GET  /downloads  — list jobs for the current session
DELETE /downloads/{job_id} — cancel a job
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.database import get_job, get_jobs_by_session
from app.dependencies import get_session_id
from app.models.job import Job, JobCreate

logger = logging.getLogger("mediarip.api.downloads")

router = APIRouter(tags=["downloads"])


@router.post("/downloads", response_model=Job, status_code=201)
async def create_download(
    job_create: JobCreate,
    request: Request,
    session_id: str = Depends(get_session_id),
) -> Job:
    """Submit a URL for download."""
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
    """Cancel (mark as failed) a download job."""
    logger.debug("DELETE /downloads/%s", job_id)
    db = request.app.state.db
    download_service = request.app.state.download_service

    # Fetch the job first to get its session_id for the SSE broadcast
    job = await get_job(db, job_id)

    await download_service.cancel(job_id)

    # Notify any SSE clients watching this session
    if job is not None:
        request.app.state.broker.publish(
            job.session_id,
            {"event": "job_removed", "data": {"job_id": job_id}},
        )

    return {"status": "cancelled"}

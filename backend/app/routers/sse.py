"""Server-Sent Events endpoint for live download progress.

GET /events streams real-time updates for the current session:
  - ``init`` — replays all non-terminal jobs on connect
  - ``job_update`` — live progress from yt-dlp workers
  - ``job_removed`` — a job was deleted via the API
  - ``ping`` — keepalive every 15 s of inactivity
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_active_jobs_by_session
from app.dependencies import get_session_id

logger = logging.getLogger("mediarip.sse")

router = APIRouter(tags=["sse"])

KEEPALIVE_TIMEOUT = 15.0  # seconds


async def event_generator(
    session_id: str,
    broker,
    db,
) -> AsyncGenerator[dict, None]:
    """Async generator that yields SSE event dicts.

    Lifecycle:
      1. Subscribe to the broker for *session_id*
      2. Replay non-terminal jobs as an ``init`` event
      3. Enter a loop yielding ``job_update`` / ``job_removed`` events
         with a keepalive ``ping`` on idle
      4. ``finally`` — always unsubscribe to prevent zombie connections

    ``CancelledError`` is deliberately NOT caught — it must propagate so
    that ``sse-starlette`` can cleanly close the response.
    """
    queue = broker.subscribe(session_id)
    logger.info("SSE connected for session %s", session_id)
    try:
        # 1. Replay current non-terminal jobs
        jobs = await get_active_jobs_by_session(db, session_id)
        yield {
            "event": "init",
            "data": json.dumps({"jobs": [job.model_dump() for job in jobs]}),
        }

        # 2. Live stream
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_TIMEOUT)
                if isinstance(event, dict):
                    yield {
                        "event": event.get("event", "job_update"),
                        "data": json.dumps(event.get("data", {})),
                    }
                else:
                    # ProgressEvent or any Pydantic model
                    yield {
                        "event": "job_update",
                        "data": json.dumps(event.model_dump()),
                    }
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": ""}
    finally:
        broker.unsubscribe(session_id, queue)
        logger.info("SSE disconnected for session %s", session_id)


@router.get("/events")
async def sse_events(
    request: Request,
    session_id: str = Depends(get_session_id),
):
    """Stream SSE events for the current session."""
    broker = request.app.state.broker
    db = request.app.state.db

    return EventSourceResponse(
        event_generator(session_id, broker, db),
        ping=0,  # we handle keepalive ourselves
    )

"""Cookie-based session middleware.

Reads or creates an ``mrip_session`` httpOnly cookie on every request.
In "open" mode, skips cookie handling and assigns a fixed session ID.
"""

from __future__ import annotations

import logging
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.database import create_session, get_session, update_session_last_seen

logger = logging.getLogger("mediarip.session")

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_valid_uuid4(value: str) -> bool:
    """Return True if *value* looks like a UUID4 string."""
    return bool(_UUID4_RE.match(value))


class SessionMiddleware(BaseHTTPMiddleware):
    """Populate ``request.state.session_id`` from cookie or generate a new one."""

    async def dispatch(self, request: Request, call_next) -> Response:
        config = request.app.state.config
        db = request.app.state.db

        # --- Open mode: fixed session, no cookie ---
        if config.session.mode == "open":
            request.state.session_id = "open"
            return await call_next(request)

        # --- Resolve or create session ---
        cookie_value = request.cookies.get("mrip_session")

        if cookie_value and _is_valid_uuid4(cookie_value):
            session_id = cookie_value
            existing = await get_session(db, session_id)
            if existing:
                await update_session_last_seen(db, session_id)
                logger.debug("Session reused: %s", session_id)
            else:
                # Valid UUID but not in DB (expired/purged) — recreate
                await create_session(db, session_id)
                logger.info("Session recreated (cookie valid, DB miss): %s", session_id)
        else:
            # Missing or invalid cookie — brand new session
            session_id = str(uuid.uuid4())
            await create_session(db, session_id)
            logger.info("New session created: %s", session_id)

        request.state.session_id = session_id

        response = await call_next(request)

        # --- Set cookie on every response (refresh Max-Age) ---
        timeout_seconds = config.session.timeout_hours * 3600
        response.set_cookie(
            key="mrip_session",
            value=session_id,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=timeout_seconds,
        )

        return response

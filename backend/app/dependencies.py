"""Request-scoped dependencies for FastAPI routes."""

from __future__ import annotations

import logging
import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

logger = logging.getLogger("mediarip.admin")

_security = HTTPBasic(auto_error=False)


def get_session_id(request: Request) -> str:
    """Return the session ID set by SessionMiddleware."""
    return request.state.session_id


async def require_admin(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(_security),
) -> str:
    """Verify admin credentials via HTTPBasic + bcrypt.

    Returns the authenticated username on success.
    Raises 404 if admin is disabled, 401 if credentials are invalid.
    """
    config = request.app.state.config

    # If admin is not enabled, pretend the route doesn't exist
    if not config.admin.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if credentials is None:
        logger.info("Admin auth: no credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Timing-safe username comparison
    username_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        config.admin.username.encode("utf-8"),
    )

    # bcrypt password check — only if we have a hash configured
    password_ok = False
    if config.admin.password_hash:
        try:
            password_ok = bcrypt.checkpw(
                credentials.password.encode("utf-8"),
                config.admin.password_hash.encode("utf-8"),
            )
        except (ValueError, TypeError):
            # Invalid hash format
            password_ok = False

    if not (username_ok and password_ok):
        logger.info("Admin auth: failed login attempt for user '%s'", credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.debug("Admin auth: successful login for user '%s'", credentials.username)
    return credentials.username

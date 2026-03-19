"""Tests for the cookie-based SessionMiddleware."""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.database import close_db, get_session, init_db
from app.middleware.session import SessionMiddleware


def _build_test_app(config, db_conn):
    """Build a minimal FastAPI app with SessionMiddleware and a probe endpoint."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware)
    app.state.config = config
    app.state.db = db_conn

    @app.get("/probe")
    async def probe(request: Request):
        return {"session_id": request.state.session_id}

    return app


@pytest_asyncio.fixture()
async def mw_app(tmp_path):
    """Yield (app, db_conn, config) for middleware-focused tests."""
    db_path = str(tmp_path / "session_mw.db")
    config = AppConfig(server={"db_path": db_path})
    db_conn = await init_db(db_path)

    app = _build_test_app(config, db_conn)

    yield app, db_conn, config

    await close_db(db_conn)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_session_sets_cookie(mw_app):
    """Request without cookie → response has Set-Cookie with mrip_session, httpOnly, SameSite=Lax."""
    app, db_conn, _ = mw_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/probe")

    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    assert len(session_id) == 36  # UUID format

    cookie_header = resp.headers.get("set-cookie", "")
    assert f"mrip_session={session_id}" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()
    assert "path=/" in cookie_header.lower()
    # Max-Age should be 72 * 3600 = 259200
    assert "max-age=259200" in cookie_header.lower()

    # Session should exist in DB
    row = await get_session(db_conn, session_id)
    assert row is not None
    assert row["id"] == session_id


@pytest.mark.asyncio
async def test_reuse_valid_cookie(mw_app):
    """Request with valid mrip_session cookie → reuses session, last_seen updated."""
    app, db_conn, _ = mw_app
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # First request creates session
        resp1 = await ac.get("/probe")
        session_id = resp1.json()["session_id"]

        # Read initial last_seen
        row_before = await get_session(db_conn, session_id)

        # Second request with cookie (httpx auto-sends it)
        resp2 = await ac.get("/probe")
        assert resp2.json()["session_id"] == session_id

    # last_seen should be updated (or at least present)
    row_after = await get_session(db_conn, session_id)
    assert row_after is not None
    assert row_after["last_seen"] >= row_before["last_seen"]


@pytest.mark.asyncio
async def test_invalid_cookie_creates_new_session(mw_app):
    """Request with invalid (non-UUID) cookie → new session created, new cookie set."""
    app, db_conn, _ = mw_app
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/probe", cookies={"mrip_session": "not-a-uuid"})

    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    assert session_id != "not-a-uuid"
    assert len(session_id) == 36

    # New session should exist in DB
    row = await get_session(db_conn, session_id)
    assert row is not None

    # Cookie should be set with the new session
    cookie_header = resp.headers.get("set-cookie", "")
    assert f"mrip_session={session_id}" in cookie_header


@pytest.mark.asyncio
async def test_uuid_cookie_not_in_db_recreates(mw_app):
    """Request with valid UUID cookie not in DB → session created with that UUID."""
    app, db_conn, _ = mw_app
    transport = ASGITransport(app=app)

    orphan_id = str(uuid.uuid4())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/probe", cookies={"mrip_session": orphan_id})

    assert resp.status_code == 200
    # Should reuse the UUID from the cookie
    assert resp.json()["session_id"] == orphan_id

    # Session should now exist in DB
    row = await get_session(db_conn, orphan_id)
    assert row is not None
    assert row["id"] == orphan_id


@pytest.mark.asyncio
async def test_open_mode_no_cookie(tmp_path):
    """Open mode → no cookie set, request.state.session_id == 'open'."""
    db_path = str(tmp_path / "open_mode.db")
    config = AppConfig(
        server={"db_path": db_path},
        session={"mode": "open"},
    )
    db_conn = await init_db(db_path)

    app = _build_test_app(config, db_conn)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/probe")

    await close_db(db_conn)

    assert resp.status_code == 200
    assert resp.json()["session_id"] == "open"

    # No Set-Cookie header in open mode
    cookie_header = resp.headers.get("set-cookie", "")
    assert "mrip_session" not in cookie_header


@pytest.mark.asyncio
async def test_max_age_reflects_config(tmp_path):
    """Cookie Max-Age reflects config.session.timeout_hours."""
    db_path = str(tmp_path / "maxage.db")
    config = AppConfig(
        server={"db_path": db_path},
        session={"timeout_hours": 24},
    )
    db_conn = await init_db(db_path)

    app = _build_test_app(config, db_conn)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/probe")

    await close_db(db_conn)

    cookie_header = resp.headers.get("set-cookie", "")
    # 24 * 3600 = 86400
    assert "max-age=86400" in cookie_header.lower()

"""Tests for admin authentication, security headers, and admin API endpoints."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

import bcrypt
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.database import close_db, init_db
from app.middleware.session import SessionMiddleware
from app.routers.admin import router as admin_router


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _basic_auth(username: str, password: str) -> str:
    cred = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {cred}"


@pytest_asyncio.fixture()
async def admin_client(tmp_path):
    """Client with admin enabled and a known password hash."""
    db_path = str(tmp_path / "admin_test.db")
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()

    pw_hash = _hash_password("secret123")
    config = AppConfig(
        server={"db_path": db_path},
        downloads={"output_dir": str(dl_dir)},
        admin={"enabled": True, "username": "admin", "password_hash": pw_hash},
    )

    db_conn = await init_db(db_path)
    app = FastAPI()
    app.add_middleware(SessionMiddleware)
    app.include_router(admin_router, prefix="/api")
    app.state.config = config
    app.state.db = db_conn
    app.state.start_time = datetime.now(timezone.utc)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await close_db(db_conn)


@pytest_asyncio.fixture()
async def disabled_admin_client(tmp_path):
    """Client with admin disabled."""
    db_path = str(tmp_path / "admin_disabled.db")
    config = AppConfig(
        server={"db_path": db_path},
        admin={"enabled": False},
    )

    db_conn = await init_db(db_path)
    app = FastAPI()
    app.add_middleware(SessionMiddleware)
    app.include_router(admin_router, prefix="/api")
    app.state.config = config
    app.state.db = db_conn
    app.state.start_time = datetime.now(timezone.utc)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await close_db(db_conn)


class TestAdminAuth:
    """Admin authentication tests."""

    @pytest.mark.anyio
    async def test_no_credentials_returns_401(self, admin_client):
        resp = await admin_client.get("/api/admin/sessions")
        assert resp.status_code == 401
        assert "WWW-Authenticate" in resp.headers

    @pytest.mark.anyio
    async def test_wrong_password_returns_401(self, admin_client):
        resp = await admin_client.get(
            "/api/admin/sessions",
            headers={"Authorization": _basic_auth("admin", "wrong")},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_wrong_username_returns_401(self, admin_client):
        resp = await admin_client.get(
            "/api/admin/sessions",
            headers={"Authorization": _basic_auth("hacker", "secret123")},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_correct_credentials_returns_200(self, admin_client):
        resp = await admin_client.get(
            "/api/admin/sessions",
            headers={"Authorization": _basic_auth("admin", "secret123")},
        )
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_disabled_admin_returns_404(self, disabled_admin_client):
        resp = await disabled_admin_client.get(
            "/api/admin/sessions",
            headers={"Authorization": _basic_auth("admin", "secret123")},
        )
        assert resp.status_code == 404


class TestAdminSessions:
    """Admin session list endpoint."""

    @pytest.mark.anyio
    async def test_sessions_returns_list(self, admin_client):
        resp = await admin_client.get(
            "/api/admin/sessions",
            headers={"Authorization": _basic_auth("admin", "secret123")},
        )
        data = resp.json()
        assert "sessions" in data
        assert "total" in data
        assert isinstance(data["sessions"], list)


class TestAdminStorage:
    """Admin storage info endpoint."""

    @pytest.mark.anyio
    async def test_storage_returns_disk_info(self, admin_client):
        resp = await admin_client.get(
            "/api/admin/storage",
            headers={"Authorization": _basic_auth("admin", "secret123")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "disk" in data
        assert "jobs_by_status" in data
        assert data["disk"]["total"] > 0


class TestAdminUnsupportedUrls:
    """Admin unsupported URL log endpoint."""

    @pytest.mark.anyio
    async def test_unsupported_urls_returns_empty(self, admin_client):
        resp = await admin_client.get(
            "/api/admin/unsupported-urls",
            headers={"Authorization": _basic_auth("admin", "secret123")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

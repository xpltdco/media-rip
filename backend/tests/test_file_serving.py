"""Tests for cookie auth upload and file serving."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.database import close_db, init_db
from app.middleware.session import SessionMiddleware
from app.routers.cookies import router as cookies_router
from app.routers.files import router as files_router


@pytest_asyncio.fixture()
async def file_client(tmp_path):
    """Client with file serving and cookie upload routers."""
    db_path = str(tmp_path / "file_test.db")
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()

    config = AppConfig(
        server={"db_path": db_path, "data_dir": str(tmp_path / "data")},
        downloads={"output_dir": str(dl_dir)},
    )

    db_conn = await init_db(db_path)
    app = FastAPI()
    app.add_middleware(SessionMiddleware)
    app.include_router(cookies_router, prefix="/api")
    app.include_router(files_router, prefix="/api")
    app.state.config = config
    app.state.db = db_conn
    app.state.start_time = datetime.now(timezone.utc)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, dl_dir

    await close_db(db_conn)


class TestCookieUpload:
    """Cookie auth upload tests."""

    @pytest.mark.anyio
    async def test_upload_cookies(self, file_client):
        client, dl_dir = file_client
        cookie_content = b"# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tSID\tvalue123\n"

        resp = await client.post(
            "/api/cookies",
            files={"file": ("cookies.txt", cookie_content, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["size"] > 0

    @pytest.mark.anyio
    async def test_upload_normalizes_crlf(self, file_client):
        client, dl_dir = file_client
        # Windows-style line endings
        cookie_content = b"line1\r\nline2\r\nline3\r\n"

        resp = await client.post(
            "/api/cookies",
            files={"file": ("cookies.txt", cookie_content, "text/plain")},
        )
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_delete_cookies(self, file_client):
        client, dl_dir = file_client
        # Upload first
        await client.post(
            "/api/cookies",
            files={"file": ("cookies.txt", b"data", "text/plain")},
        )

        # Delete
        resp = await client.delete("/api/cookies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"

    @pytest.mark.anyio
    async def test_delete_nonexistent_cookies(self, file_client):
        client, dl_dir = file_client
        resp = await client.delete("/api/cookies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_found"


class TestFileServing:
    """File download serving tests."""

    @pytest.mark.anyio
    async def test_serve_existing_file(self, file_client):
        client, dl_dir = file_client
        # Create a file in the downloads dir
        test_file = dl_dir / "video.mp4"
        test_file.write_bytes(b"fake video content")

        resp = await client.get("/api/downloads/video.mp4")
        assert resp.status_code == 200
        assert resp.content == b"fake video content"

    @pytest.mark.anyio
    async def test_missing_file_returns_404(self, file_client):
        client, dl_dir = file_client
        resp = await client.get("/api/downloads/nonexistent.mp4")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_path_traversal_blocked(self, file_client):
        client, dl_dir = file_client
        resp = await client.get("/api/downloads/../../../etc/passwd")
        assert resp.status_code in (403, 404)

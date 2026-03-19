"""API-level tests via httpx AsyncClient + ASGITransport.

No real server is started — httpx drives FastAPI through the ASGI interface.
Sessions are managed by SessionMiddleware (cookie-based).
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# POST / GET / DELETE /api/downloads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_download(client):
    """POST /api/downloads creates a job and returns it with status 201."""
    resp = await client.post(
        "/api/downloads",
        json={"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["status"] == "queued"
    assert body["url"] == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    # Session ID is a UUID assigned by middleware
    assert len(body["session_id"]) == 36


@pytest.mark.asyncio
async def test_post_download_sets_cookie(client):
    """First request should return a Set-Cookie header with mrip_session."""
    resp = await client.post(
        "/api/downloads",
        json={"url": "https://example.com/video"},
    )
    assert resp.status_code == 201
    cookie_header = resp.headers.get("set-cookie", "")
    assert "mrip_session=" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()
    assert "path=/" in cookie_header.lower()


@pytest.mark.asyncio
async def test_get_downloads_empty(client):
    """GET /api/downloads with a new session returns an empty list."""
    resp = await client.get("/api/downloads")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_downloads_after_post(client):
    """POST a download, then GET should return a list containing that job."""
    post_resp = await client.post(
        "/api/downloads",
        json={"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"},
    )
    assert post_resp.status_code == 201
    job_id = post_resp.json()["id"]

    get_resp = await client.get("/api/downloads")
    assert get_resp.status_code == 200
    jobs = get_resp.json()
    assert len(jobs) >= 1
    assert any(j["id"] == job_id for j in jobs)


@pytest.mark.asyncio
async def test_delete_download(client):
    """POST a download, DELETE it — the job is fully removed from the system.

    DELETE now removes the job from the database and deletes its file.
    We verify:
    1. DELETE returns 200 with ``{"status": "deleted"}``
    2. The job no longer appears in the downloads list
    """
    post_resp = await client.post(
        "/api/downloads",
        json={"url": "https://example.com/nonexistent-video"},
    )
    assert post_resp.status_code == 201
    job_id = post_resp.json()["id"]

    del_resp = await client.delete(f"/api/downloads/{job_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Give the background worker time to settle
    await asyncio.sleep(0.5)

    # Verify the job is gone
    get_resp = await client.get("/api/downloads")
    jobs = get_resp.json()
    target = [j for j in jobs if j["id"] == job_id]
    assert len(target) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_formats(client):
    """GET /api/formats?url= returns a non-empty format list (integration — needs network)."""
    resp = await client.get(
        "/api/formats",
        params={"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"},
    )
    assert resp.status_code == 200
    formats = resp.json()
    assert isinstance(formats, list)
    assert len(formats) > 0
    assert "format_id" in formats[0]


@pytest.mark.asyncio
async def test_post_download_invalid_url(client):
    """POST with a non-URL string still creates a job (yt-dlp validates later)."""
    resp = await client.post(
        "/api/downloads",
        json={"url": "not-a-url"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["url"] == "not-a-url"
    assert body["status"] == "queued"


@pytest.mark.asyncio
async def test_default_session_from_middleware(client):
    """Without any prior cookie, middleware creates a UUID session automatically."""
    resp = await client.post(
        "/api/downloads",
        json={"url": "https://example.com/video"},
    )
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]
    # Should be a valid UUID (36 chars with hyphens)
    assert len(session_id) == 36
    assert session_id != "00000000-0000-0000-0000-000000000000"


@pytest.mark.asyncio
async def test_session_isolation(client, tmp_path):
    """Jobs from different sessions don't leak into each other's GET responses.

    Uses two separate httpx clients to get distinct session cookies.
    """
    from fastapi import FastAPI

    from app.core.config import AppConfig
    from app.core.database import close_db, init_db
    from app.core.sse_broker import SSEBroker
    from app.middleware.session import SessionMiddleware
    from app.routers.downloads import router as downloads_router
    from app.routers.formats import router as formats_router
    from app.services.download import DownloadService

    # Build a second, independent test app + DB for isolation test
    db_path = str(tmp_path / "isolation_test.db")
    dl_dir = tmp_path / "dl_iso"
    dl_dir.mkdir()
    config = AppConfig(
        server={"db_path": db_path},
        downloads={"output_dir": str(dl_dir)},
    )
    db_conn = await init_db(db_path)
    loop = asyncio.get_running_loop()
    broker = SSEBroker(loop)
    download_service = DownloadService(config, db_conn, broker, loop)

    test_app = FastAPI(title="media.rip()")
    test_app.add_middleware(SessionMiddleware)
    test_app.include_router(downloads_router, prefix="/api")
    test_app.include_router(formats_router, prefix="/api")
    test_app.state.config = config
    test_app.state.db = db_conn
    test_app.state.broker = broker
    test_app.state.download_service = download_service

    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client_a:
        async with AsyncClient(transport=transport, base_url="http://test") as client_b:
            await client_a.post(
                "/api/downloads",
                json={"url": "https://example.com/a"},
            )
            await client_b.post(
                "/api/downloads",
                json={"url": "https://example.com/b"},
            )

            resp_a = await client_a.get("/api/downloads")
            resp_b = await client_b.get("/api/downloads")

    download_service.shutdown()
    await close_db(db_conn)

    jobs_a = resp_a.json()
    jobs_b = resp_b.json()

    assert len(jobs_a) == 1
    assert jobs_a[0]["url"] == "https://example.com/a"

    assert len(jobs_b) == 1
    assert jobs_b[0]["url"] == "https://example.com/b"

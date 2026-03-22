"""Shared test fixtures for the media-rip backend test suite."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.database import close_db, init_db
from app.core.sse_broker import SSEBroker


@pytest.fixture()
def tmp_db_path(tmp_path: Path) -> str:
    """Return a path for a temporary SQLite database."""
    return str(tmp_path / "test.db")


@pytest.fixture()
def test_config(tmp_path: Path) -> AppConfig:
    """Return an AppConfig with downloads.output_dir pointing at a temp dir."""
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()
    return AppConfig(
        server={"data_dir": str(tmp_path / "data")},
        downloads={"output_dir": str(dl_dir)},
    )


@pytest_asyncio.fixture()
async def db(tmp_db_path: str):
    """Yield an initialised async database connection, cleaned up after."""
    conn = await init_db(tmp_db_path)
    yield conn
    await close_db(conn)


@pytest_asyncio.fixture()
async def broker() -> SSEBroker:
    """Return an SSEBroker bound to the running event loop."""
    loop = asyncio.get_running_loop()
    return SSEBroker(loop)


@pytest_asyncio.fixture()
async def client(tmp_path: Path):
    """Yield an httpx AsyncClient backed by the FastAPI app with temp resources.

    Manually manages the app lifespan since httpx ASGITransport doesn't
    trigger Starlette lifespan events.
    """
    from fastapi import FastAPI

    from app.core.config import AppConfig
    from app.core.database import close_db, init_db
    from app.core.sse_broker import SSEBroker
    from app.middleware.session import SessionMiddleware
    from app.routers.admin import router as admin_router
    from app.routers.cookies import router as cookies_router
    from app.routers.downloads import router as downloads_router
    from app.routers.files import router as files_router
    from app.routers.formats import router as formats_router
    from app.routers.health import router as health_router
    from app.routers.sse import router as sse_router
    from app.routers.system import router as system_router
    from app.routers.themes import router as themes_router
    from app.services.download import DownloadService

    # Temp paths
    db_path = str(tmp_path / "api_test.db")
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()

    # Build config pointing at temp resources
    config = AppConfig(
        server={"db_path": db_path, "data_dir": str(tmp_path / "data")},
        downloads={"output_dir": str(dl_dir)},
    )

    # Initialise services (same as app lifespan)
    db_conn = await init_db(db_path)
    loop = asyncio.get_running_loop()
    broker = SSEBroker(loop)
    download_service = DownloadService(config, db_conn, broker, loop)

    # Build a fresh FastAPI app with routers
    test_app = FastAPI(title="media.rip()")
    test_app.add_middleware(SessionMiddleware)
    test_app.include_router(admin_router, prefix="/api")
    test_app.include_router(cookies_router, prefix="/api")
    test_app.include_router(downloads_router, prefix="/api")
    test_app.include_router(files_router, prefix="/api")
    test_app.include_router(formats_router, prefix="/api")
    test_app.include_router(health_router, prefix="/api")
    test_app.include_router(sse_router, prefix="/api")
    test_app.include_router(system_router, prefix="/api")
    test_app.include_router(themes_router, prefix="/api")

    # Wire state manually
    test_app.state.config = config
    test_app.state.db = db_conn
    test_app.state.broker = broker
    test_app.state.download_service = download_service
    test_app.state.start_time = datetime.now(timezone.utc)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as ac:
        yield ac

    # Teardown
    download_service.shutdown()
    await close_db(db_conn)

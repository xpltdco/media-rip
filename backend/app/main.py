"""media.rip() — FastAPI application entry point.

The lifespan context manager wires together config, database, SSE broker,
download service, and purge scheduler.  All services are stored on
``app.state`` for access from route handlers via ``request.app.state``.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

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

logger = logging.getLogger("mediarip.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialise services on startup, tear down on shutdown."""

    # --- Config ---
    config_path = Path("config.yaml")
    if config_path.is_file():
        config = AppConfig(yaml_file=str(config_path))
        logger.info("Config loaded from YAML: %s", config_path)
    else:
        config = AppConfig()
        logger.info("Config loaded from defaults + env vars (no YAML file)")

    # --- TLS warning ---
    if config.admin.enabled:
        logger.warning(
            "Admin panel is enabled. Ensure HTTPS is configured via a reverse proxy "
            "(Caddy, Traefik, nginx) to protect admin credentials in transit."
        )

    # --- Database ---
    # Ensure data directory exists for DB and session state
    data_dir = Path(config.server.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    db = await init_db(config.server.db_path)
    logger.info("Database initialised at %s", config.server.db_path)

    # --- Event loop + SSE broker ---
    loop = asyncio.get_event_loop()
    broker = SSEBroker(loop)

    # --- Download service ---
    download_service = DownloadService(config, db, broker, loop)

    # --- Purge scheduler ---
    scheduler = None
    if config.purge.enabled:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
            from app.services.purge import run_purge

            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                run_purge,
                CronTrigger.from_crontab(config.purge.cron),
                args=[db, config],
                id="purge_job",
                name="Scheduled purge",
            )
            scheduler.start()
            logger.info("Purge scheduler started: cron=%s", config.purge.cron)
        except ImportError:
            logger.warning("APScheduler not installed — scheduled purge disabled")
        except Exception as e:
            logger.error("Failed to start purge scheduler: %s", e)

    # --- Store on app.state ---
    app.state.config = config
    app.state.db = db
    app.state.broker = broker
    app.state.download_service = download_service
    app.state.start_time = datetime.now(timezone.utc)

    yield

    # --- Teardown ---
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    download_service.shutdown()
    await close_db(db)
    logger.info("Application shutdown complete")


app = FastAPI(title="media.rip()", lifespan=lifespan)
app.add_middleware(SessionMiddleware)


# --- Security headers middleware (R020: zero outbound telemetry) ---


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers enforcing no outbound resource loading."""

    async def dispatch(self, request: StarletteRequest, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        # Content-Security-Policy: only allow resources from self
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.include_router(admin_router, prefix="/api")
app.include_router(cookies_router, prefix="/api")
app.include_router(downloads_router, prefix="/api")
app.include_router(files_router, prefix="/api")
app.include_router(formats_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(sse_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(themes_router, prefix="/api")

# --- Static file serving (production: built frontend) ---
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the Vue SPA. Falls back to index.html for client-side routing."""
        file_path = _static_dir / full_path
        if file_path.is_file() and file_path.resolve().is_relative_to(_static_dir.resolve()):
            return FileResponse(file_path)
        return FileResponse(_static_dir / "index.html")

    logger.info("Static file serving enabled from %s", _static_dir)

"""Tests for theme loader service and API."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.database import close_db, init_db
from app.middleware.session import SessionMiddleware
from app.routers.themes import router as themes_router
from app.services.theme_loader import get_theme_css, scan_themes


class TestScanThemes:
    """Theme directory scanner tests."""

    def test_empty_directory(self, tmp_path):
        themes = scan_themes(tmp_path)
        assert themes == []

    def test_nonexistent_directory(self, tmp_path):
        themes = scan_themes(tmp_path / "nonexistent")
        assert themes == []

    def test_valid_theme(self, tmp_path):
        theme_dir = tmp_path / "my-theme"
        theme_dir.mkdir()
        (theme_dir / "metadata.json").write_text(
            json.dumps({"name": "My Theme", "author": "Test"})
        )
        (theme_dir / "theme.css").write_text("[data-theme='my-theme'] { --color-bg: red; }")

        themes = scan_themes(tmp_path)
        assert len(themes) == 1
        assert themes[0]["id"] == "my-theme"
        assert themes[0]["name"] == "My Theme"
        assert themes[0]["author"] == "Test"

    def test_missing_metadata_skipped(self, tmp_path):
        theme_dir = tmp_path / "bad-theme"
        theme_dir.mkdir()
        (theme_dir / "theme.css").write_text("body {}")

        themes = scan_themes(tmp_path)
        assert themes == []

    def test_missing_css_skipped(self, tmp_path):
        theme_dir = tmp_path / "no-css"
        theme_dir.mkdir()
        (theme_dir / "metadata.json").write_text('{"name": "No CSS"}')

        themes = scan_themes(tmp_path)
        assert themes == []

    def test_invalid_json_skipped(self, tmp_path):
        theme_dir = tmp_path / "bad-json"
        theme_dir.mkdir()
        (theme_dir / "metadata.json").write_text("not json")
        (theme_dir / "theme.css").write_text("body {}")

        themes = scan_themes(tmp_path)
        assert themes == []

    def test_preview_detected(self, tmp_path):
        theme_dir = tmp_path / "with-preview"
        theme_dir.mkdir()
        (theme_dir / "metadata.json").write_text('{"name": "Preview"}')
        (theme_dir / "theme.css").write_text("body {}")
        (theme_dir / "preview.png").write_bytes(b"PNG")

        themes = scan_themes(tmp_path)
        assert themes[0]["has_preview"] is True

    def test_multiple_themes_sorted(self, tmp_path):
        for name in ["beta", "alpha", "gamma"]:
            d = tmp_path / name
            d.mkdir()
            (d / "metadata.json").write_text(f'{{"name": "{name}"}}')
            (d / "theme.css").write_text("body {}")

        themes = scan_themes(tmp_path)
        assert [t["id"] for t in themes] == ["alpha", "beta", "gamma"]

    def test_files_in_root_ignored(self, tmp_path):
        (tmp_path / "readme.txt").write_text("not a theme")
        themes = scan_themes(tmp_path)
        assert themes == []


class TestGetThemeCSS:
    """Theme CSS retrieval tests."""

    def test_returns_css(self, tmp_path):
        theme_dir = tmp_path / "my-theme"
        theme_dir.mkdir()
        css_content = "[data-theme='my-theme'] { --color-bg: #fff; }"
        (theme_dir / "theme.css").write_text(css_content)

        result = get_theme_css(tmp_path, "my-theme")
        assert result == css_content

    def test_missing_theme_returns_none(self, tmp_path):
        result = get_theme_css(tmp_path, "nonexistent")
        assert result is None

    def test_path_traversal_blocked(self, tmp_path):
        result = get_theme_css(tmp_path, "../../etc")
        assert result is None


@pytest_asyncio.fixture()
async def theme_client(tmp_path):
    """Client with theme API router."""
    db_path = str(tmp_path / "theme_test.db")
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir()

    # Create a sample custom theme
    custom = themes_dir / "neon"
    custom.mkdir()
    (custom / "metadata.json").write_text(
        json.dumps({"name": "Neon", "author": "Test", "description": "Bright neon"})
    )
    (custom / "theme.css").write_text("[data-theme='neon'] { --color-accent: #ff00ff; }")

    config = AppConfig(
        server={"db_path": db_path},
        themes_dir=str(themes_dir),
    )

    db_conn = await init_db(db_path)
    app = FastAPI()
    app.add_middleware(SessionMiddleware)
    app.include_router(themes_router, prefix="/api")
    app.state.config = config
    app.state.db = db_conn
    app.state.start_time = datetime.now(timezone.utc)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await close_db(db_conn)


class TestThemeAPI:
    """Theme API endpoint tests."""

    @pytest.mark.anyio
    async def test_list_themes(self, theme_client):
        resp = await theme_client.get("/api/themes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["themes"][0]["id"] == "neon"
        assert data["themes"][0]["name"] == "Neon"

    @pytest.mark.anyio
    async def test_get_theme_css(self, theme_client):
        resp = await theme_client.get("/api/themes/neon/theme.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]
        assert "--color-accent: #ff00ff" in resp.text

    @pytest.mark.anyio
    async def test_get_missing_theme_returns_404(self, theme_client):
        resp = await theme_client.get("/api/themes/nonexistent/theme.css")
        assert resp.status_code == 404

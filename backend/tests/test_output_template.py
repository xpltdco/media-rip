"""Tests for output template resolution."""

from __future__ import annotations

import pytest

from app.core.config import AppConfig
from app.services.output_template import resolve_template


@pytest.fixture()
def config() -> AppConfig:
    """AppConfig with default source_templates."""
    return AppConfig()


class TestResolveTemplate:
    """Test output template resolution logic."""

    def test_youtube_url_matches_domain(self, config: AppConfig):
        result = resolve_template(
            "https://youtube.com/watch?v=abc123", None, config
        )
        assert result == "%(uploader)s/%(title)s.%(ext)s"

    def test_soundcloud_url_matches_domain(self, config: AppConfig):
        result = resolve_template(
            "https://soundcloud.com/artist/track", None, config
        )
        assert result == "%(uploader)s/%(title)s.%(ext)s"

    def test_unknown_domain_fallback(self, config: AppConfig):
        result = resolve_template(
            "https://example.com/video.mp4", None, config
        )
        assert result == "%(title)s.%(ext)s"

    def test_www_prefix_stripped(self, config: AppConfig):
        """www.youtube.com should resolve the same as youtube.com."""
        result = resolve_template(
            "https://www.youtube.com/watch?v=abc123", None, config
        )
        assert result == "%(uploader)s/%(title)s.%(ext)s"

    def test_user_override_takes_priority(self, config: AppConfig):
        """User override should beat the domain match."""
        result = resolve_template(
            "https://youtube.com/watch?v=abc123",
            "my_custom/%(title)s.%(ext)s",
            config,
        )
        assert result == "my_custom/%(title)s.%(ext)s"

    def test_malformed_url_returns_fallback(self, config: AppConfig):
        result = resolve_template("not-a-url", None, config)
        assert result == "%(title)s.%(ext)s"

    def test_empty_url_returns_fallback(self, config: AppConfig):
        result = resolve_template("", None, config)
        assert result == "%(title)s.%(ext)s"

    def test_url_with_port_resolves(self, config: AppConfig):
        """Domain extraction should work even with port numbers."""
        result = resolve_template(
            "https://youtube.com:443/watch?v=abc123", None, config
        )
        assert result == "%(uploader)s/%(title)s.%(ext)s"

    def test_custom_domain_template(self):
        """A custom source_template config should be respected."""
        cfg = AppConfig(
            downloads={
                "source_templates": {
                    "vimeo.com": "vimeo/%(title)s.%(ext)s",
                    "*": "%(title)s.%(ext)s",
                }
            }
        )
        result = resolve_template("https://vimeo.com/12345", None, cfg)
        assert result == "vimeo/%(title)s.%(ext)s"

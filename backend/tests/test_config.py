"""Tests for the pydantic-settings config system."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.core.config import AppConfig


class TestZeroConfig:
    """Verify AppConfig works out of the box with zero user config."""

    def test_defaults_load_without_crash(self):
        config = AppConfig()
        assert config.server.host == "0.0.0.0"
        assert config.server.port == 8000
        assert config.server.db_path == "mediarip.db"

    def test_downloads_defaults(self):
        config = AppConfig()
        assert config.downloads.output_dir == "/downloads"
        assert config.downloads.max_concurrent == 3

    def test_session_defaults(self):
        config = AppConfig()
        assert config.session.mode == "isolated"
        assert config.session.timeout_hours == 72

    def test_admin_defaults(self):
        config = AppConfig()
        assert config.admin.enabled is False

    def test_source_templates_default_entries(self):
        config = AppConfig()
        templates = config.downloads.source_templates
        assert "youtube.com" in templates
        assert "soundcloud.com" in templates
        assert "*" in templates


class TestEnvVarOverride:
    """Environment variables with MEDIARIP__ prefix override defaults."""

    def test_override_max_concurrent(self, monkeypatch):
        monkeypatch.setenv("MEDIARIP__DOWNLOADS__MAX_CONCURRENT", "5")
        config = AppConfig()
        assert config.downloads.max_concurrent == 5

    def test_override_server_port(self, monkeypatch):
        monkeypatch.setenv("MEDIARIP__SERVER__PORT", "9000")
        config = AppConfig()
        assert config.server.port == 9000

    def test_override_session_timeout(self, monkeypatch):
        monkeypatch.setenv("MEDIARIP__SESSION__TIMEOUT_HOURS", "24")
        config = AppConfig()
        assert config.session.timeout_hours == 24


class TestYamlConfig:
    """YAML file loading and graceful fallback."""

    def test_yaml_values_load(self, tmp_path: Path, monkeypatch):
        yaml_content = """
server:
  port: 7777
  log_level: debug
downloads:
  max_concurrent: 10
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        monkeypatch.setitem(AppConfig.model_config, "yaml_file", str(yaml_file))
        config = AppConfig()
        assert config.server.port == 7777
        assert config.server.log_level == "debug"
        assert config.downloads.max_concurrent == 10

    def test_missing_yaml_no_crash(self, tmp_path: Path, monkeypatch):
        """A non-existent YAML path should not raise — zero-config mode."""
        monkeypatch.setitem(
            AppConfig.model_config, "yaml_file",
            str(tmp_path / "nonexistent.yaml"),
        )
        config = AppConfig()
        # Falls back to defaults
        assert config.server.port == 8000

    def test_yaml_file_none(self):
        """Explicitly None yaml_file should be fine."""
        config = AppConfig()
        assert config is not None

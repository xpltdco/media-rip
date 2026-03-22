"""Application configuration via pydantic-settings.

Loads settings from (highest → lowest priority):
  1. Environment variables (prefix ``MEDIARIP``, nested delimiter ``__``)
  2. YAML config file (optional — zero-config if missing)
  3. Init kwargs
  4. .env file

Zero-config mode: if no YAML file is provided or the file doesn't exist,
all settings fall back to sensible defaults.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

logger = logging.getLogger("mediarip.config")


# ---------------------------------------------------------------------------
# Nested config sections
# ---------------------------------------------------------------------------


class ServerConfig(BaseModel):
    """Core server settings."""

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    db_path: str = "mediarip.db"
    data_dir: str = "/data"
    api_key: str = ""  # Managed via admin panel — not typically set via env


class DownloadsConfig(BaseModel):
    """Download behaviour defaults."""

    output_dir: str = "/downloads"
    max_concurrent: int = 3
    source_templates: dict[str, str] = {
        "youtube.com": "%(uploader)s/%(title)s.%(ext)s",
        "soundcloud.com": "%(uploader)s/%(title)s.%(ext)s",
        "*": "%(title)s.%(ext)s",
    }
    default_template: str = "%(title)s.%(ext)s"


class YtdlpConfig(BaseModel):
    """yt-dlp tuning — operator-level knobs for YouTube and other extractors.

    ``extractor_args`` maps extractor names to dicts of arg lists, e.g.:
        youtube:
          player_client: ["web_safari", "android_vr"]

    These are passed through to yt-dlp as ``extractor_args``.
    """

    extractor_args: dict[str, dict[str, list[str]]] = {}


class SessionConfig(BaseModel):
    """Session management settings."""

    mode: str = "isolated"
    timeout_hours: int = 72


class PurgeConfig(BaseModel):
    """Automatic purge / cleanup settings."""

    enabled: bool = True
    max_age_minutes: int = 1440  # 24 hours
    cron: str = "* * * * *"  # every minute
    privacy_mode: bool = False
    privacy_retention_minutes: int = 1440  # default when privacy mode enabled


class UIConfig(BaseModel):
    """UI preferences."""

    default_theme: str = "dark"
    welcome_message: str = "Paste any video or audio URL. We rip it, you download it. No accounts, no tracking."


class AdminConfig(BaseModel):
    """Admin panel settings."""

    enabled: bool = True
    username: str = "admin"
    password: str = ""       # Plaintext — hashed on startup, never stored
    password_hash: str = ""  # Internal — set by app on startup or first-run wizard


# ---------------------------------------------------------------------------
# Safe YAML source — tolerates missing files
# ---------------------------------------------------------------------------


class _SafeYamlSource(YamlConfigSettingsSource):
    """YAML source that returns an empty dict when the file is missing."""

    def __call__(self) -> dict[str, Any]:
        yaml_file = self.yaml_file_path
        if yaml_file is None:
            return {}
        if not Path(yaml_file).is_file():
            logger.debug("YAML config file not found at %s — using defaults", yaml_file)
            return {}
        return super().__call__()


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class AppConfig(BaseSettings):
    """Top-level application configuration.

    Priority (highest wins): env vars → YAML file → init kwargs → .env file.
    """

    model_config = SettingsConfigDict(
        env_prefix="MEDIARIP__",
        env_nested_delimiter="__",
        yaml_file=None,
    )

    server: ServerConfig = ServerConfig()
    downloads: DownloadsConfig = DownloadsConfig()
    session: SessionConfig = SessionConfig()
    purge: PurgeConfig = PurgeConfig()
    ui: UIConfig = UIConfig()
    admin: AdminConfig = AdminConfig()
    ytdlp: YtdlpConfig = YtdlpConfig()
    themes_dir: str = "./themes"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            env_settings,
            _SafeYamlSource(settings_cls),
            init_settings,
            dotenv_settings,
        )

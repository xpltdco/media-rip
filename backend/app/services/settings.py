"""Persistent settings service — reads/writes the `config` table in SQLite.

Settings priority (highest wins):
  1. Admin writes via UI → persisted in SQLite `config` table
  2. Environment variables (MEDIARIP__*)
  3. config.yaml
  4. Hardcoded defaults

On startup, persisted settings are loaded and applied to the AppConfig.
Admin writes go to DB immediately and update the live config.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger("mediarip.settings")

# Keys that can be persisted via admin UI
ADMIN_WRITABLE_KEYS = {
    "welcome_message",
    "default_video_format",
    "default_audio_format",
    "privacy_mode",
    "privacy_retention_hours",
    "max_concurrent",
    "session_mode",
    "session_timeout_hours",
    "admin_username",
    "admin_password_hash",
    "purge_enabled",
    "purge_max_age_hours",
}


async def load_persisted_settings(db: aiosqlite.Connection) -> dict:
    """Load all persisted settings from the config table."""
    cursor = await db.execute("SELECT key, value FROM config")
    rows = await cursor.fetchall()
    settings = {}
    for row in rows:
        key = row["key"]
        raw = row["value"]
        if key in ADMIN_WRITABLE_KEYS:
            settings[key] = _deserialize(key, raw)
    return settings


async def save_setting(db: aiosqlite.Connection, key: str, value: object) -> None:
    """Persist a single setting to the config table."""
    if key not in ADMIN_WRITABLE_KEYS:
        raise ValueError(f"Setting '{key}' is not admin-writable")
    now = datetime.now(timezone.utc).isoformat()
    serialized = json.dumps(value)
    await db.execute(
        """
        INSERT INTO config (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, serialized, now),
    )
    await db.commit()
    logger.info("Persisted setting %s", key)


async def save_settings(db: aiosqlite.Connection, settings: dict) -> list[str]:
    """Persist multiple settings. Returns list of keys saved."""
    saved = []
    for key, value in settings.items():
        if key in ADMIN_WRITABLE_KEYS:
            await save_setting(db, key, value)
            saved.append(key)
    return saved


async def delete_setting(db: aiosqlite.Connection, key: str) -> None:
    """Remove a persisted setting (reverts to default)."""
    await db.execute("DELETE FROM config WHERE key = ?", (key,))
    await db.commit()


def apply_persisted_to_config(config, settings: dict) -> None:
    """Apply persisted settings to the live AppConfig object.

    Only applies values for keys that exist in settings dict.
    Does NOT overwrite values that were explicitly set via env vars.
    """
    if "welcome_message" in settings:
        config.ui.welcome_message = settings["welcome_message"]
    if "max_concurrent" in settings:
        config.downloads.max_concurrent = settings["max_concurrent"]
    if "session_mode" in settings:
        config.session.mode = settings["session_mode"]
    if "session_timeout_hours" in settings:
        config.session.timeout_hours = settings["session_timeout_hours"]
    if "admin_username" in settings:
        config.admin.username = settings["admin_username"]
    if "admin_password_hash" in settings:
        config.admin.password_hash = settings["admin_password_hash"]
    if "purge_enabled" in settings:
        config.purge.enabled = settings["purge_enabled"]
    if "purge_max_age_hours" in settings:
        config.purge.max_age_hours = settings["purge_max_age_hours"]
    if "privacy_mode" in settings:
        config.purge.privacy_mode = settings["privacy_mode"]
    if "privacy_retention_hours" in settings:
        config.purge.privacy_retention_hours = settings["privacy_retention_hours"]

    logger.info("Applied %d persisted settings to config", len(settings))


def _deserialize(key: str, raw: str) -> object:
    """Deserialize a config value from its JSON string."""
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw

    # Type coercion for known keys
    bool_keys = {"privacy_mode", "purge_enabled"}
    int_keys = {"max_concurrent", "session_timeout_hours", "purge_max_age_hours", "privacy_retention_hours"}

    if key in bool_keys:
        return bool(value)
    if key in int_keys:
        return int(value) if value is not None else value
    return value

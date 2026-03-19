"""
Theme loader service — discovers custom themes from /themes volume.

Each theme is a directory containing at minimum:
  - metadata.json: { "name": "Theme Name", "author": "Author", "description": "..." }
  - theme.css: CSS variable overrides inside [data-theme="<dirname>"] selector

Optional:
  - preview.png: Preview thumbnail for the theme picker
  - assets/: Additional assets (fonts, images) served statically
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def scan_themes(themes_dir: str | Path) -> list[dict[str, Any]]:
    """Scan a directory for valid theme packs.

    Returns a list of theme metadata dicts with the directory name as 'id'.
    Skips directories missing metadata.json or theme.css.
    """
    themes_path = Path(themes_dir)
    if not themes_path.is_dir():
        logger.debug("Themes directory does not exist: %s", themes_dir)
        return []

    themes: list[dict[str, Any]] = []

    for entry in sorted(themes_path.iterdir()):
        if not entry.is_dir():
            continue

        metadata_file = entry / "metadata.json"
        css_file = entry / "theme.css"

        if not metadata_file.exists():
            logger.warning("Theme '%s' missing metadata.json — skipping", entry.name)
            continue

        if not css_file.exists():
            logger.warning("Theme '%s' missing theme.css — skipping", entry.name)
            continue

        try:
            meta = json.loads(metadata_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Theme '%s' has invalid metadata.json: %s — skipping", entry.name, e)
            continue

        theme_info = {
            "id": entry.name,
            "name": meta.get("name", entry.name),
            "author": meta.get("author"),
            "description": meta.get("description"),
            "has_preview": (entry / "preview.png").exists(),
            "path": str(entry),
        }
        themes.append(theme_info)
        logger.info("Discovered custom theme: %s (%s)", theme_info["name"], entry.name)

    return themes


def get_theme_css(themes_dir: str | Path, theme_id: str) -> str | None:
    """Read the CSS for a specific custom theme.

    Returns None if the theme doesn't exist or lacks theme.css.
    """
    css_path = Path(themes_dir) / theme_id / "theme.css"
    if not css_path.is_file():
        return None

    # Security: verify the resolved path is inside themes_dir
    try:
        css_path.resolve().relative_to(Path(themes_dir).resolve())
    except ValueError:
        logger.warning("Path traversal attempt in theme CSS: %s", theme_id)
        return None

    return css_path.read_text(encoding="utf-8")

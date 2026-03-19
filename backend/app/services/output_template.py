"""Output template resolution for yt-dlp downloads.

Determines the yt-dlp output template for a given URL by checking:
1. User override (per-download, highest priority)
2. Domain-specific template from config
3. Wildcard fallback from config
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from app.core.config import AppConfig

logger = logging.getLogger("mediarip.output_template")

_DEFAULT_FALLBACK = "%(title)s.%(ext)s"


def resolve_template(
    url: str,
    user_override: str | None,
    config: AppConfig,
) -> str:
    """Resolve the yt-dlp output template for *url*.

    Priority:
      1. *user_override* — returned verbatim when not ``None``
      2. Domain match in ``config.downloads.source_templates``
      3. Wildcard ``*`` entry in source_templates
      4. Hard-coded fallback ``%(title)s.%(ext)s``
    """
    if user_override is not None:
        logger.debug("Using user override template: %s", user_override)
        return user_override

    domain = _extract_domain(url)
    templates = config.downloads.source_templates

    if domain and domain in templates:
        logger.debug("Domain '%s' matched template: %s", domain, templates[domain])
        return templates[domain]

    fallback = templates.get("*", _DEFAULT_FALLBACK)
    logger.debug("No domain match for '%s', using fallback: %s", domain, fallback)
    return fallback


def _extract_domain(url: str) -> str | None:
    """Extract the bare domain from *url*, stripping ``www.`` prefix.

    Returns ``None`` for malformed URLs that lack a hostname.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname is None:
            return None
        hostname = hostname.lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname
    except Exception:
        return None

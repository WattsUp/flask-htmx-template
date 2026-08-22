"""Common controller context constants."""

from __future__ import annotations

import re
from typing import NamedTuple

from flask_htmx_template import web, web_theme
from flask_htmx_template.models.config import Config, ConfigKey

SWATCH_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
COOKIE_SWATCH = "theme_swatch"
COOKIE_MOOD = "theme_mood"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60


class ThemeSelection(NamedTuple):
    """Resolved swatch and mood for generating a theme."""

    swatch: web_theme.HexColor
    mood: web_theme.Mood


def ctx_theme(
    swatch: str | None = None,
    mood_name: str | None = None,
) -> ThemeSelection:
    """Resolve a theme selection, falling back to configured defaults.

    Args:
        swatch: Requested swatch color, if any.
        mood_name: Requested mood name, if any.

    Returns:
        Swatch color and mood used to generate the theme.

    """
    try:
        mood = web_theme.Mood[mood_name] if mood_name else None
    except KeyError:
        mood = None

    if not swatch or mood is None:
        with web.db.begin_session():
            if not swatch:
                swatch = Config.fetch(ConfigKey.WEB_THEME_SWATCH)
            if mood is None:
                mood = Config.web_theme_mood()

    return ThemeSelection(swatch, mood)

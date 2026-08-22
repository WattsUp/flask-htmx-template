"""Common controller context constants."""

from __future__ import annotations

import re

SWATCH_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
COOKIE_SWATCH = "theme_swatch"
COOKIE_MOOD = "theme_mood"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60

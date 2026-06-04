"""Add web theme config."""

from __future__ import annotations

from typing import override, TYPE_CHECKING

from flask_htmx_template import web_theme
from flask_htmx_template.migrations.base import Migrator
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from flask_htmx_template.database import Database


class AddWebThemeConfig(Migrator):
    """Add web theme swatch and mood config entries."""

    @override
    def migrate(self, d: Database) -> list[str]:
        """Run migration.

        Args:
            d: Database to migrate

        Returns:
            List of comments to display to user

        """
        comments: list[str] = []

        with d.begin_session():
            Config.set_(ConfigKey.WEB_THEME_SWATCH, web_theme.DEFAULT_SWATCH)
            Config.set_(ConfigKey.WEB_THEME_MOOD, web_theme.DEFAULT_MOOD.name)

        return comments

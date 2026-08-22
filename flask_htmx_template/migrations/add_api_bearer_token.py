"""Add the API bearer token configuration."""

from __future__ import annotations

import secrets
from typing import override, TYPE_CHECKING

from flask_htmx_template.migrations.base import Migrator
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from flask_htmx_template.database import Database


class AddAPIBearerToken(Migrator):
    """Add the opaque bearer token used by JSON API clients."""

    @override
    def migrate(self, d: Database) -> list[str]:
        """Add a newly generated bearer token to the database.

        Args:
            d: Database to migrate.

        Returns:
            Migration comments.

        """
        with d.begin_session():
            Config.set_(ConfigKey.API_BEARER_TOKEN, secrets.token_urlsafe(32))
        return []

"""Create Item table."""

from __future__ import annotations

from typing import override, TYPE_CHECKING

from flask_htmx_template.migrations.base import Migrator
from flask_htmx_template.models.base import Base
from flask_htmx_template.models.config import Config
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    from flask_htmx_template.database import Database


class CreateItemTable(Migrator):
    """Create Item table."""

    @override
    def migrate(self, d: Database) -> list[str]:
        """Run migration.

        Args:
            d: Database to migrate

        Returns:
            List of comments to display to user

        """
        comments: list[str] = []

        with d.begin_session() as s:
            Base.metadata.create_all(
                s.get_bind(),
                [Item.sql_table()],
            )
            self.pending_schema_updates.add(Config)
            comments.append("Created Item table")

        return comments

"""Migrators."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy

from flask_htmx_template import sql
from flask_htmx_template.migrations.add_api_bearer_token import AddAPIBearerToken
from flask_htmx_template.migrations.add_web_theme_config import AddWebThemeConfig
from flask_htmx_template.migrations.create_item_table import CreateItemTable
from flask_htmx_template.models.applied_migration import AppliedMigration

if TYPE_CHECKING:
    from flask_htmx_template.database import Database
    from flask_htmx_template.migrations.base import Migrator

_MIGRATORS: list[type[Migrator]] = [
    CreateItemTable,
    AddWebThemeConfig,
    AddAPIBearerToken,
]


def collect(d: Database) -> list[type[Migrator]]:
    """Return migrators that have not yet been applied, in order.

    Args:
        d: Database to check applied migrations against

    Returns:
        Ordered list of unapplied migrator classes

    """
    with d.begin_session() as s:
        engine = s.get_bind().engine
        inspector = sqlalchemy.inspect(engine)
        if not inspector.has_table("applied_migration"):
            return list(_MIGRATORS)
        applied = {am.name for am in sql.yield_(AppliedMigration.query())}

    return [m for m in _MIGRATORS if m.__name__ not in applied]

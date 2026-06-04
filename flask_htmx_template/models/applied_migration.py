"""AppliedMigration model."""

from __future__ import annotations

from sqlalchemy import orm

from flask_htmx_template.models.base import Base, ORMDateTime, ORMStr


class AppliedMigration(Base):
    """Records a migration that has been applied to this database.

    Attributes:
        name: Class name of the applied Migrator
        applied_at_utc: UTC timestamp when the migration was applied

    """

    __tablename__ = "applied_migration"
    __table_id__ = None

    name: ORMStr = orm.mapped_column(unique=True)
    applied_at_utc: ORMDateTime

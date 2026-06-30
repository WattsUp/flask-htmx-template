"""Migrate database."""

from __future__ import annotations

from typing import override, TYPE_CHECKING

from colorama import Fore

from flask_htmx_template.commands.base import Command

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

    from flask_htmx_template.models.base import Base


class Migrate(Command):
    """Migrate database."""

    NAME = "migrate"
    HELP = "migrate database"
    DESCRIPTION = "Migrate database to latest version"

    def __init__(
        self,
        path_db: Path | str,
    ) -> None:
        """Initialize migrate command.

        Args:
            path_db: Path to Database DB or postgres connection URL

        """
        super().__init__(path_db, check_migration=False)

    @override
    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        # No arguments
        _ = parser

    @override
    def run(self) -> int:
        # Defer for faster time to main
        import datetime

        import sqlalchemy

        from flask_htmx_template.migrations.base import SchemaMigrator
        from flask_htmx_template.migrations.top import collect
        from flask_htmx_template.models.applied_migration import AppliedMigration
        from flask_htmx_template.models.base import Base
        from flask_htmx_template.models.config import Config, ConfigKey

        d = self._d

        # Ensure applied_migration table exists (old databases won't have it)
        with d.begin_session() as s:
            engine = s.get_bind().engine
            inspector = sqlalchemy.inspect(engine)
            table_exists = inspector.has_table("applied_migration")

        if not table_exists:
            with d.begin_session() as s:
                Base.metadata.create_all(
                    s.get_bind().engine,
                    [AppliedMigration.sql_table()],
                )

        pending = collect(d)
        if not pending:
            print(f"{Fore.GREEN}Database does not need migration")
            return 0

        pending_schema_updates: set[type[Base]] = set()
        for m_class in pending:
            m = m_class()
            comments = m.migrate(d)

            for line in comments:
                print(f"{Fore.CYAN}{line}")

            print(f"{Fore.GREEN}Database migrated: {m_class.__name__}")
            pending_schema_updates.update(m.pending_schema_updates)

            with d.begin_session():
                AppliedMigration.create(
                    name=m_class.__name__,
                    applied_at_utc=datetime.datetime.now(datetime.UTC),
                )

        if pending_schema_updates:
            m = SchemaMigrator(pending_schema_updates)
            comments = m.migrate(d)
            for line in comments:
                print(f"{Fore.CYAN}{line}")
            print(f"{Fore.GREEN}Database model schemas updated")

        with d.begin_session():
            Config.set_(ConfigKey.VERSION, "1.0")

        return 0

"""Migrate database."""

from __future__ import annotations

from typing import override, TYPE_CHECKING

from colorama import Fore

from flask_htmx_template.commands.base import Command
from flask_htmx_template.version import __version__

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
        path_password: Path | None,
    ) -> None:
        """Initialize migrate command.

        Args:
            path_db: Path to Database DB or postgres connection URL
            path_password: Path to password file, None will prompt when necessary

        """
        super().__init__(path_db, path_password, check_migration=False)

    @override
    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        # No arguments
        _ = parser

    @override
    def run(self) -> int:
        # Defer for faster time to main
        from packaging.version import Version

        from flask_htmx_template import database
        from flask_htmx_template.migrations.base import SchemaMigrator
        from flask_htmx_template.migrations.top import MIGRATORS
        from flask_htmx_template.models.config import Config, ConfigKey

        d = self._d

        # Back up Database (SQLite only)
        tar_ver: int | None = None
        if not d.is_postgres:
            _, tar_ver = d.backup()

        with d.begin_session():
            v_db = Config.db_version()

        any_migrated = False
        try:
            pending_schema_updates: set[type[Base]] = set()
            for m_class in MIGRATORS:
                v_m = m_class.min_version()
                if v_db >= v_m:
                    continue
                m = m_class()
                any_migrated = True
                comments = m.migrate(d)
                for line in comments:
                    print(f"{Fore.CYAN}{line}")

                print(f"{Fore.GREEN}Database migrated to v{v_m}")
                pending_schema_updates.update(m.pending_schema_updates)

            if pending_schema_updates:
                m = SchemaMigrator(pending_schema_updates)
                m.migrate(d)  # no comments
                print(f"{Fore.GREEN}Database model schemas updated")

            with d.begin_session():
                v = max(
                    Version(__version__),
                    *[m.min_version() for m in MIGRATORS],
                )

                Config.set_(ConfigKey.VERSION, str(v))
        except Exception:  # pragma: no cover
            # No immediate exception thrown, can't easily test
            if tar_ver is not None:
                database.Database.restore(d, tar_ver=tar_ver)
                print(f"{Fore.RED}Abandoned migrate, restored from backup")
            raise

        if not any_migrated:
            print(f"{Fore.GREEN}Database does not need migration")

        return 0

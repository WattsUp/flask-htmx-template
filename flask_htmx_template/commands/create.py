"""Create a database command."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import override, TYPE_CHECKING

from colorama import Fore

from flask_htmx_template.commands.base import Command

if TYPE_CHECKING:
    import argparse

DATABASE_ALREADY_INITIALIZED_EXIT_CODE = 2


class Create(Command):
    """Create database."""

    NAME = "create"
    HELP = "create flask_htmx_template database"
    DESCRIPTION = "Create a new flask_htmx_template database"

    def __init__(
        self,
        path_db: Path | str,
        *,
        force: bool,
    ) -> None:
        """Initialize create command.

        Args:
            path_db: Path to Database DB or postgres connection URL
            force: True will overwrite existing if necessary

        """
        super().__init__(path_db, do_unlock=False)
        self._force = force

    @override
    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--force",
            default=False,
            action="store_true",
            help="Force create a new database, will overwrite existing",
        )

    @override
    def run(self) -> int:
        # Defer for faster time to main
        from flask_htmx_template import database, sql

        if sql.is_postgres_url(str(self._path_db)):
            try:
                database.PostgresDatabase.create(self._path_db)
            except FileExistsError as e:
                if self._force:
                    print(
                        f"{Fore.RED}--force is not supported for postgres databases",
                        file=sys.stderr,
                    )
                    return -1
                print(f"{Fore.RED}{e}", file=sys.stderr)
                # NOTE: The container entrypoint relies on this distinct status to
                # distinguish an existing database from connection failures.
                return DATABASE_ALREADY_INITIALIZED_EXIT_CODE
            print(f"{Fore.GREEN}Postgres database initialized at {self._path_db}")
            return 0

        # SQLite: self._path_db is a Path (set by base Command.__init__)
        path_db = Path(self._path_db)
        if path_db.exists():
            if self._force:
                path_db.unlink()
            else:
                print(
                    f"{Fore.RED}Cannot overwrite database at {path_db}. "
                    "Try with --force",
                    file=sys.stderr,
                )
                return -1

        database.SQLiteDatabase.create(path_db)
        print(f"{Fore.GREEN}Database created at {path_db}")

        return 0

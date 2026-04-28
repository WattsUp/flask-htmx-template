"""Create a database command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import override

from colorama import Fore

from flask_htmx_template.commands.base import Command


class Create(Command):
    """Create database."""

    NAME = "create"
    HELP = "create flask_htmx_template database"
    DESCRIPTION = "Create a new flask_htmx_template database"

    def __init__(
        self,
        path_db: Path | str,
        path_password: Path | None,
        *,
        force: bool,
        no_encrypt: bool,
    ) -> None:
        """Initialize create command.

        Args:
            path_db: Path to Database DB or postgres connection URL
            path_password: Path to password file, None will prompt when necessary
            force: True will overwrite existing if necessary
            no_encrypt: True will not encrypt the Database

        """
        super().__init__(path_db, path_password, do_unlock=False)
        self._force = force
        self._no_encrypt = no_encrypt

    @override
    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--force",
            default=False,
            action="store_true",
            help="Force create a new database, will overwrite existing",
        )
        parser.add_argument(
            "--no-encrypt",
            default=False,
            action="store_true",
            # No encrypt is for testing only
            help=argparse.SUPPRESS,
        )

    @override
    def run(self) -> int:
        # Defer for faster time to main
        from flask_htmx_template import database, sql, utils

        if sql.is_postgres_url(str(self._path_db)):
            try:
                database.Database.create(self._path_db)
            except FileExistsError as e:
                if self._force:
                    print(
                        f"{Fore.RED}--force is not supported for postgres databases",
                        file=sys.stderr,
                    )
                    return -1
                print(f"{Fore.RED}{e}", file=sys.stderr)
                return -1
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

        key: str | None = None
        if not self._no_encrypt:
            if self._path_password is not None and self._path_password.exists():
                key = self._path_password.read_text("utf-8").strip()

            # Get key from user is password file empty
            key = key or utils.get_password()
            if key is None:
                # Canceled
                return -1

        database.Database.create(path_db, key)
        print(f"{Fore.GREEN}Database created at {path_db}")

        return 0

"""Backup and restore a database."""

from __future__ import annotations

import datetime
import sys
from typing import cast, override, TYPE_CHECKING

from colorama import Fore

from flask_htmx_template.commands.base import Command

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

    from flask_htmx_template.database import SQLiteDatabase


class Backup(Command):
    """Backup database."""

    NAME = "backup"
    HELP = "backup database"
    DESCRIPTION = "Backup database to a tar"

    def __init__(
        self,
        path_db: Path | str,
        path_password: Path | None,
    ) -> None:
        """Initialize backup command.

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
        if self._d.is_postgres:
            print(
                f"{Fore.RED}backup is not supported for postgres databases",
                file=sys.stderr,
            )
            return -1

        d = cast("SQLiteDatabase", self._d)
        backup_tar, _ = d.backup()
        print(f"{Fore.GREEN}Database backed up to {backup_tar}")
        return 0


class Restore(Command):
    """Restore database from backup."""

    NAME = "restore"
    HELP = "restore database from backup"
    DESCRIPTION = "Restore database from backup"

    def __init__(
        self,
        path_db: Path | str,
        path_password: Path | None,
        tar_ver: int | None,
        *,
        list_ver: bool,
    ) -> None:
        """Initialize restore command.

        Args:
            path_db: Path to Database DB or postgres connection URL
            path_password: Path to password file, None will prompt when necessary
            tar_ver: Backup tar version to restore from, None will restore latest
            list_ver: True will list backups available, False will restore

        """
        super().__init__(path_db, path_password, do_unlock=False)
        self._tar_ver = tar_ver
        self._list_ver = list_ver

    @override
    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-v",
            dest="tar_ver",
            metavar="VERSION",
            type=int,
            help="number of backup to use for restore, omit for latest",
        )
        parser.add_argument(
            "-l",
            "--list",
            dest="list_ver",
            default=False,
            action="store_true",
            help="list available backups",
        )

    @override
    def run(self) -> int:
        # Defer for faster time to main
        from flask_htmx_template import database
        from flask_htmx_template import sql as sql_mod
        from flask_htmx_template import utils

        if sql_mod.is_postgres_url(str(self._path_db)):
            print(
                f"{Fore.RED}restore is not supported for postgres databases",
                file=sys.stderr,
            )
            return -1

        try:
            if self._list_ver:
                backups = database.SQLiteDatabase.backups(self._path_db)
                if len(backups) == 0:
                    print(
                        f"{Fore.RED}No backups found, run 'flask_htmx_template backup'",
                        file=sys.stderr,
                    )
                    return 0
                now = datetime.datetime.now(datetime.UTC)
                for ver, ts in backups:
                    ago_s = (now - ts).total_seconds()
                    ago = utils.format_seconds(ago_s)

                    # Convert ts utc to local timezone
                    ts_local = ts.astimezone().isoformat(timespec="seconds")
                    print(
                        f"{Fore.CYAN}Backup #{ver:2} created at {ts_local} ({ago} ago)",
                    )
                return 0
            database.SQLiteDatabase.restore(self._path_db, tar_ver=self._tar_ver)
            print(f"{Fore.CYAN}Extracted backup tar")
        except FileNotFoundError as e:
            print(f"{Fore.RED}{e}", file=sys.stderr)
            return -1
        print(f"{Fore.GREEN}Database restored for {self._path_db}")
        return 0

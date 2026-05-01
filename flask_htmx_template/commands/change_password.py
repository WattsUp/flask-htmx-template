"""Change database password."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast, override

from colorama import Fore

from flask_htmx_template.commands.base import Command, confirm, get_password


class ChangePassword(Command):
    """Change database password."""

    NAME = "change-password"
    HELP = "change database password"
    DESCRIPTION = "Change database and/or web password"

    def __init__(
        self,
        path_db: Path | str,
        path_password: Path | None,
        path_password_new: Path | None,
    ) -> None:
        """Initialize create command.

        Args:
            path_db: Path to Database DB or postgres connection URL
            path_password: Path to password file, None will prompt when necessary
            path_password_new: Path to new password file,
                None will prompt when necessary

        """
        super().__init__(path_db, path_password)
        self._path_password_new = path_password_new

    @override
    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--new-pass-file",
            dest="path_password_new",
            metavar="PATH",
            type=Path,
            help=argparse.SUPPRESS,
        )

    @override
    def run(self) -> int:
        # Defer for faster time to main
        from flask_htmx_template import database

        if self._d.is_postgres:
            print(
                f"{Fore.RED}change-password is not supported for postgres databases",
                file=sys.stderr,
            )
            return -1

        d = cast("database.SQLiteDatabase", self._d)

        new_db_key, new_web_key = self._get_keys()
        if new_db_key is None and new_web_key is None:
            print(f"{Fore.YELLOW}Neither password changing", file=sys.stderr)
            return -1

        # Back up Database
        _, tar_ver = d.backup()
        try:
            if new_db_key is not None:
                d.change_key(new_db_key)

            if new_web_key is not None:
                d.change_web_key(new_web_key)
        except Exception:  # pragma: no cover
            # No immediate exception thrown, can't easily test
            database.SQLiteDatabase.restore(d, tar_ver=tar_ver)
            print(f"{Fore.RED}Abandoned password change, restored from backup")
            raise
        print(f"{Fore.GREEN}Changed password(s)")
        print(
            f"{Fore.CYAN}Run 'flask_htmx_template clean' "
            "to remove backups with old password",
        )
        return 0

    def _get_keys(self) -> tuple[str | None, str | None]:
        if self._path_password_new:
            with self._path_password_new.open("r", encoding="utf-8") as file:
                new_db_key = file.readline().split(":", 1)[-1].strip() or None
                new_web_key = file.readline().split(":", 1)[-1].strip() or None
            return new_db_key, new_web_key

        from flask_htmx_template import utils

        new_db_key: str | None = None
        new_web_key: str | None = None
        if confirm("Change database password?"):
            new_db_key = get_password(utils.MIN_PASS_LEN)
            if new_db_key is None:
                # Canceled
                return None, None

        if (self._d.is_encrypted or new_db_key is not None) and confirm(
            "Change web password?",
        ):
            new_web_key = get_password(utils.MIN_PASS_LEN)
            if new_web_key is None:
                # Canceled
                return None, None

        return new_db_key, new_web_key

"""Base command interface."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import colorama
from colorama import Fore

if TYPE_CHECKING:
    import argparse

    from flask_htmx_template.database import Database


class Command(ABC):
    """Base command interface."""

    NAME: str = ""
    HELP: str = ""
    DESCRIPTION: str = ""

    def __init__(
        self,
        path_db: Path | str,
        *,
        do_unlock: bool = True,
        check_migration: bool = True,
    ) -> None:
        """Initialize base command.

        Args:
            path_db: Path to DB or postgres connection URL
            do_unlock: True will unlock database, False will not
            check_migration: True will check if migration is required

        """
        super().__init__()
        colorama.init(autoreset=True)

        # Defer for faster time to main
        from flask_htmx_template import exceptions as exc
        from flask_htmx_template import sql

        if sql.is_postgres_url(str(path_db)):
            self._path_db: Path | str = sql.normalize_postgres_url(str(path_db))
        else:
            self._path_db = Path(path_db).expanduser().absolute()

        if not do_unlock:
            return

        if isinstance(self._path_db, Path) and not self._path_db.exists():
            print(
                f"{Fore.RED}Database does not exist at {self._path_db}. "
                "Run flask_htmx_template create",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            self._d = self._unlock(
                self._path_db,
                check_migration=check_migration,
            )
        except exc.MigrationRequiredError as e:
            print(f"{Fore.RED}{e}", file=sys.stderr)
            print(
                f"{Fore.YELLOW}Run 'flask_htmx_template migrate' to resolve",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print(f"{Fore.GREEN}Database is unlocked")

    @classmethod
    @abstractmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        """Set up subparser for this command.

        Args:
            parser: Subparser to add args to

        """
        raise NotImplementedError

    @abstractmethod
    def run(self) -> int:
        """Run command.

        Returns:
            0 on success
            non-zero on failure

        """
        raise NotImplementedError

    @classmethod
    def _unlock(
        cls,
        path_db: Path | str,
        *,
        check_migration: bool = True,
    ) -> Database:
        """Unlock an existing Database.

        Args:
            path_db: Path to Database DB to unlock, or postgres connection URL
            check_migration: True will check if migration is required

        Returns:
            Unlocked Database

        """
        # defer for faster time to main
        from flask_htmx_template import database, sql

        if sql.is_postgres_url(str(path_db)):
            return database.PostgresDatabase(
                path_db,
                check_migration=check_migration,
            )

        return database.SQLiteDatabase(
            path_db,
            check_migration=check_migration,
        )


def get_password(min_len: int) -> str | None:
    """Get password from user input with confirmation.

    Args:
        min_len: Minimum length of password

    Returns:
        Password or None if canceled.

    """
    key: str | None = None
    while key is None:
        key = get_input("Please enter password: ", secure=True)
        if key is None:
            return None

        if len(key) < min_len:
            print(
                f"{Fore.RED}Password must be at least {min_len} characters",
            )
            key = None
            continue

        repeat = get_input("Please confirm password: ", secure=True)
        if repeat is None:
            return None

        if key != repeat:
            print(f"{Fore.RED}Passwords must match")
            key = None

    return key


def confirm(
    prompt: str | None = None,
    *,
    default: bool | None = False,
) -> bool | None:
    """Prompt user for yes/no confirmation.

    Args:
        prompt: string to print to user
        default: default response if only [Enter] is pressed

    Returns:
        bool True for yes, False for no

    """
    prompt = prompt or "Confirm"
    prompt += " [Y/n]: " if default else " [y/N]: "

    while True:
        input_ = (input(prompt) or "").lower()
        if not input_:
            return default
        if input_ == "y":
            return True
        if input_ == "n":
            return False
        print("\nPlease enter y or n.\n")


def get_input(
    prompt: str = "",
    *,
    secure: bool = False,
    print_key: bool | None = None,
) -> str | None:
    """Get input from the user, optionally secure.

    Args:
        prompt: string to print to user
        secure: True will prompt for a password
        print_key: True will print key symbol, False will not, None will check
            stdout.encoding

    Returns:
        str String entered by user, None if canceled

    """
    # defer for faster time to main
    import getpass

    if secure:
        secure_icon = "\u26bf"
        to_print = (
            f"{secure_icon}  {prompt}"
            if print_key is True
            or (
                print_key is None
                and sys.stdout.encoding
                and sys.stdout.encoding.lower().startswith("utf-")
            )
            else prompt
        )

        try:
            return getpass.getpass(to_print)
        except (KeyboardInterrupt, EOFError):
            return None

    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError):
        return None

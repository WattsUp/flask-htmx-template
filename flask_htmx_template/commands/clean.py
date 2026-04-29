"""Clean and optimize a database."""

from __future__ import annotations

import sys
from typing import cast, override, TYPE_CHECKING

from colorama import Fore

from flask_htmx_template.commands.base import Command

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

    from flask_htmx_template.database import SQLiteDatabase


class Clean(Command):
    """Clean database."""

    NAME = "clean"
    HELP = "clean database folder"
    DESCRIPTION = "Delete unused database files"

    def __init__(
        self,
        path_db: Path | str,
        path_password: Path | None,
    ) -> None:
        """Initialize clean command.

        Args:
            path_db: Path to Database DB or postgres connection URL
            path_password: Path to password file, None will prompt when necessary

        """
        super().__init__(path_db, path_password)

    @override
    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        # No arguments
        _ = parser

    @override
    def run(self) -> int:
        if self._d.is_postgres:
            print(
                f"{Fore.RED}clean is not supported for postgres databases",
                file=sys.stderr,
            )
            return -1

        d = cast("SQLiteDatabase", self._d)
        size_before, size_after = d.clean()
        print(f"{Fore.GREEN}Database cleaned")
        p_change = size_before - size_after
        print(
            f"{Fore.CYAN}Database was optimized by "
            f"{p_change / 1000:,.1f}KB/{p_change / 1024:,.1f}KiB",
        )

        return 0

"""Clean and optimize a database."""

from __future__ import annotations

from typing import override, TYPE_CHECKING

from colorama import Fore

from flask_htmx_template.commands.base import Command

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


class Clean(Command):
    """Clean database."""

    NAME = "clean"
    HELP = "clean database folder"
    DESCRIPTION = "Delete unused database files"

    def __init__(
        self,
        path_db: Path,
        path_password: Path | None,
    ) -> None:
        """Initialize clean command.

        Args:
            path_db: Path to Database DB
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
        size_before, size_after = self._d.clean()
        print(f"{Fore.GREEN}Database cleaned")
        p_change = size_before - size_after
        print(
            f"{Fore.CYAN}Database was optimized by "
            f"{p_change / 1000:,.1f}KB/{p_change / 1024:,.1f}KiB",
        )

        return 0

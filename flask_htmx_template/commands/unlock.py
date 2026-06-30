"""Unlock a database command."""

from __future__ import annotations

from typing import override, TYPE_CHECKING

from flask_htmx_template.commands.base import Command

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


class Unlock(Command):
    """Test unlocking database."""

    NAME = "unlock"
    HELP = "test unlocking database"
    DESCRIPTION = "Test unlocking database"

    def __init__(
        self,
        path_db: Path | str,
    ) -> None:
        """Initialize unlock command.

        Args:
            path_db: Path to Database DB or postgres connection URL

        """
        super().__init__(path_db)

    @override
    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        # No arguments
        _ = parser

    @override
    def run(self) -> int:
        return 0

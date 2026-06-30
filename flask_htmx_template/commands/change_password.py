"""Change web key command."""

from __future__ import annotations

from typing import override, TYPE_CHECKING

from colorama import Fore

from flask_htmx_template.commands.base import Command, get_password

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


class ChangePassword(Command):
    """Change the web key."""

    NAME = "change-password"
    HELP = "change web key"
    DESCRIPTION = "Change the web key used for authentication"

    def __init__(
        self,
        path_db: Path | str,
        new_pass: str | None,
    ) -> None:
        """Initialize change-password command.

        Args:
            path_db: Path to Database DB or postgres connection URL
            new_pass: New web key value

        """
        super().__init__(path_db)
        self._new_pass = new_pass

    @override
    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--new-pass",
            metavar="PASSWORD",
            help="new web key",
        )

    @override
    def run(self) -> int:
        # Defer for faster time to main
        from flask_htmx_template import utils

        new_web_key = self._new_pass or get_password(utils.MIN_PASS_LEN)
        if new_web_key is None:
            print(f"{Fore.RED}Aborted change password")
            return -1

        self._d.change_web_key(new_web_key)
        print(f"{Fore.GREEN}Changed password(s)")
        print(
            f"{Fore.CYAN}Run 'flask_htmx_template clean' "
            "to remove backups with old password",
        )
        return 0

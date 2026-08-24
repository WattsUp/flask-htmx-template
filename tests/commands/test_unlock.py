from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from flask_htmx_template.commands.unlock import Unlock

if TYPE_CHECKING:
    import pytest

    from flask_htmx_template.database import SQLiteDatabase


def test_empty(
    capsys: pytest.CaptureFixture[str],
    empty_database: SQLiteDatabase,
) -> None:

    c = Unlock(empty_database.path)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = "Database is unlocked\n"
    assert captured.out == target
    assert not captured.err


def test_setup_args() -> None:
    parser = argparse.ArgumentParser()

    Unlock.setup_args(parser)

    assert vars(parser.parse_args([])) == {}

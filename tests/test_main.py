from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import main, version

if TYPE_CHECKING:
    from flask_htmx_template.database import SQLiteDatabase


def test_entrypoints() -> None:
    # Check can execute entrypoint
    path = Path(sys.executable).with_name("flask_htmx_template")
    with subprocess.Popen(  # noqa: S603
        [str(path), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    ) as process:
        stdout, stderr = process.communicate()
        stdout = stdout.decode().strip("\r\n").strip("\n")
        stderr = stderr.decode().strip("\r\n").strip("\n")
        assert not stderr
        assert stdout == version.__version__


def test_unlock_non_existant(empty_database: SQLiteDatabase) -> None:
    # Try unlocking non-existent Database
    args = [
        "--database",
        str(empty_database.path.with_suffix(".non-existent")),
        "unlock",
    ]
    with pytest.raises(SystemExit):
        main.main(args)


def test_unlock_successful(
    capsys: pytest.CaptureFixture[str],
    empty_database: SQLiteDatabase,
) -> None:
    args = ["--database", str(empty_database.path), "unlock"]
    assert main.main(args) == 0
    assert capsys.readouterr().out == "Database is unlocked\n"

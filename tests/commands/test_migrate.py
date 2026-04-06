from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from flask_htmx_template.commands.migrate import Migrate

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from flask_htmx_template.database import Database


def test_not_required(
    capsys: pytest.CaptureFixture[str],
    empty_database: Database,
) -> None:

    c = Migrate(empty_database.path, None)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = "Database is unlocked\nDatabase does not need migration\n"
    assert captured.out == target
    assert not captured.err


def test_v0_1_migration(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    data_path: Path,
) -> None:
    path = tmp_path / "database.db"
    shutil.copyfile(data_path / "old_versions" / "v0.0.0.db", path)

    c = Migrate(path, None)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = (
        "Database is unlocked\n"
        "Created Item table\n"
        "Database migrated to v0.1.0\n"
        "Database model schemas updated\n"
    )
    assert captured.out == target
    assert not captured.err

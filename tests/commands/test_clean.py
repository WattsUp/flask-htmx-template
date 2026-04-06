from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template.commands.clean import Clean

if TYPE_CHECKING:
    import pytest

    from flask_htmx_template.database import Database


def test_clean(capsys: pytest.CaptureFixture[str], empty_database: Database) -> None:
    c = Clean(empty_database.path, None)
    assert c.run() == 0

    path_backup = empty_database.path.with_suffix(".backup1.tar")
    assert path_backup.exists()

    captured = capsys.readouterr()
    target = (
        "Database is unlocked\n"
        "Database cleaned\n"
        "Database was optimized by 0.0KB/0.0KiB\n"
    )
    assert captured.out == target
    assert not captured.err

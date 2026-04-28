from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template.commands.clean import Clean

if TYPE_CHECKING:
    import pytest

    from flask_htmx_template.database import Database
    from tests.conftest import PostgresDatabaseGenerator


def test_clean(capsys: pytest.CaptureFixture[str], empty_database: Database) -> None:
    c = Clean(empty_database.path, None)
    assert c.run() == 0

    path_backup = empty_database.path.with_suffix(".backup1.tar")
    assert path_backup.exists()

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    assert lines[0] == "Database is unlocked"
    assert lines[1] == "Database cleaned"
    assert lines[2].startswith("Database was optimized by ")
    assert len(lines) == 3
    assert not captured.err


def test_clean_postgres(
    capsys: pytest.CaptureFixture[str],
    postgres_database_generator: PostgresDatabaseGenerator,
) -> None:
    """Clean.run() returns -1 for postgres databases."""
    postgres_database_generator()
    c = Clean(postgres_database_generator.url, None)
    assert c.run() == -1

    captured = capsys.readouterr()
    assert "Database is unlocked" in captured.out
    assert "clean is not supported for postgres databases" in captured.err

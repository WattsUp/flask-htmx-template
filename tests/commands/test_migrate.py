from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from flask_htmx_template.commands.migrate import Migrate
from flask_htmx_template.database import SQLiteDatabase
from flask_htmx_template.models.applied_migration import AppliedMigration

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from tests.conftest import PostgresDatabaseGenerator


def test_not_required(
    capsys: pytest.CaptureFixture[str],
    empty_database: SQLiteDatabase,
) -> None:
    c = Migrate(empty_database.path)
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

    c = Migrate(path)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = (
        "Database is unlocked\n"
        "Created Item table\n"
        "Database migrated: CreateItemTable\n"
        "Database migrated: AddWebThemeConfig\n"
        "Database migrated: AddAPIBearerToken\n"
        "Migrated config\n"
        "Database model schemas updated\n"
    )
    assert captured.out == target
    assert not captured.err


def test_no_schema_updates(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:

    path = tmp_path / "database.db"
    d = SQLiteDatabase.create(path)

    # Remove AddWebThemeConfig so it re-runs; it has no pending_schema_updates
    with d.begin_session():
        AppliedMigration.query().filter_by(name="AddWebThemeConfig").delete()

    c = Migrate(path)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = "Database is unlocked\nDatabase migrated: AddWebThemeConfig\n"
    assert captured.out == target
    assert not captured.err


def test_migrate_postgres(
    capsys: pytest.CaptureFixture[str],
    postgres_database_generator: PostgresDatabaseGenerator,
) -> None:
    postgres_database_generator()
    c = Migrate(postgres_database_generator.url)
    assert c.run() == 0

    captured = capsys.readouterr()
    assert "Database is unlocked" in captured.out
    assert not captured.err

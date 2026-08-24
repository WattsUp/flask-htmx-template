from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql
from flask_htmx_template.database import SQLiteDatabase
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from pathlib import Path


def test_non_existant(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        SQLiteDatabase(path)


def test_postgres_url_rejected() -> None:
    with pytest.raises(exc.UnlockingError):
        SQLiteDatabase("postgresql://user:pass@host/db")


def test_corrupted(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    path.write_bytes(b"fake")
    with pytest.raises(exc.UnlockingError):
        SQLiteDatabase(path)


def test_already_exists(tmp_path: Path) -> None:
    path = tmp_path / "database.db"
    path.touch()
    with pytest.raises(FileExistsError):
        SQLiteDatabase.create(path)


def test_create(tmp_path: Path) -> None:
    path = tmp_path / "database.db"
    d = SQLiteDatabase.create(path)

    assert path.exists()
    assert d.path == path

    with d.begin_session():
        assert sql.count(Config.query()) == len(ConfigKey)


def test_sqlite_database_kind(empty_database: SQLiteDatabase) -> None:
    assert not empty_database.is_postgres


def test_migration_required(tmp_path: Path, data_path: Path) -> None:
    path_original = data_path / "old_versions" / "v0.0.0.db"
    path_db = tmp_path / "database.v0.1.db"
    shutil.copyfile(path_original, path_db)

    with pytest.raises(exc.MigrationRequiredError):
        SQLiteDatabase(path_db)


@pytest.mark.parametrize(
    "key",
    [
        ConfigKey.CIPHER,
        ConfigKey.VERSION,
    ],
)
def test_no_required_config(
    empty_database: SQLiteDatabase,
    key: ConfigKey,
) -> None:
    with empty_database.begin_session():
        Config.query().where(Config.key == key).delete()

    with pytest.raises(exc.ProtectedObjectNotFoundError):
        SQLiteDatabase(empty_database.path)

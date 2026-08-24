from __future__ import annotations

import argparse
import sys
from typing import override, TYPE_CHECKING

from flask_htmx_template.commands.create import Create
from flask_htmx_template.database import SQLiteDatabase

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from tests.conftest import PostgresDatabaseGenerator


class MockDatabase(SQLiteDatabase):
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    # Creating takes a long time so mock actual function
    @override
    @classmethod
    def create(cls, path: str | Path) -> MockDatabase:
        print(f"Creating {path}", file=sys.stderr)
        return MockDatabase()


def test_create_existing(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    path = tmp_path / "new.db"
    path.touch()

    c = Create(path, force=False)
    assert c.run() != 0

    captured = capsys.readouterr()
    assert not captured.out
    target = f"Cannot overwrite database at {path}. Try with --force\n"
    assert captured.err == target


def test_create_forced(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "new.db"
    path.touch()
    monkeypatch.setattr("flask_htmx_template.database.SQLiteDatabase", MockDatabase)

    c = Create(path, force=True)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = f"Database created at {path}\n"
    assert captured.out == target
    target = f"Creating {path}\n"
    assert captured.err == target


def test_create(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "new.db"
    monkeypatch.setattr("flask_htmx_template.database.SQLiteDatabase", MockDatabase)

    c = Create(path, force=False)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = f"Database created at {path}\n"
    assert captured.out == target
    target = f"Creating {path}\n"
    assert captured.err == target


def test_create_postgres(
    capsys: pytest.CaptureFixture[str],
    postgres_database_generator: PostgresDatabaseGenerator,
) -> None:
    postgres_database_generator.drop()
    c = Create(postgres_database_generator.url, force=False)
    assert c.run() == 0


def test_create_postgres_already_exists(
    capsys: pytest.CaptureFixture[str],
    postgres_database_generator: PostgresDatabaseGenerator,
) -> None:
    postgres_database_generator()
    c = Create(postgres_database_generator.url, force=False)
    assert c.run() == -1

    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err  # FileExistsError message


def test_create_postgres_force(
    capsys: pytest.CaptureFixture[str],
    postgres_database_generator: PostgresDatabaseGenerator,
) -> None:
    postgres_database_generator()
    c = Create(postgres_database_generator.url, force=True)
    assert c.run() == -1

    captured = capsys.readouterr()
    assert not captured.out
    assert "--force is not supported for postgres databases" in captured.err


def test_setup_args() -> None:
    parser = argparse.ArgumentParser()

    Create.setup_args(parser)

    args = parser.parse_args(["--force"])
    assert args.force

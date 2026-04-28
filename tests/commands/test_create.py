from __future__ import annotations

import sys
from typing import override, TYPE_CHECKING

from flask_htmx_template.commands.create import Create
from flask_htmx_template.database import Database

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from tests.conftest import PostgresDatabaseGenerator


class MockDatabase(Database):

    def __init__(self) -> None:
        pass

    # Creating takes a long time so mock actual function
    @override
    @classmethod
    def create(cls, path: str | Path, key: str | None = None) -> Database:
        print(f"Creating {path} with {key}", file=sys.stderr)
        return MockDatabase()


def test_create_existing(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    path = tmp_path / "new.db"
    path.touch()

    c = Create(path, None, force=False, no_encrypt=True)
    assert c.run() != 0

    captured = capsys.readouterr()
    assert not captured.out
    target = f"Cannot overwrite database at {path}. Try with --force\n"
    assert captured.err == target


def test_create_unencrypted_forced(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "new.db"
    path.touch()
    monkeypatch.setattr("flask_htmx_template.database.Database", MockDatabase)

    c = Create(path, None, force=True, no_encrypt=True)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = f"Database created at {path}\n"
    assert captured.out == target
    target = f"Creating {path} with None\n"
    assert captured.err == target


def test_create_unencrypted(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "new.db"
    monkeypatch.setattr("flask_htmx_template.database.Database", MockDatabase)

    c = Create(path, None, force=False, no_encrypt=True)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = f"Database created at {path}\n"
    assert captured.out == target
    target = f"Creating {path} with None\n"
    assert captured.err == target


def test_create_encrypted(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rand_str: str,
) -> None:
    path = tmp_path / "new.db"
    monkeypatch.setattr("flask_htmx_template.database.Database", MockDatabase)

    queue = [rand_str, rand_str]

    def mock_get_pass(_: str) -> str | None:
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", mock_get_pass)
    monkeypatch.setattr("getpass.getpass", mock_get_pass)

    c = Create(path, None, force=False, no_encrypt=False)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = f"Database created at {path}\n"
    assert captured.out == target
    target = f"Creating {path} with {rand_str}\n"
    assert captured.err == target


def test_create_encrypted_pass_file(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rand_str: str,
) -> None:
    path = tmp_path / "new.db"
    monkeypatch.setattr("flask_htmx_template.database.Database", MockDatabase)

    path_password = tmp_path / "password.secret"
    path_password.write_text(rand_str, "utf-8")

    c = Create(path, path_password, force=False, no_encrypt=False)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = f"Database created at {path}\n"
    assert captured.out == target
    target = f"Creating {path} with {rand_str}\n"
    assert captured.err == target


def test_create_encrypted_cancelled(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "new.db"
    monkeypatch.setattr("flask_htmx_template.database.Database", MockDatabase)

    queue = [None]

    def mock_get_pass(_: str) -> str | None:
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", mock_get_pass)
    monkeypatch.setattr("getpass.getpass", mock_get_pass)

    c = Create(path, None, force=False, no_encrypt=False)
    assert c.run() != 0

    captured = capsys.readouterr()
    assert not captured.out
    assert not captured.err


def test_create_postgres(
    capsys: pytest.CaptureFixture[str],
    postgres_database_generator: PostgresDatabaseGenerator,
) -> None:
    """Create.run() initializes a postgres database and returns 0."""
    postgres_database_generator.drop()
    c = Create(postgres_database_generator.url, None, force=False, no_encrypt=False)
    assert c.run() == 0

    captured = capsys.readouterr()
    assert f"Postgres database initialized at {c._path_db}" in captured.out
    assert not captured.err


def test_create_postgres_already_exists(
    capsys: pytest.CaptureFixture[str],
    postgres_database_generator: PostgresDatabaseGenerator,
) -> None:
    """Create.run() returns -1 when postgres database is already initialized."""
    postgres_database_generator()
    c = Create(postgres_database_generator.url, None, force=False, no_encrypt=False)
    assert c.run() == -1

    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err  # FileExistsError message


def test_create_postgres_force(
    capsys: pytest.CaptureFixture[str],
    postgres_database_generator: PostgresDatabaseGenerator,
) -> None:
    """Create.run() returns -1 with error when --force used with postgres."""
    postgres_database_generator()
    c = Create(postgres_database_generator.url, None, force=True, no_encrypt=False)
    assert c.run() == -1

    captured = capsys.readouterr()
    assert not captured.out
    assert "--force is not supported for postgres databases" in captured.err

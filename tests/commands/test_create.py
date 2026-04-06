from __future__ import annotations

import sys
from typing import override, TYPE_CHECKING

from flask_htmx_template.commands.create import Create
from flask_htmx_template.database import Database

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


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

from __future__ import annotations

import argparse
import sys
from typing import override, TYPE_CHECKING

import pytest

from flask_htmx_template.commands.backup import Backup, Restore
from flask_htmx_template.commands.base import Command
from flask_htmx_template.commands.change_password import ChangePassword
from flask_htmx_template.commands.clean import Clean
from flask_htmx_template.commands.create import Create
from flask_htmx_template.commands.migrate import Migrate
from flask_htmx_template.commands.unlock import Unlock
from flask_htmx_template.encryption.top import ENCRYPTION_AVAILABLE
from flask_htmx_template.migrations.top import MIGRATORS

if TYPE_CHECKING:
    from pathlib import Path

    from flask_htmx_template.database import Database
    from tests.conftest import PostgresDatabaseGenerator


class MockCommand(Command):

    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        pass

    @override
    def run(self) -> int:
        return 0


def test_no_unlock(tmp_path: Path) -> None:
    MockCommand(tmp_path / "fake.db", None, do_unlock=False)


def test_no_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "fake.db"
    with pytest.raises(SystemExit):
        MockCommand(path, None)

    captured = capsys.readouterr()
    assert not captured.out
    target = f"Database does not exist at {path}. Run flask_htmx_template create\n"
    assert captured.err == target


def test_unlock(capsys: pytest.CaptureFixture[str], empty_database: Database) -> None:
    MockCommand(empty_database.path, None)

    captured = capsys.readouterr()
    target = "Database is unlocked\n"
    assert captured.out == target
    assert not captured.err


def test_migration_required(
    capsys: pytest.CaptureFixture[str],
    data_path: Path,
) -> None:
    with pytest.raises(SystemExit):
        MockCommand(data_path / "old_versions" / "v0.0.0.db", None)

    captured = capsys.readouterr()
    assert not captured.out
    v = MIGRATORS[-1].min_version()
    target = (
        f"Database requires migration to v{v}\n"
        "Run 'flask_htmx_template migrate' to resolve\n"
    )
    assert captured.err == target


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="Encryption is not installed")
@pytest.mark.encryption
def test_unlock_encrypted_path(
    capsys: pytest.CaptureFixture[str],
    empty_database_encrypted: tuple[Database, str],
    tmp_path: Path,
) -> None:
    d, key = empty_database_encrypted
    path_password = tmp_path / "password.secret"
    path_password.write_text(key, "utf-8")

    MockCommand(d.path, path_password)

    captured = capsys.readouterr()
    target = "Database is unlocked\n"
    assert captured.out == target
    assert not captured.err


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="Encryption is not installed")
@pytest.mark.encryption
def test_unlock_encrypted_path_bad_key(
    capsys: pytest.CaptureFixture[str],
    empty_database_encrypted: tuple[Database, str],
    tmp_path: Path,
) -> None:
    d, _ = empty_database_encrypted
    path_password = tmp_path / "password.secret"
    path_password.write_text("not key", "utf-8")

    with pytest.raises(SystemExit):
        MockCommand(d.path, path_password)

    captured = capsys.readouterr()
    assert not captured.out
    target = "Could not decrypt with password file\n"
    assert captured.err == target


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="Encryption is not installed")
@pytest.mark.encryption
def test_unlock_encrypted(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    empty_database_encrypted: tuple[Database, str],
) -> None:
    d, key = empty_database_encrypted
    queue = ["not key", key]

    def mock_get_pass(to_print: str) -> str | None:
        print(to_print, file=sys.stderr)
        return queue.pop(0)

    monkeypatch.setattr("getpass.getpass", mock_get_pass)

    MockCommand(d.path, None)

    captured = capsys.readouterr()
    assert captured.out == "Database is unlocked\n"
    target = (
        "\u26bf  Please enter password: \n"
        "Incorrect password\n"
        "\u26bf  Please enter password: \n"
    )
    assert captured.err == target


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="Encryption is not installed")
@pytest.mark.encryption
def test_unlock_encrypted_cancel(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    empty_database_encrypted: tuple[Database, str],
) -> None:
    d, _ = empty_database_encrypted

    def mock_get_pass(to_print: str) -> str | None:
        print(to_print, file=sys.stderr)
        return None

    monkeypatch.setattr("getpass.getpass", mock_get_pass)

    with pytest.raises(SystemExit):
        MockCommand(d.path, None)

    captured = capsys.readouterr()
    assert not captured.out
    target = "\u26bf  Please enter password: \n"
    assert captured.err == target


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="Encryption is not installed")
@pytest.mark.encryption
def test_unlock_encrypted_failed(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    empty_database_encrypted: tuple[Database, str],
) -> None:
    d, _ = empty_database_encrypted

    def mock_get_pass(to_print: str) -> str | None:
        print(to_print, file=sys.stderr)
        return "not key"

    monkeypatch.setattr("getpass.getpass", mock_get_pass)

    with pytest.raises(SystemExit):
        MockCommand(d.path, None)

    captured = capsys.readouterr()
    assert not captured.out
    target = (
        "\u26bf  Please enter password: \n"
        "Incorrect password\n"
        "\u26bf  Please enter password: \n"
        "Incorrect password\n"
        "\u26bf  Please enter password: \n"
        "Incorrect password\n"
        "Too many incorrect attempts\n"
    )
    assert captured.err == target


@pytest.mark.parametrize(
    ("cmd_class", "extra_args"),
    [
        (Create, []),
        (Unlock, []),
        (Migrate, []),
        (Backup, []),
        (Restore, []),
        (Clean, []),
        (ChangePassword, []),
    ],
)
def test_args(
    empty_database: Database,
    cmd_class: type[Command],
    extra_args: list[str],
) -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest="cmd",
        metavar="<command>",
        required=True,
    )

    sub = subparsers.add_parser(
        cmd_class.NAME,
        help=cmd_class.HELP,
        description=cmd_class.DESCRIPTION,
    )
    cmd_class.setup_args(sub)

    command_line = [cmd_class.NAME, *extra_args]
    args = parser.parse_args(args=command_line)
    args_d = vars(args)
    args_d["path_db"] = empty_database.path
    args_d["path_password"] = None
    cmd: str = args_d.pop("cmd")
    assert cmd == cmd_class.NAME

    # Make sure all args from parse_args are given to constructor
    cmd_class(**args_d)


def test_postgres_url_normalized_in_command(pg_url: str) -> None:
    """Command.__init__ normalizes a postgres URL and stores it as a string."""
    c = MockCommand(pg_url, None, do_unlock=False)
    assert isinstance(c._path_db, str)
    assert c._path_db.startswith("postgresql+psycopg://")


def test_unlock_postgres_with_key(
    postgres_database_generator: PostgresDatabaseGenerator,
    pg_url_no_creds: str,
    pg_key: str,
    tmp_path: Path,
) -> None:
    """_unlock with a key file injects credentials and returns a postgres Database."""
    postgres_database_generator()
    path_key = tmp_path / "key.secret"
    path_key.write_text(pg_key, "utf-8")
    c = MockCommand(pg_url_no_creds, path_key)
    assert c._d.is_postgres

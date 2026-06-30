from __future__ import annotations

import argparse
from typing import override, TYPE_CHECKING

import pytest

from flask_htmx_template import utils
from flask_htmx_template.commands import base
from flask_htmx_template.commands.base import Command, confirm, get_input, get_password
from flask_htmx_template.commands.create import Create
from flask_htmx_template.commands.migrate import Migrate
from flask_htmx_template.commands.unlock import Unlock

if TYPE_CHECKING:
    from pathlib import Path

    from flask_htmx_template.database import SQLiteDatabase
    from tests.conftest import RandomStringGenerator


class MockCommand(Command):

    @classmethod
    def setup_args(cls, parser: argparse.ArgumentParser) -> None:
        pass

    @override
    def run(self) -> int:
        return 0


def test_no_unlock(tmp_path: Path) -> None:
    MockCommand(tmp_path / "fake.db", do_unlock=False)


def test_no_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "fake.db"
    with pytest.raises(SystemExit):
        MockCommand(path)

    captured = capsys.readouterr()
    assert not captured.out
    target = f"Database does not exist at {path}. Run flask_htmx_template create\n"
    assert captured.err == target


def test_unlock(
    capsys: pytest.CaptureFixture[str],
    empty_database: SQLiteDatabase,
) -> None:
    MockCommand(empty_database.path)

    captured = capsys.readouterr()
    target = "Database is unlocked\n"
    assert captured.out == target
    assert not captured.err


def test_migration_required(
    capsys: pytest.CaptureFixture[str],
    data_path: Path,
) -> None:
    with pytest.raises(SystemExit):
        MockCommand(data_path / "old_versions" / "v0.0.0.db")

    captured = capsys.readouterr()
    assert not captured.out
    target = (
        "Database requires migration\nRun 'flask_htmx_template migrate' to resolve\n"
    )
    assert captured.err == target


@pytest.mark.parametrize(
    ("cmd_class", "extra_args"),
    [
        (Create, []),
        (Unlock, []),
        (Migrate, []),
    ],
)
def test_args(
    empty_database: SQLiteDatabase,
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
    cmd: str = args_d.pop("cmd")
    assert cmd == cmd_class.NAME

    # Make sure all args from parse_args are given to constructor
    cmd_class(**args_d)


def test_postgres_url_normalized_in_command(pg_url: str) -> None:
    c = MockCommand(pg_url, do_unlock=False)
    assert isinstance(c._path_db, str)
    assert c._path_db.startswith("postgresql+psycopg://")


def test_get_input_insecure(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str_generator: RandomStringGenerator,
) -> None:
    prompt = rand_str_generator()
    prompt_input = rand_str_generator()

    def mock_input(to_print: str) -> str | None:
        print(to_print + prompt_input)
        return prompt_input

    monkeypatch.setattr("builtins.input", mock_input)
    assert get_input(prompt=prompt, secure=False) == prompt_input
    assert capsys.readouterr().out == prompt + prompt_input + "\n"


def test_get_input_insecure_abort(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str_generator: RandomStringGenerator,
) -> None:
    prompt = rand_str_generator()
    prompt_input = rand_str_generator()

    def mock_input(to_print: str) -> str | None:
        print(to_print + prompt_input)
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", mock_input)
    assert get_input(prompt=prompt, secure=False) is None
    assert capsys.readouterr().out == prompt + prompt_input + "\n"


def test_get_input_secure(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str_generator: RandomStringGenerator,
) -> None:
    prompt = rand_str_generator()
    prompt_input = rand_str_generator()

    def mock_get_pass(to_print: str) -> str | None:
        print(to_print)
        return prompt_input

    monkeypatch.setattr("getpass.getpass", mock_get_pass)
    assert get_input(prompt=prompt, secure=True, print_key=False) == prompt_input
    assert capsys.readouterr().out == prompt + "\n"


def test_get_input_secure_abort(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str: str,
) -> None:
    def mock_get_pass(to_print: str) -> str | None:
        print(to_print)
        raise EOFError

    monkeypatch.setattr("getpass.getpass", mock_get_pass)
    assert get_input(prompt=rand_str, secure=True, print_key=False) is None
    assert capsys.readouterr().out == rand_str + "\n"


def test_get_input_secure_with_icon(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str_generator: RandomStringGenerator,
) -> None:
    prompt = rand_str_generator()
    prompt_input = rand_str_generator()

    def mock_get_pass(to_print: str) -> str | None:
        print(to_print)
        return prompt_input

    monkeypatch.setattr("getpass.getpass", mock_get_pass)
    assert get_input(prompt=prompt, secure=True, print_key=True) == prompt_input
    assert capsys.readouterr().out == "\u26bf  " + prompt + "\n"


@pytest.mark.parametrize(
    ("queue", "target"),
    [
        (["password", "password"], "password"),
        (["short", "password", "typo", "password", "password"], "password"),
        ([None], None),
        (["password", None], None),
    ],
)
def test_get_password(
    monkeypatch: pytest.MonkeyPatch,
    queue: list[str | None],
    target: str,
) -> None:

    def mock_input(to_print: str, *, secure: bool) -> str | None:
        assert secure
        print(to_print)
        return queue.pop(0)

    monkeypatch.setattr(base, "get_input", mock_input)

    assert get_password(utils.MIN_PASS_LEN) == target


@pytest.mark.parametrize(
    ("queue", "default", "target"),
    [
        ([None], False, False),
        ([None], True, True),
        (["Y"], False, True),
        (["N"], False, False),
        (["bad", "y"], False, True),
    ],
)
def test_confirm(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    rand_str: str,
    queue: list[str | None],
    default: bool,
    target: bool | None,
) -> None:
    retries = len(queue) > 1

    def mock_input(to_print: str) -> str | None:
        print(to_print)
        if len(queue) == 1:
            return queue[0]
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", mock_input)
    assert confirm(prompt=rand_str, default=default) == target

    out = capsys.readouterr().out
    assert rand_str in out
    if default:
        assert "[Y/n]" in out
    else:
        assert "[y/N]" in out

    assert ("Please enter y or n" in out) == retries

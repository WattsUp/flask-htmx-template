from __future__ import annotations

import sys
from typing import override, TYPE_CHECKING

import pytest

from flask_htmx_template.commands.change_password import ChangePassword
from flask_htmx_template.database import Database

if TYPE_CHECKING:
    from pathlib import Path


class MockDatabase(Database):

    # Changing password takes a while so mock the actual function
    @override
    def change_key(self, key: str) -> None:
        print(f"Changing key to {key}", file=sys.stderr)

    @override
    def change_web_key(self, key: str) -> None:
        print(f"Changing web key to {key}", file=sys.stderr)


def test_no_change_unencrypted(
    capsys: pytest.CaptureFixture[str],
    empty_database: Database,
    tmp_path: Path,
) -> None:
    path_password_new = tmp_path / "password.secret"
    path_password_new.write_text("db:\nweb:\n", "utf-8")

    c = ChangePassword(empty_database.path, None, path_password_new)
    assert c.run() != 0

    captured = capsys.readouterr()
    assert captured.out == "Database is unlocked\n"
    assert captured.err == "Neither password changing\n"


@pytest.mark.parametrize(
    ("new_db_key", "new_web_key", "target"),
    [
        ("12345678", "", "Changing key to 12345678\n"),
        ("", "01010101", "Changing web key to 01010101\n"),
    ],
)
def test_change(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    empty_database: Database,
    tmp_path: Path,
    new_db_key: str,
    new_web_key: str,
    target: str,
) -> None:
    path_password_new = tmp_path / "password.secret"
    path_password_new.write_text(f"db:{new_db_key}\nweb:{new_web_key}\n", "utf-8")
    monkeypatch.setattr("flask_htmx_template.database.Database", MockDatabase)

    c = ChangePassword(empty_database.path, None, path_password_new)
    assert c.run() == 0

    captured = capsys.readouterr()
    target_out = (
        "Database is unlocked\n"
        "Changed password(s)\n"
        "Run 'flask_htmx_template clean' to remove backups with old password\n"
    )
    assert captured.out == target_out
    assert captured.err == target


@pytest.mark.parametrize(
    ("queue", "target_db", "target_web"),
    [
        (["N"], None, None),
        (["Y", None], None, None),
        (["Y", "12345678", "12345678", "N"], "12345678", None),
        (["Y", "12345678", "12345678", "Y", None], None, None),
        (
            ["Y", "12345678", "12345678", "Y", "01010101", "01010101"],
            "12345678",
            "01010101",
        ),
    ],
)
def test_get_keys_input(
    monkeypatch: pytest.MonkeyPatch,
    empty_database: Database,
    queue: list[str],
    target_db: str | None,
    target_web: str | None,
) -> None:
    def mock_get_pass(_: str) -> str | None:
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", mock_get_pass)
    monkeypatch.setattr("getpass.getpass", mock_get_pass)

    c = ChangePassword(empty_database.path, None, None)
    new_db_key, new_web_key = c._get_keys()

    assert new_db_key == target_db
    assert new_web_key == target_web


def test_get_keys_file(
    empty_database: Database,
    tmp_path: Path,
) -> None:
    path_password_new = tmp_path / "password.secret"
    path_password_new.write_text("db:12345678\nweb:01010101\n", "utf-8")

    c = ChangePassword(empty_database.path, None, path_password_new)
    new_db_key, new_web_key = c._get_keys()

    assert new_db_key == "12345678"
    assert new_web_key == "01010101"

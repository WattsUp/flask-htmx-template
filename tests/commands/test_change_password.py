from __future__ import annotations

import sys
from typing import override, TYPE_CHECKING

import flask_htmx_template.commands.change_password as change_password_module
from flask_htmx_template.commands.change_password import ChangePassword
from flask_htmx_template.database import SQLiteDatabase

if TYPE_CHECKING:
    import pytest


class MockDatabase(SQLiteDatabase):
    @override
    def change_web_key(self, key: str) -> None:
        print(f"Changing web key to {key}", file=sys.stderr)


def test_change(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    empty_database: SQLiteDatabase,
) -> None:
    monkeypatch.setattr(
        "flask_htmx_template.database.SQLiteDatabase",
        MockDatabase,
    )

    c = ChangePassword(empty_database.path, "01010101")
    assert c.run() == 0

    captured = capsys.readouterr()
    target_out = (
        "Database is unlocked\n"
        "Changed password(s)\n"
        "Run 'flask_htmx_template clean' to remove backups with old password\n"
    )
    assert captured.out == target_out
    assert captured.err == "Changing web key to 01010101\n"


def test_aborted_when_get_password_returns_none(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    empty_database: SQLiteDatabase,
) -> None:
    def no_password(_: int) -> str | None:
        return None

    monkeypatch.setattr(change_password_module, "get_password", no_password)

    c = ChangePassword(empty_database.path, None)
    assert c.run() == -1

    captured = capsys.readouterr()
    assert "Aborted change password" in captured.out

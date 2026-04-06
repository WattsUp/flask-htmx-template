from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template.commands.backup import Backup, Restore

if TYPE_CHECKING:
    import datetime

    import pytest

    from flask_htmx_template.database import Database


def test_backup(capsys: pytest.CaptureFixture[str], empty_database: Database) -> None:
    c = Backup(empty_database.path, None)
    assert c.run() == 0

    path_backup = empty_database.path.with_suffix(".backup1.tar")
    assert path_backup.exists()

    captured = capsys.readouterr()
    target = f"Database is unlocked\nDatabase backed up to {path_backup}\n"
    assert captured.out == target
    assert not captured.err


def test_restore(
    capsys: pytest.CaptureFixture[str],
    empty_database: Database,
) -> None:
    empty_database.backup()
    c = Restore(empty_database.path, None, tar_ver=None, list_ver=False)
    assert c.run() == 0

    captured = capsys.readouterr()
    target = f"Extracted backup tar\nDatabase restored for {empty_database.path}\n"
    assert captured.out == target
    assert not captured.err


def test_restore_missing(
    capsys: pytest.CaptureFixture[str],
    empty_database: Database,
) -> None:
    c = Restore(empty_database.path, None, tar_ver=None, list_ver=False)
    assert c.run() != 0

    captured = capsys.readouterr()
    assert not captured.out
    target = f"No backup exists for {empty_database.path}\n"
    assert captured.err == target


def test_restore_list_empty(
    capsys: pytest.CaptureFixture[str],
    empty_database: Database,
) -> None:
    c = Restore(empty_database.path, None, tar_ver=None, list_ver=True)
    assert c.run() == 0

    captured = capsys.readouterr()
    assert not captured.out
    target = "No backups found, run 'flask_htmx_template backup'\n"
    assert captured.err == target


def test_restore_list(
    capsys: pytest.CaptureFixture[str],
    empty_database: Database,
    utc_frozen: datetime.datetime,
) -> None:
    empty_database.backup()
    c = Restore(empty_database.path, None, tar_ver=None, list_ver=True)
    assert c.run() == 0

    ts_local = utc_frozen.astimezone().isoformat(timespec="seconds")

    captured = capsys.readouterr()
    target = f"Backup # 1 created at {ts_local} (0.0 seconds ago)\n"
    assert captured.out == target
    assert not captured.err

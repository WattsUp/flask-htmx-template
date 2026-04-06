from __future__ import annotations

import tarfile
from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template.database import Database
from flask_htmx_template.encryption.top import ENCRYPTION_AVAILABLE
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    import datetime
    from pathlib import Path


def test_backup(utc_frozen: datetime.datetime, empty_database: Database) -> None:
    path_db = empty_database.path
    path_salt = path_db.with_suffix(".nacl")

    path_tar, tar_ver = empty_database.backup()
    assert path_tar.exists()
    assert path_tar.is_file()
    assert path_tar.stat().st_mode & 0o777 == 0o600
    assert tar_ver == 1

    with tarfile.open(path_tar, "r") as tar:
        file = tar.extractfile(path_db.name)
        assert file is not None
        buf_backup = file.read()
        assert buf_backup == path_db.read_bytes()

        file = tar.extractfile("_timestamp")
        assert file is not None
        buf_ts = file.read()
        assert buf_ts == utc_frozen.isoformat().encode()

        assert path_salt.name not in tar.getnames()


def test_backup_second(empty_database: Database) -> None:
    empty_database.backup()
    path_tar, tar_ver = empty_database.backup()
    assert path_tar.exists()
    assert path_tar.is_file()
    assert path_tar.stat().st_mode & 0o777 == 0o600
    assert tar_ver == 2


def test_backups_empty(empty_database: Database) -> None:
    assert not Database.backups(empty_database)


def test_backups(utc_frozen: datetime.datetime, empty_database: Database) -> None:
    empty_database.backup()
    empty_database.backup()
    empty_database.backup()

    target = [(i + 1, utc_frozen) for i in range(3)]
    assert Database.backups(empty_database) == target


def test_backups_no_ts(empty_database: Database) -> None:
    path = empty_database.path.with_suffix(".backup1.tar")
    with tarfile.open(path, "w") as _:
        pass

    with pytest.raises(exc.InvalidBackupTarError):
        Database.backups(empty_database.path)


def test_backups_ts_dir(empty_database: Database) -> None:
    path = empty_database.path.with_suffix(".backup1.tar")
    with tarfile.open(path, "w") as tar:
        info = tarfile.TarInfo("_timestamp")
        info.type = tarfile.DIRTYPE
        tar.addfile(info)

    with pytest.raises(exc.InvalidBackupTarError):
        Database.backups(empty_database.path)


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_backup_encrypted(empty_database_encrypted: tuple[Database, str]) -> None:
    d, _ = empty_database_encrypted
    path_db = d.path
    path_salt = path_db.with_suffix(".nacl")

    path_tar, tar_ver = d.backup()
    assert path_tar.exists()
    assert path_tar.is_file()
    assert path_tar.stat().st_mode & 0o777 == 0o600
    assert tar_ver == 1

    with tarfile.open(path_tar, "r") as tar:
        file = tar.extractfile(path_db.name)
        assert file is not None
        buf_backup = file.read()
        assert buf_backup == path_db.read_bytes()

        assert path_salt.name in tar.getnames()


def test_clean(empty_database: Database) -> None:
    path_1 = empty_database.path.with_suffix(".backup1.tar")
    path_2 = empty_database.path.with_suffix(".backup2.tar")
    path_dir = empty_database.path.with_suffix(".things")
    path_1.touch()
    path_2.touch()
    path_dir.mkdir()
    assert path_1.stat().st_size == 0

    size_b = empty_database.clean()
    assert size_b[0] == empty_database.path.stat().st_size
    assert size_b[0] >= size_b[1]

    assert path_1.exists()
    assert path_1.stat().st_size > 0
    assert not path_2.exists()
    assert not path_dir.exists()


def test_restore_non_existant(tmp_path: Path) -> None:
    path = tmp_path / "database.db"
    with pytest.raises(FileNotFoundError):
        Database.restore(path)


def test_restore_no_ts(tmp_path: Path) -> None:
    path = tmp_path / "database.db"
    path_tar = path.with_suffix(".backup1.tar")
    with tarfile.open(path_tar, "w") as _:
        pass

    with pytest.raises(exc.InvalidBackupTarError):
        Database.restore(path)


def test_restore_path_traversal(tmp_path: Path) -> None:
    path = tmp_path / "database.db"
    path_tar = path.with_suffix(".backup1.tar")
    with tarfile.open(path_tar, "w") as tar:
        info = tarfile.TarInfo("_timestamp")
        tar.addfile(info)
        info = tarfile.TarInfo(path.name)
        tar.addfile(info)

        info = tarfile.TarInfo("../injection.sh")
        tar.addfile(info)

    with pytest.raises(exc.InvalidBackupTarError):
        Database.restore(path)


def test_restore(empty_database: Database) -> None:
    # Delete ENCRYPTION_TEST so reload fails
    with empty_database.begin_session():
        Config.query().where(Config.key == ConfigKey.ENCRYPTION_TEST).delete()
    empty_database.backup()
    empty_database.path.unlink()

    with pytest.raises(exc.ProtectedObjectNotFoundError):
        Database.restore(empty_database)

    assert empty_database.path.exists()


def test_restore_path(empty_database: Database) -> None:
    # Delete ENCRYPTION_TEST so reload fails
    with empty_database.begin_session():
        Config.query().where(Config.key == ConfigKey.ENCRYPTION_TEST).delete()
    empty_database.backup()
    empty_database.path.unlink()

    Database.restore(empty_database.path)

    assert empty_database.path.exists()

    with pytest.raises(exc.ProtectedObjectNotFoundError):
        empty_database._unlock()


def test_restore_version_not_found(empty_database: Database) -> None:
    with pytest.raises(FileNotFoundError):
        Database.restore(empty_database, tar_ver=100)

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql
from flask_htmx_template.database import Database
from flask_htmx_template.encryption.top import ENCRYPTION_AVAILABLE
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from pathlib import Path


def test_non_existant(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        Database(path, None)

    with pytest.raises(FileNotFoundError):
        Database.is_encrypted_path(path)


def test_corrupted(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    path.write_bytes(b"fake")
    with pytest.raises(exc.UnlockingError):
        Database(path, None)


def test_already_exists(tmp_path: Path) -> None:
    path = tmp_path / "database.db"
    path.touch()
    with pytest.raises(FileExistsError):
        Database.create(path)


def test_unencrypted(tmp_path: Path) -> None:
    path = tmp_path / "database.db"
    path_importers = path.with_suffix(".importers")
    path_salt = path.with_suffix(".nacl")
    d = Database.create(path)

    assert path.exists()
    assert path_importers.exists()
    assert path_importers.is_dir()
    assert not path_salt.exists()
    assert d.path == path

    assert not d.is_encrypted
    assert not Database.is_encrypted_path(path)

    with d.begin_session():
        assert sql.count(Config.query()) == 4

    with pytest.raises(exc.NotEncryptedError):
        d.encrypt("")

    with pytest.raises(exc.NotEncryptedError):
        d.decrypt("")

    with pytest.raises(exc.NotEncryptedError):
        d.decrypt_s("")


def test_migration_required(tmp_path: Path, data_path: Path) -> None:
    path_original = data_path / "old_versions" / "v0.0.0.db"
    path_db = tmp_path / "database.v0.1.db"
    shutil.copyfile(path_original, path_db)

    with pytest.raises(exc.MigrationRequiredError):
        Database(path_db, None)


@pytest.mark.parametrize(
    "key",
    [
        ConfigKey.ENCRYPTION_TEST,
        ConfigKey.CIPHER,
        ConfigKey.VERSION,
    ],
)
def test_no_encryption_test(
    empty_database: Database,
    key: ConfigKey,
) -> None:
    with empty_database.begin_session():
        Config.query().where(Config.key == key).delete()

    with pytest.raises(exc.ProtectedObjectNotFoundError):
        Database(empty_database.path, None)


def test_bad_encryption_test(empty_database: Database) -> None:
    with empty_database.begin_session():
        Config.set_(ConfigKey.ENCRYPTION_TEST, "fake")

    with pytest.raises(exc.UnlockingError):
        Database(empty_database.path, None)


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_encrypted(tmp_path: Path, rand_str: str) -> None:
    path = tmp_path / "database.db"
    path_importers = path.with_suffix(".importers")
    path_salt = path.with_suffix(".nacl")
    d = Database.create(path, rand_str)

    assert path.exists()
    assert path_importers.exists()
    assert path_importers.is_dir()
    assert path_salt.exists()
    assert path_salt.is_file()

    assert d.is_encrypted
    assert Database.is_encrypted_path(path)

    with d.begin_session():
        assert sql.count(Config.query()) == 5


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_encrypted_no_salt(
    empty_database_encrypted: tuple[Database, str],
) -> None:
    d, key = empty_database_encrypted
    path_salt = d.path.with_suffix(".nacl")
    path_salt.unlink()

    with pytest.raises(FileNotFoundError):
        Database(d.path, key)


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_encrypted_bad_enc_test(
    empty_database_encrypted: tuple[Database, str],
) -> None:
    d, key = empty_database_encrypted
    with d.begin_session():
        Config.set_(ConfigKey.ENCRYPTION_TEST, "fake")

    with pytest.raises(exc.UnlockingError):
        Database(d.path, key)


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_encrypt(
    empty_database_encrypted: tuple[Database, str],
    rand_str: str,
) -> None:
    d, _ = empty_database_encrypted
    assert d.decrypt_s(d.encrypt(rand_str)) == rand_str

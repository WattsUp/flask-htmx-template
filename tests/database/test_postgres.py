from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import sqlalchemy.engine

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql
from flask_htmx_template.database import Database, PostgresDatabase

if TYPE_CHECKING:
    from tests.conftest import PostgresDatabaseGenerator

# ---------------------------------------------------------------------------
# sql helper unit tests (no postgres server needed)
# ---------------------------------------------------------------------------


def test_inject_postgres_password() -> None:
    url_str = sql.inject_postgres_password(
        "postgresql://existinguser@host/db",
        "mypass",
    )
    u = sqlalchemy.engine.make_url(url_str)
    assert u.username == "existinguser"
    assert u.password == "mypass"  # noqa: S105


def test_postgres_url_has_password_true() -> None:
    assert sql.postgres_url_has_password("postgresql://u:p@host/db") is True


def test_postgres_url_has_password_false_no_password() -> None:
    assert sql.postgres_url_has_password("postgresql://u@host/db") is False


def test_postgres_url_has_password_false_no_creds() -> None:
    assert sql.postgres_url_has_password("postgresql://host/db") is False


# ---------------------------------------------------------------------------
# Database.create and open
# ---------------------------------------------------------------------------


def test_create_with_url(postgres_database: PostgresDatabase) -> None:
    assert postgres_database.is_postgres


def test_create_with_key_injection(
    postgres_database_generator: PostgresDatabaseGenerator,
    pg_url_no_password: str,
    pg_key: str,
) -> None:
    postgres_database_generator.drop()
    d = PostgresDatabase.create(pg_url_no_password, pg_key)
    assert d.is_postgres


def test_open_with_url(postgres_database: PostgresDatabase, pg_url: str) -> None:
    d = PostgresDatabase(pg_url, None)
    assert d.is_postgres


def test_open_with_key(
    postgres_database: PostgresDatabase,  # ensures DB exists
    pg_url_no_password: str,
    pg_key: str,
) -> None:
    d = PostgresDatabase(pg_url_no_password, pg_key)
    assert d.is_postgres


def test_create_already_initialized(
    postgres_database: PostgresDatabase,
    pg_url: str,
) -> None:
    with pytest.raises(FileExistsError):
        PostgresDatabase.create(pg_url)


# ---------------------------------------------------------------------------
# NotImplementedError for SQLite-only operations
# ---------------------------------------------------------------------------


def test_no_path_attribute(postgres_database: PostgresDatabase) -> None:
    assert not hasattr(postgres_database, "path")


def test_no_path_salt_attribute(postgres_database: PostgresDatabase) -> None:
    assert not hasattr(postgres_database, "path_salt")


def test_is_encrypted_false(postgres_database: PostgresDatabase) -> None:
    assert postgres_database.is_encrypted is False


def test_is_encrypted_path_false(pg_url: str) -> None:
    assert Database.is_encrypted_path(pg_url) is False


# ---------------------------------------------------------------------------
# Backup / restore / clean / change_key not available on postgres
# ---------------------------------------------------------------------------


def test_no_backup_method(postgres_database: PostgresDatabase) -> None:
    assert not hasattr(postgres_database, "backup")


def test_no_backups_method(postgres_database: PostgresDatabase) -> None:
    assert not hasattr(postgres_database, "backups")


def test_no_clean_method(postgres_database: PostgresDatabase) -> None:
    assert not hasattr(postgres_database, "clean")


def test_no_restore_method(postgres_database: PostgresDatabase) -> None:
    assert not hasattr(postgres_database, "restore")


def test_no_change_key_method(postgres_database: PostgresDatabase) -> None:
    assert not hasattr(postgres_database, "change_key")


def test_dispose(postgres_database: PostgresDatabase) -> None:
    postgres_database.dispose()


def test_str(postgres_database: PostgresDatabase, pg_url: str) -> None:
    normalized = sql.normalize_postgres_url(pg_url)
    assert str(postgres_database) == f"<PostgresDatabase@{normalized}>"


def test_file_path_rejected(pg_url: str) -> None:
    with pytest.raises(exc.UnlockingError):
        PostgresDatabase("/tmp/not_a_postgres_url.db", None)  # noqa: S108

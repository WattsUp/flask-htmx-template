from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import sqlalchemy.engine

from flask_htmx_template import sql
from flask_htmx_template.database import Database

if TYPE_CHECKING:
    from tests.conftest import PostgresDatabaseGenerator

# ---------------------------------------------------------------------------
# sql helper unit tests (no postgres server needed)
# ---------------------------------------------------------------------------


def test_inject_credentials_user_password() -> None:
    """Key in user:password format sets both username and password."""
    url_str = sql.inject_postgres_credentials("postgresql://host/db", "myuser:mypass")
    u = sqlalchemy.engine.make_url(url_str)
    assert u.username == "myuser"
    assert u.password == "mypass"  # noqa: S105


def test_inject_credentials_password_only() -> None:
    """Key without colon sets only the password, preserving existing username."""
    url_str = sql.inject_postgres_credentials(
        "postgresql://existinguser@host/db",
        "mypass",
    )
    u = sqlalchemy.engine.make_url(url_str)
    assert u.username == "existinguser"
    assert u.password == "mypass"  # noqa: S105


def test_postgres_url_has_credentials_true() -> None:
    assert sql.postgres_url_has_credentials("postgresql://u:p@host/db") is True


def test_postgres_url_has_credentials_false_no_password() -> None:
    assert sql.postgres_url_has_credentials("postgresql://u@host/db") is False


def test_postgres_url_has_credentials_false_no_creds() -> None:
    assert sql.postgres_url_has_credentials("postgresql://host/db") is False


# ---------------------------------------------------------------------------
# Database.create and open
# ---------------------------------------------------------------------------


def test_create_with_url(postgres_database: Database) -> None:
    """Database.create() works with a full postgres URL."""
    assert postgres_database.is_postgres


def test_create_with_key_injection(
    postgres_database_generator: PostgresDatabaseGenerator,
    pg_url_no_creds: str,
    pg_key: str,
) -> None:
    """Database.create() injects user:password from key into a bare URL."""
    postgres_database_generator.drop()
    d = Database.create(pg_url_no_creds, pg_key)
    assert d.is_postgres


def test_open_with_url(postgres_database: Database, pg_url: str) -> None:
    """Database() opens an already-initialised postgres database."""
    d = Database(pg_url, None)
    assert d.is_postgres


def test_open_with_key(
    postgres_database: Database,
    pg_url_no_creds: str,
    pg_key: str,
) -> None:
    """Database() injects credentials from key when opening."""
    d = Database(pg_url_no_creds, pg_key)
    assert d.is_postgres


def test_create_already_initialized(postgres_database: Database, pg_url: str) -> None:
    """Second Database.create() on an initialized db raises FileExistsError."""
    with pytest.raises(FileExistsError):
        Database.create(pg_url)


# ---------------------------------------------------------------------------
# NotImplementedError for SQLite-only operations
# ---------------------------------------------------------------------------


def test_path_raises(postgres_database: Database) -> None:
    with pytest.raises(NotImplementedError):
        _ = postgres_database.path


def test_path_salt_raises(postgres_database: Database) -> None:
    with pytest.raises(NotImplementedError):
        _ = postgres_database.path_salt


def test_is_encrypted_false(postgres_database: Database) -> None:
    assert postgres_database.is_encrypted is False


def test_is_encrypted_path_false(pg_url: str) -> None:
    assert Database.is_encrypted_path(pg_url) is False


# ---------------------------------------------------------------------------
# NotImplementedError for backup / restore / clean / change_key
# ---------------------------------------------------------------------------


def test_backup_raises(postgres_database: Database) -> None:
    with pytest.raises(NotImplementedError):
        postgres_database.backup()


def test_backups_raises_instance(postgres_database: Database) -> None:
    with pytest.raises(NotImplementedError):
        Database.backups(postgres_database)


def test_backups_raises_str_url(pg_url: str) -> None:
    with pytest.raises(NotImplementedError):
        Database.backups(pg_url)


def test_clean_raises(postgres_database: Database) -> None:
    with pytest.raises(NotImplementedError):
        postgres_database.clean()


def test_restore_raises_instance(postgres_database: Database) -> None:
    with pytest.raises(NotImplementedError):
        Database.restore(postgres_database)


def test_restore_raises_str_url(pg_url: str) -> None:
    with pytest.raises(NotImplementedError):
        Database.restore(pg_url)


def test_change_key_raises(postgres_database: Database) -> None:
    with pytest.raises(NotImplementedError):
        postgres_database.change_key("newkey")

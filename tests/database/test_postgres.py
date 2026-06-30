from __future__ import annotations

import pytest
import sqlalchemy.engine

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql
from flask_htmx_template.database import PostgresDatabase

# ---------------------------------------------------------------------------
# sql helper unit tests (no postgres server needed)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Database.create and open
# ---------------------------------------------------------------------------


def test_create_with_url(postgres_database: PostgresDatabase) -> None:
    assert postgres_database.is_postgres


def test_open_with_url(postgres_database: PostgresDatabase, pg_url: str) -> None:
    d = PostgresDatabase(pg_url)
    assert d.is_postgres


def test_create_already_initialized(pg_url: str) -> None:
    with pytest.raises(FileExistsError):
        PostgresDatabase.create(pg_url)


# ---------------------------------------------------------------------------
# NotImplementedError for SQLite-only operations
# ---------------------------------------------------------------------------


def test_no_path_attribute(postgres_database: PostgresDatabase) -> None:
    assert not hasattr(postgres_database, "path")


def test_dispose(postgres_database: PostgresDatabase) -> None:
    postgres_database.dispose()


def test_str(postgres_database: PostgresDatabase, pg_url: str) -> None:
    normalized = sql.normalize_postgres_url(pg_url)
    redacted = sqlalchemy.engine.make_url(normalized).render_as_string(
        hide_password=True,
    )
    assert str(postgres_database) == f"<PostgresDatabase@{redacted}>"


def test_file_path_rejected() -> None:
    with pytest.raises(exc.UnlockingError):
        PostgresDatabase("/path/to/not_a_postgres_url.db")

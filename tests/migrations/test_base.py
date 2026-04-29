from __future__ import annotations

from typing import override, TYPE_CHECKING

import pytest
import sqlalchemy
from packaging.version import Version

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql
from flask_htmx_template.migrations.base import Migrator, SchemaMigrator
from flask_htmx_template.models.item import Item
from flask_htmx_template.models.utils import dump_table_configs

if TYPE_CHECKING:
    from sqlalchemy import orm

    from flask_htmx_template.database import Database


class MockMigrator(Migrator):

    _VERSION = "999.0.0"

    @override
    def migrate(self, d: Database) -> list[str]:
        return ["Comments"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _column_names(d: Database) -> list[str]:
    """Return column names for the item table via schema inspection.

    Returns:
        List of column name strings

    """
    with d.begin_session() as s:
        inspector = sqlalchemy.inspect(s.get_bind().engine)
        return [c["name"] for c in inspector.get_columns("item")]


# ---------------------------------------------------------------------------
# Non-parameterized: version
# ---------------------------------------------------------------------------


def test_version() -> None:
    m = MockMigrator()
    assert m.min_version() == Version("999.0.0")


# ---------------------------------------------------------------------------
# Parameterized fixture — SQLite or Postgres
# ---------------------------------------------------------------------------


@pytest.fixture(params=["sqlite", "postgres"])
def migrator_db(request: pytest.FixtureRequest, empty_database: Database) -> Database:
    """Database backed by SQLite or Postgres for migration operation tests.

    Returns:
        Database instance

    """
    if request.param == "sqlite":
        return empty_database
    postgres_database: Database = request.getfixturevalue("postgres_database")
    return postgres_database


# ---------------------------------------------------------------------------
# Parameterized tests: drop / add / rename columns
# ---------------------------------------------------------------------------


def test_drop_column_simple(migrator_db: Database) -> None:
    m = MockMigrator()
    with migrator_db.begin_session():
        m.drop_column(Item, "date_ord")
    assert m.pending_schema_updates == set()
    assert "date_ord" not in _column_names(migrator_db)


def test_drop_column_constrained(migrator_db: Database) -> None:
    m = MockMigrator()
    with migrator_db.begin_session():
        m.drop_column(Item, "other_id")
    assert "other_id" not in _column_names(migrator_db)
    expected: set[type[Item]] = set() if migrator_db.is_postgres else {Item}
    assert m.pending_schema_updates == expected


def test_add_column_no_value(migrator_db: Database, today_ord: int) -> None:
    m = MockMigrator()
    with migrator_db.begin_session():
        Item.create(name="add-col-no-val", date_ord=today_ord)
    with migrator_db.begin_session():
        m.drop_column(Item, "date_ord")
    m.pending_schema_updates.clear()
    with migrator_db.begin_session():
        m.add_column(Item, Item.date_ord)
    assert m.pending_schema_updates == {Item}
    assert "date_ord" in _column_names(migrator_db)
    with migrator_db.begin_session():
        fetched = sql.one(Item.query().filter_by(name="add-col-no-val"))
        assert fetched.date_ord is None


def test_add_column_with_value(migrator_db: Database, today_ord: int) -> None:
    m = MockMigrator()
    with migrator_db.begin_session():
        Item.create(name="add-col-with-val", date_ord=today_ord)
    with migrator_db.begin_session():
        m.drop_column(Item, "date_ord")
    m.pending_schema_updates.clear()
    with migrator_db.begin_session():
        m.add_column(Item, Item.date_ord, today_ord)
    assert m.pending_schema_updates == {Item}
    with migrator_db.begin_session():
        fetched = sql.one(Item.query().filter_by(name="add-col-with-val"))
        assert fetched.date_ord == today_ord


def test_rename_column(migrator_db: Database) -> None:
    m = MockMigrator()
    with migrator_db.begin_session():
        m.rename_column(Item, "date_ord", "date_renamed")
    assert m.pending_schema_updates == {Item}
    cols = _column_names(migrator_db)
    assert "date_ord" not in cols
    assert "date_renamed" in cols


# ---------------------------------------------------------------------------
# SQLite-specific tests (constraint / schema-string detail)
# ---------------------------------------------------------------------------


def test_drop_column_with_constraints_sqlite(session: orm.Session) -> None:
    m = MockMigrator()
    with session.begin_nested():
        m.drop_column(Item, "other_id")
    assert m.pending_schema_updates == {Item}

    result = "\n".join(dump_table_configs(Item))
    assert "other_id" not in result


def test_add_column_no_value_sqlite(session: orm.Session, item: Item) -> None:
    m = MockMigrator()
    with session.begin_nested():
        m.drop_column(Item, "date_ord")
    m.pending_schema_updates.clear()

    with session.begin_nested():
        m.add_column(Item, Item.date_ord)
    assert m.pending_schema_updates == {Item}

    result = "\n".join(dump_table_configs(Item))
    assert "date_ord" in result

    item.refresh()
    assert item.date_ord is None


def test_add_column_with_value_sqlite(
    session: orm.Session,
    item: Item,
    today_ord: int,
) -> None:
    m = MockMigrator()
    with session.begin_nested():
        m.drop_column(Item, "date_ord")
    m.pending_schema_updates.clear()

    with session.begin_nested():
        m.add_column(Item, Item.date_ord, today_ord)
    assert m.pending_schema_updates == {Item}

    result = "\n".join(dump_table_configs(Item))
    assert "date_ord" in result

    item.refresh()
    assert item.date_ord == today_ord


def test_rename_column_sqlite(session: orm.Session) -> None:
    m = MockMigrator()
    with session.begin_nested():
        m.rename_column(Item, "date_ord", "class")
    assert m.pending_schema_updates == {Item}

    result = "\n".join(dump_table_configs(Item))
    assert "date_ord" not in result
    assert "class" in result


# ---------------------------------------------------------------------------
# SchemaMigrator.migrate tests
# ---------------------------------------------------------------------------


def test_migrate_schemas_no_value_set(empty_database: Database, item: Item) -> None:
    m = SchemaMigrator(set())
    with empty_database.begin_session():
        m.drop_column(Item, "date_ord")
    with empty_database.begin_session():
        m.add_column(Item, Item.date_ord)

    with pytest.raises(exc.IntegrityError):
        m.migrate(empty_database)


def test_migrate_schemas_value_set(
    empty_database: Database,
    item: Item,
    today_ord: int,
) -> None:
    m = SchemaMigrator(set())
    with empty_database.begin_session():
        m.drop_column(Item, "date_ord")
    with empty_database.begin_session():
        m.add_column(Item, Item.date_ord, today_ord)

    assert m.migrate(empty_database) == []


def test_recreate_table_not_sqlite(postgres_database: Database) -> None:
    m = SchemaMigrator(set())
    with postgres_database.begin_session(), pytest.raises(NotImplementedError):
        m.recreate_table(Item)


def test_migrate_schemas_postgres(postgres_database: Database) -> None:
    m = SchemaMigrator({Item})
    assert m.migrate(postgres_database) == []

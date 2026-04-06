from __future__ import annotations

from typing import override, TYPE_CHECKING

import pytest
from packaging.version import Version

from flask_htmx_template import exceptions as exc
from flask_htmx_template.database import Database
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


def test_version() -> None:
    m = MockMigrator()
    assert m.min_version() == Version("999.0.0")


def test_drop_column(session: orm.Session) -> None:
    m = MockMigrator()
    with session.begin_nested():
        m.drop_column(Item, "date_ord")
    assert m.pending_schema_updates == set()

    result = "\n".join(dump_table_configs(Item))
    assert "date_ord" not in result


def test_drop_column_with_constraints(session: orm.Session) -> None:
    m = MockMigrator()
    with session.begin_nested():
        m.drop_column(Item, "other_id")
    assert m.pending_schema_updates == {Item}

    result = "\n".join(dump_table_configs(Item))
    assert "other_id" not in result


def test_add_column_no_value_set(session: orm.Session, item: Item) -> None:
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


def test_add_column_value_set(session: orm.Session, item: Item, today_ord: int) -> None:
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


def test_rename_column(session: orm.Session) -> None:
    m = MockMigrator()
    with session.begin_nested():
        m.rename_column(Item, "date_ord", "class")
    assert m.pending_schema_updates == {Item}

    result = "\n".join(dump_table_configs(Item))
    assert "date_ord" not in result
    assert "class" in result


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

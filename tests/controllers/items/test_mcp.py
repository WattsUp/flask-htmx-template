from __future__ import annotations

import contextlib
from decimal import Decimal
from typing import cast, TYPE_CHECKING

import pytest

from flask_htmx_template.controllers.items import mcp
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    import datetime

    from sqlalchemy import orm

    from flask_htmx_template.database import Database


class CurrentSessionDatabase:
    """Database adapter that returns the test's active database session."""

    def __init__(self, session: orm.Session) -> None:
        """Initialize a current-session database adapter.

        Args:
            session: Active test session

        """
        self._session = session

    def begin_session(self) -> contextlib.AbstractContextManager[orm.Session]:
        """Return the active test session.

        Returns:
            Active test session context manager

        """
        return contextlib.nullcontext(self._session)


@pytest.fixture
def current_session_database(session: orm.Session) -> Database:
    """Return a database adapter backed by the active test session.

    Returns:
        Active-session database adapter

    """
    return cast("Database", CurrentSessionDatabase(session))


def test_get_items_uses_database_session(empty_database: Database) -> None:
    result = mcp.get_items(empty_database)

    assert result == {
        "count": 0,
        "items": [],
        "next_offset": None,
        "total": 0,
    }


def test_get_item_returns_matching_item(
    current_session_database: Database,
    item: Item,
) -> None:
    result = mcp.get_item(current_session_database, uri=item.uri)

    assert result == {
        "uri": item.uri,
        "name": item.name,
        "date": item.date,
        "value": item.value,
        "note": item.note,
    }


def test_create_item_persists_item(
    current_session_database: Database,
    today: datetime.date,
) -> None:
    result = mcp.create_item(
        current_session_database,
        name="New name",
        value=Decimal(1234),
        note="New note",
    )

    created = Item.one()
    assert result == {
        "uri": created.uri,
        "name": "New name",
        "date": today,
        "value": Decimal(1234),
        "note": "New note",
    }


def test_update_item_persists_item(
    current_session_database: Database,
    item: Item,
    session: orm.Session,
    today: datetime.date,
) -> None:
    result = mcp.update_item(
        current_session_database,
        uri=item.uri,
        name="New name",
        value=Decimal(1234),
        note="New note",
    )

    session.refresh(item)
    assert result == {
        "uri": item.uri,
        "name": "New name",
        "date": today,
        "value": Decimal(1234),
        "note": "New note",
    }
    assert item.name == "New name"
    assert item.value == Decimal(1234)
    assert item.date == today
    assert item.note == "New note"


def test_delete_item_removes_item(
    current_session_database: Database,
    item: Item,
    session: orm.Session,
) -> None:
    result = mcp.delete_item(current_session_database, uri=item.uri)

    assert result.get("uri") == item.uri
    assert session.get(Item, item.id_) is None

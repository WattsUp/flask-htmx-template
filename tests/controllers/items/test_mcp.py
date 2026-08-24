from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template.controllers.items import mcp

if TYPE_CHECKING:
    from flask_htmx_template.database import Database


def test_get_items_uses_database_session(empty_database: Database) -> None:
    result = mcp.get_items(empty_database)

    assert result == {
        "count": 0,
        "items": [],
        "next_offset": None,
        "total": 0,
    }

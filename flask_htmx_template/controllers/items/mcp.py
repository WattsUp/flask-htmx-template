"""Item MCP tools."""

from __future__ import annotations

import datetime
import decimal  # ruff: ignore[typing-only-standard-library-import] - MCP schema resolution needs this at runtime
from typing import Annotated, TYPE_CHECKING

from pydantic import Field

from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.items import ctx
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    from flask_htmx_template.database import Database


@base.mcp_tool(
    "List a filtered page of items with their names, dates, values, and notes.",
    read_only_hint=True,
)
def get_items(
    database: Database,
    *,
    before: datetime.date | None = None,
    limit: Annotated[int, Field(ge=1, le=ctx.MAX_PAGE_LIMIT)] = ctx.DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> ctx.ItemsContext:
    """List a filtered page of items for the MCP tool.

    Args:
        database: Database to query
        before: Exclude items on or after this date
        limit: Maximum number of items to return
        offset: Number of filtered items to skip

    Returns:
        Page of items, page value total, filtered count, and next offset

    """
    with database.begin_session():
        return ctx.items(before=before, limit=limit, offset=offset)


@base.mcp_tool(
    "Get an item by URI with its name, date, value, and note.",
    read_only_hint=True,
)
def get_item(database: Database, *, uri: str) -> ctx.ItemContext:
    """Get one item for the MCP tool.

    Args:
        database: Database to query
        uri: URI of the item

    Returns:
        Item context

    """
    with database.begin_session():
        return ctx.item(base.find(Item, uri))


@base.mcp_tool(
    "Create an item with a name, value, and note.",
    read_only_hint=False,
    destructive_hint=False,
)
def create_item(
    database: Database,
    *,
    name: Annotated[str, Field(min_length=2)],
    value: decimal.Decimal,
    note: str | None,
) -> ctx.ItemContext:
    """Create an item for the MCP tool.

    Args:
        database: Database to update
        name: Item name
        value: Item value
        note: Optional item note

    Returns:
        Newly created item context

    """
    today = datetime.datetime.now(datetime.UTC).date()
    with database.begin_session() as session:
        with session.begin_nested():
            item = Item.create(
                name=name.strip(),
                date_ord=today.toordinal(),
                value=value,
                note=note,
            )
        return ctx.item(item)


@base.mcp_tool(
    "Update an item by URI with a name, value, and note.",
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
)
def update_item(
    database: Database,
    *,
    uri: str,
    name: Annotated[str, Field(min_length=2)],
    value: decimal.Decimal,
    note: str | None,
) -> ctx.ItemContext:
    """Update an item for the MCP tool.

    Args:
        database: Database to update
        uri: URI of the item
        name: Item name
        value: Item value
        note: Optional item note

    Returns:
        Updated item context

    """
    today = datetime.datetime.now(datetime.UTC).date()
    with database.begin_session() as session:
        item = base.find(Item, uri)
        with session.begin_nested():
            item.name = name
            item.date_ord = today.toordinal()
            item.value = value
            item.note = note
        return ctx.item(item)


@base.mcp_tool(
    "Delete an item by URI.",
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
)
def delete_item(database: Database, *, uri: str) -> ctx.ItemContext:
    """Delete an item for the MCP tool.

    Args:
        database: Database to update
        uri: URI of the item

    Returns:
        Context for the deleted item

    """
    with database.begin_session() as session:
        item = base.find(Item, uri)
        deleted = ctx.item(item)
        with session.begin_nested():
            item.delete()
        return deleted

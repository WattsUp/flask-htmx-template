"""Item MCP tools."""

from __future__ import annotations

from typing import Annotated, TYPE_CHECKING

from pydantic import Field

from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.items import ctx

if TYPE_CHECKING:
    import datetime

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

"""Item MCP tools."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flask_htmx_template import utils
from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.items import ctx

if TYPE_CHECKING:
    from flask_htmx_template.database import Database


@base.mcp_tool(
    "List all items with their names, dates, values, and notes.",
    read_only_hint=True,
)
def get_items(database: Database) -> str:
    """List all items for the MCP tool.

    Args:
        database: Database to query

    Returns:
        JSON object containing all items and their total

    """
    with database.begin_session():
        result: ctx.AllItemsContext = ctx.items()
    return json.dumps(utils.json_mutate(result))


TOOLS: tuple[base.MCPTool, ...] = (get_items,)

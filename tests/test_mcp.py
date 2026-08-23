from __future__ import annotations

import contextlib
from typing import cast, TYPE_CHECKING

import anyio
import prometheus_client
import pytest
from mcp import Client
from starlette.testclient import TestClient

from flask_htmx_template import asgi
from flask_htmx_template import exceptions as exc
from flask_htmx_template import mcp
from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.items import ctx
from flask_htmx_template.controllers.items import mcp as items_mcp
from flask_htmx_template.models.config import Config, ConfigKey
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    import flask
    from mcp_types import CallToolResult, Tool
    from sqlalchemy import orm
    from starlette.routing import Mount, Route

    from flask_htmx_template.database import Database


class CurrentSessionDatabase:
    """Database adapter that returns the test's active database session."""

    def __init__(self, session: orm.Session) -> None:
        """Initialize a CurrentSessionDatabase.

        Args:
            session: Active database session

        """
        self._session = session

    def begin_session(self) -> contextlib.AbstractContextManager[orm.Session]:
        """Return the active database session.

        Returns:
            Active database session context manager

        """
        return contextlib.nullcontext(self._session)


@pytest.fixture
def current_session_database(session: orm.Session) -> Database:
    """Return a Database adapter backed by the current test session.

    Returns:
        Database adapter

    """
    return cast("Database", CurrentSessionDatabase(session))


async def _list_tools(server: mcp.MCPServer) -> list[str]:
    """List the available tools through an in-process MCP client.

    Args:
        server: MCP server to inspect

    Returns:
        Tool names

    """
    async with Client(server) as client:
        result = await client.list_tools()
    return [tool.name for tool in result.tools]


async def _get_tool(server: mcp.MCPServer, name: str) -> Tool:
    """Return one tool definition from an in-process MCP server.

    Args:
        server: MCP server to inspect
        name: Tool name to find

    Returns:
        Matching MCP tool definition

    Raises:
        AssertionError: If the named tool is not registered

    """
    async with Client(server) as client:
        result = await client.list_tools()
    for tool in result.tools:
        if tool.name == name:
            return tool
    message = f"MCP tool is not registered: {name}"
    raise AssertionError(message)


async def _call_tool(
    server: mcp.MCPServer,
    name: str,
    arguments: dict[str, object] | None = None,
) -> CallToolResult:
    """Call an MCP tool through an in-process client.

    Args:
        server: MCP server hosting the tool
        name: Tool name to call
        arguments: Typed tool arguments

    Returns:
        MCP tool call result

    """
    async with Client(server) as client:
        return await client.call_tool(name, arguments=arguments)


def _duplicate_items_tool(database: Database) -> dict[str, object]:
    """Return a dummy result for duplicate-name registration tests.

    Args:
        database: Unused database argument matching MCP tool signatures

    Returns:
        Empty MCP tool result

    """
    del database
    return {}


def test_create_app_mounts_streamable_http_endpoint(
    flask_app: flask.Flask,
) -> None:
    app = asgi.create_app(flask_app)

    routes = cast("list[Route | Mount]", app.routes)

    assert routes[0].path == "/mcp"
    assert routes[1].path == "/mcp"
    assert not routes[2].path


def test_mcp_endpoint_requires_bearer_token(
    flask_app: flask.Flask,
) -> None:
    app = asgi.create_app(flask_app)
    client: TestClient = TestClient(app)

    response = client.get(asgi.MCP_PATH)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_mcp_endpoint_accepts_api_bearer_token(
    flask_app: flask.Flask,
) -> None:
    app = asgi.create_app(flask_app)
    client: TestClient = TestClient(app)
    token = Config.fetch(ConfigKey.API_BEARER_TOKEN)

    with client:
        response = client.get(
            asgi.MCP_PATH,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code != 401


def test_create_server_registers_read_only_items_tool(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    tools = anyio.run(_list_tools, server)

    assert tools == ["get_items"]


def test_items_tool_is_registered_in_central_registry() -> None:
    expected = items_mcp.get_items

    registered_tools = base.get_mcp_tools()

    assert expected in registered_tools


def test_mcp_tool_rejects_duplicate_name() -> None:
    _duplicate_items_tool.__name__ = items_mcp.get_items.__name__

    with pytest.raises(exc.DuplicateMCPToolError, match="get_items"):
        base.mcp_tool("Duplicate item tool")(_duplicate_items_tool)

    registered_tools = base.get_mcp_tools()
    assert _duplicate_items_tool not in registered_tools
    assert registered_tools.count(items_mcp.get_items) == 1


def test_get_items_returns_current_items(
    current_session_database: Database,
    item: Item,
) -> None:
    database = current_session_database

    value: ctx.ItemsContext = items_mcp.get_items(database)

    assert not isinstance(value, str)
    assert value["items"][0]["name"] == item.name
    assert value["total"] == item.value
    assert value["count"] == 1
    assert value["next_offset"] is None


def test_get_items_filters_and_paginates(
    current_session_database: Database,
    item: Item,
    session: orm.Session,
    today_ord: int,
) -> None:
    with session.begin_nested():
        older = Item.create(
            name="Apples",
            date_ord=today_ord - 1,
            value=2,
        )
        Item.create(
            name="Apricots",
            date_ord=today_ord - 1,
            value=3,
        )
    database = current_session_database

    value = items_mcp.get_items(
        database,
        before=item.date,
        limit=1,
        offset=0,
    )

    assert value == {
        "count": 2,
        "items": [ctx.item(older)],
        "next_offset": 1,
        "total": older.value,
    }


def test_get_items_publishes_output_schema(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    tool = anyio.run(_get_tool, server, "get_items")

    assert tool.output_schema is not None
    assert tool.output_schema["type"] == "object"
    assert set(tool.output_schema["required"]) == {
        "count",
        "items",
        "next_offset",
        "total",
    }
    assert set(tool.output_schema["properties"]) == {
        "count",
        "items",
        "next_offset",
        "total",
    }


def test_get_items_publishes_typed_input_schema(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    tool = anyio.run(_get_tool, server, "get_items")

    assert "required" not in tool.input_schema
    properties = tool.input_schema["properties"]
    assert properties["before"]["anyOf"][0] == {
        "format": "date",
        "type": "string",
    }
    assert properties["limit"]["default"] == ctx.DEFAULT_PAGE_LIMIT
    assert properties["limit"]["minimum"] == 1
    assert properties["limit"]["maximum"] == ctx.MAX_PAGE_LIMIT
    assert properties["offset"]["default"] == 0
    assert properties["offset"]["minimum"] == 0


def test_get_items_returns_structured_content_in_process(
    current_session_database: Database,
    flask_app: flask.Flask,
    item: Item,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    result = anyio.run(_call_tool, server, "get_items")

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["items"][0]["name"] == item.name
    assert result.structured_content["total"] == str(item.value)
    assert result.structured_content["count"] == 1
    assert result.structured_content["next_offset"] is None


def test_get_items_accepts_typed_arguments_in_process(
    current_session_database: Database,
    flask_app: flask.Flask,
    item: Item,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)
    arguments: dict[str, object] = {
        "before": item.date.isoformat(),
        "limit": 1,
        "offset": 0,
    }

    result = anyio.run(_call_tool, server, "get_items", arguments)

    assert not result.is_error
    assert result.structured_content == {
        "count": 0,
        "items": [],
        "next_offset": None,
        "total": "0",
    }


def test_get_items_rejects_invalid_pagination_in_process(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)
    arguments: dict[str, object] = {
        "limit": ctx.MAX_PAGE_LIMIT + 1,
    }

    result = anyio.run(
        _call_tool,
        server,
        "get_items",
        arguments,
    )

    assert result.is_error
    assert result.structured_content is None


def test_mcp_tool_records_metrics(
    current_session_database: Database,
) -> None:
    registry = prometheus_client.CollectorRegistry()
    tool = mcp._bind_database(
        items_mcp.get_items,
        current_session_database,
        mcp._get_metrics(registry),
    )

    tool(limit=1, offset=0)

    metrics = prometheus_client.generate_latest(registry).decode()
    assert 'flask_htmx_template_mcp_tool_calls_total{tool="get_items"} 1.0' in metrics
    assert (
        'flask_htmx_template_mcp_tool_duration_seconds_count{tool="get_items"} 1.0'
        in metrics
    )

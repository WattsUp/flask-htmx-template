from __future__ import annotations

import contextlib
import json
from types import SimpleNamespace
from typing import cast, NamedTuple, NoReturn, TYPE_CHECKING, TypedDict

import anyio
import anyio.lowlevel
import httpx2
import prometheus_client
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import TextResourceContents
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
    from collections.abc import AsyncGenerator
    from typing import Any

    import flask
    from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
    from mcp_types import CallToolResult, Resource, Tool
    from sqlalchemy import orm
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    from flask_htmx_template.database import Database


# NOTE: localhost satisfies the SDK's DNS-rebinding validation for ASGI requests.
_TEST_SERVER_ORIGIN = "http://localhost:8000"  # flask-htmx-template: ignore[url]
_KNOWN_TOOL_PARAMS: dict[str, object] = {"name": "known_tool"}


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


class ErrorDatabase:
    """Database adapter whose session setup fails."""

    @staticmethod
    def begin_session() -> NoReturn:
        """Raise the database failure used by metrics tests.

        Raises:
            RuntimeError: Always, to exercise an MCP tool error

        """
        message = "database unavailable"
        raise RuntimeError(message)


class StreamableHTTPLifecycle(NamedTuple):
    """Results captured across one Streamable HTTP client lifecycle."""

    protocol_version: str
    tool_names: list[str]
    tool_result: CallToolResult


class ServerMetadata(TypedDict):
    """Application identity and version resource document."""

    schema_version: int
    name: str
    description: str
    version: str


class ServerCapabilities(TypedDict):
    """MCP capability resource document."""

    schema_version: int
    transport: str
    authentication: str
    tools: list[str]
    resources: list[str]


@pytest.fixture
def current_session_database(session: orm.Session) -> Database:
    """Return a Database adapter backed by the current test session.

    Returns:
        Database adapter

    """
    return cast("Database", CurrentSessionDatabase(session))


@contextlib.asynccontextmanager
async def _streamable_http_connection(
    app: Starlette,
    token: str,
) -> AsyncGenerator[Client]:
    """Connect an authenticated MCP client through the ASGI HTTP transport.

    Args:
        app: Combined Flask and MCP ASGI application
        token: MCP bearer token

    Yields:
        Connected Streamable HTTP MCP client

    """
    transport = httpx2.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx2.AsyncClient(
        transport=transport,
        base_url=_TEST_SERVER_ORIGIN,
        headers=headers,
    ) as http_client:
        client_transport = streamable_http_client(
            f"{_TEST_SERVER_ORIGIN}{asgi.MCP_PATH}",
            http_client=http_client,
        )
        async with Client(client_transport) as client:
            yield client


async def _run_streamable_http_lifecycle(
    app: Starlette,
    token: str,
) -> StreamableHTTPLifecycle:
    """Run one Streamable HTTP client from negotiation through tool call.

    Args:
        app: Combined Flask and MCP ASGI application
        token: MCP bearer token

    Returns:
        Protocol, tool listing, and tool call results

    """
    async with (
        app.router.lifespan_context(app),
        _streamable_http_connection(app, token) as client,
    ):
        protocol_version = client.protocol_version
        tools = await client.list_tools()
        tool_result = await client.call_tool("get_items")
    return StreamableHTTPLifecycle(
        protocol_version,
        [tool.name for tool in tools.tools],
        tool_result,
    )


async def _run_concurrent_streamable_http_clients(
    app: Starlette,
    token: str,
) -> list[CallToolResult]:
    """Call one MCP tool from two clients whose lifecycles overlap.

    Args:
        app: Combined Flask and MCP ASGI application
        token: MCP bearer token

    Returns:
        Tool results in client index order

    """
    client_count = 2
    connected = [anyio.Event() for _ in range(client_count)]
    release_clients = anyio.Event()
    results: dict[int, CallToolResult] = {}

    async def connect_and_call(index: int) -> None:
        """Wait until both clients connect, then call the item tool."""
        async with _streamable_http_connection(app, token) as client:
            connected[index].set()
            await release_clients.wait()
            results[index] = await client.call_tool("get_items")

    async with (
        app.router.lifespan_context(app),
        anyio.create_task_group() as task_group,
    ):
        for index in range(client_count):
            task_group.start_soon(connect_and_call, index)
        for event in connected:
            await event.wait()
        release_clients.set()

    return [results[index] for index in range(client_count)]


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


async def _list_resources(server: mcp.MCPServer) -> list[Resource]:
    """List the available resources through an in-process MCP client.

    Args:
        server: MCP server to inspect

    Returns:
        Registered MCP resources

    """
    async with Client(server) as client:
        result = await client.list_resources()
    return result.resources


async def _read_resource(server: mcp.MCPServer, uri: str) -> str:
    """Read one text resource through an in-process MCP client.

    Args:
        server: MCP server hosting the resource
        uri: Resource URI to read

    Returns:
        Resource text content

    """
    async with Client(server) as client:
        result = await client.read_resource(uri)
    content = result.contents[0]
    assert isinstance(content, TextResourceContents)
    return content.text


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


async def _get_item_from_listing(server: mcp.MCPServer) -> CallToolResult:
    """List items and fetch the first item using its published URI.

    Args:
        server: MCP server hosting the item tools

    Returns:
        Result of fetching the listed item

    """
    async with Client(server) as client:
        listed = await client.call_tool("get_items")
        assert listed.structured_content is not None
        uri = listed.structured_content["items"][0]["uri"]
        assert isinstance(uri, str)
        return await client.call_tool("get_item", arguments={"uri": uri})


async def _run_safe_tool_errors(
    call_next: CallNext,
    params: dict[str, object] | None = None,
) -> HandlerResult:
    """Invoke the MCP error middleware with a minimal request context.

    Args:
        call_next: Handler behavior to exercise
        params: MCP request parameters

    Returns:
        Middleware result

    """
    context = cast(
        "ServerRequestContext[Any, Any]",
        SimpleNamespace(method="tools/call", params=params),
    )
    middleware = mcp._SafeToolErrors(frozenset({"known_tool"}))
    return await middleware(context, call_next)


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


def test_streamable_http_client_completes_full_lifecycle(
    empty_database: Database,
    flask_app: flask.Flask,
    item: Item,
) -> None:
    app = asgi.create_app(flask_app, empty_database)
    token = Config.fetch(ConfigKey.API_BEARER_TOKEN)

    lifecycle = anyio.run(_run_streamable_http_lifecycle, app, token)

    assert lifecycle.protocol_version
    assert lifecycle.tool_names == [
        "get_items",
        "get_item",
        "create_item",
        "update_item",
        "delete_item",
    ]
    assert not lifecycle.tool_result.is_error
    assert lifecycle.tool_result.structured_content is not None
    assert lifecycle.tool_result.structured_content["items"][0]["name"] == item.name


def test_streamable_http_clients_call_tool_concurrently(
    empty_database: Database,
    flask_app: flask.Flask,
    item: Item,
) -> None:
    app = asgi.create_app(flask_app, empty_database)
    token = Config.fetch(ConfigKey.API_BEARER_TOKEN)

    results = anyio.run(_run_concurrent_streamable_http_clients, app, token)

    assert len(results) == 2
    for result in results:
        assert not result.is_error
        assert result.structured_content is not None
        assert result.structured_content["items"][0]["name"] == item.name


def test_create_server_registers_item_tools(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    tools = anyio.run(_list_tools, server)

    assert tools == [
        "get_items",
        "get_item",
        "create_item",
        "update_item",
        "delete_item",
    ]


def test_create_server_registers_metadata_resources(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    resources = anyio.run(_list_resources, server)

    assert [str(resource.uri) for resource in resources] == [
        mcp.METADATA_RESOURCE_URI,
        mcp.CAPABILITIES_RESOURCE_URI,
    ]
    assert [resource.name for resource in resources] == [
        "server_metadata",
        "server_capabilities",
    ]
    assert all(resource.mime_type == "application/json" for resource in resources)


def test_server_metadata_resource_identifies_application_version(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    content = anyio.run(_read_resource, server, mcp.METADATA_RESOURCE_URI)

    metadata = cast("ServerMetadata", json.loads(content))
    assert metadata == {
        "schema_version": 1,
        "name": "Flask HTMX Template",
        "description": "Read and write item information from Flask HTMX Template.",
        "version": mcp.__version__,
    }


def test_server_capabilities_resource_describes_mcp_surface(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    content = anyio.run(_read_resource, server, mcp.CAPABILITIES_RESOURCE_URI)

    capabilities = cast("ServerCapabilities", json.loads(content))
    assert capabilities == {
        "schema_version": 1,
        "transport": "streamable-http",
        "authentication": "bearer",
        "tools": [
            "create_item",
            "delete_item",
            "get_item",
            "get_items",
            "update_item",
        ],
        "resources": [
            mcp.METADATA_RESOURCE_URI,
            mcp.CAPABILITIES_RESOURCE_URI,
        ],
    }


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
    assert tool.description == items_mcp.get_items.mcp_description
    assert tool.description is not None
    assert "count is the number of matching items before pagination" in tool.description
    assert "total is the sum of values in the returned page" in tool.description


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


def test_get_item_accepts_uri_from_get_items(
    current_session_database: Database,
    flask_app: flask.Flask,
    item: Item,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    result = anyio.run(_get_item_from_listing, server)

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["uri"] == item.uri


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
    assert result.meta is not None
    assert result.meta["errorCode"] == int(mcp.MCPErrorCode.INVALID_PARAMS)
    assert result.content[0].model_dump() == {
        "type": "text",
        "text": "MCP tool arguments are invalid.",
        "annotations": None,
        "meta": None,
    }


def test_mcp_tool_hides_internal_error_details(
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, cast("Database", ErrorDatabase()))

    result = anyio.run(_call_tool, server, "get_items")

    assert result.is_error
    assert result.meta is not None
    assert result.meta["errorCode"] == int(mcp.MCPErrorCode.INTERNAL_ERROR)
    assert result.content[0].model_dump() == {
        "type": "text",
        "text": "MCP tool execution failed.",
        "annotations": None,
        "meta": None,
    }
    assert "database unavailable" not in str(result)


def test_get_item_returns_structured_error_when_item_is_missing(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)
    arguments: dict[str, object] = {"uri": Item.id_to_uri(999)}

    result = anyio.run(_call_tool, server, "get_item", arguments)

    assert result.is_error
    assert result.structured_content is None
    assert result.meta is not None
    assert result.meta["errorCode"] == int(mcp.MCPErrorCode.RESOURCE_NOT_FOUND)
    assert result.content[0].model_dump() == {
        "type": "text",
        "text": "Requested resource was not found.",
        "annotations": None,
        "meta": None,
    }


def test_mcp_tool_returns_safe_code_when_tool_is_missing(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    result = anyio.run(_call_tool, server, "missing_tool")

    assert result.is_error
    assert result.meta is not None
    assert result.meta["errorCode"] == int(mcp.MCPErrorCode.METHOD_NOT_FOUND)
    assert result.content[0].model_dump() == {
        "type": "text",
        "text": "MCP tool was not found.",
        "annotations": None,
        "meta": None,
    }


def test_safe_tool_errors_sanitizes_unknown_mcp_error_code() -> None:
    async def call_next(
        _context: ServerRequestContext[Any, Any],
    ) -> HandlerResult:
        """Raise an MCP error with an unrecognized code.

        Raises:
            MCPError: Always, with an unknown error code

        """
        await anyio.lowlevel.checkpoint()
        raise MCPError(code=-32099, message="sensitive error")

    result = anyio.run(
        _run_safe_tool_errors,
        call_next,
        _KNOWN_TOOL_PARAMS,
    )

    safe_result = cast("CallToolResult", result)
    assert safe_result.is_error
    assert safe_result.meta == {
        "errorCode": int(mcp.MCPErrorCode.INTERNAL_ERROR),
    }
    assert "sensitive error" not in str(safe_result)


def test_safe_tool_errors_sanitizes_unexpected_exception() -> None:
    async def call_next(
        _context: ServerRequestContext[Any, Any],
    ) -> HandlerResult:
        """Raise an unexpected handler failure.

        Raises:
            RuntimeError: Always, to exercise unexpected failures

        """
        await anyio.lowlevel.checkpoint()
        message = "sensitive failure"
        raise RuntimeError(message)

    result = anyio.run(
        _run_safe_tool_errors,
        call_next,
        _KNOWN_TOOL_PARAMS,
    )

    safe_result = cast("CallToolResult", result)
    assert safe_result.is_error
    assert safe_result.meta == {
        "errorCode": int(mcp.MCPErrorCode.INTERNAL_ERROR),
    }
    assert "sensitive failure" not in str(safe_result)


def test_safe_tool_errors_preserves_result_type_and_sanitizes_metadata() -> None:
    async def call_next(
        _context: ServerRequestContext[Any, Any],
    ) -> HandlerResult:
        """Return an invalid result with metadata to sanitize.

        Returns:
            Invalid result with metadata

        """
        await anyio.lowlevel.checkpoint()
        return {
            "resultType": "partial",
            "isError": True,
            "_meta": {"requestId": "request-1", "errorCode": 1234},
        }

    result = anyio.run(
        _run_safe_tool_errors,
        call_next,
        _KNOWN_TOOL_PARAMS,
    )

    safe_result = cast("dict[str, object]", result)
    assert safe_result["resultType"] == "partial"
    assert safe_result["_meta"] == {
        "requestId": "request-1",
        "errorCode": int(mcp.MCPErrorCode.INVALID_PARAMS),
    }


def test_safe_tool_errors_sanitizes_result_without_optional_fields() -> None:
    async def call_next(
        _context: ServerRequestContext[Any, Any],
    ) -> HandlerResult:
        """Return an invalid result without optional fields.

        Returns:
            Invalid result without optional fields

        """
        await anyio.lowlevel.checkpoint()
        return {"isError": True}

    result = anyio.run(
        _run_safe_tool_errors,
        call_next,
        _KNOWN_TOOL_PARAMS,
    )

    safe_result = cast("dict[str, object]", result)
    assert safe_result["resultType"] == "complete"
    assert safe_result["_meta"] == {
        "errorCode": int(mcp.MCPErrorCode.INVALID_PARAMS),
    }


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
    assert (
        'flask_htmx_template_mcp_tool_calls_total{error_code="none",status="success",'
        'tool="get_items"} 1.0'
    ) in metrics
    assert (
        'flask_htmx_template_mcp_tool_duration_seconds_count{error_code="none",'
        'status="success",tool="get_items"} 1.0' in metrics
    )


def test_mcp_tool_records_error_metrics() -> None:
    registry = prometheus_client.CollectorRegistry()
    tool = mcp._bind_database(
        items_mcp.get_items,
        cast("Database", ErrorDatabase()),
        mcp._get_metrics(registry),
    )

    with pytest.raises(MCPError, match="MCP tool execution failed"):
        tool(limit=1, offset=0)

    metrics = prometheus_client.generate_latest(registry).decode()
    assert (
        'flask_htmx_template_mcp_tool_calls_total{error_code="internal",status="error",'
        'tool="get_items"} 1.0'
    ) in metrics
    assert (
        'flask_htmx_template_mcp_tool_duration_seconds_count{error_code="internal",'
        'status="error",tool="get_items"} 1.0'
    ) in metrics


def test_mcp_tool_records_not_found_metrics(
    current_session_database: Database,
) -> None:
    registry = prometheus_client.CollectorRegistry()
    tool = mcp._bind_database(
        items_mcp.get_item,
        current_session_database,
        mcp._get_metrics(registry),
    )

    with pytest.raises(MCPError, match="Requested resource was not found"):
        tool(uri=Item.id_to_uri(999))

    metrics = prometheus_client.generate_latest(registry).decode()
    assert (
        'flask_htmx_template_mcp_tool_calls_total{error_code="not_found",'
        'status="error",tool="get_item"} 1.0'
    ) in metrics
    assert (
        'flask_htmx_template_mcp_tool_duration_seconds_count{error_code="not_found",'
        'status="error",tool="get_item"} 1.0' in metrics
    )

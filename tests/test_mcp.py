from __future__ import annotations

import contextlib
import json
from typing import cast, TYPE_CHECKING

import anyio
import prometheus_client
import pytest
from mcp import Client
from starlette.testclient import TestClient

from flask_htmx_template import asgi, mcp
from flask_htmx_template.controllers.items import mcp as items_mcp
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    import flask
    from sqlalchemy import orm
    from starlette.routing import Mount, Route

    from flask_htmx_template.database import Database
    from flask_htmx_template.models.item import Item


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


def test_create_app_mounts_streamable_http_endpoint(
    flask_app: flask.Flask,
) -> None:
    # Arrange
    app = asgi.create_app(flask_app)

    # Act
    routes = cast("list[Route | Mount]", app.routes)

    # Assert
    assert routes[0].path == "/mcp"
    assert routes[1].path == "/mcp"
    assert not routes[2].path


def test_mcp_endpoint_requires_bearer_token(
    flask_app: flask.Flask,
) -> None:
    # Arrange
    app = asgi.create_app(flask_app)
    client: TestClient = TestClient(app)

    # Act
    response = client.get(asgi.MCP_PATH)

    # Assert
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_mcp_endpoint_accepts_api_bearer_token(
    flask_app: flask.Flask,
) -> None:
    # Arrange
    app = asgi.create_app(flask_app)
    client: TestClient = TestClient(app)
    token = Config.fetch(ConfigKey.API_BEARER_TOKEN)

    # Act
    with client:
        response = client.get(
            asgi.MCP_PATH,
            headers={"Authorization": f"Bearer {token}"},
        )

    # Assert
    assert response.status_code != 401


def test_create_server_registers_read_only_items_tool(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    # Arrange
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    server = mcp.create_server(registry, current_session_database)

    # Act
    tools = anyio.run(_list_tools, server)

    # Assert
    assert tools == ["get_items"]


def test_mcp_tool_records_metrics(
    current_session_database: Database,
    flask_app: flask.Flask,
) -> None:
    # Arrange
    registry = flask_app.extensions["flask_htmx_template_metrics"].registry
    tool = mcp._bind_database(
        items_mcp.get_items,
        current_session_database,
        mcp._get_metrics(registry),
    )

    # Act
    tool()

    # Assert
    metrics = prometheus_client.generate_latest(registry).decode()
    assert 'flask_htmx_template_mcp_tool_calls_total{tool="get_items"} 1.0' in metrics
    assert (
        'flask_htmx_template_mcp_tool_duration_seconds_count{tool="get_items"} 1.0'
        in metrics
    )


def test_get_items_returns_current_items(
    current_session_database: Database,
    item: Item,
) -> None:
    # Arrange
    database = current_session_database

    # Act
    value = items_mcp.get_items(database)

    # Assert
    result = json.loads(value)
    assert result["items"][0]["name"] == item.name

"""ASGI application that combines Flask and MCP endpoints."""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import Any, cast, TYPE_CHECKING

from asgiref.wsgi import WsgiToAsgi
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from flask_htmx_template import mcp, web
from flask_htmx_template.models.config import Config, ConfigKey

MCP_PATH = "/mcp"

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import flask
    from starlette.types import ASGIApp, Receive, Scope, Send

    from flask_htmx_template.database import Database


class _MCPRootPath:
    """Adapt an exact mount-path request to the MCP app's root path."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the MCP root-path adapter.

        Args:
            app: MCP ASGI application

        """
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Serve an exact `/mcp` request through the mounted MCP app.

        Args:
            scope: ASGI request scope
            receive: ASGI request receiver
            send: ASGI response sender

        """
        scope = {**scope, "path": "/"}
        await self._app(scope, receive, send)


class _BearerAuth:
    """Require the database-backed API bearer token for MCP requests."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        """Initialize the bearer authentication adapter.

        Args:
            app: MCP ASGI application
            token: Expected API bearer token

        """
        self._app = app
        self._token = token

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Authenticate an MCP request before forwarding it.

        Args:
            scope: ASGI request scope
            receive: ASGI request receiver
            send: ASGI response sender

        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = {
            key.lower(): value
            for key, value in cast("list[tuple[bytes, bytes]]", scope["headers"])
        }
        authorization = headers.get(b"authorization", b"").decode(
            "utf-8",
            errors="replace",
        )
        scheme, separator, credential = authorization.partition(" ")
        authenticated = (
            bool(separator)
            and scheme.lower() == "bearer"
            and secrets.compare_digest(credential, self._token)
        )
        if authenticated:
            await self._app(scope, receive, send)
            return

        body = b'{"error":"Bearer token required"}\n'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b"Bearer"),
                ],
            },
        )
        await send({"type": "http.response.body", "body": body})


def create_app(
    flask_app: flask.Flask | None = None,
    database: Database | None = None,
) -> Starlette:
    """Create the combined Flask and MCP ASGI application.

    Args:
        flask_app: Existing Flask app, None creates the template web app
        database: Database to expose, None uses the Flask extension database

    Returns:
        ASGI app serving Flask routes and the MCP endpoint

    """
    flask_app = flask_app or web.create_app()
    database = database or web.ext.db
    metrics = flask_app.extensions["flask_htmx_template_metrics"]
    server = mcp.create_server(metrics.registry, database)
    mcp_transport = server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
    )
    # NOTE: Read the token once so concurrent ASGI requests do not mutate the ORM's
    # process-global active-session context merely to authenticate each request.
    with database.begin_session():
        bearer_token = Config.fetch(ConfigKey.API_BEARER_TOKEN)
    mcp_app = _BearerAuth(mcp_transport, bearer_token)

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncGenerator[None]:
        async with server.session_manager.run():
            yield

    return Starlette(
        routes=[
            Route(MCP_PATH, endpoint=_MCPRootPath(mcp_app), methods=None),
            Mount(MCP_PATH, app=mcp_app),
            Mount("/", app=cast("Any", WsgiToAsgi(cast("Any", flask_app)))),
        ],
        lifespan=lifespan,
    )

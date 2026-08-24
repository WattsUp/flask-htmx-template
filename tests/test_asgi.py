from __future__ import annotations

from contextlib import asynccontextmanager
from typing import cast, TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import anyio

from flask_htmx_template import asgi

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import flask
    import pytest
    from starlette.types import ASGIApp, Receive, Scope, Send

    from flask_htmx_template.database import Database


def test_mcp_root_path_forwards_request_at_root() -> None:
    app_mock = AsyncMock()
    app = cast("ASGIApp", app_mock)
    root_path = asgi._MCPRootPath(app)
    scope = cast("Scope", {"type": "http", "path": "/mcp"})
    receive = cast("Receive", AsyncMock())
    send = cast("Send", AsyncMock())

    anyio.run(root_path, scope, receive, send)

    assert app_mock.await_args is not None
    forwarded_scope = app_mock.await_args.args[0]
    assert forwarded_scope["path"] == "/"
    assert scope["path"] == "/mcp"
    app_mock.assert_awaited_once_with(forwarded_scope, receive, send)


def test_bearer_auth_forwards_non_http_scope() -> None:
    app_mock = AsyncMock()
    app = cast("ASGIApp", app_mock)
    bearer_auth = asgi._BearerAuth(app, "token")
    scope = cast("Scope", {"type": "lifespan"})
    receive = cast("Receive", AsyncMock())
    send = cast("Send", AsyncMock())

    anyio.run(bearer_auth, scope, receive, send)

    app_mock.assert_awaited_once_with(scope, receive, send)


def test_bearer_auth_forwards_valid_http_scope() -> None:
    app_mock = AsyncMock()
    app = cast("ASGIApp", app_mock)
    bearer_auth = asgi._BearerAuth(app, "token")
    scope = cast(
        "Scope",
        {
            "type": "http",
            "headers": [(b"AUTHORIZATION", b"bEaReR token")],
        },
    )
    receive = cast("Receive", AsyncMock())
    send_mock = AsyncMock()
    send = cast("Send", send_mock)

    anyio.run(bearer_auth, scope, receive, send)

    app_mock.assert_awaited_once_with(scope, receive, send)
    send_mock.assert_not_awaited()


def test_bearer_auth_rejects_http_scope_without_valid_token() -> None:
    app_mock = AsyncMock()
    app = cast("ASGIApp", app_mock)
    bearer_auth = asgi._BearerAuth(app, "token")
    scope = cast("Scope", {"type": "http", "headers": []})
    receive = cast("Receive", AsyncMock())
    send_mock = AsyncMock()
    send = cast("Send", send_mock)

    anyio.run(bearer_auth, scope, receive, send)

    app_mock.assert_not_awaited()
    assert [call.args[0] for call in send_mock.await_args_list] == [
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", b"34"),
                (b"www-authenticate", b"Bearer"),
            ],
        },
        {
            "type": "http.response.body",
            "body": b'{"error":"Bearer token required"}\n',
        },
    ]


def test_create_app_uses_default_flask_app_and_database(
    flask_app: flask.Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = MagicMock()
    lifecycle_events: list[str] = []

    @asynccontextmanager
    async def run_session_manager() -> AsyncGenerator[None]:
        lifecycle_events.append("started")
        try:
            yield
        finally:
            lifecycle_events.append("stopped")

    def create_server(*_args: object) -> MagicMock:
        return server

    server.session_manager.run.side_effect = run_session_manager
    server.streamable_http_app.return_value = AsyncMock()
    monkeypatch.setattr(asgi.web, "create_app", lambda: flask_app)
    monkeypatch.setattr(asgi.mcp, "create_server", create_server)

    app = asgi.create_app()

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            lifecycle_events.append("running")

    anyio.run(run_lifespan)

    assert lifecycle_events == ["started", "running", "stopped"]
    server.streamable_http_app.assert_called_once_with(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
    )
    server.session_manager.run.assert_called_once_with()


def test_create_app_uses_explicit_flask_app_and_database(
    flask_app: flask.Flask,
    empty_database: Database,
) -> None:
    app = asgi.create_app(flask_app, empty_database)

    assert len(app.routes) == 3

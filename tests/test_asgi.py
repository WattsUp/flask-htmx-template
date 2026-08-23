from __future__ import annotations

from typing import cast, TYPE_CHECKING
from unittest.mock import AsyncMock

import anyio

from flask_htmx_template import asgi

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


def test_bearer_auth_forwards_non_http_scope() -> None:
    app_mock = AsyncMock()
    app = cast("ASGIApp", app_mock)
    bearer_auth = asgi._BearerAuth(app, "token")
    scope = cast("Scope", {"type": "lifespan"})
    receive = cast("Receive", AsyncMock())
    send = cast("Send", AsyncMock())

    anyio.run(bearer_auth, scope, receive, send)

    app_mock.assert_awaited_once_with(scope, receive, send)

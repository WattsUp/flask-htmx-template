"""Database-backed bearer-token authentication."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from flask_htmx_template import web
from flask_htmx_template.controllers.auth import ctx
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    import flask


_AUTHORIZATION_PARTS = 2


def load_user(request: flask.Request) -> ctx.WebUser | None:
    """Load the web user when the request supplies the configured bearer token.

    Args:
        request: Request whose Authorization header is checked.

    Returns:
        Authenticated web user, or ``None`` when the header is absent or invalid.

    """
    authorization = request.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) != _AUTHORIZATION_PARTS or parts[0].lower() != "bearer":
        return None

    with web.db.begin_session():
        expected = Config.fetch(ConfigKey.API_BEARER_TOKEN, no_raise=True)
    if expected is None or not secrets.compare_digest(parts[1], expected):
        return None
    return ctx.WebUser()

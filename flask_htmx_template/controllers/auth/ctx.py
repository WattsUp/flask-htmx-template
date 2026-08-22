"""Authentication request context helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flask
import flask_login

from flask_htmx_template.controllers import base

if TYPE_CHECKING:
    from collections.abc import Callable


def login_exempt[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Exclude a route from requiring authentication.

    Returns:
        The marked route callable.

    """
    # NOTE: The marker is read by default_login_required before the view runs.
    func.__dict__["login_exempt"] = True
    return func


def default_login_required() -> flask.Response | None:
    """Require authentication for routes that are not explicitly exempt.

    Returns:
        Login or JSON authorization response when authentication is required,
        otherwise ``None``.

    """
    endpoint = flask.request.endpoint
    if not endpoint or endpoint.rsplit(".", 1)[-1] == "static":
        return None
    if flask.current_app.testing:
        return None
    view = flask.current_app.view_functions[endpoint]
    if getattr(view, "login_exempt", False):
        return None

    if flask.request.path.startswith("/j/"):
        if flask_login.current_user.is_authenticated:
            return None
        response = flask.jsonify({"errors": ["Bearer token required"]})
        response.status_code = base.HTTP_CODE_UNAUTHORIZED
        response.headers["WWW-Authenticate"] = "Bearer"
        return response

    return flask_login.login_required(lambda: None)()


class WebUser(flask_login.UserMixin):
    """Web user model."""

    ID = "web"

    def __init__(self) -> None:
        """Initialize the web user."""
        super().__init__()
        self.id = self.ID


def get_user(username: str) -> flask_login.UserMixin | flask_login.AnonymousUserMixin:
    """Load the single web user by name.

    Returns:
        The authenticated web user or an anonymous user.

    """
    if username != WebUser.ID:  # pragma: no cover
        return flask_login.AnonymousUserMixin()
    return WebUser()

"""Authentication request context helpers."""

from __future__ import annotations

import flask
import flask.typing
import flask_login


def login_exempt(func: flask.typing.RouteCallable) -> flask.typing.RouteCallable:
    """Exclude a route from requiring authentication.

    Returns:
        The marked route callable.

    """
    # login_exempt is not an attribute of RouteCallable.
    func.login_exempt = True  # type: ignore[attr-defined]
    return func


def default_login_required() -> flask.Response | None:
    """Require authentication for routes that are not explicitly exempt.

    Returns:
        Login response when authentication is required, otherwise ``None``.

    """
    endpoint = flask.request.endpoint
    if not endpoint or endpoint.rsplit(".", 1)[-1] == "static":
        return None
    if flask.current_app.testing:
        return None
    view = flask.current_app.view_functions[endpoint]
    if getattr(view, "login_exempt", False):
        return None
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

"""Authentication controller."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import flask
import flask.typing
import flask_login

from flask_htmx_template import web
from flask_htmx_template.controllers import base
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:

    import werkzeug


def login_exempt(func: flask.typing.RouteCallable) -> flask.typing.RouteCallable:
    """Dectorator to exclude route from requiring authentication.

    Args:
        func: Function to decorate

    Returns:
        Decorated function

    """
    # login_exempt is not an attribute of RouteCallable
    func.login_exempt = True  # type: ignore[attr-defined]
    return func


def default_login_required() -> flask.Response | None:
    """Make all routes require login, use @login_exempt to exclude.

    Returns:
        Response if redirect is required

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

    # Only one user, for now?
    ID = "web"

    def __init__(self) -> None:
        """Initialize WebUser."""
        super().__init__()

        self.id = self.ID


def get_user(username: str) -> flask_login.UserMixin | flask_login.AnonymousUserMixin:
    """Load a user from name.

    Args:
        username: Username of user

    Returns:
        User object or Anonymous

    """
    if username != WebUser.ID:  # pragma: no cover
        # Don't need to test anonymous
        return flask_login.AnonymousUserMixin()
    return WebUser()


@login_exempt
def page_login() -> str | werkzeug.Response:
    """GET /login.

    Returns:
        HTML response

    """
    next_url = flask.request.args.get("next")
    if flask_login.current_user.is_authenticated:
        # If already authenticated, skip login page
        return flask.redirect(next_url or flask.url_for("common.page_dashboard"))
    templates = Path(flask.current_app.root_path) / (
        flask.current_app.template_folder or "templates"
    )
    return flask.render_template(
        "auth/login.jinja",
        title="Login - flask_htmx_template",
        **base.ctx_base_page(
            templates,
            datetime.datetime.now(datetime.UTC),
            debug=flask.current_app.debug,
        ),
        next_url=next_url,
    )


@login_exempt
def login() -> str | werkzeug.Response:
    """POST /h/login.

    Returns:
        HTML response

    """
    db = web.db
    form = flask.request.form
    password = form.get("password")

    if not password:
        return base.error("Password must not be blank")

    with db.begin_session():
        expected = Config.fetch(ConfigKey.WEB_KEY)

    if password != expected:
        return base.error("Bad password")

    web_user = WebUser()
    flask_login.login_user(web_user, remember=True)

    next_url = form.get("next")
    return flask.redirect(next_url or flask.url_for("common.page_dashboard"))


def logout() -> str | werkzeug.Response:
    """POST /h/logout.

    Returns:
        HTML response

    """
    flask_login.logout_user()
    return flask.redirect(flask.url_for("auth.page_login"))


ROUTES: base.Routes = {
    "/login": (page_login, ["GET"]),
    "/h/login": (login, ["POST"]),
    "/h/logout": (logout, ["POST"]),
}

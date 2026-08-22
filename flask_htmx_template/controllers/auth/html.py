"""Authentication HTML controllers."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import flask
import flask_login

from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.auth import ctx, password

if TYPE_CHECKING:
    import werkzeug


@ctx.login_exempt
def page_login() -> str | werkzeug.Response:
    """GET the login page.

    Returns:
        Login page or redirect for an authenticated user.

    """
    next_url = flask.request.args.get("next")
    if flask_login.current_user.is_authenticated:
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
        debug=flask.current_app.debug,
        next_url=next_url,
    )


@ctx.login_exempt
def login() -> str | werkzeug.Response:
    """POST password credentials.

    Returns:
        Validation error or dashboard redirect.

    """
    return password.login()


def logout() -> str | werkzeug.Response:
    """POST logout.

    Returns:
        Redirect to the login page.

    """
    flask_login.logout_user()
    return flask.redirect(flask.url_for("auth.page_login"))


ROUTE_PREFIX = "auth"
ROUTES: base.Routes = {
    "/login": (page_login, ["GET"]),
    "/h/login": (login, ["POST"]),
    "/h/logout": (logout, ["POST"]),
}

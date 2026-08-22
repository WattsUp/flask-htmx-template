"""Password authentication endpoint."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

import flask
import flask_login

from flask_htmx_template import web
from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.auth import ctx
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    import werkzeug


@ctx.login_exempt
def login() -> str | werkzeug.Response:
    """POST password credentials.

    Returns:
        Validation error or dashboard redirect.

    """
    password = flask.request.form.get("password")
    if not password:
        return base.error("Password must not be blank")
    with web.db.begin_session():
        expected = Config.fetch(ConfigKey.WEB_KEY)
    if not secrets.compare_digest(password, expected):
        return base.error("Bad password")
    flask_login.login_user(ctx.WebUser(), remember=True)
    return flask.redirect(
        flask.request.form.get("next") or flask.url_for("common.page_dashboard"),
    )

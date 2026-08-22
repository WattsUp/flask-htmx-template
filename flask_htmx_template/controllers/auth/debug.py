"""Debug-only authentication endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flask
import flask_login

from flask_htmx_template import exceptions as exc
from flask_htmx_template.controllers.auth import ctx

if TYPE_CHECKING:
    from werkzeug.wrappers import Response

    from flask_htmx_template.controllers import base


@ctx.login_exempt
def debug_login() -> Response:
    """POST a debug login without credentials.

    Returns:
        Redirect to the requested page.

    Raises:
        Unauthorized: If Flask debug mode is disabled.

    """
    if not flask.current_app.debug:
        raise exc.http.Unauthorized
    flask_login.login_user(ctx.WebUser(), remember=True)
    return flask.redirect(
        flask.request.form.get("next")
        or flask.request.args.get("next")
        or flask.url_for("common.page_dashboard"),
    )


ROUTE_PREFIX = "auth"
ROUTES: base.Routes = {
    "/d/auth/login": (debug_login, ["POST"]),
}

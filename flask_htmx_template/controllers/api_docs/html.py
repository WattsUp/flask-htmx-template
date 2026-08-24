"""Interactive JSON API documentation HTML controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template import web
from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.api_docs import ctx
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    import flask


def page() -> flask.Response:
    """GET interactive JSON API documentation page.

    Returns:
        Rendered API documentation page.

    """
    with web.db.begin_session():
        bearer_token = Config.fetch(ConfigKey.API_BEARER_TOKEN)
    return base.page(
        "api/page.jinja",
        "API",
        groups=ctx.GROUPS,
        bearer_token=bearer_token,
    )


ROUTE_PREFIX = "api_docs"
ROUTES: base.Routes = {"/api": (page, ["GET"])}

"""API documentation JSON endpoints."""

from __future__ import annotations

from typing import cast, TYPE_CHECKING

from flask_htmx_template.controllers.api_docs import ctx

if TYPE_CHECKING:
    from flask_htmx_template.controllers import base


def json_api_enums() -> dict[str, list[str]]:
    """GET known enum values for JSON API fields.

    Returns:
        Enum names and their values.

    """
    return ctx.api_enums()


def json_api() -> ctx._APIDocsJSON:
    """GET machine-readable API documentation.

    Returns:
        API documentation grouped by URL and HTTP method.

    """
    return ctx.api()


ROUTE_PREFIX = "api_docs"
ROUTES: base.Routes = {
    "/j/api": (cast("base.RouteCallable", json_api), ["GET"]),
    "/j/api/enums": (cast("base.RouteCallable", json_api_enums), ["GET"]),
}

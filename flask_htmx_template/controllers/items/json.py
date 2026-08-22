"""Item JSON controllers."""

from __future__ import annotations

import datetime

import flask

from flask_htmx_template import exceptions as exc
from flask_htmx_template import utils, web
from flask_htmx_template.controllers import base
from flask_htmx_template.controllers.items import ctx
from flask_htmx_template.models.item import Item


def _parse_query_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    """Parse and bound an integer query parameter.

    Args:
        name: Query parameter name
        default: Value when the parameter is absent
        minimum: Inclusive minimum value
        maximum: Inclusive maximum value, if any

    Returns:
        Parsed integer value

    Raises:
        ValueError: If the value is not an integer or is outside its bounds

    """
    raw_value = flask.request.args.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        message = f"{name} must be an integer"
        raise ValueError(message) from error
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            message = f"{name} must be at least {minimum}"
        else:
            message = f"{name} must be between {minimum} and {maximum}"
        raise ValueError(message)
    return value


def json_all() -> ctx.ItemsContext | base.JSONResponse:
    """GET all items.

    Query args:
        before: filter items that appear before this date, optional
        limit: maximum items to return, 1 to 100, defaults to 50
        offset: filtered items to skip, at least 0, defaults to 0

    Returns:
        Item-list context or JSON validation error.

    """
    try:
        before = utils.parse_date(flask.request.args.get("before"))
    except ValueError:
        return {
            "errors": ["before must be an ISO 8601 date string"],
        }, base.HTTP_CODE_BAD_REQUEST
    try:
        limit = _parse_query_int(
            "limit",
            ctx.DEFAULT_PAGE_LIMIT,
            minimum=1,
            maximum=ctx.MAX_PAGE_LIMIT,
        )
        offset = _parse_query_int("offset", 0, minimum=0)
    except ValueError as error:
        return {"errors": [str(error)]}, base.HTTP_CODE_BAD_REQUEST
    with web.db.begin_session():
        return ctx.items(before=before, limit=limit, offset=offset)


def json_new() -> ctx.ItemContext | base.JSONResponse:
    """POST new item.

    Returns:
        Created item context or JSON validation error.

    """
    with web.db.begin_session() as session:
        payload: ctx.ItemContext = flask.request.json
        payload, errors = utils.validate_json(payload, ctx.ItemContext)
        if errors:
            return {"errors": errors}, base.HTTP_CODE_BAD_REQUEST
        try:
            with session.begin_nested():
                item = Item.create(
                    name=payload["name"].strip(),
                    date_ord=datetime.datetime.now(datetime.UTC).date().toordinal(),
                    value=payload["value"],
                    note=payload["note"],
                )
        except (exc.IntegrityError, exc.InvalidORMValueError) as error:
            return {"errors": [str(error)]}, base.HTTP_CODE_BAD_REQUEST
        return ctx.item(item)


def json_get(uri: str) -> ctx.ItemContext | base.JSONResponse:
    """GET item by URI.

    Args:
        uri: Item URI

    Returns:
        Item context or JSON error response.

    """
    with web.db.begin_session():
        try:
            return ctx.item(base.find(Item, uri))
        except exc.http.HTTPException as error:
            return {"errors": [str(error)]}, error.code or base.HTTP_CODE_INTERNAL_ERROR


def json_put(uri: str) -> ctx.ItemContext | base.JSONResponse:
    """PUT an item by URI.

    Args:
        uri: Item URI

    Returns:
        Updated item context or JSON error response.

    """
    with web.db.begin_session() as session:
        try:
            item = base.find(Item, uri)
        except exc.http.HTTPException as error:
            return {"errors": [str(error)]}, error.code or base.HTTP_CODE_INTERNAL_ERROR
        payload: ctx.ItemContext = flask.request.json
        payload, errors = utils.validate_json(payload, ctx.ItemContext)
        if errors:
            return {"errors": errors}, base.HTTP_CODE_BAD_REQUEST
        try:
            with session.begin_nested():
                item.name = payload["name"]
                item.date_ord = datetime.datetime.now(datetime.UTC).date().toordinal()
                item.value = payload["value"]
                item.note = payload["note"]
        except (exc.IntegrityError, exc.InvalidORMValueError) as error:
            return {"errors": [str(error)]}, base.HTTP_CODE_BAD_REQUEST
        return ctx.item(item)


def json(uri: str) -> ctx.ItemContext | base.JSONResponse:
    """GET or PUT an item by URI.

    Args:
        uri: Item URI

    Returns:
        Item context or JSON error response.

    """
    match flask.request.method:
        case "GET":
            return json_get(uri)
        case "PUT":
            return json_put(uri)
        case _:
            raise NotImplementedError


ROUTE_PREFIX = "items"
ROUTES: base.Routes = {
    "/j/items": (json_all, ["GET"]),
    "/j/items/new": (json_new, ["POST"]),
    "/j/items/i/<path:uri>": (json, ["GET", "PUT"]),
}

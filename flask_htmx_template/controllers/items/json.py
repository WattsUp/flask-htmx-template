"""Item JSON controllers."""

from __future__ import annotations

import datetime

import flask

from flask_htmx_template import exceptions as exc
from flask_htmx_template import web
from flask_htmx_template.controllers import base, json_api
from flask_htmx_template.controllers.items import ctx
from flask_htmx_template.models.item import Item


def json_all() -> ctx.ItemsContext | base.JSONResponse:
    """GET all items.

    Returns:
        Item-list context or JSON validation error.

    """
    args, errors = json_api.args(ctx.ItemsQuery)
    if errors:
        return {"errors": errors}, base.HTTP_CODE_BAD_REQUEST
    with web.db.begin_session():
        return ctx.items(
            before=args.before,
            limit=args.limit,
            offset=args.offset,
        )


def json_new() -> ctx.ItemContext | base.JSONResponse:
    """POST new item.

    Returns:
        Created item context or JSON validation error.

    """
    payload, errors = json_api.body(ctx.ItemContext)
    if errors:
        return {"errors": errors}, base.HTTP_CODE_BAD_REQUEST
    with web.db.begin_session() as session:
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
        payload, errors = json_api.body(ctx.ItemContext)
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

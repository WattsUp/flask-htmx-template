"""Item controllers."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict

import flask

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql, utils, web
from flask_htmx_template.controllers import base
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:

    import werkzeug


class ItemContext(TypedDict):
    """Type definition for Item context."""

    uri: str | None
    name: str
    value: Decimal
    date: datetime.date
    note: str | None


class AllItemsContext(TypedDict):
    """Context for page_all Items."""

    total: Decimal
    items_: list[ItemContext]


def page_all() -> flask.Response:
    """GET all items page.

    Returns:
        string HTML response

    """
    with web.db.begin_session():
        return base.page(
            "items/page-all.jinja",
            "Items",
            ctx=ctx_items(),
        )


def page(uri: str) -> flask.Response:
    """GET item page.

    Args:
        uri: Item URI

    Returns:
        string HTML response

    """
    with web.db.begin_session():
        item = base.find(Item, uri)
        title = item.name

        return base.page(
            "items/page.jinja",
            title=title,
            item=ctx_item(item),
        )


def new() -> str | flask.Response:
    """GET & POST new item dialog.

    Returns:
        HTML response

    """
    today = datetime.datetime.now(datetime.UTC).date()
    with web.db.begin_session() as s:
        if flask.request.method == "GET":
            ctx: ItemContext = {
                "uri": None,
                "name": "",
                "date": today,
                "value": Decimal(),
                "note": None,
            }
            return flask.render_template(
                "items/edit.jinja",
                item=ctx,
            )

        form = flask.request.form
        name = form["name"].strip()
        value = Decimal(form["value"])
        note = form["note"].strip()

        try:
            with s.begin_nested():
                Item.create(
                    name=name,
                    date_ord=today.toordinal(),
                    value=value,
                    note=note,
                )
        except (exc.IntegrityError, exc.InvalidORMValueError) as e:
            return base.error(e)

        return base.dialog_swap(event="item", snackbar="All changes saved")


def item(uri: str) -> str | werkzeug.Response:
    """GET, PUT, DELETE item edit dialog.

    Args:
        uri: Item URI

    Returns:
        string HTML response

    """
    with web.db.begin_session() as s:
        item = base.find(Item, uri)

        if flask.request.method == "GET":
            return flask.render_template(
                "items/edit.jinja",
                item=ctx_item(item),
            )
        if flask.request.method == "DELETE":
            with s.begin_nested():
                item.delete()
            return flask.redirect(flask.url_for("items.page_all"))

        form = flask.request.form
        name = form["name"].strip()
        value = Decimal(form["value"])
        note = form["note"].strip()
        today = datetime.datetime.now(datetime.UTC).date()

        try:
            with s.begin_nested():
                item.name = name
                item.date_ord = today.toordinal()
                item.value = value
                item.note = note
        except (exc.IntegrityError, exc.InvalidORMValueError) as e:
            return base.error(e)

        return base.dialog_swap(event="item", snackbar="All changes saved")


def validation() -> str:
    """GET validation for items UI.

    Returns:
        string HTML response

    """
    # dict{key: (required, prop if unique required)}
    properties: dict[str, tuple[bool, sql.Column | None]] = {
        "name": (True, Item.name),
        "note": (False, None),
    }

    args = flask.request.args
    if "value" in args:
        return base.validate_real(args["value"], is_required=True)

    with web.db.begin_session():
        uri = args.get("uri")
        for key, (required, prop) in properties.items():
            if key not in args:
                continue
            return base.validate_string(
                args[key],
                is_required=required,
                duplicate=(
                    None
                    if prop is None
                    else base.DuplicateCheck(
                        cls=Item,
                        column=prop,
                        extra_wheres=(
                            None if uri is None else [Item.id_ != Item.uri_to_id(uri)]
                        ),
                    )
                ),
            )

    raise NotImplementedError


def json_all() -> AllItemsContext | base.JSONResponse:
    """GET all items via JSON.

    Returns:
        JSON response

    """
    with web.db.begin_session():
        return ctx_items()


def json_new() -> ItemContext | base.JSONResponse:
    """POST new item via JSON.

    Returns:
        JSON response

    """
    today = datetime.datetime.now(datetime.UTC).date()
    with web.db.begin_session() as s:
        today = datetime.datetime.now(datetime.UTC).date()
        j: ItemContext = flask.request.json
        j["uri"] = ""
        j["date"] = today
        j, e = utils.validate_json(j, ItemContext)
        if e:
            return {"errors": e}, base.HTTP_CODE_BAD_REQUEST

        try:
            with s.begin_nested():
                item = Item.create(
                    name=j["name"].strip(),
                    date_ord=today.toordinal(),
                    value=j["value"],
                    note=j["note"],
                )
        except (exc.IntegrityError, exc.InvalidORMValueError) as e:
            return {"errors": [str(e)]}, base.HTTP_CODE_BAD_REQUEST

        return ctx_item(item)


def json(uri: str) -> ItemContext | base.JSONResponse:
    """GET & PUT settings via JSON.

    Args:
        uri: Item URI

    Returns:
        JSON response

    """
    with web.db.begin_session() as s:
        try:
            item = base.find(Item, uri)
        except exc.http.HTTPException as e:
            return {"errors": [str(e)]}, e.code or base.HTTP_CODE_INTERNAL_ERROR

        if flask.request.method == "PUT":
            today = datetime.datetime.now(datetime.UTC).date()
            j: ItemContext = flask.request.json
            j["uri"] = uri
            j["date"] = today
            j, e = utils.validate_json(j, ItemContext)
            if e:
                return {"errors": e}, base.HTTP_CODE_BAD_REQUEST

            try:
                with s.begin_nested():
                    item.name = j["name"]
                    item.date_ord = today.toordinal()
                    item.value = j["value"]
                    item.note = j["note"]
            except (exc.IntegrityError, exc.InvalidORMValueError) as e:
                return {"errors": [str(e)]}, base.HTTP_CODE_BAD_REQUEST

        return ctx_item(item)


def ctx_item(
    item: Item,
) -> ItemContext:
    """Get the context to build the item details.

    Args:
        item: Item to generate context for

    Returns:
        Dictionary HTML context

    """
    return {
        "uri": item.uri,
        "name": item.name,
        "date": item.date,
        "value": item.value,
        "note": item.note,
    }


def ctx_items() -> AllItemsContext:
    """Get the context to build the items table.

    Returns:
        AllItemsContext

    """
    total = Decimal()

    items: list[ItemContext] = []

    query = Item.query().order_by(Item.date_ord)
    for item in sql.yield_(query):
        items.append(ctx_item(item))
        total += item.value

    return {
        "total": total,
        "items_": items,
    }


ROUTES: base.Routes = {
    "/items": (page_all, ["GET"]),
    "/items/<path:uri>": (page, ["GET"]),
    "/h/items/new": (new, ["GET", "POST"]),
    "/h/items/i/<path:uri>": (item, ["GET", "PUT", "DELETE"]),
    "/h/items/validation": (validation, ["GET"]),
    "/j/items": (json_all, ["GET"]),
    "/j/items/new": (json_new, ["POST"]),
    "/j/items/i/<path:uri>": (json, ["GET", "PUT"]),
}

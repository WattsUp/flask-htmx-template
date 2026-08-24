"""Item HTML controllers."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import flask

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql, web
from flask_htmx_template.controllers import base, json_api
from flask_htmx_template.controllers.items import ctx
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    import werkzeug


def page_all() -> flask.Response:
    """GET all items page.

    Query args:
        before: Filter items that appear before this date, optional
        limit: Maximum items to return, 1 to 100, defaults to 50
        offset: Filtered items to skip, at least 0, defaults to 0

    Returns:
        Rendered all-items page.

    Raises:
        BadRequest: If a query argument is invalid.

    """
    query_args = flask.request.args.to_dict()
    # NOTE: An empty date input is submitted as ``before=`` by the browser, but
    # an empty filter has always meant no date cutoff in the HTML interface.
    if not query_args.get("before"):
        query_args.pop("before", None)
    args, errors = json_api.args(ctx.ItemsQuery, query_args=query_args)
    if errors:
        raise exc.http.BadRequest("; ".join(errors))
    with web.db.begin_session():
        return base.page(
            "items/page-all.jinja",
            "Items",
            before="" if args.before is None else args.before.isoformat(),
            limit=args.limit,
            offset=args.offset,
            ctx=ctx.items(
                before=args.before,
                limit=args.limit,
                offset=args.offset,
            ),
        )


def page(uri: str) -> flask.Response:
    """GET item page.

    Returns:
        Rendered item page.

    """
    with web.db.begin_session():
        item = base.find(Item, uri)
        return base.page("items/page.jinja", title=item.name, item=ctx.item(item))


def new() -> str | flask.Response:
    """GET and POST new item dialog.

    Returns:
        Item editor, validation error, or update response.

    """
    today = datetime.datetime.now(datetime.UTC).date()
    with web.db.begin_session() as session:
        if flask.request.method == "GET":
            item: ctx.ItemPayload = {
                "name": "",
                "date": today,
                "value": Decimal(),
                "note": None,
            }
            return flask.render_template("items/edit.jinja", item=item)

        form = flask.request.form
        try:
            with session.begin_nested():
                Item.create(
                    name=form["name"].strip(),
                    date_ord=today.toordinal(),
                    value=Decimal(form["value"]),
                    note=form["note"].strip(),
                )
        except (exc.IntegrityError, exc.InvalidORMValueError) as error:
            return base.error(error)
        return base.dialog_swap(event="item", snackbar="All changes saved")


def item(uri: str) -> str | werkzeug.Response:
    """GET, PUT, and DELETE item edit dialog.

    Returns:
        Item editor, validation error, redirect, or update response.

    """
    with web.db.begin_session() as session:
        item_ = base.find(Item, uri)
        if flask.request.method == "GET":
            return flask.render_template("items/edit.jinja", item=ctx.item(item_))
        if flask.request.method == "DELETE":
            with session.begin_nested():
                item_.delete()
            return flask.redirect(flask.url_for("items.page_all"))

        form = flask.request.form
        try:
            with session.begin_nested():
                item_.name = form["name"].strip()
                item_.date_ord = datetime.datetime.now(datetime.UTC).date().toordinal()
                item_.value = Decimal(form["value"])
                item_.note = form["note"].strip()
        except (exc.IntegrityError, exc.InvalidORMValueError) as error:
            return base.error(error)
        return base.dialog_swap(event="item", snackbar="All changes saved")


def validation() -> str:
    """GET item UI validation.

    Returns:
        Validation response for the requested field.

    """
    properties: dict[str, tuple[bool, sql.Column | None]] = {
        "name": (True, Item.name),
        "note": (False, None),
    }
    args = flask.request.args
    if "value" in args:
        return base.validate_real(args["value"], is_required=True)

    with web.db.begin_session():
        # NOTE: New-item forms have no URI; treat an empty query value as absent.
        uri = args.get("uri") or None
        for key, (required, column) in properties.items():
            if key in args:
                return base.validate_string(
                    args[key],
                    is_required=required,
                    duplicate=(
                        None
                        if column is None
                        else base.DuplicateCheck(
                            cls=Item,
                            column=column,
                            extra_wheres=(
                                None
                                if uri is None
                                else [Item.id_ != Item.uri_to_id(uri)]
                            ),
                        )
                    ),
                )
    raise NotImplementedError


ROUTE_PREFIX = "items"
ROUTES: base.Routes = {
    "/items": (page_all, ["GET"]),
    "/items/<path:uri>": (page, ["GET"]),
    "/h/items/new": (new, ["GET", "POST"]),
    "/h/items/i/<path:uri>": (item, ["GET", "PUT", "DELETE"]),
    "/h/items/validation": (validation, ["GET"]),
}

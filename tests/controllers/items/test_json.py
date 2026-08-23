from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from flask_htmx_template.controllers import json_api
from flask_htmx_template.controllers.base import HTTP_CODE_BAD_REQUEST
from flask_htmx_template.controllers.items import ctx
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    import datetime

    from sqlalchemy import orm

    from tests.controllers.conftest import WebClient


def test_body_item_context_resolves_type_checking_datetime() -> None:
    payload, errors = json_api.body(
        ctx.ItemContext,
        {
            "name": "New name",
            "value": "1234",
            "date": "2026-08-22",
            "note": None,
        },
    )

    assert not errors
    assert type(payload.get("date")).__name__ == "date"


def test_get_all(web_client: WebClient, item: Item) -> None:
    result, _ = web_client.GET_J("items.json_all")
    target = {
        "count": 1,
        "total": 0,
        "next_offset": None,
        "items": [
            {
                "uri": item.uri,
                "name": item.name,
                "date": item.date.isoformat(),
                "value": 0,
                "note": item.note,
            },
        ],
    }
    assert result == target


def test_get_all_before_filters_items_and_total(
    web_client: WebClient,
    item: Item,
    session: orm.Session,
    today_ord: int,
) -> None:
    with session.begin_nested():
        older = Item.create(
            name="Apples",
            date_ord=today_ord - 1,
            value=Decimal(2),
        )
        Item.create(
            name="Cherries",
            date_ord=today_ord + 1,
            value=Decimal(3),
        )

    result, _ = web_client.GET_J(
        "items.json_all",
        query_string={"before": item.date.isoformat()},
    )

    assert result == {
        "count": 1,
        "total": 2,
        "next_offset": None,
        "items": [
            {
                "uri": older.uri,
                "name": older.name,
                "date": older.date.isoformat(),
                "value": 2,
                "note": older.note,
            },
        ],
    }


def test_get_all_before_rejects_invalid_date(web_client: WebClient) -> None:
    result, _ = web_client.GET_J(
        "items.json_all",
        query_string={"before": "not-a-date"},
        rc=HTTP_CODE_BAD_REQUEST,
    )

    assert result == {"errors": ["before must be an ISO 8601 date string"]}


def test_get_all_limit_and_offset_paginate_items(
    web_client: WebClient,
    item: Item,
    session: orm.Session,
    today_ord: int,
) -> None:
    with session.begin_nested():
        Item.create(name="Apples", date_ord=today_ord - 1, value=Decimal(2))
        Item.create(name="Cherries", date_ord=today_ord + 1, value=Decimal(3))

    result, _ = web_client.GET_J(
        "items.json_all",
        query_string={"limit": 1, "offset": 1},
    )

    assert result == {
        "count": 3,
        "items": [
            {
                "uri": item.uri,
                "name": item.name,
                "date": item.date.isoformat(),
                "value": 0,
                "note": item.note,
            },
        ],
        "next_offset": 2,
        "total": 0,
    }


@pytest.mark.parametrize(
    ("query_string", "message"),
    [
        ({"limit": "invalid"}, "limit must be an integer"),
        (
            {"limit": 0},
            f"limit must be between 1 and {ctx.MAX_PAGE_LIMIT}",
        ),
        (
            {"limit": ctx.MAX_PAGE_LIMIT + 1},
            f"limit must be between 1 and {ctx.MAX_PAGE_LIMIT}",
        ),
        ({"offset": "invalid"}, "offset must be an integer"),
        ({"offset": -1}, "offset must be at least 0"),
    ],
)
def test_get_all_rejects_invalid_pagination(
    web_client: WebClient,
    query_string: dict[str, object],
    message: str,
) -> None:
    result, _ = web_client.GET_J(
        "items.json_all",
        query_string=query_string,
        rc=HTTP_CODE_BAD_REQUEST,
    )

    assert result == {"errors": [message]}


def test_get_all_collects_query_errors(web_client: WebClient) -> None:
    result, _ = web_client.GET_J(
        "items.json_all",
        query_string={
            "before": "not-a-date",
            "limit": 0,
            "offset": -1,
            "unknown": "value",
        },
        rc=HTTP_CODE_BAD_REQUEST,
    )

    assert result == {
        "errors": [
            "before must be an ISO 8601 date string",
            f"limit must be between 1 and {ctx.MAX_PAGE_LIMIT}",
            "offset must be at least 0",
            "unknown is not recognized",
        ],
    }


def test_get(web_client: WebClient, item: Item, session: orm.Session) -> None:
    with session.begin_nested():
        item.value = Decimal("1.234567")
    result, _ = web_client.GET_J(("items.json", {"uri": item.uri}))
    target = {
        "uri": item.uri,
        "name": item.name,
        "date": item.date.isoformat(),
        "value": "1.234567",
        "note": item.note,
    }
    assert result == target


def test_new(
    web_client: WebClient,
    today: datetime.date,
) -> None:
    j = {
        "name": "New name",
        "value": "1234",
        "note": "New note",
    }
    result, _ = web_client.POST_J("items.json_new", json=j)
    item = Item.one()
    target = {
        "uri": item.uri,
        "name": "New name",
        "date": today.isoformat(),
        "value": Decimal(1234),
        "note": "New note",
    }
    assert result == target

    assert item.name == "New name"
    assert item.value == Decimal(1234)
    assert item.date == today
    assert item.note == "New note"


def test_edit(
    web_client: WebClient,
    item: Item,
    today: datetime.date,
) -> None:
    j = {
        "uri": item.uri,
        "name": "New name",
        "value": 1234,
        "date": item.date.isoformat(),
        "note": "New note",
    }
    result, _ = web_client.PUT_J(("items.json", {"uri": item.uri}), json=j)
    assert result == j

    item.refresh()
    assert item.name == "New name"
    assert item.value == Decimal(1234)
    assert item.date == today
    assert item.note == "New note"


def test_edit_empty(web_client: WebClient, item: Item) -> None:
    result, _ = web_client.PUT_J(
        ("items.json", {"uri": item.uri}),
        rc=HTTP_CODE_BAD_REQUEST,
        json={},
    )
    target = [
        "json.name is missing",
        "json.note is missing",
        "json.value is missing",
    ]
    assert result == {"errors": target}


def test_edit_invalid_name(
    web_client: WebClient,
    item: Item,
) -> None:
    j = {
        "uri": item.uri,
        "name": "a",
        "value": 1234,
        "date": item.date,
        "note": "New note",
    }
    result, _ = web_client.PUT_J(
        ("items.json", {"uri": item.uri}),
        json=j,
        rc=HTTP_CODE_BAD_REQUEST,
    )
    target = [
        "Item name must be at least 2 characters long",
    ]
    assert result == {"errors": target}


def test_new_empty(web_client: WebClient) -> None:
    result, _ = web_client.POST_J(
        "items.json_new",
        rc=HTTP_CODE_BAD_REQUEST,
        json={},
    )
    target = [
        "json.name is missing",
        "json.note is missing",
        "json.value is missing",
    ]
    assert result == {"errors": target}


def test_new_duplicate_name(web_client: WebClient, item: Item) -> None:
    j = {
        "name": item.name,
        "value": "1234",
        "note": "New note",
    }
    result, _ = web_client.POST_J(
        "items.json_new",
        rc=HTTP_CODE_BAD_REQUEST,
        json=j,
    )
    assert "errors" in result


def test_get_not_found(web_client: WebClient) -> None:
    result, _ = web_client.GET_J(
        ("items.json", {"uri": "bad-uri"}),
        rc=HTTP_CODE_BAD_REQUEST,
    )
    assert "errors" in result


def test_put_not_found(web_client: WebClient) -> None:
    result, _ = web_client.PUT_J(
        ("items.json", {"uri": "bad-uri"}),
        rc=HTTP_CODE_BAD_REQUEST,
        json={"name": "x", "value": "1", "note": ""},
    )
    assert "errors" in result

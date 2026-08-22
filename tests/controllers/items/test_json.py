from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from flask_htmx_template.controllers.base import HTTP_CODE_BAD_REQUEST
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    import datetime

    from sqlalchemy import orm

    from tests.controllers.conftest import WebClient


def test_get_all(web_client: WebClient, item: Item) -> None:
    result, _ = web_client.GET_J("items.json_all")
    target = {
        "total": 0,
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
        "total": 2,
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

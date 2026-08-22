from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from flask_htmx_template.controllers import base
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    import datetime

    from sqlalchemy import orm

    from tests.controllers.conftest import WebClient


def test_page_all(web_client: WebClient, item: Item) -> None:
    result, _ = web_client.GET("items.page_all")
    assert item.name in result


def test_page_all_before_filters_items(
    web_client: WebClient,
    item: Item,
    session: orm.Session,
    today_ord: int,
) -> None:
    with session.begin_nested():
        older = Item.create(name="Apples", date_ord=today_ord - 1)
        newer = Item.create(name="Cherries", date_ord=today_ord + 1)

    result, _ = web_client.GET(
        "items.page_all",
        query_string={"before": item.date.isoformat()},
    )

    assert older.name in result
    assert item.name not in result
    assert newer.name not in result
    assert f'value="{item.date.isoformat()}"' in result
    assert "hx-include=\"[name='before']\"" in result


def test_page_all_before_rejects_invalid_date(web_client: WebClient) -> None:
    result, _ = web_client.GET(
        "items.page_all",
        query_string={"before": "not-a-date"},
        rc=base.HTTP_CODE_BAD_REQUEST,
    )

    assert "before must be an ISO 8601 date string" in result


def test_page(web_client: WebClient, item: Item) -> None:
    result, _ = web_client.GET(("items.page", {"uri": item.uri}))
    assert item.name in result


def test_new_get(web_client: WebClient) -> None:
    result, _ = web_client.GET("items.new")
    assert "New item" in result
    assert "Save" in result
    assert "Delete" not in result


def test_new(
    web_client: WebClient,
    session: orm.Session,
    today: datetime.date,
) -> None:
    result, headers = web_client.POST(
        "items.new",
        data={
            "name": "New name",
            "value": "1234",
            "note": "New note",
        },
    )
    assert "snackbar.show" in result
    assert "All changes saved" in result
    assert "item" in headers["HX-Trigger"]

    item = Item.one()
    assert item.name == "New name"
    assert item.value == Decimal(1234)
    assert item.date == today
    assert item.note == "New note"


@pytest.mark.parametrize(
    ("name", "target"),
    [
        ("a", "Item name must be at least 2 characters long"),
        ("Bananas", "Item name must be unique"),
    ],
)
def test_new_error(
    web_client: WebClient,
    item: Item,
    name: str,
    target: str,
) -> None:
    result, _ = web_client.POST(
        "items.new",
        data={
            "name": name,
            "value": "1",
            "note": " ",
        },
    )
    assert result == base.error(target)


def test_item_get(
    web_client: WebClient,
    item: Item,
) -> None:
    result, _ = web_client.GET(("items.item", {"uri": item.uri}))
    assert item.name in result
    assert str(item.value) in result
    assert "Edit item" in result
    assert "Save" in result
    assert "Delete" in result


def test_item_edit(
    web_client: WebClient,
    session: orm.Session,
    item: Item,
    today: datetime.date,
) -> None:
    result, headers = web_client.PUT(
        ("items.item", {"uri": item.uri}),
        data={
            "name": "New name",
            "value": "1234",
            "note": "New note",
        },
    )
    assert "snackbar.show" in result
    assert "All changes saved" in result
    assert "item" in headers["HX-Trigger"]

    session.refresh(item)
    assert item.name == "New name"
    assert item.value == Decimal(1234)
    assert item.date == today
    assert item.note == "New note"


def test_item_edit_error(
    web_client: WebClient,
    item: Item,
) -> None:
    result, _ = web_client.PUT(
        ("items.item", {"uri": item.uri}),
        data={
            "name": "a",
            "value": "1234",
            "note": " ",
        },
    )
    assert result == base.error("Item name must be at least 2 characters long")


def test_item_delete(web_client: WebClient, item: Item) -> None:
    result, headers = web_client.DELETE(("items.item", {"uri": item.uri}))
    assert not result
    assert headers["HX-Redirect"] == web_client.url_for("items.page_all")


@pytest.mark.parametrize(
    ("prop", "value", "target"),
    [
        ("name", "New Name", ""),
        ("name", " ", "Required"),
        ("name", "a", "2 characters required"),
        ("name", "Bananas", ""),
        ("note", "New Note", ""),
        ("note", " ", ""),
        ("note", "a", "2 characters required"),
        ("value", "1234", ""),
        ("value", " ", "Required"),
        ("value", "a", "Unable to parse"),
    ],
)
def test_validation(
    web_client: WebClient,
    item: Item,
    prop: str,
    value: str,
    target: str,
) -> None:
    result, _ = web_client.GET(
        (
            "items.validation",
            {"uri": item.uri, prop: value},
        ),
    )
    assert result == target


def test_validation_new_item_name_without_uri(
    web_client: WebClient,
    item: Item,
) -> None:
    result, _ = web_client.GET(
        ("items.validation", {"name": item.name}),
    )

    assert result == "Must be unique"


def test_validation_new_item_name_with_empty_uri(web_client: WebClient) -> None:
    result, _ = web_client.GET(
        ("items.validation", {"name": "New Name", "uri": ""}),
    )

    assert not result

from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template.controllers.items import ctx

if TYPE_CHECKING:
    from flask_htmx_template.models.item import Item


def test_ctx_item(item: Item) -> None:
    result = ctx.item(item)

    target: ctx.ItemContext = {
        "date": item.date,
        "name": item.name,
        "uri": item.uri,
        "value": item.value,
        "note": item.note,
    }
    assert result == target


def test_ctx_items(item: Item) -> None:
    result = ctx.items()

    target: ctx.ItemsContext = {
        "count": 1,
        "total": item.value,
        "next_offset": None,
        "items": [
            {
                "date": item.date,
                "name": item.name,
                "uri": item.uri,
                "value": item.value,
                "note": item.note,
            },
        ],
    }
    assert result == target


def test_ctx_items_excludes_items_on_or_after_before(item: Item) -> None:
    result = ctx.items(before=item.date)

    assert result == {
        "count": 0,
        "items": [],
        "next_offset": None,
        "total": 0,
    }


def test_ctx_items_returns_paginated_results(item: Item) -> None:
    result = ctx.items(limit=1)

    assert result["count"] == 1
    assert result["items"]
    assert result["next_offset"] is None
    assert result["total"] == item.value

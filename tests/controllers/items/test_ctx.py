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

from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template.controllers import items

if TYPE_CHECKING:
    from flask_htmx_template.models.item import Item


def test_ctx_item(item: Item) -> None:
    ctx = items.ctx_item(item)

    target: items.ItemContext = {
        "date": item.date,
        "name": item.name,
        "uri": item.uri,
        "value": item.value,
        "note": item.note,
    }
    assert ctx == target


def test_ctx_items(item: Item) -> None:
    ctx = items.ctx_items()

    target: items.AllItemsContext = {
        "total": item.value,
        "items_": [
            {
                "date": item.date,
                "name": item.name,
                "uri": item.uri,
                "value": item.value,
                "note": item.note,
            },
        ],
    }
    assert ctx == target

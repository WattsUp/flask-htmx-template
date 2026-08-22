"""Item template and JSON contexts."""

from __future__ import annotations

import datetime  # ruff: ignore[typing-only-standard-library-import]
from decimal import Decimal
from typing import Literal, NotRequired, TypedDict

from flask_htmx_template import sql
from flask_htmx_template.models.base import BaseEnum
from flask_htmx_template.models.item import Item


class ItemCategory(BaseEnum):
    """Category of an item."""

    GENERAL = 0
    SPECIAL = 1


class ItemContext(TypedDict):
    """Type definition for Item context."""

    # NOTE: ``utils.validate_json`` resolves these annotations at runtime.
    uri: NotRequired[str]
    name: str
    value: Decimal
    date: NotRequired[datetime.date]
    note: str | None
    category: NotRequired[ItemCategory]
    literal: NotRequired[Literal["a word"]]
    many: NotRequired[Literal[1, 2, 3]]


class AllItemsContext(TypedDict):
    """Context for all items."""

    total: Decimal
    items: list[ItemContext]


def item(item: Item) -> ItemContext:
    """Build an item context.

    Returns:
        Context for one item.

    """
    return {
        "uri": item.uri,
        "name": item.name,
        "date": item.date,
        "value": item.value,
        "note": item.note,
    }


def items(*, before: datetime.date | None = None) -> AllItemsContext:
    """Build the all-items context.

    Args:
        before: Exclude items on or after this date

    Returns:
        Context for all items and their total.

    """
    total = Decimal()
    result: list[ItemContext] = []
    query = Item.query().order_by(Item.date_ord)
    if before is not None:
        # NOTE: "before" is an exclusive cutoff, matching its plain-language meaning.
        query = query.where(Item.date_ord < before.toordinal())
    for item_ in sql.yield_(query):
        result.append(item(item_))
        total += item_.value
    return {"total": total, "items": result}

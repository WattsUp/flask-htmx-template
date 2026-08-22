"""Item template and JSON contexts."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, NotRequired, TYPE_CHECKING, TypedDict

from flask_htmx_template import sql
from flask_htmx_template.models import utils as model_utils
from flask_htmx_template.models.base import BaseEnum
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    import datetime


DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 100


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


class ItemsContext(TypedDict):
    """Context for all items."""

    total: Decimal
    items: list[ItemContext]

    count: int
    next_offset: int | None


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


def items(
    *,
    before: datetime.date | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> ItemsContext:
    """Build the all-items context.

    Args:
        before: Exclude items on or after this date
        limit: Maximum number of items to return, or None for all items
        offset: Number of filtered items to skip

    Returns:
        Context for all items and their total.

    """
    query = Item.query().order_by(Item.date_ord, Item.id_)
    if before is not None:
        # NOTE: "before" is an exclusive cutoff, matching its plain-language meaning.
        query = query.where(Item.date_ord < before.toordinal())
    if limit is None:
        result = [item(item_) for item_ in sql.yield_(query)]
        total = sum((item_["value"] for item_ in result), start=Decimal())
        return {
            "count": len(result),
            "items": result,
            "next_offset": None,
            "total": total,
        }

    page = model_utils.paginate(query, limit, offset)
    result = [item(item_) for item_ in page.results]
    total = sum((item_["value"] for item_ in result), start=Decimal())
    return {
        "count": page.count_,
        "items": result,
        "next_offset": page.next_offset,
        "total": total,
    }

"""Item template and JSON contexts."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, NamedTuple, NotRequired, TYPE_CHECKING, TypedDict

from pydantic import Field

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


class ItemFields(TypedDict):
    """Fields shared by serialized items and writable payloads."""

    name: str
    value: Decimal
    note: str | None


class ItemContext(ItemFields):
    """Canonical serialized item context."""

    uri: str
    date: datetime.date


# NOTE: Keep optional input and demonstration fields out of ItemContext so its
# exact output contract remains valid for JSON responses and MCP tools.
class ItemPayload(ItemFields):
    """Writable item fields accepted by the JSON API."""

    # NOTE: ``json_api.body()`` resolves these annotations at runtime.
    uri: NotRequired[str]
    date: NotRequired[datetime.date]
    category: NotRequired[ItemCategory]
    literal: NotRequired[Literal["a word"]]
    many: NotRequired[Literal[1, 2, 3]]


class ItemsContext(TypedDict):
    """Context for an item page and its pagination metadata."""

    total: Decimal
    items: list[ItemContext]

    count: int
    next_offset: int | None


class ItemsQuery(NamedTuple):
    """Query parameters for listing items."""

    # NOTE: ``json_api.args()`` resolves these annotations at runtime.
    before: datetime.date | None = None
    limit: Annotated[int, Field(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT
    offset: Annotated[int, Field(ge=0)] = 0


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
        Context for an item page, its pre-pagination match count, and its page total.

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

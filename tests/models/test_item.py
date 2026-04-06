from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    import datetime

    from tests.conftest import RandomStringGenerator


def test_init_properties(
    rand_str_generator: RandomStringGenerator,
    today: datetime.date,
    today_ord: int,
) -> None:
    d = {
        "name": rand_str_generator(),
        "date_ord": today_ord,
        "note": rand_str_generator(),
    }
    obj = Item.create(**d)

    assert obj.name == d["name"]
    assert obj.date_ord == d["date_ord"]
    assert obj.date == today
    assert obj.note == d["note"]


def test_short(item: Item) -> None:
    with pytest.raises(exc.InvalidORMValueError):
        item.name = "a"

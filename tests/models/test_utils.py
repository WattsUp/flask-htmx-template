from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from flask_htmx_template.models import utils
from flask_htmx_template.models.item import Item
from flask_htmx_template.utils import MIN_STR_LEN

if TYPE_CHECKING:
    from tests.conftest import RandomStringGenerator


@pytest.fixture
def items(
    rand_str_generator: RandomStringGenerator,
    today_ord: int,
) -> list[Item]:
    for _ in range(10):
        Item.create(
            name=rand_str_generator(),
            date_ord=today_ord,
        )
    return Item.all()


def test_paginate_all(items: list[Item]) -> None:
    page, count, next_offset = utils.paginate(Item.query(), 50, 0)
    assert page == items
    assert count == len(items)
    assert next_offset is None


@pytest.mark.parametrize("offset", range(10))
def test_paginate_three(
    items: list[Item],
    offset: int,
) -> None:
    page, count, next_offset = utils.paginate(Item.query(), 3, offset)
    assert page == items[offset : offset + 3]
    assert count == len(items)
    if offset >= (len(items) - 3):
        assert next_offset is None
    else:
        assert next_offset == offset + 3


def test_paginate_three_page_1000(items: list[Item]) -> None:
    page, count, next_offset = utils.paginate(Item.query(), 3, 1000)
    assert page == []
    assert count == len(items)
    assert next_offset is None


def test_paginate_three_page_n1000(items: list[Item]) -> None:
    page, count, next_offset = utils.paginate(Item.query(), 3, -1000)
    assert page == items[0:3]
    assert count == len(items)
    assert next_offset == 3


def test_dump_table_configs() -> None:
    result = utils.dump_table_configs(Item)
    assert result[0] == "CREATE TABLE item ("
    assert result[-1] == ")"
    assert "\t" not in "\n".join(result)


def test_get_constraints() -> None:
    target = [
        (UniqueConstraint, "name"),
        (CheckConstraint, f"length(name) >= {MIN_STR_LEN}"),
        (CheckConstraint, "name not like ' %' and name not like '% '"),
        (CheckConstraint, f"length(note) >= {MIN_STR_LEN}"),
        (CheckConstraint, "note not like ' %' and note not like '% '"),
        (ForeignKeyConstraint, "other_id"),
    ]
    assert utils.get_constraints(Item) == target

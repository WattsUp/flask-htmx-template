from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple, TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql
from flask_htmx_template.models import utils
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    from sqlalchemy import orm


@pytest.fixture(autouse=True)
def active_session(session: orm.Session) -> orm.Session:
    """Activate the shared ORM session for this module.

    Returns:
        Active ORM session.

    """
    return session


class RelatedItems(NamedTuple):
    """An item and the rows related to it through ``other_id``."""

    parent: Item
    children: list[Item]


@pytest.fixture
def related_items(session: orm.Session, today_ord: int) -> RelatedItems:
    """Create an item with two related rows.

    Returns:
        Parent item and its two related children.

    """
    with session.begin_nested():
        parent = Item.create(name="bulk-parent", date_ord=today_ord)
        children = [
            Item.create(
                name="bulk-child-one",
                date_ord=today_ord,
                note="original note",
                other_id=parent.id_,
            ),
            Item.create(
                name="bulk-child-two",
                date_ord=today_ord,
                note="second note",
                other_id=parent.id_,
            ),
        ]
    return RelatedItems(parent, children)


def test_update_rows_creates_missing_row(today_ord: int) -> None:
    utils.update_rows(
        Item,
        Item.name,
        {"bulk-new": {Item.date_ord: today_ord, Item.value: Decimal("1.25")}},
    )

    created = sql.one(Item.query().where(Item.name == "bulk-new"))
    assert created.date_ord == today_ord
    assert created.value == Decimal("1.25")


def test_update_rows_updates_existing_row(today_ord: int) -> None:
    existing = Item.create(
        name="bulk-existing",
        date_ord=today_ord,
        note="before",
    )

    utils.update_rows(
        Item,
        Item.id_,
        {
            existing.id_: {
                Item.note: "after",
                Item.value: Decimal("2.5"),
            },
        },
    )
    existing.refresh()

    assert existing.note == "after"
    assert existing.value == Decimal("2.5")


def test_update_rows_skips_unchanged_values(
    session: orm.Session,
    today_ord: int,
) -> None:
    existing = Item.create(
        name="bulk-unchanged",
        date_ord=today_ord,
        note="same",
    )

    utils.update_rows(
        Item,
        Item.id_,
        {existing.id_: {Item.note: "same"}},
    )

    assert not session.dirty
    existing.refresh()
    assert existing.note == "same"


def test_update_rows_assigns_explicit_none(today_ord: int) -> None:
    existing = Item.create(
        name="bulk-clear",
        date_ord=today_ord,
        note="present",
    )

    utils.update_rows(
        Item,
        Item.id_,
        {existing.id_: {Item.note: None}},
    )
    existing.refresh()

    assert existing.note is None


def test_update_rows_does_not_overwrite_selected_existing_values(
    today_ord: int,
) -> None:
    existing = Item.create(
        name="bulk-protected",
        date_ord=today_ord,
        note="keep me",
    )

    utils.update_rows(
        Item,
        Item.id_,
        {
            existing.id_: {
                Item.note: "replace me",
                Item.value: Decimal("3.75"),
            },
        },
        dont_overwrite={Item.note},
    )
    existing.refresh()

    assert existing.note == "keep me"
    assert existing.value == Decimal("3.75")


def test_update_rows_processes_multiple_batches(
    monkeypatch: pytest.MonkeyPatch,
    today_ord: int,
) -> None:
    existing = Item.create(name="bulk-batched-existing", date_ord=today_ord)
    updates: dict[int, utils.RowUpdate] = {
        existing.id_: {Item.note: "updated"},
        existing.id_
        + 1: {
            Item.name: "bulk-batched-new",
            Item.date_ord: today_ord,
        },
    }
    monkeypatch.setattr(utils, "N_BATCH", 2)

    utils.update_rows(Item, Item.id_, updates)
    existing.refresh()

    assert existing.note == "updated"
    assert Item.query().where(Item.name == "bulk-batched-new").one_or_none()


def test_update_rows_aborts_all_batches_on_integrity_error(
    monkeypatch: pytest.MonkeyPatch,
    today_ord: int,
) -> None:
    first = Item.create(name="bulk-conflict-one", date_ord=today_ord)
    second = Item.create(name="bulk-conflict-two", date_ord=today_ord)
    monkeypatch.setattr(utils, "N_BATCH", 1)

    with pytest.raises(exc.IntegrityError):
        utils.update_rows(
            Item,
            Item.id_,
            {
                first.id_: {Item.note: "must roll back"},
                second.id_: {Item.name: "bulk-conflict-one"},
            },
        )
    first.refresh()
    second.refresh()

    assert first.name == "bulk-conflict-one"
    assert first.note is None
    assert second.name == "bulk-conflict-two"


def test_update_rows_aborts_on_invalid_new_row(
    today_ord: int,
) -> None:
    with pytest.raises(exc.InvalidORMValueError):
        utils.update_rows(
            Item,
            Item.name,
            {"x": {Item.date_ord: today_ord}},
        )

    assert not Item.query().where(Item.name == "x").first()


def test_update_rows_list_deletes_all_rows_for_empty_list(
    related_items: RelatedItems,
) -> None:
    utils.update_rows_list(Item, Item.other_id, {related_items.parent.id_: []})

    assert (
        sql.count(
            Item.query().where(Item.other_id == related_items.parent.id_),
        )
        == 0
    )


def test_update_rows_list_deletes_leftovers_and_updates_first_row(
    related_items: RelatedItems,
    today_ord: int,
) -> None:
    utils.update_rows_list(
        Item,
        Item.other_id,
        {
            related_items.parent.id_: [
                {Item.name: "bulk-child-updated", Item.date_ord: today_ord},
            ],
        },
    )

    rows = list(
        Item.query()
        .where(Item.other_id == related_items.parent.id_)
        .order_by(Item.id_),
    )
    assert len(rows) == 1
    assert rows[0].name == "bulk-child-updated"


def test_update_rows_list_assigns_none_and_creates_remainder(
    related_items: RelatedItems,
    today_ord: int,
) -> None:
    utils.update_rows_list(
        Item,
        Item.other_id,
        {
            related_items.parent.id_: [
                {Item.name: "bulk-child-one-updated", Item.note: None},
                {Item.name: "bulk-child-two-updated", Item.note: "new note"},
                {Item.name: "bulk-child-three", Item.date_ord: today_ord},
            ],
        },
    )

    rows = list(
        Item.query()
        .where(Item.other_id == related_items.parent.id_)
        .order_by(Item.id_),
    )
    assert [row.name for row in rows] == [
        "bulk-child-one-updated",
        "bulk-child-two-updated",
        "bulk-child-three",
    ]
    assert rows[0].note is None
    assert rows[1].note == "new note"


def test_update_rows_list_does_not_overwrite_populated_values(
    related_items: RelatedItems,
) -> None:
    related_items.children[1].note = None
    updates: dict[int, list[utils.RowUpdate]] = {
        related_items.parent.id_: [
            {Item.note: "replacement"},
            {Item.note: "filled"},
        ],
    }

    utils.update_rows_list(
        Item,
        Item.other_id,
        updates,
        dont_overwrite={Item.note},
    )
    for child in related_items.children:
        child.refresh()

    assert related_items.children[0].note == "original note"
    assert related_items.children[1].note == "filled"


def test_update_rows_list_does_not_mutate_updates(
    related_items: RelatedItems,
) -> None:
    updates: dict[int, list[utils.RowUpdate]] = {
        related_items.parent.id_: [
            {Item.name: "bulk-child-copy-one"},
            {Item.name: "bulk-child-copy-two"},
        ],
    }
    expected = {
        related_items.parent.id_: [
            {Item.name: "bulk-child-copy-one"},
            {Item.name: "bulk-child-copy-two"},
        ],
    }

    utils.update_rows_list(Item, Item.other_id, updates)

    assert updates == expected


def test_update_rows_list_aborts_all_changes_on_integrity_error(
    related_items: RelatedItems,
) -> None:
    with pytest.raises(exc.IntegrityError):
        utils.update_rows_list(
            Item,
            Item.other_id,
            {
                related_items.parent.id_: [
                    {Item.note: "must roll back"},
                    {Item.name: related_items.parent.name},
                ],
            },
        )
    for child in related_items.children:
        child.refresh()

    assert related_items.children[0].note == "original note"
    assert related_items.children[1].name == "bulk-child-two"

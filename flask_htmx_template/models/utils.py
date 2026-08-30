"""Common model helpers."""

from __future__ import annotations

import re
import sqlite3
from typing import Any, cast, NamedTuple, TYPE_CHECKING

import sqlalchemy
from packaging.version import Version
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    orm,
    UniqueConstraint,
)

from flask_htmx_template import sql

if TYPE_CHECKING:
    from sqlalchemy import Constraint

    from flask_htmx_template.models.base import Base


# NOTE: SQLite permits more bound parameters on newer versions; older versions
# limit statements to 999 parameters.
N_BATCH = 10_000 if Version(sqlite3.sqlite_version) > Version("3.32.0") else 999

RowUpdate = dict[orm.QueryableAttribute[object], object]


class Page[T](NamedTuple):
    """Paginatation page."""

    results: list[T]
    count_: int
    next_offset: int | None


def paginate[T: Base](
    query: orm.Query[T],
    limit: int,
    offset: int,
) -> Page[T]:
    """Paginate query response for smaller results.

    Args:
        query: Session query to execute to get results
        limit: Maximum number of results per page
        offset: Result offset, advances to subsequent pages

    Returns:
        Page (list of result from query), amount count for query, next_offset for
        subsequent calls (None if no more)

    """
    offset = max(0, offset)

    # Get amount number from filters
    count = sql.count(query)

    # Apply limiting, and offset
    query = query.limit(limit).offset(offset)

    results = list(sql.yield_(query))

    # Compute next_offset
    n_current = len(results)
    remaining = count - n_current - offset
    next_offset = offset + n_current if remaining > 0 else None

    return Page(results, count, next_offset)


def dump_table_configs(model: type[Base]) -> list[str]:
    """Get the table configs (columns and constraints) and print.

    Args:
        model: Filter to specific table

    Returns:
        List of lines used to create tables

    """
    stmt = f"""
        SELECT sql
        FROM sqlite_master
        WHERE
            type='table'
            AND name='{model.__tablename__}'
        """.strip()  # ruff: ignore[hardcoded-sql-expression]
    query: orm.query.RowReturningQuery[tuple[str]] = cast(
        "orm.query.RowReturningQuery[tuple[str]]",
        model.session().execute(sqlalchemy.text(stmt)),
    )
    result: str = sql.one(query)
    return [s.replace("\t", "    ") for s in result.splitlines()]


def get_constraints(
    model: type[Base],
) -> list[tuple[type[Constraint], str]]:
    """Get constraints of a table.

    Args:
        model: Filter to specific table

    Returns:
        list[(Constraint type, construction text)]

    """
    config = "\n".join(dump_table_configs(model))

    re_unique = re.compile(r"UNIQUE \(([^\)]+)\)")
    constraints: list[tuple[type[Constraint], str]] = [
        (UniqueConstraint, cols) for cols in re_unique.findall(config)
    ]

    re_check = re.compile(r'CONSTRAINT "[^"]+" CHECK \((.+)\),? *\n')
    constraints.extend(
        (CheckConstraint, sql_text) for sql_text in re_check.findall(config)
    )

    re_foreign = re.compile(r"FOREIGN KEY\((\w+)\) REFERENCES \w+ \(\w+\),? *\n")
    constraints.extend(
        (ForeignKeyConstraint, cols) for cols in re_foreign.findall(config)
    )

    return constraints


def _apply_bulk_row_updates[T](
    cls: type[Base],
    id_prop: orm.QueryableAttribute[object],
    to_update_ids: set[T],
    cases: dict[orm.QueryableAttribute[object], dict[T, object]],
) -> None:
    """Apply changed values with SQL CASE expressions.

    Args:
        cls: Row model to update
        id_prop: Property to identify rows with
        to_update_ids: Identifier values to update
        cases: Changed values grouped by property and identifier

    """
    if not to_update_ids:
        return

    cls.query().where(id_prop.in_(to_update_ids)).update(
        {
            key: sqlalchemy.type_coerce(
                sql.case(
                    {
                        id_value: sqlalchemy.type_coerce(value, key.type)
                        for id_value, value in whens.items()
                    },
                    value=id_prop,
                    else_=key,
                ),
                key.type,
            )
            for key, whens in cases.items()
            if whens
        },
    )


def _create_missing_rows[T](
    cls: type[Base],
    id_prop: orm.QueryableAttribute[object],
    updates: dict[T, RowUpdate],
) -> None:
    """Create rows that were not found by the existing-row query.

    Args:
        cls: Row model to update
        id_prop: Property to identify rows with
        updates: Missing rows grouped by identifier

    """
    for id_value, update in updates.items():
        row_update = update.copy()
        row_update[id_prop] = id_value
        kwargs = {key.key: value for key, value in row_update.items()}
        cls.create(**kwargs)


def _build_filtered_update(
    update: RowUpdate,
    keys: list[orm.QueryableAttribute[object]],
    row_values: tuple[object, ...],
    dont_overwrite: set[orm.QueryableAttribute[object]],
) -> RowUpdate:
    """Remove unchanged and protected values from one row update.

    Args:
        update: Requested property changes
        keys: Properties selected from the existing row
        row_values: Existing values in the same order as ``keys``
        dont_overwrite: Properties to preserve when already populated

    Returns:
        Changes that should be applied

    """
    result: RowUpdate = {}
    for key, row_value in zip(keys, row_values, strict=True):
        if key not in update:
            continue
        new_value = update[key]
        if key in dont_overwrite and row_value is not None:
            continue
        if row_value == new_value:
            continue
        result[key] = new_value
    return result


def _update_rows[T](
    cls: type[Base],
    id_prop: orm.QueryableAttribute[object],
    updates: dict[T, RowUpdate],
    dont_overwrite: set[orm.QueryableAttribute[object]] | None = None,
) -> None:
    """Apply one atomic set of row updates.

    Args:
        cls: Row model to update
        id_prop: Property to identify rows with
        updates: Mapping of id_value -> property changes
        dont_overwrite: Set of attributes to not set if existing

    """
    protected = dont_overwrite or set()
    pending = {id_value: update.copy() for id_value, update in updates.items()}
    key_set: set[orm.QueryableAttribute[object]] = set()
    for update in pending.values():
        key_set.update(update.keys())
    key_set.discard(id_prop)
    keys = list(key_set)

    # NOTE: Each CASE entry binds an identifier and value, and the WHERE IN
    # clause binds each identifier again.
    batch_size = max(1, N_BATCH // (2 * len(keys) + 1))
    id_values = list(pending.keys())
    for start in range(0, len(id_values), batch_size):
        batch = id_values[start : start + batch_size]
        cases: dict[orm.QueryableAttribute[object], dict[T, object]] = {
            key: {} for key in keys
        }
        to_update_ids: set[T] = set()

        query = cast(
            "orm.Query[tuple[object, ...]]",
            cls.query(id_prop, *keys),
        ).where(id_prop.in_(batch))
        for row in sql.yield_(query):
            id_value = cast("T", row[0])
            update = pending.pop(id_value)
            filtered_update = _build_filtered_update(
                update,
                keys,
                tuple(row[1:]),
                protected,
            )
            if not filtered_update:
                continue
            to_update_ids.add(id_value)
            for key, value in filtered_update.items():
                cases[key][id_value] = value

        _apply_bulk_row_updates(cls, id_prop, to_update_ids, cases)

    _create_missing_rows(cls, id_prop, pending)


def update_rows[T](
    cls: type[Base],
    id_prop: orm.QueryableAttribute[object],
    updates: dict[T, RowUpdate],
    dont_overwrite: set[orm.QueryableAttribute[object]] | None = None,
) -> None:
    """Update existing rows and create missing ones in bulk.

    The complete operation is wrapped in one savepoint. Any validation or
    database error rolls back every batch and is propagated to the caller.
    Call this helper inside ``Database.begin_session()`` so the model's active
    session is bound.

    Args:
        cls: Row model to update
        id_prop: Property to identify rows with
        updates: Mapping of id_value -> property changes
        dont_overwrite: Set of attributes to not set if existing

    """
    with cls.session().begin_nested():
        _update_rows(cls, id_prop, updates, dont_overwrite)


def _update_rows_list[T](
    cls: type[Base],
    id_prop: orm.QueryableAttribute[object],
    updates: dict[T, list[RowUpdate]],
    dont_overwrite: set[orm.QueryableAttribute[object]] | None = None,
) -> None:
    """Apply one atomic reconciliation of rows by identifier.

    Args:
        cls: Row model to update
        id_prop: Property to identify rows with
        updates: Mapping of id_value -> list of property changes (one per row)
        dont_overwrite: Set of attributes to not set if existing

    """
    protected = dont_overwrite or set()
    pending = {
        id_value: [update.copy() for update in update_list]
        for id_value, update_list in updates.items()
    }
    key_set: set[orm.QueryableAttribute[object]] = set()
    for update_list in pending.values():
        for update in update_list:
            key_set.update(update.keys())
    key_set.discard(id_prop)
    keys = list(key_set)

    id_values = list(pending.keys())
    for start in range(0, len(id_values), N_BATCH):
        batch = id_values[start : start + N_BATCH]
        query = cast(
            "orm.Query[tuple[object, ...]]",
            cls.query(id_prop, cls.id_, *keys),
        ).where(id_prop.in_(batch))
        for row in sql.yield_(query):
            id_value = cast("T", row[0])
            row_id = cast("int", row[1])
            update_list = pending[id_value]
            if not update_list:
                cls.query().where(cls.id_ == row_id).delete()
                continue

            update = update_list.pop(0)
            filtered_update = _build_filtered_update(
                update,
                keys,
                tuple(row[2:]),
                protected,
            )
            if filtered_update:
                update_values = cast("dict[Any, object]", filtered_update)
                cls.query().where(cls.id_ == row_id).update(
                    update_values,
                )

    for id_value, update_list in pending.items():
        for update in update_list:
            row_update = update.copy()
            row_update[id_prop] = id_value
            cls.create(**{key.key: value for key, value in row_update.items()})


def update_rows_list[T](
    cls: type[Base],
    id_prop: orm.QueryableAttribute[object],
    updates: dict[T, list[RowUpdate]],
    dont_overwrite: set[orm.QueryableAttribute[object]] | None = None,
) -> None:
    """Reconcile multiple rows for each identifier.

    Existing rows are updated in query order, surplus rows are deleted, and
    remaining updates are created. The complete operation is wrapped in one
    savepoint, so any failure rolls back all changes and propagates to the
    caller. Call this helper inside ``Database.begin_session()`` so the model's
    active session is bound.

    Args:
        cls: Row model to update
        id_prop: Property to identify rows with
        updates: Mapping of id_value -> list of property changes (one per row)
        dont_overwrite: Set of attributes to not set if existing

    """
    with cls.session().begin_nested():
        _update_rows_list(cls, id_prop, updates, dont_overwrite)

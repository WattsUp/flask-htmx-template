"""Common API Controller."""

from __future__ import annotations

import re
from typing import cast, NamedTuple, TYPE_CHECKING

import sqlalchemy
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    UniqueConstraint,
)

from flask_htmx_template import sql

if TYPE_CHECKING:
    from sqlalchemy import (
        Constraint,
        orm,
    )

    from flask_htmx_template.models.base import Base


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
        """.strip()  # noqa: S608
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

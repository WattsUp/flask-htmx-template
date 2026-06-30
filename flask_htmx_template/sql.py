"""SQL interface."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import cast, overload, TYPE_CHECKING

import sqlalchemy
import sqlalchemy.event
from sqlalchemy import func, orm
from sqlalchemy.sql import case

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator, Iterable
    from pathlib import Path


_ENGINE_ARGS: dict[str, object] = {}

# SSL mode for postgres connections. Set to "disable" in tests.
# Valid values: "require", "verify-ca", "verify-full", "disable", "allow", "prefer"
_POSTGRES_SSL_MODE: str = "require"

Column = (
    orm.InstrumentedAttribute[str]
    | orm.InstrumentedAttribute[str | None]
    | orm.InstrumentedAttribute[int]
    | orm.InstrumentedAttribute[int | None]
)
ColumnClause = sqlalchemy.ColumnElement[bool]

__all__ = ["case"]

_POSTGRES_PREFIXES = ("postgres://", "postgres+", "postgresql://", "postgresql+")


def is_postgres_url(s: str) -> bool:
    """Check if a string is a postgres connection URL.

    Args:
        s: String to check

    Returns:
        True if s looks like a postgres URL

    """
    return s.startswith(_POSTGRES_PREFIXES)


def normalize_postgres_url(url: str) -> str:
    """Normalize a postgres URL to a SQLAlchemy-compatible form.

    Converts the ``postgres`` scheme to ``postgresql`` and ensures the
    ``psycopg`` (v3) driver is specified if no driver is present.

    Args:
        url: postgres connection URL

    Returns:
        Normalized URL with ``postgresql+psycopg`` scheme

    """
    if url.startswith(("postgres://", "postgres+")):
        url = "postgresql" + url[len("postgres") :]

    # If no driver is specified, default to psycopg (v3)
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg" + url[len("postgresql") :]

    return url


@sqlalchemy.event.listens_for(sqlalchemy.engine.Engine, "connect")
def set_sqlite_pragma(db_connection: sqlite3.Connection, *_) -> None:
    """Set PRAGMA upon opening SQLite connection.

    Args:
        db_connection: Connection to SQLite DB

    """
    module = type(db_connection).__module__
    if "sqlite" not in module:
        return
    cursor = db_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(path: Path) -> sqlalchemy.engine.Engine:
    """Get sqlalchemy Engine to the database.

    Args:
        path: Path to database file

    Returns:
        sqlalchemy.Engine

    """
    db_path = (
        f"sqlite:///{path}"
        if sys.platform == "win32" or not path.is_absolute()
        else f"sqlite:////{path}"
    )
    return sqlalchemy.create_engine(db_path, **_ENGINE_ARGS)


def get_engine_postgres(url: str) -> sqlalchemy.engine.Engine:
    """Get sqlalchemy Engine for a postgres database.

    Args:
        url: SQLAlchemy-compatible postgres connection URL

    Returns:
        sqlalchemy.Engine

    """
    connect_args: dict[str, object] = {}
    if _POSTGRES_SSL_MODE:
        connect_args["sslmode"] = _POSTGRES_SSL_MODE
    return sqlalchemy.create_engine(
        normalize_postgres_url(url),
        connect_args=connect_args,
        **_ENGINE_ARGS,
    )


def escape(s: str) -> str:
    """Escape a string if it is reserved.

    Args:
        s: String to escape

    Returns:
        `s` if escaping is needed else s

    """
    return f'"{s}"' if s in sqlalchemy.sql.compiler.RESERVED_WORDS else s


@overload
def to_dict_tuple[K, T0, T1](
    query: orm.query.RowReturningQuery[tuple[K, T0, T1]],
) -> dict[K, tuple[T0, T1]]: ...


@overload
def to_dict_tuple[K, T0, T1, T2](
    query: orm.query.RowReturningQuery[tuple[K, T0, T1, T2]],
) -> dict[K, tuple[T0, T1, T2]]: ...


@overload
def to_dict_tuple[K, T0, T1, T2, T3](
    query: orm.query.RowReturningQuery[tuple[K, T0, T1, T2, T3]],
) -> dict[K, tuple[T0, T1, T2, T3]]: ...


def to_dict_tuple[T: tuple[object, ...]](  # type: ignore[attr-defined]
    query: orm.query.RowReturningQuery[T],
) -> dict[object, tuple[object, ...]]:
    """Fetch results from query and return a dict.

    Args:
        query: Query that returns 2 columns

    Returns:
        dict{first column: second column}
        or
        dict{first column: tuple(other columns)}

    """
    return {r[0]: r[1:] for r in yield_(query)}


def to_dict[K, V](
    query: orm.query.RowReturningQuery[tuple[K, V]],
) -> dict[K, V]:
    """Fetch results from query and return a dict.

    Args:
        query: Query that returns 2 columns

    Returns:
        dict{first column: second column}

    """
    return {r[0]: r[1] for r in yield_(query)}


def count[T](query: orm.Query[T]) -> int:
    """Count the number of result a query will return.

    Args:
        query: Session query to execute

    Returns:
        Number of instances query will return upon execution

    Raises:
        TypeError: if query.statement is not a Select

    """
    # From here:
    # https://datawookie.dev/blog/2021/01/sqlalchemy-efficient-counting/
    col_one: sqlalchemy.ColumnClause[object] = sqlalchemy.literal_column("1")
    stmt = query.statement
    if not isinstance(stmt, sqlalchemy.Select):
        raise TypeError
    counter = stmt.with_only_columns(
        func.count(col_one),
        maintain_column_froms=True,
    )
    counter = counter.order_by(None)
    return query.session.execute(counter).scalar() or 0  # flask_htmx_template: ignore


def any_[T](query: orm.Query[T]) -> bool:
    """Check if any rows exists in query.

    Args:
        query: Session query to execute

    Returns:
        True if any results

    """
    return count(query.limit(1)) != 0


@overload
def one[T0](
    query: orm.query.RowReturningQuery[tuple[T0]],
) -> T0: ...


@overload
def one[T0, T1](
    query: orm.query.RowReturningQuery[tuple[T0, T1]],
) -> tuple[T0, T1]: ...


@overload
def one[T](query: orm.Query[T]) -> T: ...


def one[T](query: orm.Query[T]) -> object:
    """Check if any rows exists in query.

    Args:
        query: Session query to execute

    Returns:
        One result

    """
    ret: T | Sequence[T] = query.one()  # flask_htmx_template: ignore
    if not isinstance(ret, Sequence):
        return ret
    seq = cast("Sequence[T]", ret)
    if len(seq) == 1:
        return seq[0]
    return seq[0:]


@overload
def scalar[T0](
    query: orm.query.RowReturningQuery[tuple[T0]],
) -> T0 | None: ...


@overload
def scalar[T0, T1](
    query: orm.query.RowReturningQuery[tuple[T0, T1]],
) -> T0 | None: ...


@overload
def scalar[T0, T1, T2](
    query: orm.query.RowReturningQuery[tuple[T0, T1, T2]],
) -> T0 | None: ...


@overload
def scalar[T](query: orm.Query[T]) -> T | None: ...


def scalar[T](query: orm.Query[T]) -> object | None:
    """Check if any rows exists in query.

    Args:
        query: Session query to execute

    Returns:
        One result

    """
    return query.scalar()  # flask_htmx_template: ignore


@overload
def yield_[T: tuple[object, ...]](
    query: orm.query.RowReturningQuery[T],
) -> Iterable[T]: ...


@overload
def yield_[T](query: orm.Query[T]) -> Iterable[T]: ...


def yield_[T](query: orm.Query[T]) -> Iterable[object]:
    """Yield a query.

    Args:
        query: Query to yield

    Yields:
        Rows

    """
    # Yield per instead of fetch all is faster
    for r in query.yield_per(100):  # flask_htmx_template: ignore
        yield r[0:] if isinstance(r, Sequence) else r


def col0[T](query: orm.query.RowReturningQuery[tuple[T]]) -> Generator[T]:
    """Yield a query into a list.

    Args:
        query: Query to yield

    Yields:
        first column

    """
    for (r,) in yield_(query):
        yield r

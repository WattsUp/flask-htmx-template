"""SQL interface."""

from __future__ import annotations

import inspect
import logging
import sqlite3
import sys
import time
from collections.abc import Sequence
from contextlib import contextmanager, suppress
from typing import cast, overload, TYPE_CHECKING

import sqlalchemy
import sqlalchemy.event
from sqlalchemy import func, orm
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import case

from flask_htmx_template import exceptions as exc
from flask_htmx_template import utils

if TYPE_CHECKING:
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

__all__ = ["case", "time_limit"]

logger = logging.getLogger(__name__)

_SQLITE_PROGRESS_INSTRUCTIONS = 2000

_POSTGRES_PREFIXES = ("postgres://", "postgres+", "postgresql://", "postgresql+")


@contextmanager
def _sqlite_time_limit(
    conn: sqlite3.Connection,
    timeout_ms: int,
    caller: inspect.FrameInfo,
    threshold_warning_ms: float,
) -> Generator[None, None, None]:
    """Limit work performed by a SQLite connection.

    Args:
        conn: Raw SQLite connection to limit
        timeout_ms: Time limit in milliseconds
        caller: First-party caller frame for diagnostics
        threshold_warning_ms: Minimum duration that should be logged

    Yields:
        Control to the operation being limited

    Raises:
        TimeoutError: If SQLite interrupts the operation after the deadline

    """
    deadline = time.perf_counter() + (timeout_ms / 1000)

    def handler() -> int:
        """Interrupt SQLite when the operation's deadline has passed.

        Returns:
            One when the deadline has passed, otherwise zero

        """
        return int(time.perf_counter() >= deadline)

    start = time.perf_counter()
    try:
        conn.set_progress_handler(handler, _SQLITE_PROGRESS_INSTRUCTIONS)
        yield
    except OperationalError as error:
        message = (
            "Session operation exceeded time limit - called from "
            f"{caller.filename}:{caller.lineno}"
        )
        raise TimeoutError(message) from error
    finally:
        conn.set_progress_handler(None, _SQLITE_PROGRESS_INSTRUCTIONS)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms >= threshold_warning_ms:
            logger.warning(
                "Query used %.0f ms of %d ms timeout (%.0f%%) - called from %s:%d",
                elapsed_ms,
                timeout_ms,
                elapsed_ms / timeout_ms * 100,
                caller.filename,
                caller.lineno,
            )


@contextmanager
def _psycopg_time_limit(
    session: orm.Session,
    timeout_ms: int,
    caller: inspect.FrameInfo,
    threshold_warning_ms: float,
) -> Generator[None, None, None]:
    """Limit statements executed by a PostgreSQL session.

    Args:
        session: SQLAlchemy session to limit
        timeout_ms: Time limit in milliseconds
        caller: First-party caller frame for diagnostics
        threshold_warning_ms: Minimum duration that should be logged

    Yields:
        Control to the operation being limited

    Raises:
        TimeoutError: If PostgreSQL cancels a statement after the deadline

    """
    sa_connection = session.connection()
    timing: dict[str, float] = {"start": 0.0, "max_ms": 0.0}

    def before_cursor_execute(*_args: object, **_kwargs: object) -> None:
        """Record the start of a statement."""
        timing["start"] = time.perf_counter()

    def after_cursor_execute(*_args: object, **_kwargs: object) -> None:
        """Record the longest statement duration."""
        elapsed_ms = (time.perf_counter() - timing["start"]) * 1000
        timing["max_ms"] = max(timing["max_ms"], elapsed_ms)

    sqlalchemy.event.listen(
        sa_connection,
        "before_cursor_execute",
        before_cursor_execute,
    )
    sqlalchemy.event.listen(
        sa_connection,
        "after_cursor_execute",
        after_cursor_execute,
    )
    try:
        session.execute(
            sqlalchemy.text(f"SET LOCAL statement_timeout = {timeout_ms}"),
        )
        yield
    except OperationalError as error:
        message = (
            "Session operation exceeded time limit - called from "
            f"{caller.filename}:{caller.lineno}"
        )
        raise TimeoutError(message) from error
    finally:
        sqlalchemy.event.remove(
            sa_connection,
            "before_cursor_execute",
            before_cursor_execute,
        )
        sqlalchemy.event.remove(
            sa_connection,
            "after_cursor_execute",
            after_cursor_execute,
        )
        # NOTE: A timed-out PostgreSQL transaction may already be aborted. In
        # that case rollback will restore the previous transaction-local setting.
        with suppress(Exception):
            session.execute(
                sqlalchemy.text("SET LOCAL statement_timeout = DEFAULT"),
            )
        max_statement_ms = timing["max_ms"]
        if max_statement_ms >= threshold_warning_ms:
            logger.warning(
                "Query used %.0f ms of %d ms timeout (%.0f%%) - called from %s:%d",
                max_statement_ms,
                timeout_ms,
                max_statement_ms / timeout_ms * 100,
                caller.filename,
                caller.lineno,
            )


@contextmanager
def time_limit(session: orm.Session, timeout_ms: int) -> Generator[None, None, None]:
    """Limit SQL work performed by an active session.

    The limit applies only while this context is active. SQLite uses a
    progress handler, while PostgreSQL uses its transaction-local
    ``statement_timeout`` setting. The timeout is approximate for SQLite and
    is measured per statement for PostgreSQL.

    Args:
        session: Active SQLAlchemy session to limit
        timeout_ms: Positive time limit in milliseconds

    Yields:
        Control to the operation being limited

    Raises:
        TypeError: If ``timeout_ms`` is not an integer or the session uses an
            unsupported database driver
        InvalidTimeoutError: If ``timeout_ms`` is not positive

    """
    if timeout_ms <= 0:
        msg = "timeout_ms must be positive"
        raise exc.InvalidTimeoutError(msg)

    # TimeoutError is explicitly raised by the dialect-specific implementations.
    raw_connection = session.connection().connection.driver_connection
    # NOTE: Skip both this generator and contextlib's __enter__ frame so the
    # fallback is the actual caller when it lives outside the package.
    caller = utils.first_party_caller(inspect.stack()[2:])
    threshold_warning_ms = 0.5 * timeout_ms

    if isinstance(raw_connection, sqlite3.Connection):
        with _sqlite_time_limit(
            raw_connection,
            timeout_ms,
            caller,
            threshold_warning_ms,
        ):
            yield
    elif "psycopg" in type(raw_connection).__module__:
        with _psycopg_time_limit(
            session,
            timeout_ms,
            caller,
            threshold_warning_ms,
        ):
            yield
    else:
        msg = "unsupported database driver for time_limit"
        raise TypeError(msg)


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
    return (
        query.session.execute(counter).scalar()  # flask_htmx_template: ignore[mixins]
        or 0
    )


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
    ret: T | Sequence[T] = query.one()  # flask_htmx_template: ignore[mixins]
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
    return query.scalar()  # flask_htmx_template: ignore[mixins]


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
    for r in query.yield_per(100):  # flask_htmx_template: ignore[mixins]
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

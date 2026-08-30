from __future__ import annotations

import inspect
import logging
import sqlite3
from typing import cast, TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import sqlalchemy.event
from sqlalchemy import orm, text
from sqlalchemy.exc import OperationalError

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from _pytest.logging import LogCaptureFixture


class ORMBase(orm.DeclarativeBase):
    id_: orm.Mapped[int] = orm.mapped_column(primary_key=True, autoincrement=True)

    def __repr__(self) -> str:
        try:
            return f"<{self.__class__.__name__} id={self.id_}>"
        except orm.exc.DetachedInstanceError:
            return f"<{self.__class__.__name__} id=Detached Instance>"


class Child(ORMBase):
    __tablename__ = "child"


class UnsupportedConnection:
    __module__ = "unsupported_driver"


class PsycopgConnection:
    __module__ = "psycopg.testing"


@pytest.fixture(autouse=True)
def session(session: orm.Session) -> orm.Session:
    """Activate the shared database session for this module.

    Returns:
        Active database session

    """
    return session


def test_get_engine(tmp_path: Path) -> None:
    # Absolute file
    path = (tmp_path / "absolute.db").absolute()
    e = sql.get_engine(path)
    s = orm.Session(e)
    assert "child" in ORMBase.metadata.tables
    ORMBase.metadata.create_all(s.get_bind())
    s.commit()
    assert b"SQLite" in path.read_bytes()


def test_escape_not_reserved() -> None:
    assert sql.escape("abc") == "abc"


def test_escape_reserved() -> None:
    assert sql.escape("where") == '"where"'


def test_to_dict() -> None:
    query = Config.query(Config.key, Config.value)
    result = sql.to_dict(query)
    assert isinstance(result, dict)
    assert all(isinstance(k, ConfigKey) for k in result)
    assert all(isinstance(v, str) for v in result.values())


def test_to_dict_tuple() -> None:
    query = Config.query(Config.id_, Config.key, Config.value)
    result = sql.to_dict_tuple(query)
    assert isinstance(result, dict)
    assert all(isinstance(k, int) for k in result)
    assert all(isinstance(v, tuple) for v in result.values())
    assert all(len(v) == 2 for v in result.values())
    assert all(isinstance(v[0], ConfigKey) for v in result.values())
    assert all(isinstance(v[1], str) for v in result.values())


def test_count() -> None:
    query = Config.query()
    assert sql.count(query) == query.count()


def test_any() -> None:
    assert sql.any_(Config.query())


def test_any_none() -> None:
    Config.query().delete()
    assert not sql.any_(Config.query())


def test_one() -> None:
    query = Config.query().where(
        Config.key == ConfigKey.VERSION,
    )
    result = sql.one(query)
    assert isinstance(result, Config)


def test_one_value() -> None:
    query = Config.query(Config.key).where(
        Config.key == ConfigKey.VERSION,
    )
    result = sql.one(query)
    assert isinstance(result, ConfigKey)


def test_one_tuple() -> None:
    query = Config.query(Config.key, Config.value).where(
        Config.key == ConfigKey.VERSION,
    )
    result = sql.one(query)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], ConfigKey)
    assert isinstance(result[1], str)


def test_scalar() -> None:
    query = Config.query().where(
        Config.key == ConfigKey.VERSION,
    )
    result = sql.scalar(query)
    assert isinstance(result, Config)


def test_scalar_value() -> None:
    query = Config.query(Config.key).where(
        Config.key == ConfigKey.VERSION,
    )
    result = sql.scalar(query)
    assert isinstance(result, ConfigKey)


def test_scalar_tuple() -> None:
    query = Config.query(Config.key, Config.value).where(
        Config.key == ConfigKey.VERSION,
    )
    result = sql.scalar(query)
    assert isinstance(result, ConfigKey)


def test_yield() -> None:
    query = Config.query().where()
    for r in sql.yield_(query):
        assert isinstance(r, Config)


def test_yield_value() -> None:
    query = Config.query(Config.key)
    for r in sql.yield_(query):
        assert isinstance(r, tuple)
        assert len(r) == 1
        assert isinstance(r[0], ConfigKey)


def test_yield_tuple() -> None:
    query = Config.query(Config.key, Config.value)
    for r in sql.yield_(query):
        assert isinstance(r, tuple)
        assert len(r) == 2
        assert isinstance(r[0], ConfigKey)
        assert isinstance(r[1], str)


def test_col0() -> None:
    query = Config.query(Config.key)
    for r in sql.col0(query):
        assert isinstance(r, ConfigKey)


def test_normalize_postgres_url_postgres_scheme() -> None:
    result = sql.normalize_postgres_url("postgres://user:pass@host/db")
    assert result == "postgresql+psycopg://user:pass@host/db"


def test_get_engine_postgres_no_ssl() -> None:
    original = sql._POSTGRES_SSL_MODE
    sql._POSTGRES_SSL_MODE = ""
    try:
        engine = sql.get_engine_postgres("postgresql+psycopg://user:pass@localhost/db")
        assert engine is not None
    finally:
        sql._POSTGRES_SSL_MODE = original


def test_set_sqlite_pragma_ignores_non_sqlite_connection() -> None:
    sql.set_sqlite_pragma(cast("sqlite3.Connection", object()))


def test_get_engine_postgres_ssl_mode() -> None:
    original = sql._POSTGRES_SSL_MODE
    sql._POSTGRES_SSL_MODE = "require"
    try:
        engine = sql.get_engine_postgres("postgresql+psycopg://user:pass@localhost/db")
        assert engine is not None
    finally:
        sql._POSTGRES_SSL_MODE = original


def test_time_limit_sqlite_completion(session: orm.Session) -> None:
    with sql.time_limit(session, 1_000):
        result = session.execute(text("SELECT 1")).scalar_one()

    assert result == 1


def test_time_limit_sqlite_timeout(session: orm.Session) -> None:
    query = text(
        "WITH RECURSIVE counter(value) AS ("
        "SELECT 1 UNION ALL SELECT value + 1 FROM counter) "
        "SELECT value FROM counter",
    )

    with (
        pytest.raises(TimeoutError, match="exceeded time limit"),
        sql.time_limit(
            session,
            1,
        ),
    ):
        list(session.execute(query))


def test_time_limit_sqlite_cleanup() -> None:
    connection = MagicMock(spec=sqlite3.Connection)
    caller = inspect.stack()[0]
    error = OperationalError(None, {}, RuntimeError("interrupted"))

    with (
        pytest.raises(TimeoutError),
        sql._sqlite_time_limit(
            connection,
            1_000,
            caller,
            500,
        ),
    ):
        raise error

    assert connection.set_progress_handler.call_count == 2
    connection.set_progress_handler.assert_any_call(None, 2_000)


def test_time_limit_sqlite_warning(
    session: orm.Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    timestamps = iter((0.0, 0.0, 0.6))
    monkeypatch.setattr(sql.time, "perf_counter", lambda: next(timestamps))

    with (
        caplog.at_level(
            logging.WARNING,
            logger=sql.__name__,
        ),
        sql.time_limit(session, 1_000),
    ):
        session.execute(text("SELECT 1")).scalar_one()

    assert any(
        "Query used 600 ms of 1000 ms timeout" in record.message
        for record in caplog.records
    )


@pytest.fixture
def postgres_session(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, dict[str, list[tuple[str, object]]]]:
    raw_connection = PsycopgConnection()
    sa_connection = MagicMock()
    sa_connection.connection.driver_connection = raw_connection
    session = MagicMock()
    session.connection.return_value = sa_connection
    events: dict[str, list[tuple[str, object]]] = {"listen": [], "remove": []}

    def listen(
        _target: object,
        identifier: str,
        callback: object,
    ) -> None:
        events["listen"].append((identifier, callback))

    def remove(
        _target: object,
        identifier: str,
        callback: object,
    ) -> None:
        events["remove"].append((identifier, callback))

    monkeypatch.setattr(sqlalchemy.event, "listen", listen)
    monkeypatch.setattr(sqlalchemy.event, "remove", remove)
    return session, events


def test_time_limit_postgres_completion(
    postgres_session: tuple[MagicMock, dict[str, list[tuple[str, object]]]],
) -> None:
    session, events = postgres_session

    with sql.time_limit(session, 1_000):
        session.execute(text("SELECT 1"))

    statements = [str(call.args[0]) for call in session.execute.call_args_list]
    assert statements == [
        "SET LOCAL statement_timeout = 1000",
        "SELECT 1",
        "SET LOCAL statement_timeout = DEFAULT",
    ]
    assert events["remove"] == events["listen"]


def test_time_limit_postgres_timeout(
    postgres_session: tuple[MagicMock, dict[str, list[tuple[str, object]]]],
) -> None:
    session, events = postgres_session
    session.execute.side_effect = [
        None,
        OperationalError("SELECT 1", {}, RuntimeError("cancelled")),
        None,
    ]

    with (
        pytest.raises(TimeoutError, match="exceeded time limit"),
        sql.time_limit(
            session,
            1_000,
        ),
    ):
        session.execute(text("SELECT 1"))

    assert len(events["remove"]) == 2
    assert events["remove"] == events["listen"]
    assert str(session.execute.call_args_list[-1].args[0]) == (
        "SET LOCAL statement_timeout = DEFAULT"
    )


def test_time_limit_postgres_warning(
    postgres_session: tuple[MagicMock, dict[str, list[tuple[str, object]]]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    session, events = postgres_session
    timestamps = iter((0.0, 0.6))
    monkeypatch.setattr(sql.time, "perf_counter", lambda: next(timestamps))

    def execute(statement: object) -> None:
        if str(statement) == "SELECT 1":
            callback = cast("Callable[..., object]", events["listen"][0][1])
            callback()

    session.execute.side_effect = execute

    with (
        caplog.at_level(
            logging.WARNING,
            logger=sql.__name__,
        ),
        sql.time_limit(session, 1_000),
    ):
        session.execute(text("SELECT 1"))
        callback = cast("Callable[..., object]", events["listen"][1][1])
        callback()

    assert any(
        "Query used 600 ms of 1000 ms timeout" in record.message
        for record in caplog.records
    )


@pytest.mark.parametrize("timeout_ms", [0, -1])
def test_time_limit_rejects_nonpositive_timeout(
    session: orm.Session,
    timeout_ms: int,
) -> None:
    with (
        pytest.raises(exc.InvalidTimeoutError, match="timeout_ms must be positive"),
        sql.time_limit(
            session,
            timeout_ms,
        ),
    ):
        pass


def test_time_limit_rejects_unsupported_driver() -> None:
    raw_connection = UnsupportedConnection()
    sa_connection = MagicMock()
    sa_connection.connection.driver_connection = raw_connection
    session = MagicMock()
    session.connection.return_value = sa_connection

    with (
        pytest.raises(TypeError, match="unsupported database driver"),
        sql.time_limit(
            session,
            1_000,
        ),
    ):
        pass

    session.execute.assert_not_called()

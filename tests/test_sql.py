from __future__ import annotations

from typing import cast, TYPE_CHECKING

import pytest
from sqlalchemy import orm

from flask_htmx_template import sql
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path


class ORMBase(orm.DeclarativeBase):
    id_: orm.Mapped[int] = orm.mapped_column(primary_key=True, autoincrement=True)

    def __repr__(self) -> str:
        try:
            return f"<{self.__class__.__name__} id={self.id_}>"
        except orm.exc.DetachedInstanceError:
            return f"<{self.__class__.__name__} id=Detached Instance>"


class Child(ORMBase):
    __tablename__ = "child"


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

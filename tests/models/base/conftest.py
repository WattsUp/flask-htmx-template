from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import ForeignKey, orm

from flask_htmx_template import sql
from flask_htmx_template.models.base import (
    Base,
    BaseEnum,
    Decimal6,
    ORMInt,
    ORMIntOpt,
    ORMRealOpt,
    ORMStrOpt,
    SQLEnum,
    string_column_args,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping
    from decimal import Decimal
    from pathlib import Path


class Bytes:
    """Byte-backed value used to test model comparisons."""

    def __init__(self, s: str) -> None:
        self._data = s.encode(encoding="utf-8")

    def __eq__(self, other: Bytes | object) -> bool:
        return isinstance(other, Bytes) and self._data == other._data

    def __hash__(self) -> int:
        return hash(self._data)


class Derived(BaseEnum):
    """Enum used by the base-model tests."""

    RED = 1
    BLUE = 2
    SEAFOAM_GREEN = 3

    @classmethod
    def lut(cls) -> Mapping[str, Derived]:
        return {"r": cls.RED, "b": cls.BLUE}


class Parent(Base, skip_register=True):
    """Parent model shared by base and mixin tests."""

    __tablename__ = "parent"
    __table_id__ = 0xF0000000

    generic_column: ORMIntOpt
    name: ORMStrOpt
    children: orm.Mapped[list[Child]] = orm.relationship(back_populates="parent")

    __table_args__ = (*string_column_args("name"),)

    _SEARCH_PROPERTIES = ("name",)

    @orm.validates("name")
    def validate_strings(self, key: str, field: str | None) -> str | None:
        return self.clean_strings(key, field)

    @property
    def favorite_child(self) -> Child | None:
        if len(self.children) < 1:
            return None
        return self.children[0]

    @property
    def uri_bytes(self) -> Bytes:
        return Bytes(self.uri)


class Child(Base, skip_register=True):
    """Child model shared by base and mixin tests."""

    __tablename__ = "child"
    __table_id__ = 0xE0000000

    parent_id: ORMInt = orm.mapped_column(ForeignKey("parent.id_"))
    parent: orm.Mapped[Parent] = orm.relationship(back_populates="children")
    name: ORMStrOpt

    height: ORMRealOpt = orm.mapped_column(Decimal6)

    color: orm.Mapped[Derived | None] = orm.mapped_column(SQLEnum(Derived))

    __table_args__ = (*string_column_args("name", lower_check=True),)

    @orm.validates("height")
    def validate_decimals(self, key: str, field: Decimal | None) -> Decimal | None:
        return self.clean_decimals(key, field)


class NoURI(Base, skip_register=True):
    """Model without a URI table identifier."""

    __tablename__ = "no_uri"
    __table_id__ = None


@pytest.fixture
def session(tmp_path: Path, uri_cipher: None) -> Generator[orm.Session]:
    """Create SQL session.

    Args:
        tmp_path: Temp path to create DB in
        uri_cipher: Initialize the URI cipher

    Yields:
        Session generator

    """
    path = tmp_path / "sql.db"
    s = orm.Session(sql.get_engine(path))
    with s.begin_nested():
        Base.metadata.create_all(
            s.get_bind(),
            tables=[Parent.sql_table(), Child.sql_table()],
        )
    with Base.set_session(s):
        yield s


@pytest.fixture
def parent(session: orm.Session) -> Parent:
    """Create a Parent.

    Returns:
        Parent

    """
    with session.begin_nested():
        return Parent.create()


@pytest.fixture
def child(session: orm.Session, parent: Parent) -> Child:
    """Create a Child.

    Returns:
        Child

    """
    with session.begin_nested():
        return Child.create(parent=parent)

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import ForeignKey, orm

import flask_htmx_template
import tests
from flask_htmx_template import exceptions as exc
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
from tests import conftest

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping

    from flask_htmx_template.models.base import (
        NamePair,
    )
    from tests.conftest import RandomStringGenerator


class Bytes:
    def __init__(self, s: str) -> None:
        self._data = s.encode(encoding="utf-8")

    def __eq__(self, other: Bytes | object) -> bool:
        return isinstance(other, Bytes) and self._data == other._data

    def __hash__(self) -> int:
        return hash(self._data)


class Derived(BaseEnum):
    RED = 1
    BLUE = 2
    SEAFOAM_GREEN = 3

    @classmethod
    def lut(cls) -> Mapping[str, Derived]:
        return {"r": cls.RED, "b": cls.BLUE}


class Parent(Base, skip_register=True):
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
    __tablename__ = "no_uri"
    __table_id__ = None


@pytest.fixture
def session(tmp_path: Path) -> Generator[orm.Session]:
    """Create SQL session.

    Args:
        tmp_path: Temp path to create DB in

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


def test_init_properties(parent: Parent) -> None:
    assert parent.id_ is not None
    assert parent.uri is not None
    assert Parent.uri_to_id(parent.uri) == parent.id_
    assert hash(parent) == parent.id_


def test_link_child(parent: Parent, child: Child) -> None:
    assert child.id_ is not None
    assert child.parent == parent
    assert child.parent_id == parent.id_


def test_wrong_uri_type(parent: Parent) -> None:
    with pytest.raises(exc.WrongURITypeError):
        Child.uri_to_id(parent.uri)


def test_set_decimal_none(session: orm.Session, child: Child) -> None:
    with session.begin_nested():
        child.height = None
    child.refresh()
    assert child.height is None


def test_set_decimal_value(session: orm.Session, child: Child) -> None:
    with session.begin_nested():
        height = Decimal("1.2")
    child.refresh()
    child.height = height
    assert isinstance(child.height, Decimal)
    assert child.height == height


def test_set_enum(session: orm.Session, child: Child) -> None:
    with session.begin_nested():
        child.color = Derived.RED
    child.refresh()
    assert isinstance(child.color, Derived)
    assert child.color == Derived.RED


def test_no_uri() -> None:
    no_uri = NoURI(id_=1)
    with pytest.raises(exc.NoURIError):
        _ = no_uri.uri


def test_comparators_same_session() -> None:
    parent_a = Parent.create()
    parent_b = Parent.create()

    assert parent_a == parent_a  # noqa: PLR0124
    assert parent_a != parent_b


def test_comparators_different_session(session: orm.Session, parent: Parent) -> None:
    # Make a new s to same DB
    with orm.create_session(bind=session.get_bind()) as session_2:
        # Get same parent_a but in a different Python object
        parent_a_queried = (
            session_2.query(Parent).where(Parent.id_ == parent.id_).first()
        )
        assert id(parent) != id(parent_a_queried)
        assert parent == parent_a_queried


def test_map_name_none() -> None:
    with pytest.raises(KeyError, match="Base does not have name column"):
        Base.map_name()


def test_map_name_parent(rand_str_generator: RandomStringGenerator) -> None:
    parent_a = Parent.create(name=rand_str_generator())
    parent_b = Parent.create(name=rand_str_generator())

    target = {
        parent_a.id_: parent_a.name,
        parent_b.id_: parent_b.name,
    }
    assert Parent.map_name() == target


def test_clean_strings_none(parent: Parent) -> None:
    parent.name = None
    assert parent.name is None


def test_clean_strings_empty(parent: Parent) -> None:
    parent.name = "    "
    assert parent.name is None


def test_clean_strings_good(
    parent: Parent,
    rand_str_generator: RandomStringGenerator,
) -> None:
    field = rand_str_generator(3)
    parent.name = field
    assert parent.name == field


def test_clean_strings_short(parent: Parent) -> None:
    with pytest.raises(exc.InvalidORMValueError):
        parent.name = "a"


def test_string_check_none(parent: Parent) -> None:
    with pytest.raises(exc.IntegrityError):
        Parent.query().where(Parent.id_ == parent.id_).update({Parent.name: ""})


def test_string_check_leading(parent: Parent) -> None:
    with pytest.raises(exc.IntegrityError):
        Parent.query().where(Parent.id_ == parent.id_).update(
            {Parent.name: " leading"},
        )


def test_string_check_trailing(parent: Parent) -> None:
    with pytest.raises(exc.IntegrityError):
        Parent.query().where(Parent.id_ == parent.id_).update(
            {Parent.name: "trailing "},
        )


def test_string_check_short(parent: Parent) -> None:
    with pytest.raises(exc.IntegrityError):
        Parent.query().where(Parent.id_ == parent.id_).update({Parent.name: "a"})


def test_lower(child: Child) -> None:
    with pytest.raises(exc.IntegrityError):
        Child.query().where(Child.id_ == child.id_).update({Child.name: "AAAA"})


def test_clean_decimals() -> None:
    child = Child()

    # Only 6 decimals
    height = Decimal("1.23456789")
    child.height = height
    assert child.height == Decimal("1.234567")


def test_query_kwargs() -> None:
    with pytest.raises(exc.NoKeywordArgumentsError):
        # Intentional bad argument
        Parent.query(kw=None)  # type: ignore[attr-defined]


def test_unbound_error() -> None:
    s = Base._sessions.pop()
    with pytest.raises(exc.UnboundExecutionError):
        Base.session()
    Base._sessions.append(s)


def noop[T](x: T) -> T:
    return x


def lower(s: str) -> str:
    return s.lower()


def upper(s: str) -> str:
    return s.upper()


@pytest.mark.parametrize(
    ("prop", "value_adjuster"),
    [
        ("uri", noop),
        ("name", noop),
        ("name", lower),
        ("name", upper),
    ],
)
def test_find(
    parent: Parent,
    prop: str,
    value_adjuster: Callable[[str], str],
) -> None:
    parent.name = "Fake"
    query = value_adjuster(getattr(parent, prop))

    cache: dict[str, NamePair] = {}

    result = Parent.find(query, cache)
    assert result.id_ == parent.id_
    assert result.name == parent.name

    assert cache == {query: result}

    # Test again for cache
    result = Parent.find(query, cache)
    assert result.id_ == parent.id_


def test_find_missing(parent: Parent) -> None:
    query = Parent.id_to_uri(parent.id_ + 1)

    cache: dict[str, NamePair] = {}
    with pytest.raises(exc.NoResultFound):
        Parent.find(query, cache)

    assert not cache


def test_delete(session: orm.Session, parent: Parent) -> None:
    with session.begin_nested():
        parent.delete()
    assert not sql.any_(Parent.query())


def test_all(parent: Parent) -> None:
    assert Parent.all() == [parent]


def test_one(parent: Parent) -> None:
    assert Parent.one() == parent


def test_first(parent: Parent) -> None:
    assert Parent.first() == parent


def test_count(parent: Parent) -> None:
    assert Parent.count() == 1


re_check_no_session_add = re.compile(r"^ *(s|session)\.add\(\w+\)")
re_check_no_model_new = re.compile(
    "|".join(rf"\b{m.__name__}\(" for m in Base._MODELS),
)
re_check_no_session_query = re.compile(r"[( ](s|session)\.query\(")
re_check_no_scalar_query = re.compile(r"(\w*)\.scalar\(")
re_check_no_query_one = re.compile(r"(\w*)\.one\(")
re_check_no_query_all = re.compile(r"(\w*)\.all\(")
re_check_no_query_col0 = re.compile(r"for \w+,? in query")


def check_no_session_add(line: str) -> str:
    if re_check_no_session_add.match(line):
        return "Use of session.add found, use Model.create()"
    return ""


def check_no_model_new(line: str) -> str:
    if not line.startswith("class") and re_check_no_model_new.search(line):
        return "Use of Model(...) found, use Model.create()"
    return ""


def check_no_session_query(line: str) -> str:
    if re_check_no_session_query.search(line):
        return "Use of session.query found, use Model.query()"
    return ""


def check_no_query_with_entities(line: str) -> str:
    if ".with_entities" in line:
        return "Use of with_entities found, use Model.query(col, ...)"
    return ""


def check_no_query_scalar(line: str) -> str:
    if (m := re_check_no_scalar_query.search(line)) and m.group(1) != "sql":
        return "Use of query.scalar found, use sql.scalar()"
    return ""


def check_no_query_one(line: str) -> str:
    if not (m := re_check_no_query_one.search(line)):
        return ""
    g = m.group(1)
    if (g and g[0] == g[0].upper()) or g == "sql":
        # use of Model.one()
        return ""
    return "Use of query.one found, use sql.one()"


def check_no_query_all(line: str) -> str:
    if not (m := re_check_no_query_all.search(line)):
        return ""
    g = m.group(1)
    if (g and g[0] == g[0].upper()) or g == "sql":
        # use of Model.all()
        return ""
    return "Use of query.all found, use sql.yield_()"


def check_no_query_col0(line: str) -> str:
    if re_check_no_query_col0.search(line):
        return "Use of first column iterator found, use sql.col0()"
    return ""


@pytest.mark.parametrize(
    "path",
    sorted(
        [
            *Path(flask_htmx_template.__file__).parent.glob("**/*.py"),
            *Path(tests.__file__).parent.glob("**/*.py"),
        ],
    ),
    ids=conftest.id_func,
)
def test_use_of_mixins(path: Path) -> None:
    lines = path.read_text("utf-8").splitlines()

    ignore = "# flask_htmx_template: ignore"

    errors: list[str] = []

    for i, line in enumerate(lines):
        checks = [
            check_no_query_col0(line),
        ]
        if "(" in line:
            checks.extend(
                [
                    check_no_session_add(line),
                    check_no_model_new(line),
                    check_no_session_query(line),
                    check_no_query_with_entities(line),
                    check_no_query_scalar(line),
                    check_no_query_one(line),
                    check_no_query_all(line),
                ],
            )
        checks = [f"{path:}:{i + 1}: {c}" for c in checks if c]
        if checks:
            if not line.endswith(ignore):
                errors.extend(checks)
        elif line.endswith(ignore):
            errors.append(
                f"{path}:{i + 1}: Use of unnecessary 'flask_htmx_template: ignore'",
            )

    print("\n".join(errors))
    assert not errors

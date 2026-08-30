from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import orm
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

from flask_htmx_template import exceptions as exc
from flask_htmx_template.models.base import Base, Decimal6
from tests.models.base.conftest import Child, Derived, NoURI, Parent

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask_htmx_template.models.base import (
        NamePair,
    )
    from tests.conftest import RandomStringGenerator


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


def test_decimal6_process_bind_param() -> None:
    value = Decimal("1.2345678")

    result = Decimal6().process_bind_param(value, sqlite_dialect())

    assert result == 1234567


def test_decimal6_process_result_value() -> None:
    result = Decimal6().process_result_value(1234567, sqlite_dialect())

    assert result == Decimal("1.234567")


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


def test_comparators_same_session(session: orm.Session) -> None:
    parent_a = Parent.create()
    parent_b = Parent.create()

    assert parent_a == parent_a  # ruff: ignore[comparison-with-itself]
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


def test_map_name_parent(
    session: orm.Session,
    rand_str_generator: RandomStringGenerator,
) -> None:
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

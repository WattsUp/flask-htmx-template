from __future__ import annotations

import re
from pathlib import Path
from typing import cast, TYPE_CHECKING

import pytest

import flask_htmx_template
import tests
from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql
from flask_htmx_template.models.base import Base
from flask_htmx_template.models.mixins.query import QueryMixIn
from flask_htmx_template.models.mixins.session import SessionMixIn
from tests import conftest
from tests.models.base.conftest import Parent

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import orm


def test_query_mixin_is_public_and_composed_into_base() -> None:
    assert issubclass(QueryMixIn, SessionMixIn)
    assert issubclass(Base, QueryMixIn)


def test_query_kwargs() -> None:
    query = cast("Callable[..., object]", Parent.query)

    with pytest.raises(exc.NoKeywordArgumentsError):
        query(kw=None)


def test_delete(session: orm.Session, parent: Parent) -> None:
    with session.begin_nested():
        parent.delete()
    assert not sql.any_(Parent.query())


def test_delete_flushes_immediately(session: orm.Session, parent: Parent) -> None:
    parent.delete()

    assert parent not in session.deleted


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
    """Reject direct session additions.

    Returns:
        Error message, or an empty string when valid

    """
    if re_check_no_session_add.match(line):
        return "Use of session.add found, use Model.create()"
    return ""


def check_no_model_new(line: str) -> str:
    """Reject direct construction of registered models.

    Returns:
        Error message, or an empty string when valid

    """
    if not line.startswith("class") and re_check_no_model_new.search(line):
        return "Use of Model(...) found, use Model.create()"
    return ""


def check_no_session_query(line: str) -> str:
    """Reject direct session queries.

    Returns:
        Error message, or an empty string when valid

    """
    if re_check_no_session_query.search(line):
        return "Use of session.query found, use Model.query()"
    return ""


def check_no_query_with_entities(line: str) -> str:
    """Reject direct use of Query.with_entities.

    Returns:
        Error message, or an empty string when valid

    """
    if ".with_entities" in line:
        return "Use of with_entities found, use Model.query(col, ...)"
    return ""


def check_no_query_scalar(line: str) -> str:
    """Reject direct Query.scalar calls.

    Returns:
        Error message, or an empty string when valid

    """
    if (m := re_check_no_scalar_query.search(line)) and m.group(1) != "sql":
        return "Use of query.scalar found, use sql.scalar()"
    return ""


def check_no_query_one(line: str) -> str:
    """Reject direct Query.one calls.

    Returns:
        Error message, or an empty string when valid

    """
    if not (m := re_check_no_query_one.search(line)):
        return ""
    g = m.group(1)
    if (g and g[0] == g[0].upper()) or g == "sql":
        # use of Model.one()
        return ""
    return "Use of query.one found, use sql.one()"


def check_no_query_all(line: str) -> str:
    """Reject direct Query.all calls.

    Returns:
        Error message, or an empty string when valid

    """
    if not (m := re_check_no_query_all.search(line)):
        return ""
    g = m.group(1)
    if (g and g[0] == g[0].upper()) or g == "sql":
        # use of Model.all()
        return ""
    return "Use of query.all found, use sql.yield_()"


def check_no_query_col0(line: str) -> str:
    """Reject manual iteration over a query's first column.

    Returns:
        Error message, or an empty string when valid

    """
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

    ignore = "# flask_htmx_template: ignore[mixins]"

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
                f"{path}:{i + 1}: Use of unnecessary '{ignore}'",
            )

    print("\n".join(errors))
    assert not errors
